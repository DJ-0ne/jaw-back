# urls.py - Add to your main app urls.py

from django.urls import path
from cbe_app.views.teacher_views import teacher_class_view as view

urlpatterns = [
    # Class Management
    path('my-classes/', view.TeacherMyClassesView.as_view(), name='teacher-my-classes'),
    path('subject-classes/', view.TeacherSubjectClassesView.as_view(), name='teacher-subject-classes'),
    path('class-students/<uuid:class_id>/', view.ClassStudentsView.as_view(), name='class-students'),
    path('class-analytics/<uuid:class_id>/', view.ClassAnalyticsView.as_view(), name='class-analytics'),
    
    # Attendance
    path('attendance/', view.TakeAttendanceView.as_view(), name='take-attendance'),
    path('attendance/<uuid:class_id>/', view.GetAttendanceView.as_view(), name='get-attendance'),
    
    # Assessment
    path('assessment/', view.SaveAssessmentView.as_view(), name='save-assessment'),
    
    # Evidence/Portfolio
    path('evidence/', view.UploadEvidenceView.as_view(), name='upload-evidence'),
    path('evidence/<uuid:student_id>/', view.GetEvidenceView.as_view(), name='get-evidence'),
]