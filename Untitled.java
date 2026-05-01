from django.urls import path
from cbe_app.views.registrar_views import reportcard_mngmnt_views as views

urlpatterns = [
    path('', views.RegistrarResultsListView.as_view(), name='results-list'),
    path('analytics/', views.RegistrarResultsAnalyticsView.as_view(), name='results-analytics'),
    path('student/<uuid:student_id>/', views.RegistrarStudentReportView.as_view(), name='student-report'),
    path('bulk-upload/', views.RegistrarBulkResultsUploadView.as_view(), name='bulk-upload'),
    path('subjects/', views.RegistrarResultSubjectsView.as_view(), name='results-subjects'),
    path('bulk-generate/', views.RegistrarBulkReportGenerationView.as_view(), name='bulk-generate'),
    path('exams/', views.RegistrarExamsForReportView.as_view(), name='exams-for-report'),  # <-- ADD THIS
]