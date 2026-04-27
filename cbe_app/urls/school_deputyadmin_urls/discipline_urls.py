# cbe_app/urls/deputy_urls/discipline_urls.py

from django.urls import path
from cbe_app.views.school_deputyadmin_views import deputy_views as views

urlpatterns = [
    path('cases/', views.get_discipline_cases, name='get-discipline-cases'),
    path('cases/create/', views.create_discipline_case, name='create-discipline-case'),
    path('cases/<uuid:case_id>/resolve/', views.resolve_discipline_case, name='resolve-discipline-case'),
    path('cases/<uuid:case_id>/delete/', views.delete_discipline_case, name='delete-discipline-case'),
    
    path('conduct/', views.get_conduct_records, name='get-conduct-records'),
    
    path('interventions/', views.get_interventions, name='get-interventions'),
    path('interventions/create/', views.create_intervention, name='create-intervention'),
    
    path('sessions/', views.get_counseling_sessions, name='get-counseling-sessions'),
    path('sessions/create/', views.create_counseling_session, name='create-counseling-session'),
    
    path('suspensions/', views.get_suspensions, name='get-suspensions'),
    
    path('stats/', views.get_discipline_stats, name='get-discipline-stats'),
]