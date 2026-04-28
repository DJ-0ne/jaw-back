from django.urls import path
from cbe_app.views.teacher_views.teacher_assesment_views import (
    TeacherAssessmentClassesView,
    TeacherAssessmentSubjectsView,
    TeacherAssessmentsListView,
    TeacherCreateAssessmentView,
    TeacherAssessmentStudentsView,
    TeacherPublishAssessmentView,
    TeacherSaveGradesView,
    TeacherAssessmentResultsView,
    TeacherDeleteAssessmentView,
    TeacherUpdateAssessmentView
)

urlpatterns = [
    # Assessment URLs
    path('classes/', TeacherAssessmentClassesView.as_view(), name='teacher-assessment-classes'),
    path('subjects/', TeacherAssessmentSubjectsView.as_view(), name='teacher-assessment-subjects'),
    path('list/', TeacherAssessmentsListView.as_view(), name='teacher-assessment-list'),
    path('create/', TeacherCreateAssessmentView.as_view(), name='teacher-assessment-create'),
    path('<uuid:assessment_id>/students/', TeacherAssessmentStudentsView.as_view(), name='teacher-assessment-students'),
    path('<uuid:assessment_id>/grade/', TeacherSaveGradesView.as_view(), name='teacher-assessment-grade'),
    path('<uuid:assessment_id>/results/', TeacherAssessmentResultsView.as_view(), name='teacher-assessment-results'),
    path('<uuid:assessment_id>/delete/', TeacherDeleteAssessmentView.as_view(), name='teacher-assessment-delete'),
    path('<uuid:assessment_id>/update/', TeacherUpdateAssessmentView.as_view(), name='teacher-assessment-update'),
    path('<uuid:assessment_id>/publish/', TeacherPublishAssessmentView.as_view(), name='teacher-assessment-publish'),
]