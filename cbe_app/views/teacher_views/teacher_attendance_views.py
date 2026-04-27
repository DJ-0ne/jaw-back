# views.py - Add to your existing views file

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Q, Count, Avg, Sum, F, Case, When, Value, IntegerField
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from datetime import datetime, timedelta
from collections import defaultdict

from cbe_app.models import (
    Class, Student, LearningArea, StudentAttendance, 
    AttendanceSession, User, ClassSubjectAllocation,
    Term, AcademicYear
)
from cbe_app.serializers.teacher_serializers.teacher_attendance_serializers import (
    TeacherClassWithSubjectSerializer, TeacherSubjectSerializer,
    StudentForAttendanceSerializer, BulkAttendanceSaveSerializer,
    AttendanceHistorySerializer, AttendanceSessionSerializer
)


class TeacherSubjectClassesView(APIView):
    """Get classes where teacher teaches a subject (for attendance)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            academic_year = request.query_params.get('academic_year')
            
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            # Get subjects allocated to this teacher
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=request.user,
                academic_year=academic_year if academic_year else ''
            ).select_related('class_id', 'subject')
            
            class_ids = allocations.values_list('class_id', flat=True).distinct()
            classes = Class.objects.filter(
                id__in=class_ids,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            serializer = TeacherClassWithSubjectSerializer(
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


class TeacherSubjectsView(APIView):
    """Get subjects taught by the teacher"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            academic_year = request.query_params.get('academic_year')
            
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            # Get unique subjects from teacher's allocations
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=request.user,
                academic_year=academic_year if academic_year else ''
            ).select_related('subject').distinct('subject')
            
            subjects = [allocation.subject for allocation in allocations if allocation.subject]
            
            serializer = TeacherSubjectSerializer(subjects, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Subjects retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve subjects'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClassStudentsForAttendanceView(APIView):
    """Get students in a class for attendance marking"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            class_obj = Class.objects.filter(id=class_id, is_active=True).first()
            if not class_obj:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check teacher access
            has_access = False
            if class_obj.class_teacher == request.user:
                has_access = True
            else:
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
            
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')
            
            serializer = StudentForAttendanceSerializer(students, many=True)
            
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


class AttendanceRecordsView(APIView):
    """Get attendance records for a specific date and class/subject"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            subject_id = request.query_params.get('subject_id')
            date_str = request.query_params.get('date')
            period = request.query_params.get('period', 'morning')
            
            if not class_id or not date_str:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'class_id and date are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Map period to session type
            session_type_map = {
                'morning': 'Morning',
                'afternoon': 'Afternoon',
                'full': 'Full Day'
            }
            session_type = session_type_map.get(period, 'Morning')
            
            class_obj = Class.objects.filter(id=class_id).first()
            subject_obj = None
            if subject_id:
                subject_obj = LearningArea.objects.filter(id=subject_id).first()
            
            session = AttendanceSession.objects.filter(
                session_date=attendance_date,
                session_type=session_type,
                class_id=class_obj,
                subject=subject_obj
            ).first()
            
            if not session:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No attendance records found for this date'
                })
            
            attendance_records = StudentAttendance.objects.filter(
                session=session
            ).select_related('student')
            
            records_data = []
            for record in attendance_records:
                records_data.append({
                    'student_id': str(record.student.id),
                    'status': record.attendance_status.lower() if record.attendance_status else 'unmarked',
                    'remarks': record.remarks or ''
                })
            
            return Response({
                'success': True,
                'data': records_data,
                'message': 'Attendance records retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve attendance records'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AttendanceHistoryView(APIView):
    """Get attendance history for a class/subject"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            subject_id = request.query_params.get('subject_id')
            days = int(request.query_params.get('days', 30))
            
            if not class_id:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'class_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            class_obj = Class.objects.filter(id=class_id).first()
            subject_obj = None
            if subject_id:
                subject_obj = LearningArea.objects.filter(id=subject_id).first()
            
            # Get sessions for the last N days
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days)
            
            sessions = AttendanceSession.objects.filter(
                session_date__gte=start_date,
                session_date__lte=end_date,
                class_id=class_obj,
                subject=subject_obj
            ).order_by('-session_date')
            
            history_data = []
            for session in sessions:
                present_count = session.attendance_records.filter(
                    attendance_status='Present'
                ).count()
                absent_count = session.attendance_records.filter(
                    attendance_status='Absent'
                ).count()
                total = present_count + absent_count
                percentage = round((present_count / total) * 100) if total > 0 else 0
                
                history_data.append({
                    'date': session.session_date.isoformat(),
                    'present': present_count,
                    'absent': absent_count,
                    'percentage': percentage
                })
            
            return Response({
                'success': True,
                'data': history_data,
                'message': 'Attendance history retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve attendance history'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BulkAttendanceSaveView(APIView):
    """Save multiple attendance records at once"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = BulkAttendanceSaveSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors,
                'message': 'Invalid attendance data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            data = serializer.validated_data
            records = data['records']
            saved_count = 0
            errors = []
            
            # Group records by session parameters
            session_groups = defaultdict(list)
            for record in records:
                session_key = (
                    record['date'],
                    record['period'],
                    record.get('class_id'),
                    record.get('subject_id')
                )
                session_groups[session_key].append(record)
            
            for session_key, group_records in session_groups.items():
                session_date, period, class_id, subject_id = session_key
                
                # Map period to session type
                session_type_map = {
                    'morning': 'Morning',
                    'afternoon': 'Afternoon',
                    'full': 'Full Day'
                }
                session_type = session_type_map.get(period, 'Morning')
                
                class_obj = None
                if class_id:
                    class_obj = Class.objects.filter(id=class_id).first()
                
                subject_obj = None
                if subject_id:
                    subject_obj = LearningArea.objects.filter(id=subject_id).first()
                
                # Get or create attendance session
                session, created = AttendanceSession.objects.get_or_create(
                    session_date=session_date,
                    session_type=session_type,
                    class_id=class_obj,
                    subject=subject_obj,
                    defaults={
                        'conducted_by': request.user,
                        'start_time': timezone.now().time(),
                        'is_active': True
                    }
                )
                
                # Process each record in the group
                for record in group_records:
                    student = Student.objects.filter(id=record['student_id']).first()
                    if not student:
                        errors.append(f"Student {record['student_id']} not found")
                        continue
                    
                    status_map = {
                        'present': 'Present',
                        'absent': 'Absent'
                    }
                    attendance_status = status_map.get(record['status'], 'Absent')
                    
                    attendance, created = StudentAttendance.objects.update_or_create(
                        session=session,
                        student=student,
                        defaults={
                            'attendance_status': attendance_status,
                            'recorded_by': request.user,
                            'recorded_at': timezone.now()
                        }
                    )
                    saved_count += 1
            
            return Response({
                'success': True,
                'message': f'Successfully saved {saved_count} attendance records',
                'data': {
                    'saved_count': saved_count,
                    'errors': errors if errors else None
                }
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to save attendance records'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TakeAttendanceView(APIView):
    """Record attendance for a class (single session)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            data = request.data
            attendance_date = data.get('date')
            period = data.get('period')
            class_id = data.get('class_id')
            subject_id = data.get('subject_id')
            records = data.get('records', [])
            
            if not attendance_date or not records:
                return Response({
                    'success': False,
                    'message': 'Date and records are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Map period to session type
            session_type_map = {
                'morning': 'Morning',
                'afternoon': 'Afternoon',
                'full': 'Full Day'
            }
            session_type = session_type_map.get(period, 'Morning')
            
            class_obj = None
            if class_id:
                class_obj = Class.objects.filter(id=class_id).first()
            
            subject_obj = None
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
            
            saved_count = 0
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
                attendance_status = status_map.get(record.get('status', 'absent'), 'Absent')
                
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
                    from datetime import datetime
                    now = datetime.now().time()
                    if now > session.start_time:
                        late_minutes = (datetime.combine(attendance_date, now) - 
                                      datetime.combine(attendance_date, session.start_time)).seconds // 60
                        attendance.late_minutes = late_minutes
                        attendance.save()
                
                saved_count += 1
            
            return Response({
                'success': True,
                'message': f'Attendance recorded for {saved_count} students',
                'data': {'session_id': str(session.id)}
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to record attendance'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)