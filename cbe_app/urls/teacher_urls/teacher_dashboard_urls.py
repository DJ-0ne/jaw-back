from django.urls import path
from cbe_app.views.teacher_views import teacher_dashboard_views as views

urlpatterns = [
    path('', views.TeacherDashboardView.as_view(), name='teacher-dashboard'),
]