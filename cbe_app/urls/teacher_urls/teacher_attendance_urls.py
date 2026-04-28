from django.urls import path
from cbe_app.views.teacher_views.teacher_attendance_views import (
    TeacherAttendanceClassesView,
    TeacherAttendanceSubjectsView,
    ClassStudentsForAttendanceView,
    GetAttendanceRecordsView,
    BulkSaveAttendanceView,
    AttendanceHistoryView
)

urlpatterns = [
    # Attendance URLs
    path('subject-classes/', TeacherAttendanceClassesView.as_view(), name='teacher-attendance-classes'),
    path('my-subjects/', TeacherAttendanceSubjectsView.as_view(), name='teacher-attendance-subjects'),
    path('class-students/<uuid:class_id>/', ClassStudentsForAttendanceView.as_view(), name='teacher-attendance-students'),
    path('records/', GetAttendanceRecordsView.as_view(), name='get-attendance-records'),
    path('bulk-save/', BulkSaveAttendanceView.as_view(), name='bulk-save-attendance'),
    path('history/', AttendanceHistoryView.as_view(), name='attendance-history'),
]