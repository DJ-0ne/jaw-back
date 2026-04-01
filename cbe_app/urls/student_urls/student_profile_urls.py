# cbe_app/urls/student_urls/profile_urls.py

from django.urls import path
from cbe_app.views.student_views.student_profile_views import (
    get_profile,
    get_user_info,
    update_profile,
    change_password,
    update_profile_image,
    get_profile_stats,
    get_complete_profile,
)

urlpatterns = [
    # Profile endpoints
    path('', get_profile, name='profile'),
    path('update/', update_profile, name='profile-update'),
    path('complete/', get_complete_profile, name='profile-complete'),
    path('stats/', get_profile_stats, name='profile-stats'),
    path('image/', update_profile_image, name='profile-image'),
    path('change-password/', change_password, name='change-password'),
    path('user/', get_user_info, name='user-info'),
]