# cbe_app/urls/hr_urls/hr_department_urls.py

from django.urls import path
from cbe_app.views.hr_views import hr_department_views as views

urlpatterns = [
    # Department CRUD
    path('', views.get_departments, name='get-departments'),
    path('create/', views.create_department, name='create-department'),
    path('<uuid:department_id>/', views.get_department_detail, name='get-department-detail'),
    path('update/<uuid:department_id>/', views.update_department, name='update-department'),
    path('delete/<uuid:department_id>/', views.delete_department, name='delete-department'),
    
    # Department Statistics
    path('stats/', views.get_department_stats, name='department-stats'),
    
    # Department Head Management
    path('<uuid:department_id>/set-head/', views.set_department_head, name='set-department-head'),
    path('<uuid:department_id>/remove-head/', views.remove_department_head, name='remove-department-head'),
    
]