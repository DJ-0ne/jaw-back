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

class EvidenceClassesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'No staff profile linked'
                })
            
            staff = request.user.staff_profile
            
            # Get classes where teacher is class teacher
            classes_as_teacher = Class.objects.filter(
                class_teacher=staff,
                is_active=True
            )
            
            # Get classes where teacher teaches a subject
            allocated_class_ids = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).values_list('class_id', flat=True)
            
            classes_as_subject = Class.objects.filter(
                id__in=allocated_class_ids,
                is_active=True
            )
            
            # Combine unique classes
            all_classes = {}
            for cls in classes_as_teacher:
                all_classes[cls.id] = cls
            for cls in classes_as_subject:
                all_classes[cls.id] = cls
            
            # Format response
            data = []
            for cls in all_classes.values():
                # Use the actual class_name from database, don't reconstruct
                # Just add stream if it exists
                display_name = cls.class_name
                if cls.stream:
                    display_name = f"{cls.class_name} - {cls.stream}"
                
                data.append({
                    'id': str(cls.id),
                    'class_name': cls.class_name,
                    'class_code': cls.class_code,
                    'stream': cls.stream,
                    'numeric_level': cls.numeric_level,
                    'grade_level': cls.numeric_level,  # Use actual numeric_level
                    'class_name_display': display_name  # Just the class name + stream
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} classes'
            })
            
        except Exception as e:
            logger.error(f"EvidenceClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class EvidenceStudentsView(APIView):
    """Get students for a class"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=404)
            
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')
            
            serializer = EvidenceStudentSerializer(students, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} students'
            })
            
        except Exception as e:
            logger.error(f"EvidenceStudentsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class EvidenceSubjectsView(APIView):
    """Get subjects for evidence tagging - filtered by grade level"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get class_id from query params
            class_id = request.query_params.get('class_id')
            
            if not class_id:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'class_id parameter is required'
                }, status=400)
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=404)
            
            # Get subjects for this grade level from Strands
            # Link: Strand -> grade_level -> learning_area
            subject_ids = Strand.objects.filter(
                grade_level__level=class_obj.numeric_level
            ).values_list('learning_area_id', flat=True).distinct()
            
            subjects = LearningArea.objects.filter(
                id__in=subject_ids,
                is_active=True
            ).order_by('area_name')
            
            data = [{'id': str(s.id), 'name': s.area_name, 'code': s.area_code} for s in subjects]
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} subjects for Grade {class_obj.numeric_level}'
            })
            
        except Exception as e:
            logger.error(f"EvidenceSubjectsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class EvidenceCompetenciesView(APIView):
    """Get core competencies for evidence tagging"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            competencies = CoreCompetency.objects.all().order_by('display_order', 'code')
            serializer = CoreCompetencySerializer(competencies, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} competencies'
            })
            
        except Exception as e:
            logger.error(f"EvidenceCompetenciesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class EvidenceListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            student_id = request.query_params.get('student_id')
            subject_filter = request.query_params.get('subject', None)
            
            if not student_id:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No student selected'
                })
            
            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Student not found'
                }, status=404)
            
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
                # Extract subject from teacher_comment
                subject = "General"
                comment_text = p.teacher_comment or ''
                
                if comment_text.startswith('[SUBJECT:'):
                    # Extract subject between [SUBJECT: and ]
                    end_bracket = comment_text.find(']')
                    if end_bracket > 0:
                        subject = comment_text[9:end_bracket]  # len('[SUBJECT:') = 9
                        # Remove the subject prefix from comment
                        comment_text = comment_text[end_bracket + 1:].strip()
                else:
                    comment_text = p.teacher_comment or ''
                
                item = {
                    'id': str(p.id),
                    'title': comment_text[:100] if comment_text else 'Evidence Item',
                    'description': comment_text,
                    'student_id': str(p.student_id),
                    'student_name': p.student.full_name,
                    'competency_id': str(p.core_competency_id) if p.core_competency_id else None,
                    'competency_name': p.core_competency.name if p.core_competency else None,
                    'competency_code': p.core_competency.code if p.core_competency else None,
                    'subject': subject,
                    'date': p.assessed_date.date().isoformat() if p.assessed_date else None,
                    'file_url': p.evidence_url,
                    'evidence_type': p.evidence_type,
                    'teacher_comment': comment_text,
                    'featured': False,
                    'created_at': p.created_at.isoformat(),
                    'updated_at': p.updated_at.isoformat()
                }
                data.append(item)
            
            # Apply subject filter
            if subject_filter and subject_filter != 'all':
                data = [d for d in data if d['subject'] == subject_filter]
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} evidence items'
            })
            
        except Exception as e:
            logger.error(f"EvidenceListView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class EvidenceUploadView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Parse form data directly (not JSON)
            title = request.data.get('title')
            description = request.data.get('description', '')
            student_id = request.data.get('student_id')
            subject = request.data.get('subject', '')
            competencies_str = request.data.get('competencies', '[]')
            evidence_date = request.data.get('date', timezone.now().date())
            student_reflection = request.data.get('student_reflection', '')
            teacher_feedback = request.data.get('teacher_feedback', '')
            uploaded_file = request.FILES.get('file')
            
            if not title or not student_id:
                return Response({
                    'success': False,
                    'error': 'Title and student are required'
                }, status=400)
            
            # Parse competencies JSON
            try:
                import json
                competencies = json.loads(competencies_str) if competencies_str else []
            except:
                competencies = []
            
            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Student not found'
                }, status=404)
            
            # Get current term
            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({
                    'success': False,
                    'error': 'No active term found'
                }, status=400)
            
            academic_year = current_term.academic_year
            
            # Handle file upload
            file_path = None
            file_type = None
            if uploaded_file:
                import os
                import uuid
                file_extension = os.path.splitext(uploaded_file.name)[1]
                file_name = f"evidence/{timezone.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex}{file_extension}"
                from django.core.files.storage import default_storage
                from django.core.files.base import ContentFile
                file_path = default_storage.save(file_name, ContentFile(uploaded_file.read()))
                file_type = uploaded_file.content_type
            
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
                    teacher_comment=description or title,
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
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class EvidenceDeleteView(APIView):
    """Delete evidence"""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, evidence_id):
        try:
            portfolio = StudentPortfolio.objects.filter(
                id=evidence_id,
                assessed_by=request.user
            ).first()
            
            if not portfolio:
                return Response({
                    'success': False,
                    'message': 'Evidence not found or unauthorized'
                }, status=404)
            
            portfolio.delete()
            
            return Response({
                'success': True,
                'message': 'Evidence deleted successfully'
            })
            
        except Exception as e:
            logger.error(f"EvidenceDeleteView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class EvidenceAddCommentView(APIView):
    """Add comment to evidence"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, evidence_id):
        serializer = AddCommentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            comment = data['comment']
            comment_type = data['type']
            
            portfolio = StudentPortfolio.objects.filter(id=evidence_id).first()
            if not portfolio:
                return Response({
                    'success': False,
                    'message': 'Evidence not found'
                }, status=404)
            
            # Store comment in teacher_comment field (append)
            new_comment = f"[{comment_type.upper()}] {request.user.get_full_name()}: {comment}\n"
            portfolio.teacher_comment = (portfolio.teacher_comment or '') + new_comment
            portfolio.save()
            
            return Response({
                'success': True,
                'message': 'Comment added successfully'
            })
            
        except Exception as e:
            logger.error(f"EvidenceAddCommentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class EvidenceToggleFeatureView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, evidence_id):
        try:
            # evidence_id is a UUID string
            portfolio = StudentPortfolio.objects.filter(id=evidence_id).first()
            if not portfolio:
                return Response({
                    'success': False,
                    'message': 'Evidence not found'
                }, status=404)
            
            # Toggle featured (you can add a featured field to StudentPortfolio)
            # For now, just return success
            return Response({
                'success': True,
                'message': 'Feature toggled'
            })
            
        except Exception as e:
            logger.error(f"EvidenceToggleFeatureView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class PortfolioAuditView(APIView):
    """Get portfolio audit statistics"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            
            if not class_id:
                return Response({
                    'success': False,
                    'data': None,
                    'message': 'class_id required'
                }, status=400)
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': None,
                    'message': 'Class not found'
                }, status=404)
            
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
            total_evidence = portfolios.count()
            
            # Evidence by subject (approximate using learning areas)
            subjects = LearningArea.objects.filter(is_active=True)
            evidence_by_subject = []
            for subject in subjects:
                count = portfolios.filter(teacher_comment__icontains=subject.area_name).count()
                evidence_by_subject.append({
                    'name': subject.area_name,
                    'count': count
                })
            
            audit_data = {
                'total_students': students.count(),
                'students_with_evidence': students_with_evidence,
                'total_evidence': total_evidence,
                'featured_count': 0,
                'missing_evidence': students.count() - students_with_evidence,
                'evidence_by_subject': evidence_by_subject
            }
            
            return Response({
                'success': True,
                'data': audit_data,
                'message': 'Audit data retrieved'
            })
            
        except Exception as e:
            logger.error(f"PortfolioAuditView error: {str(e)}")
            return Response({
                'success': False,
                'data': None,
                'error': str(e)
            }, status=500)