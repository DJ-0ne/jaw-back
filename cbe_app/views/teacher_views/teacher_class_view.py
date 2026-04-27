# views.py - Add to your existing views file

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Avg, Count, Q, Sum, F, FloatField, Case, When, Value, IntegerField
from django.db.models.functions import Coalesce, Round
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os
import uuid
from decimal import Decimal

from ...models import (
    Class, Student, Staff, LearningArea, StudentAttendance, 
    AttendanceSession, SummativeRating, SummativeAssessment,
    Term, AcademicYear, TermlySummary, User, Competency,
    StudentPortfolio, ClassSubjectAllocation, ExamResult,
    Exam, GradingScale, Timetable
)
from cbe_app.serializers.teacher_serializers.teacher_class_serializers import (
    ClassListSerializer, SubjectClassSerializer, StudentListSerializer,
    AttendanceFormSerializer, AssessmentFormSerializer, EvidenceUploadSerializer,
    ClassAnalyticsSerializer, StudentPortfolioSerializer, StudentAttendanceSerializer
)


class TeacherMyClassesView(APIView):
    """Get classes where teacher is the class teacher (owner view)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get current academic year and term from query params or use active ones
            academic_year = request.query_params.get('academic_year')
            term = request.query_params.get('term')
            
            # Get current active academic year and term if not specified
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            # Get classes where this user is the class teacher
            classes = Class.objects.filter(
                class_teacher=request.user,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            # If no classes as class teacher, get classes from staff profile
            if not classes.exists() and hasattr(request.user, 'staff_profile'):
                staff = request.user.staff_profile
                # Get classes where staff is assigned as teacher via allocation
                allocated_class_ids = ClassSubjectAllocation.objects.filter(
                    teacher=request.user,
                    academic_year=academic_year if academic_year else ''
                ).values_list('class_id', flat=True).distinct()
                
                classes = Class.objects.filter(
                    id__in=allocated_class_ids,
                    is_active=True
                ).order_by('numeric_level', 'stream')
            
            serializer = ClassListSerializer(
                classes, 
                many=True, 
                context={'request': request, 'academic_year': academic_year}
            )
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Classes retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve classes'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherSubjectClassesView(APIView):
    """Get classes where teacher teaches a subject (instructor view)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get query parameters
            academic_year = request.query_params.get('academic_year')
            term = request.query_params.get('term')
            
            # Get current active academic year and term if not specified
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            if not term:
                current_term = Term.objects.filter(is_current=True).first()
                term = current_term.term if current_term else 'Term 1'
            
            # Get subjects allocated to this teacher
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=request.user,
                academic_year=academic_year,
                is_compulsory=True
            ).select_related('class_id', 'subject')
            
            class_ids = allocations.values_list('class_id', flat=True).distinct()
            classes = Class.objects.filter(
                id__in=class_ids,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            serializer = SubjectClassSerializer(
                classes, 
                many=True, 
                context={
                    'request': request, 
                    'academic_year': academic_year,
                    'term': term
                }
            )
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Subject classes retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve subject classes'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClassStudentsView(APIView):
    """Get students in a specific class"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            # Verify teacher has access to this class
            class_obj = Class.objects.filter(id=class_id, is_active=True).first()
            if not class_obj:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if teacher has access (class teacher or subject teacher)
            has_access = False
            
            # Check if user is class teacher
            if class_obj.class_teacher == request.user:
                has_access = True
            
            # Check if user teaches any subject in this class
            if not has_access:
                allocation = ClassSubjectAllocation.objects.filter(
                    class_id=class_obj,
                    teacher=request.user
                ).exists()
                if allocation:
                    has_access = True
            
            if not has_access:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'You do not have access to this class'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get students
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')
            
            # Get current term and academic year
            current_term = Term.objects.filter(is_current=True).first()
            academic_year_obj = AcademicYear.objects.filter(is_current=True).first()
            
            serializer = StudentListSerializer(
                students, 
                many=True, 
                context={
                    'current_term': current_term,
                    'academic_year_obj': academic_year_obj,
                    'class_obj': class_obj,
                    'academic_year': academic_year_obj.year_code if academic_year_obj else None,
                    'term': current_term.term if current_term else None
                }
            )
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Students retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve students'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClassAnalyticsView(APIView):
    """Get analytics for a specific class"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            # Verify access
            class_obj = Class.objects.filter(id=class_id, is_active=True).first()
            if not class_obj:
                return Response({
                    'success': False,
                    'message': 'Class not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get students
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
                        'class_rank': 0,
                        'total_streams': Class.objects.filter(
                            numeric_level=class_obj.numeric_level,
                            is_active=True
                        ).count(),
                        'performance_distribution': {},
                        'subject_mastery': [],
                        'top_performers': [],
                        'most_improved': []
                    },
                    'message': 'No students in class'
                })
            
            # Get current term
            current_term = Term.objects.filter(is_current=True).first()
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            
            # Calculate mean score
            student_scores = []
            for student in students:
                # Get average from termly summaries
                if current_term:
                    summaries = student.termly_summaries.filter(term=current_term)
                    if summaries.exists():
                        avg_internal = summaries.aggregate(avg=Avg('final_internal_value'))['avg']
                        if avg_internal:
                            score = float(avg_internal) / 8 * 100
                            student_scores.append(score)
                            continue
                
                # Fallback to exam results
                exam = Exam.objects.filter(
                    academic_year=academic_year.year_code if academic_year else None,
                    term=int(current_term.term.split()[-1]) if current_term else None,
                    status='published'
                ).first()
                if exam:
                    results = student.exam_results.filter(exam=exam)
                    if results.exists():
                        avg = results.aggregate(avg=Avg('percentage'))['avg']
                        if avg:
                            student_scores.append(float(avg))
                            continue
                
                student_scores.append(0)
            
            mean_score = sum(student_scores) / len(student_scores) if student_scores else 0
            
            # Get all streams at same level for ranking
            same_level_classes = Class.objects.filter(
                numeric_level=class_obj.numeric_level,
                is_active=True
            )
            
            # Calculate mean scores for other classes (simplified)
            # In production, you'd have a more sophisticated calculation
            class_rank = 1
            for other_class in same_level_classes:
                if other_class.id != class_obj.id:
                    # Simplified ranking - in production, calculate actual means
                    pass
            
            total_streams = same_level_classes.count()
            
            # Performance distribution based on grading scale
            grading_scales = GradingScale.objects.all()
            distribution = {}
            for scale in grading_scales:
                distribution[f"{scale.rating}{scale.sub_level if scale.sub_level > 0 else ''}"] = 0
            
            for score in student_scores:
                found = False
                for scale in grading_scales:
                    if scale.min_percentage <= score <= scale.max_percentage:
                        key = f"{scale.rating}{scale.sub_level if scale.sub_level > 0 else ''}"
                        distribution[key] = distribution.get(key, 0) + 1
                        found = True
                        break
                if not found:
                    distribution['BE2'] = distribution.get('BE2', 0) + 1
            
            # Subject mastery - get subjects taught in this class
            allocations = ClassSubjectAllocation.objects.filter(
                class_id=class_obj,
                academic_year=academic_year.year_code if academic_year else ''
            ).select_related('subject')
            
            subject_mastery = []
            for allocation in allocations:
                # Get average score for this subject from termly summaries
                subject_scores = []
                for student in students:
                    summary = TermlySummary.objects.filter(
                        student=student,
                        term=current_term,
                        learning_area=allocation.subject
                    ).first()
                    if summary and summary.final_internal_value:
                        score = float(summary.final_internal_value) / 8 * 100
                        subject_scores.append(score)
                
                avg_score = sum(subject_scores) / len(subject_scores) if subject_scores else 0
                
                # Calculate class average (simplified - in production, get from other classes)
                class_avg = avg_score * 0.95  # Placeholder
                
                subject_mastery.append({
                    'subject': allocation.subject.area_name,
                    'score': round(avg_score),
                    'class_avg': round(class_avg),
                    'rank': 1  # Placeholder - calculate actual rank
                })
            
            # Top performers
            student_score_pairs = list(zip(students, student_scores))
            sorted_students = sorted(student_score_pairs, key=lambda x: x[1], reverse=True)
            
            top_performers = []
            for i, (student, score) in enumerate(sorted_students[:5]):
                # Get improvement from previous term
                prev_term = Term.objects.filter(
                    academic_year=academic_year,
                    term__in=['Term 1', 'Term 2', 'Term 3']
                ).exclude(id=current_term.id).first() if current_term else None
                
                prev_score = 0
                if prev_term:
                    prev_summary = student.termly_summaries.filter(term=prev_term).first()
                    if prev_summary and prev_summary.final_internal_value:
                        prev_score = float(prev_summary.final_internal_value) / 8 * 100
                
                improvement = round(score - prev_score)
                improvement_str = f"+{improvement}" if improvement >= 0 else str(improvement)
                
                top_performers.append({
                    'id': str(student.id),
                    'name': student.full_name,
                    'score': round(score),
                    'improvement': improvement_str
                })
            
            # Most improved students
            improved_pairs = []
            for student, current_score in student_score_pairs:
                prev_term = Term.objects.filter(
                    academic_year=academic_year,
                    term__in=['Term 1', 'Term 2', 'Term 3']
                ).exclude(id=current_term.id).first() if current_term else None
                
                prev_score = 0
                if prev_term:
                    prev_summary = student.termly_summaries.filter(term=prev_term).first()
                    if prev_summary and prev_summary.final_internal_value:
                        prev_score = float(prev_summary.final_internal_value) / 8 * 100
                
                improvement = current_score - prev_score
                if improvement > 0:
                    improved_pairs.append((student, current_score, prev_score, improvement))
            
            sorted_improved = sorted(improved_pairs, key=lambda x: x[3], reverse=True)
            
            most_improved = []
            for student, current_score, prev_score, improvement in sorted_improved[:5]:
                most_improved.append({
                    'id': str(student.id),
                    'name': student.full_name,
                    'improvement': round(improvement),
                    'from_score': round(prev_score),
                    'to_score': round(current_score)
                })
            
            analytics_data = {
                'mean_score': round(mean_score, 1),
                'class_rank': class_rank,
                'total_streams': total_streams,
                'performance_distribution': distribution,
                'subject_mastery': subject_mastery,
                'top_performers': top_performers,
                'most_improved': most_improved
            }
            
            return Response({
                'success': True,
                'data': analytics_data,
                'message': 'Analytics retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve analytics'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TakeAttendanceView(APIView):
    """Record attendance for a class"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AttendanceFormSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors,
                'message': 'Invalid attendance data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            data = serializer.validated_data
            attendance_date = data['date']
            period = data['period']
            records = data['records']
            
            # Map period to session type
            session_type_map = {
                'morning': 'Morning',
                'afternoon': 'Afternoon',
                'full': 'Full Day'
            }
            session_type = session_type_map.get(period, 'Morning')
            
            # Determine class and subject
            class_id = data.get('class_id')
            subject_id = data.get('subject_id')
            
            class_obj = None
            subject_obj = None
            
            if class_id:
                class_obj = Class.objects.filter(id=class_id).first()
            if subject_id:
                subject_obj = LearningArea.objects.filter(id=subject_id).first()
            
            # Get or create attendance session
            session, created = AttendanceSession.objects.get_or_create(
                session_date=attendance_date,
                session_type=session_type,
                class_id=class_obj,
                subject=subject_obj,
                defaults={
                    'conducted_by': request.user,
                    'start_time': timezone.now().time(),
                    'is_active': True
                }
            )
            
            # Process each attendance record
            for record in records:
                student = Student.objects.filter(id=record['student_id']).first()
                if not student:
                    continue
                
                status_map = {
                    'present': 'Present',
                    'absent': 'Absent',
                    'late': 'Late',
                    'excused': 'Excused'
                }
                attendance_status = status_map.get(record['status'], 'Absent')
                
                attendance, created = StudentAttendance.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={
                        'attendance_status': attendance_status,
                        'remarks': record.get('remarks', ''),
                        'recorded_by': request.user
                    }
                )
                
                # Calculate late minutes if status is late
                if attendance_status == 'Late' and session.start_time:
                    from datetime import datetime, time
                    now = datetime.now().time()
                    if now > session.start_time:
                        late_minutes = (datetime.combine(attendance_date, now) - 
                                      datetime.combine(attendance_date, session.start_time)).seconds // 60
                        attendance.late_minutes = late_minutes
                        attendance.save()
            
            return Response({
                'success': True,
                'message': 'Attendance recorded successfully',
                'data': {'session_id': str(session.id)}
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to record attendance'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetAttendanceView(APIView):
    """Get attendance records for a class"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            date = request.query_params.get('date')
            if not date:
                return Response({
                    'success': False,
                    'message': 'Date parameter is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            from datetime import datetime
            attendance_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            sessions = AttendanceSession.objects.filter(
                session_date=attendance_date,
                class_id=class_id
            )
            
            all_attendance = []
            for session in sessions:
                attendance_records = StudentAttendance.objects.filter(
                    session=session
                ).select_related('student')
                
                serializer = StudentAttendanceSerializer(attendance_records, many=True)
                all_attendance.append({
                    'session_id': str(session.id),
                    'session_type': session.session_type,
                    'records': serializer.data
                })
            
            return Response({
                'success': True,
                'data': all_attendance,
                'message': 'Attendance retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve attendance'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SaveAssessmentView(APIView):
    """Save assessment results"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AssessmentFormSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors,
                'message': 'Invalid assessment data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            data = serializer.validated_data
            
            # Create exam record
            exam = Exam.objects.create(
                exam_code=f"ASS-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                title=data['title'],
                exam_type='cba',
                academic_year=timezone.now().year,
                term=1,  # You can determine from current term
                total_marks=data['max_score'],
                status='published',
                created_by=request.user
            )
            
            # Process scores
            for score_data in data['scores']:
                student = Student.objects.filter(id=score_data['student_id']).first()
                if student:
                    ExamResult.objects.create(
                        exam=exam,
                        student=student,
                        subject=data['subject'],
                        marks_obtained=score_data['score'],
                        remarks=score_data.get('feedback', ''),
                        marked_by=request.user
                    )
            
            return Response({
                'success': True,
                'message': 'Assessment saved successfully',
                'data': {'exam_id': str(exam.id)}
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to save assessment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UploadEvidenceView(APIView):
    """Upload evidence for student competency"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = EvidenceUploadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors,
                'message': 'Invalid evidence data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            data = serializer.validated_data
            student = Student.objects.filter(id=data['student_id']).first()
            
            if not student:
                return Response({
                    'success': False,
                    'message': 'Student not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Save file
            file = data['file']
            file_extension = os.path.splitext(file.name)[1]
            file_name = f"evidence/{timezone.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex}{file_extension}"
            file_path = default_storage.save(file_name, ContentFile(file.read()))
            
            # Determine file type
            evidence_type = 'document'
            if file.content_type.startswith('image/'):
                evidence_type = 'image'
            elif file.content_type == 'application/pdf':
                evidence_type = 'pdf'
            
            # Get current term and academic year
            current_term = Term.objects.filter(is_current=True).first()
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            
            # Find or create a competency for evidence (simplified - you'd match to actual competency)
            # In production, you'd map to specific competencies
            default_competency = Competency.objects.first()
            
            if default_competency and current_term and academic_year:
                portfolio = StudentPortfolio.objects.create(
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
                'message': 'Evidence uploaded successfully',
                'data': {'file_path': file_path}
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to upload evidence'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetEvidenceView(APIView):
    """Get student evidence/portfolio"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        try:
            portfolios = StudentPortfolio.objects.filter(
                student_id=student_id
            ).order_by('-assessed_date')
            
            serializer = StudentPortfolioSerializer(
                portfolios, 
                many=True, 
                context={'request': request}
            )
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Evidence retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve evidence'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)