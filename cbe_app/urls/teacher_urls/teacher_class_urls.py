from django.urls import path
from cbe_app.views.teacher_views.teacher_class_view import (
    TeacherMyClassesView,
    TeacherSubjectClassesView,
    ClassStudentsView,
    ClassAnalyticsView,
    TakeAttendanceView,
    SaveAssessmentView,
    UploadEvidenceView,
    GetEvidenceView
)

urlpatterns = [
    # Class Management
    path('my-classes/', TeacherMyClassesView.as_view(), name='teacher-my-classes'),
    path('subject-classes/', TeacherSubjectClassesView.as_view(), name='teacher-subject-classes'),
    path('class-students/<uuid:class_id>/', ClassStudentsView.as_view(), name='class-students'),
    path('class-analytics/<uuid:class_id>/', ClassAnalyticsView.as_view(), name='class-analytics'),
    
    # Attendance
    path('attendance/', TakeAttendanceView.as_view(), name='take-attendance'),
    
    # Assessment
    path('assessment/', SaveAssessmentView.as_view(), name='save-assessment'),
    
    # Evidence/Portfolio
    path('evidence/', UploadEvidenceView.as_view(), name='upload-evidence'),
    path('evidence/<uuid:student_id>/', GetEvidenceView.as_view(), name='get-evidence'),
]