from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import uuid
import logging

from cbe_app.models import (
    Exam, ExamResult, Student, Class, ClassSubjectAllocation,
    Staff, LearningArea
)

logger = logging.getLogger(__name__)


class TeacherExamsListView(APIView):
    """Get exams assigned to teacher for marking"""
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
            
            # Get subjects teacher teaches
            teacher_subjects = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).values_list('subject__area_name', flat=True).distinct()
            
            # Get classes teacher teaches
            teacher_classes = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).values_list('class_id', flat=True).distinct()
            
            # Get exams that are available for marking
            exams = Exam.objects.filter(
                status__in=['published', 'live', 'marking'],
                subjects__overlap=list(teacher_subjects),
                classes__overlap=[str(c) for c in teacher_classes]
            ).order_by('-created_at')
            
            data = []
            for exam in exams:
                class_name = None
                if exam.classes and len(exam.classes) > 0:
                    try:
                        class_obj = Class.objects.get(id=exam.classes[0])
                        class_name = class_obj.class_name
                        if class_obj.stream:
                            class_name = f"{class_name} - {class_obj.stream}"
                    except Class.DoesNotExist:
                        pass
                
                data.append({
                    'id': str(exam.id),
                    'exam_code': exam.exam_code,
                    'title': exam.title,
                    'exam_type': exam.exam_type,
                    'grade_level': exam.grade_level,
                    'academic_year': exam.academic_year,
                    'term': exam.term,
                    'total_marks': exam.total_marks,
                    'passing_marks': exam.passing_marks,
                    'status': exam.status,
                    'start_date': exam.start_date,
                    'end_date': exam.end_date,
                    'className': class_name,
                    'subjects': exam.subjects,
                    'students_count': ExamResult.objects.filter(exam=exam).values('student').distinct().count()
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} exams'
            })
            
        except Exception as e:
            logger.error(f"TeacherExamsListView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherExamScoresView(APIView):
    """Get students and existing scores for an exam"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, exam_id):
        try:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Exam not found'
                }, status=404)
            
            # Get students for this exam's class
            students = []
            if exam.classes and len(exam.classes) > 0:
                try:
                    class_obj = Class.objects.get(id=exam.classes[0])
                    students = Student.objects.filter(
                        current_class=class_obj,
                        status='Active',
                        archived=False
                    ).order_by('first_name', 'last_name')
                except Class.DoesNotExist:
                    pass
            
            # Get existing results
            results = {r.student_id: r for r in ExamResult.objects.filter(exam=exam)}
            
            # Get grading scale based on grade level
            grade_level = exam.grade_level
            is_upper = grade_level in ['6', '7', '8', '9']
            
            data = []
            for student in students:
                result = results.get(student.id)
                percentage = float(result.percentage) if result and result.percentage else 0
                
                # Calculate grade dynamically
                grade = None
                if result and result.marks_obtained is not None:
                    if is_upper:
                        if percentage >= 90: grade = 'EE1'
                        elif percentage >= 75: grade = 'EE2'
                        elif percentage >= 58: grade = 'ME1'
                        elif percentage >= 41: grade = 'ME2'
                        elif percentage >= 31: grade = 'AE1'
                        elif percentage >= 21: grade = 'AE2'
                        elif percentage >= 11: grade = 'BE1'
                        else: grade = 'BE2'
                    else:
                        if percentage >= 90: grade = 'EE'
                        elif percentage >= 75: grade = 'ME'
                        elif percentage >= 58: grade = 'AE'
                        else: grade = 'BE'
                
                data.append({
                    'student_id': str(student.id),
                    'admission_no': student.admission_no,
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'score': float(result.marks_obtained) if result and result.marks_obtained else None,
                    'percentage': percentage,
                    'grade': grade,
                    'is_absent': result and result.marks_obtained is None
                })
            
            return Response({
                'success': True,
                'data': data,
                'maxScore': exam.total_marks,
                'message': f'Found {len(data)} students'
            })
            
        except Exception as e:
            logger.error(f"TeacherExamScoresView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherExamScoresBulkSaveView(APIView):
    """Bulk save scores for an exam"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, exam_id):
        try:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Exam not found'
                }, status=404)
            
            data = request.data
            scores_data = data.get('scores', [])
            
            saved_count = 0
            for score_item in scores_data:
                student_id = score_item.get('student_id')
                score = score_item.get('score')
                is_absent = score_item.get('is_absent', False)
                
                try:
                    student = Student.objects.get(id=student_id)
                except Student.DoesNotExist:
                    continue
                
                if is_absent:
                    marks_obtained = None
                    percentage = None
                    grade = 'AB'
                else:
                    marks_obtained = float(score) if score is not None else None
                    if marks_obtained is not None and exam.total_marks > 0:
                        percentage = (marks_obtained / exam.total_marks) * 100
                        # Calculate grade based on exam's grade level
                        if exam.grade_level in ['6', '7', '8', '9']:
                            if percentage >= 90: grade = 'EE1'
                            elif percentage >= 75: grade = 'EE2'
                            elif percentage >= 58: grade = 'ME1'
                            elif percentage >= 41: grade = 'ME2'
                            elif percentage >= 31: grade = 'AE1'
                            elif percentage >= 21: grade = 'AE2'
                            elif percentage >= 11: grade = 'BE1'
                            else: grade = 'BE2'
                        else:
                            if percentage >= 90: grade = 'EE'
                            elif percentage >= 75: grade = 'ME'
                            elif percentage >= 58: grade = 'AE'
                            else: grade = 'BE'
                    else:
                        percentage = None
                        grade = None
                
                ExamResult.objects.update_or_create(
                    exam=exam,
                    student=student,
                    subject=exam.subjects[0] if exam.subjects else 'General',
                    defaults={
                        'marks_obtained': marks_obtained,
                        'percentage': round(percentage, 2) if percentage else None,
                        'grade': grade,
                        'marked_by': request.user,
                        'marked_at': timezone.now()
                    }
                )
                saved_count += 1
            
            # Update exam status if needed
            if exam.status == 'published' and saved_count > 0:
                exam.status = 'live'
                exam.save()
            
            return Response({
                'success': True,
                'message': f'Saved {saved_count} scores',
                'saved_count': saved_count
            })
            
        except Exception as e:
            logger.error(f"TeacherExamScoresBulkSaveView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class TeacherExamFinalizeView(APIView):
    """Finalize exam - submit for moderation"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, exam_id):
        try:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Exam not found'
                }, status=404)
            
            # Update exam status to moderation
            exam.status = 'moderation'
            exam.save()
            
            return Response({
                'success': True,
                'message': 'Exam submitted for moderation'
            })
            
        except Exception as e:
            logger.error(f"TeacherExamFinalizeView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)