# cbe_app/urls/hr_urls/hr_staff_urls.py

from django.urls import path
from cbe_app.views.hr_views import hr_staff_mng_views as views

urlpatterns = [
    # Staff CRUD
    path('staff/', views.get_staff_list, name='get-staff-list'),
    path('staff/create/', views.create_staff, name='create-staff'),
    path('staff/<uuid:staff_id>/', views.get_staff_detail, name='get-staff-detail'),
    path('staff/update/<uuid:staff_id>/', views.update_staff, name='update-staff'),
    path('staff/delete/<uuid:staff_id>/', views.delete_staff, name='delete-staff'),
    
    # Department Assignments
    path('staff/<uuid:staff_id>/assign-department/', views.assign_department, name='assign-department'),
    path('staff/<uuid:staff_id>/assignments/', views.get_staff_assignments, name='get-staff-assignments'),
    path('staff/assignments/<uuid:assignment_id>/remove/', views.remove_assignment, name='remove-assignment'),
    path('staff/assignments/<uuid:assignment_id>/set-primary/', views.set_primary_assignment, name='set-primary-assignment'),
    
    # Statistics
    path('staff/stats/', views.get_staff_stats, name='staff-stats'),
    
    # Lookup Data
    path('teacher-categories/', views.get_teacher_categories, name='teacher-categories'),
    path('jss-departments/', views.get_jss_departments, name='jss-departments'),
    path('grade-levels/', views.get_grade_levels, name='grade-levels'),
    path('departments/', views.get_departments, name='departments'),
    
    # Bulk Operations
    path('staff/bulk/', views.bulk_create_staff, name='bulk-create-staff'),
    path('staff/template/', views.download_template, name='download-template'),
    path('staff/export/', views.export_staff, name='export-staff'),
    path('staff/unassigned/', views.get_unassigned_staff, name='get-unassigned-staff'),
]