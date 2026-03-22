# cbe_app/urls/bursar_urls/bursar_urls.py

from django.urls import path
from cbe_app.views.bursar_views import bursar_payment_views as views

urlpatterns = [
    # Student Search
    path('students/search/', views.search_students, name='search-students'),
    path('students/by-class/', views.get_students_by_class, name='students-by-class'),
    
    # Invoice Management
    path('students/<uuid:student_id>/invoice-status/', views.check_invoice_status, name='check-invoice-status'),
    path('students/<uuid:student_id>/generate-invoice/', views.generate_invoice, name='generate-invoice'),
    path('students/<uuid:student_id>/balance/', views.get_student_balance, name='student-balance'),
    
    # Payment Processing
    path('transactions/create/', views.process_payment, name='process-payment'),
    path('transactions/recent/', views.get_recent_transactions, name='recent-transactions'),
]