from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count, Q
from collections import defaultdict
import logging

from cbe_app.models import (
    Class, Student, Staff, ClassSubjectAllocation, 
    AttendanceSession, StudentAttendance, LearningArea,
    Term, AcademicYear
)
from cbe_app.serializers.teacher_serializers.teacher_attendance_serializers import (
    TeacherClassSerializer, TeacherSubjectSerializer, AttendanceStudentSerializer,
    BulkAttendanceSaveSerializer, AttendanceHistorySerializer
)

logger = logging.getLogger(__name__)


class TeacherAttendanceClassesView(APIView):
    """Get classes where teacher teaches a subject (for attendance)"""
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
            
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,
                academic_year=academic_year
            ).select_related('class_id', 'subject')
            
            serializer = TeacherClassSerializer(allocations, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} classes'
            })
            
        except Exception as e:
            logger.error(f"TeacherAttendanceClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherAttendanceSubjectsView(APIView):
    """Get subjects taught by teacher"""
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
            
            serializer = TeacherSubjectSerializer(subjects, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} subjects'
            })
            
        except Exception as e:
            logger.error(f"TeacherAttendanceSubjectsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class ClassStudentsForAttendanceView(APIView):
    """Get students in a specific class for attendance marking"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'No staff profile linked'
                })
            
            staff = request.user.staff_profile
            
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=404)
            
            # Check if teacher has access to this class
            has_access = ClassSubjectAllocation.objects.filter(
                class_id=class_obj,
                teacher=staff
            ).exists()
            
            if not has_access and class_obj.class_teacher != staff:
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
            
            serializer = AttendanceStudentSerializer(students, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} students'
            })
            
        except Exception as e:
            logger.error(f"ClassStudentsForAttendanceView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class GetAttendanceRecordsView(APIView):
    """Get attendance records for a specific date/class/subject"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            subject_id = request.query_params.get('subject_id')
            date_str = request.query_params.get('date')
            period = request.query_params.get('period', 'morning')
            
            if not all([class_id, subject_id, date_str]):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Missing required parameters'
                }, status=400)
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=404)
            
            try:
                subject_obj = LearningArea.objects.get(id=subject_id)
            except LearningArea.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Subject not found'
                }, status=404)
            
            session_type_map = {'morning': 'Morning', 'afternoon': 'Afternoon', 'full': 'Full Day'}
            session_type = session_type_map.get(period, 'Morning')
            
            # Find or create session (created when attendance is saved)
            session = AttendanceSession.objects.filter(
                session_date=date_str,
                session_type=session_type,
                class_id=class_obj
            ).first()
            
            if not session:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No attendance records for this date'
                })
            
            attendance_records = StudentAttendance.objects.filter(
                session=session
            ).select_related('student')
            
            data = []
            for record in attendance_records:
                data.append({
                    'student_id': str(record.student.id),
                    'status': record.attendance_status.lower()
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} records'
            })
            
        except Exception as e:
            logger.error(f"GetAttendanceRecordsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class BulkSaveAttendanceView(APIView):
    """Save multiple attendance records at once"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = BulkAttendanceSaveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            records = data['records']
            
            if not records:
                return Response({
                    'success': False,
                    'message': 'No records to save'
                }, status=400)
            
            saved_count = 0
            
            # Group records by date, period, class
            grouped = defaultdict(list)
            for record in records:
                key = (record['date'], record['period'], record['class_id'])
                grouped[key].append(record)
            
            for (date_str, period, class_id), group_records in grouped.items():
                session_type_map = {'morning': 'Morning', 'afternoon': 'Afternoon', 'full': 'Full Day'}
                session_type = session_type_map.get(period, 'Morning')
                
                try:
                    class_obj = Class.objects.get(id=class_id)
                except Class.DoesNotExist:
                    continue
                
                # Get or create attendance session
                session, created = AttendanceSession.objects.get_or_create(
                    session_date=date_str,
                    session_type=session_type,
                    class_id=class_obj,
                    defaults={
                        'conducted_by': request.user,
                        'start_time': timezone.now().time(),
                        'is_active': True
                    }
                )
                
                for record in group_records:
                    try:
                        student = Student.objects.get(id=record['student_id'])
                    except Student.DoesNotExist:
                        continue
                    
                    status_map = {'present': 'Present', 'absent': 'Absent'}
                    attendance_status = status_map.get(record['status'], 'Absent')
                    
                    obj, created = StudentAttendance.objects.update_or_create(
                        session=session,
                        student=student,
                        defaults={
                            'attendance_status': attendance_status,
                            'recorded_by': request.user
                        }
                    )
                    saved_count += 1
            
            return Response({
                'success': True,
                'message': f'Saved {saved_count} attendance records',
                'saved_count': saved_count
            })
            
        except Exception as e:
            logger.error(f"BulkSaveAttendanceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class AttendanceHistoryView(APIView):
    """Get attendance history for a class/subject"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            class_id = request.query_params.get('class_id')
            subject_id = request.query_params.get('subject_id')
            
            if not all([class_id, subject_id]):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Missing required parameters'
                }, status=400)
            
            try:
                class_obj = Class.objects.get(id=class_id)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found'
                }, status=404)
            
            current_term = Term.objects.filter(is_current=True).first()
            if not current_term:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No active term found'
                })
            
            # Get all sessions for this class in current term
            sessions = AttendanceSession.objects.filter(
                class_id=class_obj,
                session_date__gte=current_term.start_date,
                session_date__lte=current_term.end_date
            ).order_by('-session_date')
            
            history = []
            for session in sessions:
                attendance = StudentAttendance.objects.filter(session=session)
                total = attendance.count()
                present = attendance.filter(attendance_status='Present').count()
                absent = total - present
                percentage = round((present / total) * 100) if total > 0 else 0
                
                history.append({
                    'date': session.session_date,
                    'present': present,
                    'absent': absent,
                    'percentage': percentage
                })
            
            return Response({
                'success': True,
                'data': history,
                'message': f'Found {len(history)} days of history'
            })
            
        except Exception as e:
            logger.error(f"AttendanceHistoryView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)