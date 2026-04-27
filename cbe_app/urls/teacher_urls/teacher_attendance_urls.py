# urls.py - Add to your main app urls.py

from django.urls import path
from cbe_app.views.teacher_views.teacher_attendance_views import (
    TeacherSubjectClassesView,
    TeacherSubjectsView,
    ClassStudentsForAttendanceView,
    AttendanceRecordsView,
    AttendanceHistoryView,
    BulkAttendanceSaveView,
    TakeAttendanceView
)

urlpatterns = [
    # Attendance URLs
    path('subject-classes/', TeacherSubjectClassesView.as_view(), name='teacher-subject-classes'),
    path('my-subjects/', TeacherSubjectsView.as_view(), name='teacher-subjects'),
    path('class-students/<uuid:class_id>/', ClassStudentsForAttendanceView.as_view(), name='class-students-attendance'),
    path('records/', AttendanceRecordsView.as_view(), name='attendance-records'),
    path('history/', AttendanceHistoryView.as_view(), name='attendance-history'),
    path('bulk-save/', BulkAttendanceSaveView.as_view(), name='attendance-bulk-save'),
    path('take/', TakeAttendanceView.as_view(), name='take-attendance'),
]