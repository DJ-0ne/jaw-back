from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import logging
from django.db.models import Q

from cbe_app.models import (
    Class, Student, Staff, LearningArea, Exam, ExamResult,
    ClassSubjectAllocation, Term, AcademicYear,Strand
)
from cbe_app.serializers.teacher_serializers.teacher_jss_serializers import (
    JSSClassSerializer, JSSStudentSerializer, JSSSubjectSerializer,
    JSSBulkSaveSerializer
)

logger = logging.getLogger(__name__)

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
            
            # Get classes where teacher is class teacher
            classes = Class.objects.filter(
                class_teacher=staff,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            data = []
            for cls in classes:
                # Convert numeric_level to display grade
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
                    'grade_level': display_grade,  # This is what frontend uses
                    'numeric_level': cls.numeric_level,  # Actual database value
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
    """Get students for a JSS class"""
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
            
            # Convert display grade (7,8,9) to numeric_level (9,10,11)
            numeric_level_map = {7: 9, 8: 10, 9: 11}
            db_numeric_level = numeric_level_map.get(int(grade_level))
            
            if not db_numeric_level:
                return Response({
                    'success': False,
                    'data': [],
                    'message': f'Invalid grade level: {grade_level}'
                }, status=400)
            
            # Get subjects that have strands for this numeric level
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
            
            term_number = term_name.replace('Term ', '')
            year = int(year)
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': {},
                    'message': 'Class not found'
                }, status=404)
            
            students = Student.objects.filter(current_class=class_obj, status='Active')
            subjects = LearningArea.objects.filter(is_active=True)
            
            marks_data = {}
            
            for student in students:
                marks_data[str(student.id)] = {}
                
                for subject in subjects:
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
                    
                    exam_code = f"JSS-{year}-{term_number}-{str(class_id)[:8]}-{subject.area_code}"
                    exam = Exam.objects.filter(exam_code=exam_code).first()
                    
                    exam_score = None
                    if exam:
                        result = ExamResult.objects.filter(exam=exam, student=student).first()
                        if result and result.marks_obtained is not None:
                            exam_score = float(result.marks_obtained)
                    
                    weighted_total = None
                    grade_label = None
                    if sba_average is not None and exam_score is not None:
                        weighted_total = (sba_average * 0.4) + (exam_score * 0.6)
                        weighted_total = round(weighted_total * 10) / 10
                        
                        # Calculate achievement level
                        if weighted_total >= 90:
                            grade_label = 'EE1'
                        elif weighted_total >= 75:
                            grade_label = 'EE2'
                        elif weighted_total >= 58:
                            grade_label = 'ME1'
                        elif weighted_total >= 41:
                            grade_label = 'ME2'
                        elif weighted_total >= 31:
                            grade_label = 'AE1'
                        elif weighted_total >= 21:
                            grade_label = 'AE2'
                        elif weighted_total >= 11:
                            grade_label = 'BE1'
                        elif weighted_total >= 1:
                            grade_label = 'BE2'
                        else:
                            grade_label = 'AB'
                    
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
                'message': 'Marks retrieved with calculated SBA averages'
            })
            
        except Exception as e:
            logger.error(f"JSSMarksRetrieveView error: {str(e)}")
            return Response({
                'success': False,
                'data': {},
                'error': str(e)
            }, status=500)
            
class JSSMarksBulkSaveView(APIView):
    """Save only summative exam scores (SBA is calculated automatically)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            data = request.data
            class_id = data.get('class_id')
            term_name = data.get('term')
            year = data.get('year')
            marks_data = data.get('marks', {})
            
            term_number = term_name.replace('Term ', '')
            year = int(year)  # Convert to integer
            
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
                    
                    # Create a shorter exam code
                    short_class_id = str(class_id)[:8]
                    exam_code = f"JSS-{year}-{term_number}-{short_class_id}-{subject_code}"
                    # Ensure length is within limit
                    if len(exam_code) > 100:
                        exam_code = exam_code[:100]
                    
                    exam, created = Exam.objects.get_or_create(
                        exam_code=exam_code,
                        defaults={
                            'title': f"{subject.area_name} - Summative {term_name} {year}",
                            'exam_type': 'summative',
                            'grade_level': '7',
                            'academic_year': year,
                            'term': int(term_number),
                            'total_marks': 100,
                            'status': 'published',
                            'created_by': request.user
                        }
                    )
                    
                    # Save the exam score
                    result, created = ExamResult.objects.update_or_create(
                        exam=exam,
                        student=student,
                        subject=subject.area_name,
                        defaults={
                            'marks_obtained': exam_score,
                            'remarks': f"Summative Exam Score: {exam_score}%",
                            'marked_by': request.user,
                            'marked_at': timezone.now()
                        }
                    )
                    saved_count += 1
            
            return Response({
                'success': True,
                'message': f'Saved {saved_count} summative exam scores',
                'saved_count': saved_count
            })
            
        except Exception as e:
            logger.error(f"JSSMarksBulkSaveView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)