from django.urls import path
from cbe_app.views.student_views import student_result_views as views

urlpatterns = [
    path('terms/', views.StudentTermsView.as_view(), name='student-results-terms'),
    path('assessments/', views.StudentAssessmentWindowsView.as_view(), name='student-results-assessments'),
    path('preview/', views.StudentResultsPreviewView.as_view(), name='student-results-preview'),
]