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
    path('hr/departments/', include('cbe_app.urls.hr_urls.hr_department_urls')),
    path('student/', include('cbe_app.urls.student_urls.student_dashboard_urls')),
    path('student/fees/', include('cbe_app.urls.student_urls.student_fee_urls')),  
    path('student/profile/', include('cbe_app.urls.student_urls.student_profile_urls')),
    ########################DEPUTY ADMIN URLS########################
    path('deputyadmin/discipline/', include('cbe_app.urls.school_deputyadmin_urls.discipline_urls')),
    path('deputyadmin/teacher-assignments/', include('cbe_app.urls.school_deputyadmin_urls.teacher_assignment_urls')),
    #########################TEACHER URLS########################
    path('teacher/', include('cbe_app.urls.teacher_urls.teacher_class_urls')),
    path('teacher/attendance/', include('cbe_app.urls.teacher_urls.teacher_attendance_urls')),
    path('teacher/curriculum/', include('cbe_app.urls.teacher_urls.teacher_curriculum_urls')),
]