from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import uuid
import logging

from cbe_app.models import (
    Class, Student, Staff, LearningArea, Exam, ExamResult,
    ClassSubjectAllocation, Term, AcademicYear
)
from cbe_app.serializers.teacher_serializers.teacher_assessment_serializers import (
    AssessmentClassSerializer, AssessmentSubjectSerializer, AssessmentListSerializer,
    CreateAssessmentSerializer, SaveGradesSerializer, AssessmentResultSerializer
)

logger = logging.getLogger(__name__)


class TeacherAssessmentClassesView(APIView):
    """Get classes (streams) for assessment creation"""
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
            
            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No active term found'
                })
            
            academic_year = current_term.academic_year.year_code
            
            # Get unique classes with their full details (including stream)
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,
                academic_year=academic_year
            ).select_related('class_id', 'subject')
            
            unique_classes = []
            seen = set()
            for alloc in allocations:
                if alloc.class_id.id not in seen:
                    seen.add(alloc.class_id.id)
                    unique_classes.append({
                        'id': str(alloc.class_id.id),
                        'class_name': alloc.class_id.class_name,
                        'stream': alloc.class_id.stream,
                        'numeric_level': alloc.class_id.numeric_level,
                        'display_name': f"{alloc.class_id.class_name} - {alloc.class_id.stream}" if alloc.class_id.stream else alloc.class_id.class_name
                    })
            
            return Response({
                'success': True,
                'data': unique_classes,
                'message': f'Found {len(unique_classes)} classes'
            })
            
        except Exception as e:
            logger.error(f"TeacherAssessmentClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class TeacherAssessmentSubjectsView(APIView):
    """Get subjects for assessment creation"""
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
            
            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No active term found'
                })
            
            academic_year = current_term.academic_year.year_code
            
            # Get unique subjects from allocations
            subject_ids = ClassSubjectAllocation.objects.filter(
                teacher=staff,
                academic_year=academic_year
            ).values_list('subject_id', flat=True).distinct()
            
            subjects = LearningArea.objects.filter(
                id__in=subject_ids,
                is_active=True
            ).order_by('area_name')
            
            data = [{'id': str(s.id), 'name': s.area_name, 'code': s.area_code} for s in subjects]
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} subjects'
            })
            
        except Exception as e:
            logger.error(f"TeacherAssessmentSubjectsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherAssessmentsListView(APIView):
    """Get all assessments created by teacher"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            exams = Exam.objects.filter(
                created_by=request.user
            ).order_by('-created_at')
            
            serializer = AssessmentListSerializer(exams, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} assessments'
            })
            
        except Exception as e:
            logger.error(f"TeacherAssessmentsListView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class TeacherCreateAssessmentView(APIView):
    """Create a new assessment for a specific class"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = CreateAssessmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            
            # Get the specific class (stream)
            try:
                class_obj = Class.objects.get(id=data['classId'])
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Class not found'
                }, status=404)
            
            try:
                subject_obj = LearningArea.objects.get(id=data['subjectId'])
            except LearningArea.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Subject not found'
                }, status=404)
            
            # Create exam
            exam_type_map = {
                'cat': 'cat',
                'assignment': 'cba',
                'project': 'cba',
                'exam': 'end_term'
            }
            
            # Get current term and academic year
            current_term = Term.objects.filter(is_current=True).first()
            term_number = 1
            academic_year = 2025
            if current_term:
                term_number = int(current_term.term.split()[-1]) if current_term.term else 1
                academic_year = int(current_term.academic_year.year_code.split('-')[0]) if current_term.academic_year else 2025
            
            exam = Exam.objects.create(
                exam_code=f"ASS-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                title=data['title'],
                exam_type=exam_type_map.get(data['type'], 'cba'),
                instructions=data.get('instructions', ''),
                total_marks=data['maxScore'],
                grade_level=str(class_obj.numeric_level),
                term=term_number,
                academic_year=academic_year,
                status='draft' if not data.get('published', False) else 'published',
                created_by=request.user,
                classes=[str(class_obj.id)],  # Save the actual class ID, not grade level
                subjects=[subject_obj.area_name]
            )
            
            return Response({
                'success': True,
                'data': {'id': str(exam.id)},
                'message': f'Assessment created for {class_obj.class_name} - {class_obj.stream}'
            })
            
        except Exception as e:
            logger.error(f"TeacherCreateAssessmentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class TeacherAssessmentStudentsView(APIView):
    """Get students for a specific assessment (for grading)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, assessment_id):
        try:
            exam = Exam.objects.filter(id=assessment_id, created_by=request.user).first()
            if not exam:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Assessment not found'
                }, status=404)
            
            if not exam.classes or len(exam.classes) == 0:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No class associated'
                })
            
            class_id = exam.classes[0]
            try:
                class_obj = Class.objects.get(id=class_id)
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
            
            # Get existing results
            results = {r.student_id: r for r in ExamResult.objects.filter(exam=exam)}
            
            data = []
            for student in students:
                result = results.get(student.id)
                data.append({
                    'id': str(student.id),
                    'admission_no': student.admission_no,
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'score': float(result.marks_obtained) if result and result.marks_obtained else '',
                    'feedback': result.remarks if result else ''
                })
            
            return Response({
                'success': True,
                'data': data,
                'maxScore': exam.total_marks,
                'message': f'Found {len(data)} students'
            })
            
        except Exception as e:
            logger.error(f"TeacherAssessmentStudentsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherSaveGradesView(APIView):
    """Save grades for an assessment"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, assessment_id):
        serializer = SaveGradesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            exam = Exam.objects.filter(id=assessment_id, created_by=request.user).first()
            if not exam:
                return Response({
                    'success': False,
                    'message': 'Assessment not found'
                }, status=404)
            
            data = serializer.validated_data
            saved_count = 0
            
            for grade in data['grades']:
                if grade['score'] is None or grade['score'] == '':
                    continue
                
                try:
                    student = Student.objects.get(id=grade['studentId'])
                except Student.DoesNotExist:
                    continue
                
                # Get or create result
                result, created = ExamResult.objects.update_or_create(
                    exam=exam,
                    student=student,
                    defaults={
                        'marks_obtained': grade['score'],
                        'remarks': grade.get('feedback', ''),
                        'marked_by': request.user,
                        'marked_at': timezone.now()
                    }
                )
                saved_count += 1
            
            # Update assessment status if all students are graded
            total_students = ExamResult.objects.filter(exam=exam).count()
            if total_students > 0:
                exam.status = 'ongoing'
                exam.save()
            
            return Response({
                'success': True,
                'message': f'Saved {saved_count} grades',
                'saved_count': saved_count
            })
            
        except Exception as e:
            logger.error(f"TeacherSaveGradesView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class TeacherAssessmentResultsView(APIView):
    """Get assessment results for analytics"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, assessment_id):
        try:
            exam = Exam.objects.filter(id=assessment_id, created_by=request.user).first()
            if not exam:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Assessment not found'
                }, status=404)
            
            results = ExamResult.objects.filter(exam=exam).select_related('student')
            
            data = []
            for result in results:
                data.append({
                    'studentId': str(result.student.id),
                    'student_name': result.student.full_name,
                    'admission_no': result.student.admission_no,
                    'score': float(result.marks_obtained),
                    'feedback': result.remarks or ''
                })
            
            return Response({
                'success': True,
                'data': data,
                'maxScore': exam.total_marks,
                'message': f'Found {len(data)} results'
            })
            
        except Exception as e:
            logger.error(f"TeacherAssessmentResultsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherDeleteAssessmentView(APIView):
    """Delete an assessment"""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, assessment_id):
        try:
            exam = Exam.objects.filter(id=assessment_id, created_by=request.user).first()
            if not exam:
                return Response({
                    'success': False,
                    'message': 'Assessment not found'
                }, status=404)
            
            # Delete associated results first
            ExamResult.objects.filter(exam=exam).delete()
            exam.delete()
            
            return Response({
                'success': True,
                'message': 'Assessment deleted successfully'
            })
            
        except Exception as e:
            logger.error(f"TeacherDeleteAssessmentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
            
class TeacherUpdateAssessmentView(APIView):
    """Update an existing assessment"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, assessment_id):
        try:
            exam = Exam.objects.filter(id=assessment_id, created_by=request.user).first()
            if not exam:
                return Response({
                    'success': False,
                    'message': 'Assessment not found'
                }, status=404)
            
            data = request.data
            
            if 'title' in data:
                exam.title = data['title']
            if 'maxScore' in data:
                exam.total_marks = data['maxScore']
            if 'instructions' in data:
                exam.instructions = data['instructions']
            
            exam.save()
            
            return Response({
                'success': True,
                'message': 'Assessment updated successfully'
            })
            
        except Exception as e:
            logger.error(f"TeacherUpdateAssessmentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
            
class TeacherPublishAssessmentView(APIView):
    """Publish a draft assessment"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, assessment_id):
        try:
            exam = Exam.objects.filter(id=assessment_id, created_by=request.user).first()
            if not exam:
                return Response({
                    'success': False,
                    'message': 'Assessment not found'
                }, status=404)
            
            if exam.status != 'draft':
                return Response({
                    'success': False,
                    'message': 'Only draft assessments can be published'
                }, status=400)
            
            exam.status = 'published'
            exam.save()
            
            return Response({
                'success': True,
                'message': 'Assessment published successfully'
            })
            
        except Exception as e:
            logger.error(f"TeacherPublishAssessmentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)