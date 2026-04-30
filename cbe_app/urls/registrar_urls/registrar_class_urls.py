# urls.py
from django.urls import path
from cbe_app.views.registrar_views import class_mngnt_views as views

urlpatterns = [
    # Stream and level endpoints (must be fetched first)
    path('streams/', views.get_streams, name='get-streams'),
    path('numeric-levels/', views.get_numeric_levels, name='get-numeric-levels'),
    path('teachers/', views.get_teachers, name='get-teachers'),
    
    # Class management endpoints
    path('', views.get_classes, name='get-classes'),
    path('create/', views.create_class, name='create-class'),
    path('<uuid:class_id>/', views.get_class_detail, name='get-class-detail'),
    path('update/<uuid:class_id>/', views.update_class, name='update-class'),
    path('delete/<uuid:class_id>/', views.delete_class, name='delete-class'),
    path('subjects/', views.get_subjects, name='get-subjects'),
]