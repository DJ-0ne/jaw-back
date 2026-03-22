# api/urls/__init__.py
from django.urls import include, path

urlpatterns = [
    path('auth/', include('cbe_app.urls.auth_urls.auth_urls')),  # Import auth URLs
    path('registrar/classes/', include('cbe_app.urls.registrar_urls.registrar_class_urls')),
    path('registrar/students/', include('cbe_app.urls.registrar_urls.registrar_admission_urls')),
    path('registrar/academic/', include('cbe_app.urls.registrar_urls.academic_mngmnt_urls')),
    path('accountant/fees/', include('cbe_app.urls.accountant_urls.fee_management_urls')),
    path('bursar/', include('cbe_app.urls.bursar_urls.bursar_payment_urls')),
    path('bursar/records/', include('cbe_app.urls.bursar_urls.payment_records_urls')),
    path('hr/', include('cbe_app.urls.hr_urls.hr_staff_urls')),
    path('student/', include('cbe_app.urls.student_urls.student_dashboard_urls')), 
]