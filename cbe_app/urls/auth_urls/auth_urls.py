from django.urls import path
from cbe_app.views.auth_views.auth_views import*

urlpatterns = [
    # Authentication endpoints
    path('register/', register, name='register'),
    path('login/', login, name='login'),
    path('logout/', logout, name='logout'),
    path('refresh-token/', refresh_token, name='refresh_token'),
    path('validate-token/', validate_token, name='validate_token'),
    path('check-username/', check_username, name='check_username'),

    
    # Session management
    path('sessions/', get_active_sessions, name='get_sessions'),
    path('sessions/<uuid:session_id>/revoke/', revoke_session, name='revoke_session'),
]