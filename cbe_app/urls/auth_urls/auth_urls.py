from django.urls import path
from cbe_app.views.auth_views.auth_views import *
from cbe_app.services.email.otp_service import *
from cbe_app.views.student_views.student_profile_views import get_user_info
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
    
    path('user/', get_user_info, name='auth-user-info'), 
    
    # OTP endpoints for force logout
    path('resend-force-logout-otp/', resend_force_logout_otp, name='resend_force_logout_otp'),
    
    # Password reset with OTP
    path('request-password-reset-otp/', request_password_reset_otp, name='request_password_reset_otp'),
    path('verify-password-reset-otp/', verify_password_reset_otp, name='verify_password_reset_otp'),
    path('reset-password/', reset_password, name='reset_password'),
]