from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import logging
import uuid

from cbe_app.models import (
    Class, Student, Staff, LearningArea, Strand,
    ClassSubjectAllocation, Term, AcademicYear,
    SummativeAssessment, SummativeRating, AssessmentWindow
)
from cbe_app.serializers.teacher_serializers.teacher_jss_serializers import (
    JSSClassSerializer, JSSStudentSerializer, JSSSubjectSerializer,
    JSSMarksDataSerializer, JSSTermSerializer
)

logger = logging.getLogger(__name__)


def calculate_grade_label(percentage):
    """Calculate achievement level based on percentage"""
    if percentage is None:
        return None
    if percentage >= 90:
        return 'EE1'
    elif percentage >= 75:
        return 'EE2'
    elif percentage >= 58:
        return 'ME1'
    elif percentage >= 41:
        return 'ME2'
    elif percentage >= 31:
        return 'AE1'
    elif percentage >= 21:
        return 'AE2'
    elif percentage >= 11:
        return 'BE1'
    elif percentage >= 1:
        return 'BE2'
    else:
        return 'AB'


def calculate_weighted_total(sba_score, exam_score, sba_weight=40, exam_weight=60):
    """Calculate weighted total from SBA and exam scores"""
    if sba_score is None or exam_score is None:
        return None
    weighted = (sba_score * sba_weight / 100) + (exam_score * exam_weight / 100)
    return round(weighted * 10) / 10


class JSSTermsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            terms = Term.objects.all().order_by('term')
            data = [{'id': str(t.id), 'name': t.term} for t in terms]
            return Response({'success': True, 'data': data})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)


class JSSClassesView(APIView):
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
            
            classes = Class.objects.filter(
                class_teacher=staff,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            data = []
            for cls in classes:
                if cls.numeric_level == 9:
                    display_grade = 7
                elif cls.numeric_level == 10:
                    display_grade = 8
                elif cls.numeric_level == 11:
                    display_grade = 9
                else:
                    display_grade = cls.numeric_level
                
                data.append({
                    'id': str(cls.id),
                    'class_name': cls.class_name,
                    'class_code': cls.class_code,
                    'stream': cls.stream,
                    'grade_level': display_grade,
                    'numeric_level': cls.numeric_level,
                    'capacity': cls.capacity
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} classes'
            })
            
        except Exception as e:
            logger.error(f"JSSClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class JSSStudentsView(APIView):
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
            
            serializer = JSSStudentSerializer(students, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} students'
            })
            
        except Exception as e:
            logger.error(f"JSSStudentsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class JSSSubjectsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            grade_level = request.query_params.get('grade_level')
            
            if not grade_level:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'grade_level parameter is required'
                }, status=400)
            
            numeric_level_map = {7: 9, 8: 10, 9: 11}
            db_numeric_level = numeric_level_map.get(int(grade_level))
            
            if not db_numeric_level:
                return Response({
                    'success': False,
                    'data': [],
                    'message': f'Invalid grade level: {grade_level}'
                }, status=400)
            
            subject_ids = Strand.objects.filter(
                grade_level__level=db_numeric_level
            ).values_list('learning_area_id', flat=True).distinct()
            
            subjects = LearningArea.objects.filter(
                id__in=subject_ids,
                is_active=True
            ).order_by('area_name')
            
            data = []
            for subject in subjects:
                data.append({
                    'id': subject.area_code,
                    'name': subject.area_name,
                    'code': subject.area_code,
                    'sba_weight': 40,
                    'exam_weight': 60
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} subjects for Grade {grade_level}'
            })
            
        except Exception as e:
            logger.error(f"JSSSubjectsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class JSSMarksRetrieveView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            term_name = request.query_params.get('term')
            year = request.query_params.get('year')
            
            if not all([class_id, term_name, year]):
                return Response({
                    'success': True,
                    'data': {},
                    'message': 'No filters provided'
                })
            
            term = Term.objects.filter(term=term_name).first()
            if not term:
                return Response({
                    'success': True,
                    'data': {},
                    'message': 'Term not found'
                })
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': {},
                    'message': 'Class not found'
                }, status=404)
            
            # Get assessment window for this term (End-Term window)
            assessment_window = AssessmentWindow.objects.filter(
                term=term,
                assessment_type='End-Term'
            ).first()
            
            students = Student.objects.filter(current_class=class_obj, status='Active')
            subjects = LearningArea.objects.filter(is_active=True)
            
            marks_data = {}
            
            for student in students:
                marks_data[str(student.id)] = {}
                
                for subject in subjects:
                    # Get summative assessment for this class, subject, term
                    summative = None
                    exam_score = None
                    if assessment_window:
                        summative = SummativeAssessment.objects.filter(
                            assessment_window=assessment_window,
                            class_id=class_obj,
                            learning_area=subject
                        ).first()
                        
                        if summative:
                            rating = SummativeRating.objects.filter(
                                assessment=summative,
                                student=student
                            ).first()
                            if rating:
                                # Convert rating to score
                                rating_map = {
                                    'EE1': 95, 'EE2': 82, 'ME1': 66, 'ME2': 49,
                                    'AE1': 35, 'AE2': 25, 'BE1': 15, 'BE2': 5, 'AB': 0
                                }
                                exam_score = rating_map.get(rating.rating, None)
                    
                    # SBA is calculated from Exam table (CATs and CBAs)
                    # This part stays the same - SBA comes from exams
                    from cbe_app.models import Exam, ExamResult
                    assessments = Exam.objects.filter(
                        subjects__contains=[subject.area_name],
                        exam_type__in=['cat', 'cba']
                    )
                    
                    sba_scores = []
                    for assessment in assessments:
                        result = ExamResult.objects.filter(
                            exam=assessment,
                            student=student
                        ).first()
                        if result and result.marks_obtained is not None:
                            marks_obtained = float(result.marks_obtained)
                            percentage = (marks_obtained / float(assessment.total_marks)) * 100
                            sba_scores.append(percentage)
                    
                    sba_average = sum(sba_scores) / len(sba_scores) if sba_scores else None
                    
                    weighted_total = None
                    grade_label = None
                    if sba_average is not None and exam_score is not None:
                        weighted_total = calculate_weighted_total(sba_average, exam_score)
                        grade_label = calculate_grade_label(weighted_total)
                    
                    marks_data[str(student.id)][subject.area_code] = {
                        'sba': round(sba_average, 1) if sba_average else None,
                        'exam': exam_score,
                        'weighted_total': weighted_total,
                        'grade': grade_label,
                        'level_code': None
                    }
            
            return Response({
                'success': True,
                'data': marks_data,
                'message': 'Marks retrieved'
            })
            
        except Exception as e:
            logger.error(f"JSSMarksRetrieveView error: {str(e)}")
            return Response({
                'success': False,
                'data': {},
                'error': str(e)
            }, status=500)


class JSSMarksBulkSaveView(APIView):
    """Save summative scores to SummativeAssessment and SummativeRating"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            data = request.data
            class_id = data.get('class_id')
            term_name = data.get('term')
            year = data.get('year')
            marks_data = data.get('marks', {})
            
            # Get term
            term = Term.objects.filter(term=term_name).first()
            if not term:
                return Response({
                    'success': False,
                    'error': f'Term "{term_name}" not found'
                }, status=404)
            
            # Get or create assessment window
            assessment_window, _ = AssessmentWindow.objects.get_or_create(
                term=term,
                assessment_type='End-Term',
                defaults={
                    'weight_percentage': 60,
                    'open_date': timezone.now().date(),
                    'close_date': timezone.now().date(),
                    'is_active': True
                }
            )
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Class not found'
                }, status=404)
            
            saved_count = 0
            
            for student_id_str, student_marks in marks_data.items():
                try:
                    student = Student.objects.get(id=student_id_str)
                except Student.DoesNotExist:
                    continue
                
                for subject_code, marks in student_marks.items():
                    exam_score = marks.get('exam')
                    
                    if exam_score is None:
                        continue
                    
                    # Convert exam_score to float if it's a string
                    if isinstance(exam_score, str):
                        exam_score = float(exam_score)
                    
                    # Get subject
                    subject = LearningArea.objects.filter(area_code=subject_code).first()
                    if not subject:
                        continue
                    
                    # Convert score to rating
                    rating_value = calculate_grade_label(exam_score)
                    
                    # Get or create summative assessment
                    assessment_code = f"SUM-{year}-{term_name}-{class_id[:8]}-{subject_code}"
                    summative, created = SummativeAssessment.objects.get_or_create(
                        assessment_window=assessment_window,
                        class_id=class_obj,
                        learning_area=subject,
                        defaults={
                            'assessment_code': assessment_code,
                            'teacher': request.user,
                            'status': 'Published'
                        }
                    )
                    
                    # Save the rating
                    rating, created = SummativeRating.objects.update_or_create(
                        assessment=summative,
                        student=student,
                        competency=None,
                        defaults={
                            'rating': rating_value,
                            'teacher_comment': f"Summative Exam Score: {exam_score}%",
                            'rated_by': request.user,
                            'rated_at': timezone.now()
                        }
                    )
                    saved_count += 1
            
            return Response({
                'success': True,
                'message': f'Saved {saved_count} summative scores',
                'saved_count': saved_count
            })
            
        except Exception as e:
            logger.error(f"JSSMarksBulkSaveView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)