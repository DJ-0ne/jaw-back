from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count, Q
import os
import uuid
import logging

from cbe_app.models import (
    Strand, Student, Class, Staff, StudentPortfolio, CoreCompetency,
    LearningArea, Term, AcademicYear, ClassSubjectAllocation
)
from cbe_app.serializers.teacher_serializers.teacher_evidence_serializers import (
    EvidenceStudentSerializer, EvidenceClassSerializer, CoreCompetencySerializer,
    EvidenceListSerializer, CreateEvidenceSerializer, AddCommentSerializer,
    ToggleFeatureSerializer, PortfolioAuditSerializer
)

logger = logging.getLogger(__name__)


def _get_staff(user):
    if hasattr(user, 'staff_profile'):
        return user.staff_profile
    return Staff.objects.filter(user=user).first()


class EvidenceClassesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = _get_staff(request.user)
            if not staff:
                return Response({'success': False, 'data': [], 'message': 'No staff profile linked'})

            classes_as_teacher = Class.objects.filter(class_teacher=staff, is_active=True)
            allocated_class_ids = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).values_list('class_id', flat=True)
            classes_as_subject = Class.objects.filter(id__in=allocated_class_ids, is_active=True)

            all_classes = {}
            for cls in classes_as_teacher:
                all_classes[cls.id] = cls
            for cls in classes_as_subject:
                all_classes[cls.id] = cls

            data = []
            for cls in all_classes.values():
                display_name = cls.class_name
                if cls.stream:
                    display_name = f"{cls.class_name} - {cls.stream}"
                data.append({
                    'id': str(cls.id),
                    'class_name': cls.class_name,
                    'class_code': cls.class_code,
                    'stream': cls.stream,
                    'numeric_level': cls.numeric_level,
                    'grade_level': cls.numeric_level,
                    'class_name_display': display_name
                })

            return Response({'success': True, 'data': data, 'message': f'Found {len(data)} classes'})

        except Exception as e:
            logger.error(f"EvidenceClassesView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class EvidenceStudentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, class_id):
        try:
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({'success': False, 'data': [], 'message': 'Class not found'}, status=404)

            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')

            serializer = EvidenceStudentSerializer(students, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': f'Found {len(serializer.data)} students'})

        except Exception as e:
            logger.error(f"EvidenceStudentsView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class EvidenceSubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')

            if not class_id:
                return Response({'success': False, 'data': [], 'message': 'class_id parameter is required'}, status=400)

            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({'success': False, 'data': [], 'message': 'Class not found'}, status=404)

            staff = _get_staff(request.user)

            # ── STRATEGY 1: Teacher's own allocations for this specific class ──
            if staff:
                allocations = ClassSubjectAllocation.objects.filter(
                    teacher=staff,
                    class_id=class_obj
                ).select_related('subject').distinct()

                teacher_subjects = [
                    a.subject for a in allocations
                    if a.subject and a.subject.is_active
                ]

                if teacher_subjects:
                    # Deduplicate by id
                    seen = set()
                    unique = []
                    for s in teacher_subjects:
                        if s.id not in seen:
                            seen.add(s.id)
                            unique.append(s)

                    data = [
                        {'id': str(s.id), 'name': s.area_name, 'code': s.area_code}
                        for s in sorted(unique, key=lambda x: x.area_name)
                    ]
                    logger.info(
                        f"EvidenceSubjectsView: returning {len(data)} subjects "
                        f"from teacher allocations for class {class_id}"
                    )
                    return Response({
                        'success': True,
                        'data': data,
                        'message': f'Found {len(data)} subjects for this class'
                    })

                # ── STRATEGY 2: All allocations for this teacher (any class at same grade) ──
                grade_class_ids = Class.objects.filter(
                    numeric_level=class_obj.numeric_level,
                    is_active=True
                ).values_list('id', flat=True)

                grade_allocations = ClassSubjectAllocation.objects.filter(
                    teacher=staff,
                    class_id__in=grade_class_ids
                ).select_related('subject').distinct()

                grade_subjects = [
                    a.subject for a in grade_allocations
                    if a.subject and a.subject.is_active
                ]

                if grade_subjects:
                    seen = set()
                    unique = []
                    for s in grade_subjects:
                        if s.id not in seen:
                            seen.add(s.id)
                            unique.append(s)

                    data = [
                        {'id': str(s.id), 'name': s.area_name, 'code': s.area_code}
                        for s in sorted(unique, key=lambda x: x.area_name)
                    ]
                    logger.info(
                        f"EvidenceSubjectsView: returning {len(data)} subjects "
                        f"from grade-level allocations for level {class_obj.numeric_level}"
                    )
                    return Response({
                        'success': True,
                        'data': data,
                        'message': f'Found {len(data)} subjects for Grade {class_obj.numeric_level}'
                    })

            # ── STRATEGY 3: Fallback — all subjects linked to this grade via Strands ──
            subject_ids = Strand.objects.filter(
                grade_level__level=class_obj.numeric_level
            ).values_list('learning_area_id', flat=True).distinct()

            subjects = LearningArea.objects.filter(
                id__in=subject_ids,
                is_active=True
            ).order_by('area_name')

            data = [
                {'id': str(s.id), 'name': s.area_name, 'code': s.area_code}
                for s in subjects
            ]
            logger.info(
                f"EvidenceSubjectsView: fallback strand-based lookup "
                f"returned {len(data)} subjects for grade {class_obj.numeric_level}"
            )
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} subjects for Grade {class_obj.numeric_level}'
            })

        except Exception as e:
            logger.error(f"EvidenceSubjectsView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class EvidenceCompetenciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            competencies = CoreCompetency.objects.all().order_by('display_order', 'code')
            serializer = CoreCompetencySerializer(competencies, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': f'Found {len(serializer.data)} competencies'})
        except Exception as e:
            logger.error(f"EvidenceCompetenciesView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class EvidenceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            student_id    = request.query_params.get('student_id')
            subject_filter = request.query_params.get('subject', None)

            if not student_id:
                return Response({'success': True, 'data': [], 'message': 'No student selected'})

            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({'success': False, 'data': [], 'message': 'Student not found'}, status=404)

            current_term = Term.objects.filter(is_current=True).first()

            portfolios = StudentPortfolio.objects.filter(
                student=student,
                core_competency__isnull=False
            )

            if current_term:
                portfolios = portfolios.filter(
                    term=current_term,
                    academic_year=current_term.academic_year
                )

            portfolios = portfolios.order_by('-assessed_date')

            data = []
            for p in portfolios:
                subject = "General"
                comment_text = p.teacher_comment or ''

                if comment_text.startswith('[SUBJECT:'):
                    end_bracket = comment_text.find(']')
                    if end_bracket > 0:
                        subject = comment_text[9:end_bracket]
                        comment_text = comment_text[end_bracket + 1:].strip()

                data.append({
                    'id':               str(p.id),
                    'title':            comment_text[:100] if comment_text else 'Evidence Item',
                    'description':      comment_text,
                    'student_id':       str(p.student_id),
                    'student_name':     p.student.full_name,
                    'competency_id':    str(p.core_competency_id) if p.core_competency_id else None,
                    'competency_name':  p.core_competency.name if p.core_competency else None,
                    'competency_code':  p.core_competency.code if p.core_competency else None,
                    'subject':          subject,
                    'date':             p.assessed_date.date().isoformat() if p.assessed_date else None,
                    'file_url':         p.evidence_url,
                    'evidence_type':    p.evidence_type,
                    'teacher_comment':  comment_text,
                    'featured':         False,
                    'created_at':       p.created_at.isoformat(),
                    'updated_at':       p.updated_at.isoformat()
                })

            if subject_filter and subject_filter != 'all':
                data = [d for d in data if d['subject'] == subject_filter]

            return Response({'success': True, 'data': data, 'message': f'Found {len(data)} evidence items'})

        except Exception as e:
            logger.error(f"EvidenceListView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class EvidenceUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            import json

            title              = request.data.get('title')
            description        = request.data.get('description', '')
            student_id         = request.data.get('student_id')
            subject            = request.data.get('subject', '')
            competencies_str   = request.data.get('competencies', '[]')
            evidence_date      = request.data.get('date', timezone.now().date())
            student_reflection = request.data.get('student_reflection', '')
            teacher_feedback   = request.data.get('teacher_feedback', '')
            uploaded_file      = request.FILES.get('file')

            if not title or not student_id:
                return Response({'success': False, 'error': 'Title and student are required'}, status=400)

            try:
                competencies = json.loads(competencies_str) if competencies_str else []
            except Exception:
                competencies = []

            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({'success': False, 'error': 'Student not found'}, status=404)

            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({'success': False, 'error': 'No active term found'}, status=400)

            academic_year = current_term.academic_year

            file_path = None
            file_type = None
            if uploaded_file:
                import uuid as _uuid
                file_extension = os.path.splitext(uploaded_file.name)[1]
                file_name = (
                    f"evidence/{timezone.now().strftime('%Y/%m/%d')}/"
                    f"{_uuid.uuid4().hex}{file_extension}"
                )
                from django.core.files.storage import default_storage
                from django.core.files.base import ContentFile
                file_path = default_storage.save(file_name, ContentFile(uploaded_file.read()))
                file_type = uploaded_file.content_type

            # Prefix subject into teacher_comment for retrieval later
            comment_content = description or title
            if subject:
                comment_content = f"[SUBJECT:{subject}]{comment_content}"

            saved_count = 0
            for competency_id in competencies:
                try:
                    core_competency = CoreCompetency.objects.get(id=competency_id)
                except CoreCompetency.DoesNotExist:
                    continue

                StudentPortfolio.objects.create(
                    student=student,
                    core_competency=core_competency,
                    term=current_term,
                    academic_year=academic_year,
                    teacher_comment=comment_content,
                    evidence_url=file_path,
                    evidence_type=file_type,
                    status='assessed',
                    assessed_by=request.user,
                    assessed_date=evidence_date
                )
                saved_count += 1

            return Response({
                'success': True,
                'message': f'Uploaded evidence for {saved_count} competencies',
                'saved_count': saved_count
            })

        except Exception as e:
            logger.error(f"EvidenceUploadView error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class EvidenceDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, evidence_id):
        try:
            portfolio = StudentPortfolio.objects.filter(
                id=evidence_id,
                assessed_by=request.user
            ).first()

            if not portfolio:
                return Response({'success': False, 'message': 'Evidence not found or unauthorized'}, status=404)

            portfolio.delete()
            return Response({'success': True, 'message': 'Evidence deleted successfully'})

        except Exception as e:
            logger.error(f"EvidenceDeleteView error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class EvidenceAddCommentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, evidence_id):
        serializer = AddCommentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        try:
            data         = serializer.validated_data
            comment      = data['comment']
            comment_type = data['type']

            portfolio = StudentPortfolio.objects.filter(id=evidence_id).first()
            if not portfolio:
                return Response({'success': False, 'message': 'Evidence not found'}, status=404)

            new_comment = f"[{comment_type.upper()}] {request.user.get_full_name()}: {comment}\n"
            portfolio.teacher_comment = (portfolio.teacher_comment or '') + new_comment
            portfolio.save()

            return Response({'success': True, 'message': 'Comment added successfully'})

        except Exception as e:
            logger.error(f"EvidenceAddCommentView error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class EvidenceToggleFeatureView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, evidence_id):
        try:
            portfolio = StudentPortfolio.objects.filter(id=evidence_id).first()
            if not portfolio:
                return Response({'success': False, 'message': 'Evidence not found'}, status=404)

            return Response({'success': True, 'message': 'Feature toggled'})

        except Exception as e:
            logger.error(f"EvidenceToggleFeatureView error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class PortfolioAuditView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')

            if not class_id:
                return Response({'success': False, 'data': None, 'message': 'class_id required'}, status=400)

            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({'success': False, 'data': None, 'message': 'Class not found'}, status=404)

            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            )

            current_term = Term.objects.filter(is_current=True).first()

            portfolios = StudentPortfolio.objects.filter(
                student__in=students,
                core_competency__isnull=False
            )

            if current_term:
                portfolios = portfolios.filter(
                    term=current_term,
                    academic_year=current_term.academic_year
                )

            students_with_evidence = portfolios.values('student').distinct().count()
            total_evidence         = portfolios.count()

            subjects = LearningArea.objects.filter(is_active=True)
            evidence_by_subject = []
            for subject in subjects:
                count = portfolios.filter(
                    teacher_comment__icontains=subject.area_name
                ).count()
                evidence_by_subject.append({'name': subject.area_name, 'count': count})

            audit_data = {
                'total_students':        students.count(),
                'students_with_evidence': students_with_evidence,
                'total_evidence':        total_evidence,
                'featured_count':        0,
                'missing_evidence':      students.count() - students_with_evidence,
                'evidence_by_subject':   evidence_by_subject
            }

            return Response({'success': True, 'data': audit_data, 'message': 'Audit data retrieved'})

        except Exception as e:
            logger.error(f"PortfolioAuditView error: {str(e)}")
            return Response({'success': False, 'data': None, 'error': str(e)}, status=500)