from django.urls import path
from cbe_app.views.teacher_views.teacher_competency_views import (
    CompetencyClassesView,
    CompetencyStudentsView,
    CompetencySubjectsView,
    CoreCompetenciesView,
    CompetencyMatrixRetrieveView,
    CompetencyMatrixUpdateView,
    CompetencyEvidenceView
)

urlpatterns = [
    # Competency Matrix URLs
    path('classes/', CompetencyClassesView.as_view(), name='teacher-competency-classes'),
    path('students/<uuid:class_id>/', CompetencyStudentsView.as_view(), name='teacher-competency-students'),
    path('subjects/', CompetencySubjectsView.as_view(), name='teacher-competency-subjects'),
    path('core/', CoreCompetenciesView.as_view(), name='teacher-competency-core'),
    path('matrix/retrieve/', CompetencyMatrixRetrieveView.as_view(), name='teacher-competency-matrix-retrieve'),
    path('matrix/update/', CompetencyMatrixUpdateView.as_view(), name='teacher-competency-matrix-update'),
    path('evidence/', CompetencyEvidenceView.as_view(), name='teacher-competency-evidence'),
]