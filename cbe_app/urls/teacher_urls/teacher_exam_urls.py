from django.urls import path
from cbe_app.views.teacher_views import teacher_exam_views as views

urlpatterns = [
    path('', views.TeacherExamsListView.as_view(), name='teacher-exams-list'),
    path('<uuid:exam_id>/scores/', views.TeacherExamScoresView.as_view(), name='teacher-exam-scores'),
    path('<uuid:exam_id>/scores/bulk/', views.TeacherExamScoresBulkSaveView.as_view(), name='teacher-exam-scores-bulk'),
    path('<uuid:exam_id>/finalize/', views.TeacherExamFinalizeView.as_view(), name='teacher-exam-finalize'),
]