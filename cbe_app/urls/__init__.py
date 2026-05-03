# api/urls/__init__.py
from django.urls import include, path

urlpatterns = [
    path('auth/', include('cbe_app.urls.auth_urls.auth_urls')), 
    
    ###########################REGISTRAR URLS########################
    path('registrar/classes/', include('cbe_app.urls.registrar_urls.registrar_class_urls')),
    path('registrar/students/', include('cbe_app.urls.registrar_urls.registrar_admission_urls')),
    path('registrar/academic/', include('cbe_app.urls.registrar_urls.academic_mngmnt_urls')),
    path('registrar/exams/', include('cbe_app.urls.registrar_urls.exam_mngmnt_urls')),
    path('registrar/resultsreport/', include('cbe_app.urls.registrar_urls.reportcard_mngmnt_urls')),
    
    ############################ACCOUNTANT URLS########################
    path('accountant/fees/', include('cbe_app.urls.accountant_urls.fee_management_urls')),
    
    ############################BURSAR URLS########################
    path('bursar/', include('cbe_app.urls.bursar_urls.bursar_payment_urls')),
    path('bursar/records/', include('cbe_app.urls.bursar_urls.payment_records_urls')),
    path('bursar/students/', include('cbe_app.urls.bursar_urls.bursar_payment_urls')),
    
    ############################HR URLS########################
    path('hr/', include('cbe_app.urls.hr_urls.hr_staff_urls')),
    path('hr/departments/', include('cbe_app.urls.hr_urls.hr_department_urls')),
    
    ############################STUDENT URLS########################
    path('student/', include('cbe_app.urls.student_urls.student_dashboard_urls')),
    path('student/fees/', include('cbe_app.urls.student_urls.student_fee_urls')),  
    path('student/profile/', include('cbe_app.urls.student_urls.student_profile_urls')),
    path('student/chatbot/', include('cbe_app.urls.ml_AI_urls.student_chatbot_urls')),
    path('student/results/', include('cbe_app.urls.student_urls.student_results_urls')),
    path('student/exams/', include('cbe_app.urls.student_urls.student_dashboard_urls')),
    path('student/report-card/', include('cbe_app.urls.student_urls.student_report_urls')),
    
    ########################DEPUTY ADMIN URLS########################
    path('deputyadmin/', include('cbe_app.urls.school_deputyadmin_urls.teacher_assignment_urls')),
    path('deputyadmin/discipline/', include('cbe_app.urls.school_deputyadmin_urls.discipline_urls')),
    path('deputyadmin/teacher-assignments/', include('cbe_app.urls.school_deputyadmin_urls.teacher_assignment_urls')),
    
    #########################TEACHER URLS########################
    path('teacher/', include('cbe_app.urls.teacher_urls.teacher_class_urls')),
    path('teacher/attendance/', include('cbe_app.urls.teacher_urls.teacher_attendance_urls')),
    path('teacher/curriculum/', include('cbe_app.urls.teacher_urls.teacher_curriculum_urls')),
    path('teacher/assessment/', include('cbe_app.urls.teacher_urls.teacher_assesment_urls')),
    path('teacher/jss/', include('cbe_app.urls.teacher_urls.teacher_jssentry_urls')),
    path('teacher/competency/', include('cbe_app.urls.teacher_urls.teacher_competency_urls')),
    path('teacher/evidence/', include('cbe_app.urls.teacher_urls.teacher_evidence_urls')),
    path('teacher/exams/', include('cbe_app.urls.teacher_urls.teacher_exam_urls')),
    path('teacher/dashboard/', include('cbe_app.urls.teacher_urls.teacher_dashboard_urls')),
    
    ##########################PRINCIPAL URLS######################## 
    path('principal/', include('cbe_app.urls.schooladmin_urls.principal_urls')),
    
    ##########################MESSAGING URLS########################
    path('notifications/', include('cbe_app.urls.messaging_urls.messaging_urls')),
]