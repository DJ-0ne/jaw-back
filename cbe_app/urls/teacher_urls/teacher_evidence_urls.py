from django.urls import path
from cbe_app.views.teacher_views.teacher_evidence_views import (
    EvidenceClassesView,
    EvidenceStudentsView,
    EvidenceSubjectsView,
    EvidenceCompetenciesView,
    EvidenceListView,
    EvidenceUploadView,
    EvidenceDeleteView,
    EvidenceAddCommentView,
    EvidenceToggleFeatureView,
    PortfolioAuditView
)

urlpatterns = [
    # Evidence Uploader URLs
    path('classes/', EvidenceClassesView.as_view(), name='teacher-evidence-classes'),
    path('students/<uuid:class_id>/', EvidenceStudentsView.as_view(), name='teacher-evidence-students'),
    path('subjects/', EvidenceSubjectsView.as_view(), name='teacher-evidence-subjects'),
    path('competencies/', EvidenceCompetenciesView.as_view(), name='teacher-evidence-competencies'),
    path('list/', EvidenceListView.as_view(), name='teacher-evidence-list'),
    path('upload/', EvidenceUploadView.as_view(), name='teacher-evidence-upload'),
    path('evidence/<uuid:evidence_id>/delete/', EvidenceDeleteView.as_view(), name='teacher-evidence-delete'),
    path('evidence/<uuid:evidence_id>/comment/', EvidenceAddCommentView.as_view(), name='teacher-evidence-comment'),
    path('evidence/<uuid:evidence_id>/feature/', EvidenceToggleFeatureView.as_view(), name='teacher-evidence-feature'),
    path('evidence/audit/', PortfolioAuditView.as_view(), name='teacher-evidence-audit'),
]