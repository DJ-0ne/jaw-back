from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Avg, Count, Q
import logging

from cbe_app.models import (
    Class, Student, Staff, CoreCompetency, StudentPortfolio, Term, AcademicYear,
    LearningArea, ClassSubjectAllocation, GradeLevel, GradingScale
)
from cbe_app.serializers.teacher_serializers.teacher_competency_serializers import (
    CompetencyClassSerializer, CompetencyStudentSerializer, CoreCompetencySerializer,
    StudentCompetencySerializer, CompetencyMatrixDataSerializer, UpdateCompetencySerializer, EvidenceSerializer
)

logger = logging.getLogger(__name__)


def get_grade_level_from_class(class_obj):
    if class_obj.numeric_level == 9:
        return 7
    elif class_obj.numeric_level == 10:
        return 8
    elif class_obj.numeric_level == 11:
        return 9
    else:
        return class_obj.numeric_level


def get_grading_scale(grade_level):
    if grade_level >= 7:
        return {
            90: {'level': 8, 'label': 'EE1', 'name': 'Exceptional'},
            75: {'level': 7, 'label': 'EE2', 'name': 'Very Good'},
            58: {'level': 6, 'label': 'ME1', 'name': 'Good'},
            41: {'level': 5, 'label': 'ME2', 'name': 'Fair'},
            31: {'level': 4, 'label': 'AE1', 'name': 'Needs Improvement'},
            21: {'level': 3, 'label': 'AE2', 'name': 'Below Average'},
            11: {'level': 2, 'label': 'BE1', 'name': 'Well Below Average'},
            1:  {'level': 1, 'label': 'BE2', 'name': 'Minimal'},
            0:  {'level': 0, 'label': 'AB',  'name': 'Absent'}
        }
    else:
        return {
            90: {'level': 4, 'label': 'EE', 'name': 'Exceeding Expectations'},
            75: {'level': 3, 'label': 'ME', 'name': 'Meeting Expectations'},
            58: {'level': 2, 'label': 'AE', 'name': 'Approaching Expectations'},
            0:  {'level': 1, 'label': 'BE', 'name': 'Below Expectations'}
        }


def calculate_level_from_score(score, grade_level):
    if score is None:
        return None, None, None
    scale = get_grading_scale(grade_level)
    thresholds = sorted(scale.keys(), reverse=True)
    for threshold in thresholds:
        if score >= threshold:
            level_info = scale[threshold]
            return level_info['level'], level_info['label'], level_info['name']
    return None, None, None


class CompetencyClassesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({'success': False, 'data': [], 'message': 'No staff profile linked'})

            staff = request.user.staff_profile

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
                data.append({
                    'id':               str(cls.id),
                    'class_name':       cls.class_name,
                    'class_code':       cls.class_code,
                    'stream':           cls.stream,
                    'grade_level':      get_grade_level_from_class(cls),
                    'numeric_level':    cls.numeric_level,
                    'is_class_teacher': cls.class_teacher == staff,
                    'capacity':         cls.capacity
                })

            return Response({'success': True, 'data': data, 'message': f'Found {len(data)} classes'})

        except Exception as e:
            logger.error(f"CompetencyClassesView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class CompetencyStudentsView(APIView):
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

            serializer = CompetencyStudentSerializer(students, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': f'Found {len(serializer.data)} students'})

        except Exception as e:
            logger.error(f"CompetencyStudentsView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class CompetencySubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({'success': False, 'data': [], 'message': 'No staff profile linked'})

            staff = request.user.staff_profile
            subject_ids = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).values_list('subject_id', flat=True).distinct()

            subjects = LearningArea.objects.filter(
                id__in=subject_ids,
                is_active=True
            ).order_by('area_name')

            data = [{'id': str(s.id), 'name': s.area_name, 'code': s.area_code} for s in subjects]
            return Response({'success': True, 'data': data, 'message': f'Found {len(data)} subjects'})

        except Exception as e:
            logger.error(f"CompetencySubjectsView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class CoreCompetenciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            competencies = CoreCompetency.objects.all().order_by('display_order', 'code')
            serializer = CoreCompetencySerializer(competencies, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': f'Found {len(serializer.data)} core competencies'})

        except Exception as e:
            logger.error(f"CoreCompetenciesView error: {str(e)}")
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


class CompetencyMatrixRetrieveView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            if not class_id:
                return Response({'success': False, 'data': {}, 'message': 'class_id is required'}, status=400)

            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({'success': False, 'data': {}, 'message': 'Class not found'}, status=404)

            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')

            competencies  = CoreCompetency.objects.all().order_by('display_order', 'code')
            current_term  = Term.objects.filter(is_current=True).first()

            competency_data = {}
            evidence_data   = {}
            class_averages  = {}

            for student in students:
                student_key = str(student.id)
                competency_data[student_key] = {}
                for comp in competencies:
                    competency_data[student_key][str(comp.id)] = {
                        'score':        None,
                        'level':        None,
                        'level_label':  None,
                        'last_updated': None,
                        'updated_by':   None,
                        'evidence_count': 0
                    }

            if current_term:
                portfolios = StudentPortfolio.objects.filter(
                    student__in=students,
                    core_competency__isnull=False,
                    term=current_term,
                    academic_year=current_term.academic_year
                ).select_related('student', 'core_competency', 'assessed_by')

                for portfolio in portfolios:
                    student_key = str(portfolio.student_id)
                    comp_key    = str(portfolio.core_competency_id)

                    if student_key in competency_data and comp_key in competency_data[student_key]:
                        competency_data[student_key][comp_key] = {
                            'score':        float(portfolio.percentage) if portfolio.percentage else None,
                            'level':        portfolio.sub_level,
                            'level_label':  portfolio.rating,
                            'last_updated': portfolio.assessed_date.isoformat() if portfolio.assessed_date else None,
                            'updated_by':   portfolio.assessed_by.get_full_name() if portfolio.assessed_by else None,
                            'evidence_count': 1 if portfolio.evidence_url else 0
                        }

                        if portfolio.evidence_url:
                            evidence_data.setdefault(student_key, {}).setdefault(comp_key, []).append({
                                'id':            str(portfolio.id),
                                'description':   portfolio.teacher_comment or '',
                                'evidence_type': portfolio.evidence_type or 'document',
                                'date':          portfolio.assessed_date.date().isoformat() if portfolio.assessed_date else None,
                                'url':           portfolio.evidence_url
                            })

            for comp in competencies:
                comp_key = str(comp.id)
                scores = [
                    competency_data[str(s.id)][comp_key]['score']
                    for s in students
                    if competency_data.get(str(s.id), {}).get(comp_key, {}).get('score') is not None
                ]
                class_averages[comp_key] = round(sum(scores) / len(scores), 1) if scores else 0

            return Response({
                'success': True,
                'data': {
                    'competencies':  competency_data,
                    'evidence':      evidence_data,
                    'class_averages': class_averages
                },
                'message': 'Competency data retrieved successfully'
            })

        except Exception as e:
            logger.error(f"CompetencyMatrixRetrieveView error: {str(e)}")
            return Response({'success': False, 'data': {}, 'error': str(e)}, status=500)


class CompetencyMatrixUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data          = request.data
            student_id    = data.get('student_id')
            competency_id = data.get('competency_id')
            level         = data.get('level')
            score         = data.get('score')

            if isinstance(level, str):
                level = int(level) if level.isdigit() else 1
            score = int(score) if score else 0

            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({'success': False, 'error': 'Student not found'}, status=404)

            try:
                core_competency = CoreCompetency.objects.get(id=competency_id)
            except CoreCompetency.DoesNotExist:
                return Response({'success': False, 'error': 'Competency not found'}, status=404)

            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({'success': False, 'error': 'No active term'}, status=400)

            class_obj   = student.current_class
            grade_level = class_obj.numeric_level if class_obj else 9

            if grade_level <= 8:
                rating_map = {5: 'EE', 4: 'ME', 3: 'AE', 2: 'BE', 1: 'BE'}
                rating     = rating_map.get(level, 'ME')
                sub_level  = None
            else:
                rating_map = {5: 'EE1', 4: 'EE2', 3: 'ME1', 2: 'AE1', 1: 'BE1'}
                rating     = rating_map.get(level, 'ME1')
                sub_level  = level

            portfolio, created = StudentPortfolio.objects.update_or_create(
                student=student,
                core_competency=core_competency,
                term=current_term,
                academic_year=current_term.academic_year,
                defaults={
                    'competency':     None,
                    'percentage':     score,
                    'rating':         rating,
                    'sub_level':      sub_level,
                    'status':         'assessed',
                    'assessed_by':    request.user,
                    'assessed_date':  timezone.now(),
                    'teacher_comment': f"Core Competency assessed at Level {level}"
                }
            )

            return Response({
                'success': True,
                'message': f'Competency updated to Level {level}',
                'data': {
                    'score':        score,
                    'level':        level,
                    'level_label':  rating,
                    'last_updated': portfolio.assessed_date.isoformat() if portfolio.assessed_date else None,
                    'updated_by':   request.user.get_full_name() or request.user.username
                }
            })

        except Exception as e:
            logger.error(f"CompetencyMatrixUpdateView error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class CompetencyEvidenceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EvidenceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        try:
            data          = serializer.validated_data
            student_id    = data['student_id']
            competency_id = data['competency_id']
            description   = data['description']
            evidence_type = data['evidence_type']
            evidence_date = data['date']
            notes         = data.get('notes', '')

            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({'success': False, 'error': 'Student not found'}, status=404)

            try:
                core_competency = CoreCompetency.objects.get(id=competency_id)
            except CoreCompetency.DoesNotExist:
                return Response({'success': False, 'error': 'Competency not found'}, status=404)

            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({'success': False, 'error': 'No active term found'}, status=400)

            # FIXED: use core_competency= (CoreCompetency instance)
            #           NOT competency= (which expects a different Competency model)
            portfolio, created = StudentPortfolio.objects.update_or_create(
                student=student,
                core_competency=core_competency,          # ← was: competency=competency
                term=current_term,
                academic_year=current_term.academic_year,
                defaults={
                    'competency':    None,                # ← explicitly clear wrong FK
                    'teacher_comment': f"{description}\n\nNotes: {notes}" if notes else description,
                    'evidence_url':  f"evidence://{evidence_type}/{evidence_date}",
                    'evidence_type': evidence_type,
                    'status':        'pending',
                    'assessed_by':   request.user,
                    'assessed_date': timezone.now()
                }
            )

            return Response({
                'success': True,
                'message': 'Evidence linked successfully',
                'data': {
                    'portfolio_id': str(portfolio.id),
                    'evidence_type': evidence_type,
                    'date': str(evidence_date)
                }
            })

        except Exception as e:
            logger.error(f"CompetencyEvidenceView error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)