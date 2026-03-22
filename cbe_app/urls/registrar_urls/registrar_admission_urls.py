# urls.py
from django.urls import path
from cbe_app.views.registrar_views import student_admission_views as adm_views

urlpatterns = [
   # Student/Admission URLs
    path('', adm_views.get_students, name='get-students'),
    path('create/', adm_views.create_student, name='create-student'),
    path('import/', adm_views.import_students, name='import-students'),
    path('generate-admission-no/', adm_views.generate_admission_number_view, name='generate-admission-no'),
    path('validate-admission/', adm_views.validate_admission_number, name='validate-admission'),
    path('admission-stats/', adm_views.get_admission_stats, name='admission-stats'),
    path('<uuid:student_id>/', adm_views.get_student_detail, name='student-detail'),
    path('update/<uuid:student_id>/', adm_views.update_student, name='update-student'),
    path('delete/<uuid:student_id>/', adm_views.delete_student, name='delete-student'),
]