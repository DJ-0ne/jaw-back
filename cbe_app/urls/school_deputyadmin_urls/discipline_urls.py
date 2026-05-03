# cbe_app/urls/deputy_urls/discipline_urls.py

from django.urls import path
from cbe_app.views.school_deputyadmin_views.discipline_views import get_dashboard_data
from cbe_app.views.school_deputyadmin_views import deputy_views as views

urlpatterns = [
    path('cases/', views.get_discipline_cases, name='get-discipline-cases'),
    path('cases/create/', views.create_discipline_case, name='create-discipline-case'),
    path('cases/<uuid:case_id>/resolve/', views.resolve_discipline_case, name='resolve-discipline-case'),
    path('cases/<uuid:case_id>/delete/', views.delete_discipline_case, name='delete-discipline-case'),
    path('categories/', views.get_discipline_categories, name='get-discipline-categories'),
    path('categories/create/', views.create_discipline_category, name='create-discipline-category'),
    path('conduct/', views.get_conduct_records, name='get-conduct-records'),
    path('categories/<uuid:category_id>/', views.delete_discipline_category, name='delete-discipline-category'),   # ← NEW
    path('suspensions/create/', views.create_suspension, name='create-suspension'),
    path('suspensions/<uuid:suspension_id>/', views.suspension_detail, name='suspension-detail'),

    path('dashboard/', get_dashboard_data, name='discipline_dashboard'),

    path('interventions/', views.get_interventions, name='get-interventions'),
    path('interventions/create/', views.create_intervention, name='create-intervention'),
    
    path('sessions/', views.get_counseling_sessions, name='get-counseling-sessions'),
    path('sessions/create/', views.create_counseling_session, name='create-counseling-session'),
    
    path('suspensions/', views.get_suspensions, name='get-suspensions'),
    
    path('stats/', views.get_discipline_stats, name='get-discipline-stats'),
    path('students/', views.get_students_list, name='get-students-list'),
    path('classes/', views.get_classes_list, name='get-classes-list'),
]