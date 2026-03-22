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
    
    # Statistics
    path('staff/stats/', views.get_staff_stats, name='staff-stats'),
    
    # Leave Management
    path('staff/<uuid:staff_id>/leaves/', views.get_staff_leaves, name='get-staff-leaves'),
    path('staff/<uuid:staff_id>/leaves/create/', views.create_staff_leave, name='create-staff-leave'),
    path('staff/<uuid:staff_id>/leave-balance/', views.get_leave_balance, name='get-leave-balance'),
    
    # Loan Management
    path('staff/<uuid:staff_id>/loans/', views.get_staff_loans, name='get-staff-loans'),
    path('staff/<uuid:staff_id>/loans/create/', views.create_staff_loan, name='create-staff-loan'),
    
    # Payroll
    path('staff/<uuid:staff_id>/payroll/', views.get_staff_payroll, name='get-staff-payroll'),
    
    # Bulk Operations
    path('staff/bulk/', views.bulk_create_staff, name='bulk-create-staff'),
    path('staff/template/', views.download_template, name='download-template'),
    path('staff/export/', views.export_staff, name='export-staff'),
]