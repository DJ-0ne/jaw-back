from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count, Q
from datetime import datetime, timedelta
import logging

from cbe_app.models import (
    Class, Staff, ClassSubjectAllocation, Exam, ExamResult,
    Student, StudentAttendance, AttendanceSession, Term,
    StudentPortfolio, Timetable, Notification
)

logger = logging.getLogger(__name__)


class TeacherDashboardView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': True,
                    'data': {
                        'timetable': [],
                        'pendingTasks': [],
                        'attendanceStats': {'present': 0, 'absent': 0, 'late': 0, 'total': 0, 'percentage': 0},
                        'classInfo': None,
                        'upcomingEvents': [],
                        'recentActivity': []
                    }
                })
            
            staff = request.user.staff_profile
            today_date = timezone.now().date()
            today_weekday = timezone.now().weekday() + 1
            
            # 1. TIMETABLE
            timetable = Timetable.objects.filter(
                teacher=request.user,
                day_of_week=today_weekday,
                is_active=True
            ).select_related('class_id', 'subject').order_by('period')
            
            timetable_data = []
            for tt in timetable:
                timetable_data.append({
                    'id': tt.id,
                    'subject': tt.subject.area_name if tt.subject else 'General',
                    'time': f"Period {tt.period}",
                    'class': tt.class_id.class_name if tt.class_id else 'N/A',
                    'room': tt.room or 'Not Assigned',
                    'topic': 'Lesson in progress'
                })
            
            # 2. PENDING TASKS
            pending_tasks = []
            
            exam_count = Exam.objects.filter(
                status__in=['marking', 'live']
            ).count()
            
            if exam_count > 0:
                pending_tasks.append({
                    'id': 1,
                    'title': 'Exams Pending Marking',
                    'count': exam_count,
                    'dueDate': (today_date + timedelta(days=3)).isoformat(),
                    'type': 'marking'
                })
            
            portfolio_count = StudentPortfolio.objects.filter(
                status='pending'
            ).count()
            
            if portfolio_count > 0:
                pending_tasks.append({
                    'id': 2,
                    'title': 'Portfolios Pending Review',
                    'count': portfolio_count,
                    'dueDate': (today_date + timedelta(days=5)).isoformat(),
                    'type': 'evidence'
                })
            
            notification_count = Notification.objects.filter(
                recipient_id=request.user.id,
                status='Unread'
            ).count()
            
            if notification_count > 0:
                pending_tasks.append({
                    'id': 3,
                    'title': 'Unread Notifications',
                    'count': notification_count,
                    'dueDate': today_date.isoformat(),
                    'type': 'notification'
                })
            
            # 3. CLASS INFO
            my_class = Class.objects.filter(class_teacher=staff, is_active=True).first()
            class_info = None
            student_count = 0
            
            if my_class:
                student_count = Student.objects.filter(
                    current_class=my_class,
                    status='Active',
                    archived=False
                ).count()
                
                class_info = {
                    'id': str(my_class.id),
                    'name': my_class.class_name,
                    'stream': my_class.stream or '',
                    'subject': 'Class Teacher',
                    'students': student_count,
                    'classTeacher': f"{staff.first_name} {staff.last_name}"
                }
            
            # 4. ATTENDANCE STATS
            attendance_stats = {'present': 0, 'absent': 0, 'late': 0, 'total': student_count, 'percentage': 0}
            
            if my_class and student_count > 0:
                attendance_session = AttendanceSession.objects.filter(
                    session_date=today_date,
                    class_id=my_class
                ).first()
                
                if attendance_session:
                    present_count = StudentAttendance.objects.filter(
                        session=attendance_session,
                        attendance_status='Present'
                    ).count()
                    absent_count = StudentAttendance.objects.filter(
                        session=attendance_session,
                        attendance_status='Absent'
                    ).count()
                    late_count = StudentAttendance.objects.filter(
                        session=attendance_session,
                        attendance_status='Late'
                    ).count()
                    
                    attendance_stats = {
                        'present': present_count,
                        'absent': absent_count,
                        'late': late_count,
                        'total': student_count,
                        'percentage': round((present_count / student_count) * 100) if student_count > 0 else 0
                    }
            
            # 5. UPCOMING EVENTS
            upcoming_events = []
            for day_offset in range(1, 8):
                future_date = today_date + timedelta(days=day_offset)
                future_weekday = future_date.weekday() + 1
                
                future_lessons = Timetable.objects.filter(
                    teacher=request.user,
                    day_of_week=future_weekday,
                    is_active=True
                ).select_related('class_id', 'subject')[:2]
                
                for lesson in future_lessons:
                    upcoming_events.append({
                        'id': lesson.id,
                        'title': f"{lesson.subject.area_name if lesson.subject else 'Lesson'} - {lesson.class_id.class_name if lesson.class_id else 'N/A'}",
                        'date': future_date.isoformat(),
                        'time': f"Period {lesson.period}"
                    })
            
            upcoming_events = upcoming_events[:5]
            
            # 6. RECENT ACTIVITY
            recent_activity = []
            
            recent_results = ExamResult.objects.filter(
                marked_by=request.user
            ).order_by('-marked_at')[:5]
            
            for result in recent_results:
                recent_activity.append({
                    'id': str(result.id),
                    'action': f"Marked {result.subject} - {result.student.full_name}",
                    'time': self._time_ago(result.marked_at),
                    'type': 'marking'
                })
            
            recent_portfolios = StudentPortfolio.objects.filter(
                assessed_by=request.user
            ).order_by('-assessed_date')[:3]
            
            for portfolio in recent_portfolios:
                recent_activity.append({
                    'id': str(portfolio.id),
                    'action': f"Assessed {portfolio.student.full_name}",
                    'time': self._time_ago(portfolio.assessed_date),
                    'type': 'evidence'
                })
            
            return Response({
                'success': True,
                'data': {
                    'timetable': timetable_data,
                    'pendingTasks': pending_tasks,
                    'attendanceStats': attendance_stats,
                    'classInfo': class_info,
                    'upcomingEvents': upcoming_events,
                    'recentActivity': recent_activity[:5]
                }
            })
            
        except Exception as e:
            logger.error(f"TeacherDashboardView error: {str(e)}")
            return Response({
                'success': True,
                'data': {
                    'timetable': [],
                    'pendingTasks': [],
                    'attendanceStats': {'present': 0, 'absent': 0, 'late': 0, 'total': 0, 'percentage': 0},
                    'classInfo': None,
                    'upcomingEvents': [],
                    'recentActivity': []
                }
            })
    
    def _time_ago(self, dt):
        if not dt:
            return 'Recently'
        
        try:
            # Ensure dt is timezone-aware
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            
            now = timezone.now()
            delta = now - dt
            
            if delta.days > 0:
                return f"{delta.days} day(s) ago"
            elif delta.seconds > 3600:
                return f"{delta.seconds // 3600} hour(s) ago"
            elif delta.seconds > 60:
                return f"{delta.seconds // 60} minute(s) ago"
            return "Just now"
        except Exception:
            return "Recently"