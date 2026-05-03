from django.urls import path
from cbe_app.views.student_views.student_report_views import StudentReportCardView

urlpatterns = [
 
    path('', StudentReportCardView.as_view(), name='student_report_card'),
]