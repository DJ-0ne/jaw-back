from django.urls import path
from cbe_app.views.registrar_views import exam_mngmnt_views as views

urlpatterns = [
    path('', views.RegistrarExamListView.as_view(), name='exams-list'),
    path('create/', views.RegistrarExamCreateView.as_view(), name='exams-create'),
    path('update/<uuid:exam_id>/', views.RegistrarExamUpdateView.as_view(), name='exams-update'),
    path('delete/<uuid:exam_id>/', views.RegistrarExamDeleteView.as_view(), name='exams-delete'),
    path('schedule/<uuid:exam_id>/', views.RegistrarExamScheduleView.as_view(), name='exams-schedule'),
    path('markers/<uuid:exam_id>/', views.RegistrarExamMarkersView.as_view(), name='exams-markers'),
    path('getmarkers/<uuid:exam_id>/', views.RegistrarExamMarkersGetView.as_view(), name='exams-markers-get'),
    path('moderate/<uuid:exam_id>/', views.RegistrarExamModerationView.as_view(), name='exams-moderate'),
    path('permissions/<str:scope>/', views.RegistrarExamPermissionsView.as_view(), name='exams-permissions'),
    path('permissions/<str:scope>/<uuid:exam_id>/', views.RegistrarExamPermissionsView.as_view(), name='exams-permissions-exam'),
    path('grade-levels/', views.RegistrarGradeLevelsView.as_view(), name='exams-grade-levels'),
    path('all-schedules/', views.RegistrarAllSchedulesView.as_view(), name='all-schedules'),
]