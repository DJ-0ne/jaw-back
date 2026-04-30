from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Avg
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import uuid
import os
import logging

from cbe_app.models import (
    Class, LearningArea, Student, Staff, ClassSubjectAllocation, 
    Term, AcademicYear, AttendanceSession, StudentAttendance,
    Exam, ExamResult, StudentPortfolio, Competency
)
from cbe_app.serializers.teacher_serializers.teacher_class_serializers import (
    ClassListSerializer, SubjectClassSerializer, StudentListSerializer,
    AttendanceSubmitSerializer, AssessmentSubmitSerializer, 
    EvidenceUploadSerializer, StudentPortfolioSerializer
)


logger = logging.getLogger(__name__)


class TeacherMyClassesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Your user account is not linked to any staff profile.'
                }, status=200)
            
            staff = request.user.staff_profile
            
            classes = Class.objects.filter(
                class_teacher=staff,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            serializer = ClassListSerializer(classes, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} classes'
            })
            
        except Exception as e:
            logger.error(f"TeacherMyClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class TeacherSubjectClassesView(APIView):
    """Get classes where teacher teaches a subject OR is class teacher"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'No staff profile linked'
                }, status=200)
            
            staff = request.user.staff_profile
            
            # Get classes where teacher is class teacher (even without subject assignment)
            class_teacher_classes = Class.objects.filter(
                class_teacher=staff,
                is_active=True
            )
            
            # Get classes where teacher has subject allocation
            allocated_classes = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).select_related('class_id', 'subject')
            
            # Combine unique classes
            classes_dict = {}
            
            # Add class teacher classes
            for cls in class_teacher_classes:
                classes_dict[cls.id] = {
                    'id': str(cls.id),
                    'class_id': str(cls.id),
                    'class_name': cls.class_name,
                    'class_code': cls.class_code,
                    'stream': cls.stream or '',
                    'numeric_level': cls.numeric_level,
                    'subject_name': 'Class Teacher (All Subjects)',  # Show all subjects
                    'subject_id': None,
                    'subject_code': None,
                    'students_count': cls.current_students.filter(status='Active').count(),
                    'is_class_teacher': True  # Flag to identify
                }
            
            # Add subject allocated classes
            for alloc in allocated_classes:
                if alloc.class_id:
                    key = f"{alloc.class_id.id}_{alloc.subject.id if alloc.subject else 'all'}"
                    classes_dict[key] = {
                        'id': str(alloc.class_id.id),
                        'class_id': str(alloc.class_id.id),
                        'class_name': alloc.class_id.class_name,
                        'class_code': alloc.class_id.class_code,
                        'stream': alloc.class_id.stream or '',
                        'numeric_level': alloc.class_id.numeric_level,
                        'subject_name': alloc.subject.area_name if alloc.subject else 'General',
                        'subject_id': str(alloc.subject.id) if alloc.subject else None,
                        'subject_code': alloc.subject.area_code if alloc.subject else None,
                        'students_count': alloc.class_id.current_students.filter(status='Active').count(),
                        'is_class_teacher': False
                    }
            
            data = list(classes_dict.values())
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} classes'
            })
            
        except Exception as e:
            logger.error(f"TeacherSubjectClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class ClassStudentsView(APIView):
    """Get students for a specific class"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'No staff profile linked'
                }, status=200)
            
            staff = request.user.staff_profile
            
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=404)
            
            # Check access - teacher is class teacher OR teaches a subject in this class
            has_access = False
            if class_obj.class_teacher == staff:
                has_access = True
            if not has_access:
                has_access = ClassSubjectAllocation.objects.filter(
                    class_id=class_obj, 
                    teacher=staff
                ).exists()
            
            if not has_access:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'You do not have access to this class'
                }, status=403)
            
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')
            
            # Calculate scores for each student
            current_term = Term.objects.filter(is_current=True).first()
            student_data = []
            
            for student in students:
                # Calculate current score
                current_score = 0
                if current_term:
                    summaries = student.termly_summaries.filter(term=current_term)
                    if summaries.exists():
                        avg_internal = summaries.aggregate(avg=Avg('final_internal_value'))['avg']
                        if avg_internal:
                            current_score = round(float(avg_internal) / 8 * 100)
                
                # Calculate attendance rate
                attendance_rate = 0
                if current_term:
                    sessions = AttendanceSession.objects.filter(
                        session_date__gte=current_term.start_date,
                        session_date__lte=current_term.end_date,
                        class_id=class_obj
                    )
                    total_sessions = sessions.count()
                    if total_sessions > 0:
                        present_count = student.attendance_records.filter(
                            session__in=sessions,
                            attendance_status='Present'
                        ).count()
                        attendance_rate = round((present_count / total_sessions) * 100)
                
                # Get last assessment score
                last_assessment = 0
                last_result = student.exam_results.order_by('-marked_at').first()
                if last_result:
                    last_assessment = round(float(last_result.percentage))
                
                student_data.append({
                    'id': str(student.id),
                    'admission_no': student.admission_no or 'N/A',
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'full_name': student.full_name,
                    'gender': student.gender or 'N/A',
                    'current_score': current_score,
                    'attendance_rate': attendance_rate,
                    'last_assessment': last_assessment,
                    'target_level': 'ME'
                })
            
            return Response({
                'success': True,
                'data': student_data,
                'message': f'Found {len(student_data)} students'
            })
            
        except Exception as e:
            logger.error(f"ClassStudentsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class ClassAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Class not found.'
                }, status=404)
            
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            )
            
            if not students.exists():
                return Response({
                    'success': True,
                    'data': {
                        'mean_score': 0,
                        'class_rank': 1,
                        'total_streams': Class.objects.filter(
                            numeric_level=class_obj.numeric_level,
                            is_active=True
                        ).count(),
                        'performance_distribution': {'EE': 0, 'ME': 0, 'AE': 0, 'BE': 0},
                        'subject_mastery': [],
                        'top_performers': [],
                        'most_improved': []
                    }
                })
            
            current_term = Term.objects.filter(is_current=True).first()
            
            student_scores = []
            for student in students:
                score = 0
                if current_term:
                    summaries = student.termly_summaries.filter(term=current_term)
                    if summaries.exists():
                        avg_internal = summaries.aggregate(avg=Avg('final_internal_value'))['avg']
                        if avg_internal:
                            score = float(avg_internal) / 8 * 100
                student_scores.append(score)
            
            mean_score = sum(student_scores) / len(student_scores) if student_scores else 0
            
            distribution = {'EE': 0, 'ME': 0, 'AE': 0, 'BE': 0}
            for score in student_scores:
                if score >= 80:
                    distribution['EE'] += 1
                elif score >= 65:
                    distribution['ME'] += 1
                elif score >= 50:
                    distribution['AE'] += 1
                else:
                    distribution['BE'] += 1
            
            student_score_pairs = list(zip(students, student_scores))
            sorted_students = sorted(student_score_pairs, key=lambda x: x[1], reverse=True)
            
            top_performers = []
            for student, score in sorted_students[:5]:
                top_performers.append({
                    'id': str(student.id),
                    'name': student.full_name,
                    'score': round(score),
                    'improvement': '0'
                })
            
            total_streams = Class.objects.filter(
                numeric_level=class_obj.numeric_level,
                is_active=True
            ).count()
            
            return Response({
                'success': True,
                'data': {
                    'mean_score': round(mean_score, 1),
                    'class_rank': 1,
                    'total_streams': total_streams,
                    'performance_distribution': distribution,
                    'subject_mastery': [],
                    'top_performers': top_performers,
                    'most_improved': []
                }
            })
            
        except Exception as e:
            logger.error(f"ClassAnalyticsView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class TakeAttendanceView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AttendanceSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'message': 'No staff profile linked.'
                }, status=400)
            
            data = serializer.validated_data
            attendance_date = data['date']
            period = data['period']
            records = data['records']
            class_id = data.get('class_id')
            subject_id = data.get('subject_id')
            
            session_type_map = {'morning': 'Morning', 'afternoon': 'Afternoon', 'full': 'Full Day'}
            session_type = session_type_map.get(period, 'Morning')
            
            class_obj = None
            if class_id:
                try:
                    class_obj = Class.objects.get(id=class_id)
                except Class.DoesNotExist:
                    pass
            
            session, created = AttendanceSession.objects.get_or_create(
                session_date=attendance_date,
                session_type=session_type,
                class_id=class_obj,
                defaults={
                    'conducted_by': request.user,
                    'start_time': timezone.now().time(),
                    'is_active': True
                }
            )
            
            for record in records:
                try:
                    student = Student.objects.get(id=record['student_id'])
                except Student.DoesNotExist:
                    continue
                
                status_map = {'present': 'Present', 'absent': 'Absent', 
                             'late': 'Late', 'excused': 'Excused'}
                attendance_status = status_map.get(record['status'], 'Absent')
                
                StudentAttendance.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={
                        'attendance_status': attendance_status,
                        'remarks': record.get('remarks', ''),
                        'recorded_by': request.user
                    }
                )
            
            return Response({
                'success': True,
                'message': 'Attendance recorded successfully'
            })
            
        except Exception as e:
            logger.error(f"TakeAttendanceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class SaveAssessmentView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AssessmentSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            
            # Get the class object to determine grade level
            class_id = data.get('class_id')
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Class not found'
                }, status=404)
            
            # Map numeric_level to grade_level string (Exam model's GRADE_LEVEL_CHOICES)
            numeric_level = class_obj.numeric_level
            if numeric_level == 0:
                if class_obj.class_name.lower().startswith('pp1'):
                    grade_level = 'pp1'
                else:
                    grade_level = 'pp2'
            else:
                grade_level = str(numeric_level)
            
            # Get subject learning area
            subject_name = data['subject']
            try:
                subject = LearningArea.objects.filter(
                    Q(area_name=subject_name) | Q(area_code=subject_name)
                ).first()
                if not subject:
                    subject = LearningArea.objects.create(
                        area_code=subject_name[:10].upper(),
                        area_name=subject_name,
                        area_type='Core',
                        is_active=True
                    )
            except Exception:
                subject = None
            
            # Get current term from database
            current_term = Term.objects.filter(is_current=True).first()
            term_number = 1
            if current_term:
                term_number = int(current_term.term.split()[-1]) if current_term.term else 1
            
            exam = Exam.objects.create(
                exam_code=f"ASS-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                title=data['title'],
                exam_type='cba',  # Classroom-Based Assessment
                grade_level=grade_level,  # DYNAMIC from actual class
                academic_year=timezone.now().year,
                term=term_number,  # DYNAMIC from current term
                total_marks=data['max_score'],
                passing_marks=int(data['max_score'] * 0.5),  # 50% passing
                status='published',
                created_by=request.user,
                subjects=[data['subject']]
            )
            
            saved_count = 0
            for score_data in data['scores']:
                try:
                    student = Student.objects.get(id=score_data['student_id'])
                    marks = score_data.get('score', 0)
                    percentage = (marks / data['max_score']) * 100 if data['max_score'] > 0 else 0
                    
                    # Calculate grade based on grade level (using exam's grade_level)
                    if grade_level in ['pp1', 'pp2', '1', '2', '3', '4', '5']:
                        if percentage >= 90:
                            grade = 'EE'
                        elif percentage >= 75:
                            grade = 'ME'
                        elif percentage >= 58:
                            grade = 'AE'
                        else:
                            grade = 'BE'
                    else:
                        if percentage >= 90:
                            grade = 'EE1'
                        elif percentage >= 75:
                            grade = 'EE2'
                        elif percentage >= 58:
                            grade = 'ME1'
                        elif percentage >= 41:
                            grade = 'ME2'
                        elif percentage >= 31:
                            grade = 'AE1'
                        elif percentage >= 21:
                            grade = 'AE2'
                        elif percentage >= 11:
                            grade = 'BE1'
                        else:
                            grade = 'BE2'
                    
                    ExamResult.objects.update_or_create(
                        exam=exam,
                        student=student,
                        subject=data['subject'],
                        defaults={
                            'marks_obtained': marks,
                            'percentage': round(percentage, 2),
                            'grade': grade,
                            'remarks': score_data.get('feedback', ''),
                            'marked_by': request.user,
                            'marked_at': timezone.now()
                        }
                    )
                    saved_count += 1
                except Student.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'message': f'Assessment saved for {saved_count} students in Grade {grade_level}',
                'data': {
                    'exam_id': str(exam.id),
                    'grade_level': grade_level,
                    'term': term_number
                }
            })
            
        except Exception as e:
            logger.error(f"SaveAssessmentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class UploadEvidenceView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = EvidenceUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            
            try:
                student = Student.objects.get(id=data['student_id'])
            except Student.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Student not found'
                }, status=404)
            
            file = data['file']
            
            file_extension = os.path.splitext(file.name)[1]
            file_name = f"evidence/{timezone.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex}{file_extension}"
            file_path = default_storage.save(file_name, ContentFile(file.read()))
            
            evidence_type = 'document'
            if file.content_type and file.content_type.startswith('image/'):
                evidence_type = 'image'
            elif file.content_type == 'application/pdf':
                evidence_type = 'pdf'
            
            current_term = Term.objects.filter(is_current=True).first()
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            default_competency = Competency.objects.first()
            
            if default_competency and current_term and academic_year:
                StudentPortfolio.objects.create(
                    student=student,
                    competency=default_competency,
                    term=current_term,
                    academic_year=academic_year,
                    evidence_url=file_path,
                    evidence_type=evidence_type,
                    teacher_comment=data.get('description', ''),
                    status='pending',
                    assessed_by=request.user,
                    assessed_date=timezone.now()
                )
            
            return Response({
                'success': True,
                'message': 'Evidence uploaded successfully'
            })
            
        except Exception as e:
            logger.error(f"UploadEvidenceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class GetEvidenceView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        try:
            portfolios = StudentPortfolio.objects.filter(
                student_id=student_id
            ).order_by('-assessed_date')
            
            data = []
            for p in portfolios:
                data.append({
                    'id': str(p.id),
                    'student_id': str(p.student_id),
                    'student_name': p.student.full_name,
                    'evidence_url': p.evidence_url,
                    'evidence_type': p.evidence_type,
                    'teacher_comment': p.teacher_comment,
                    'assessed_date': p.assessed_date.isoformat() if p.assessed_date else None
                })
            
            return Response({
                'success': True,
                'data': data
            })
            
        except Exception as e:
            logger.error(f"GetEvidenceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)