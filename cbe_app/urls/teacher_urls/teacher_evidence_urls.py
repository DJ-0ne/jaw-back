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
    # ── non‑UUID endpoints (order matters!) ──
    path('classes/', EvidenceClassesView.as_view(), name='teacher-evidence-classes'),
    path('students/<uuid:class_id>/', EvidenceStudentsView.as_view(), name='teacher-evidence-students'),
    path('subjects/', EvidenceSubjectsView.as_view(), name='teacher-evidence-subjects'),
    path('competencies/', EvidenceCompetenciesView.as_view(), name='teacher-evidence-competencies'),
    path('list/', EvidenceListView.as_view(), name='teacher-evidence-list'),
    path('upload/', EvidenceUploadView.as_view(), name='teacher-evidence-upload'),
    path('evidence/audit/', PortfolioAuditView.as_view(), name='teacher-evidence-audit'),

    # ── evidence‑specific actions (UUID captured directly) ──
    path('<uuid:evidence_id>/delete/', EvidenceDeleteView.as_view(), name='teacher-evidence-delete'),
    path('<uuid:evidence_id>/comment/', EvidenceAddCommentView.as_view(), name='teacher-evidence-comment'),
    path('<uuid:evidence_id>/feature/', EvidenceToggleFeatureView.as_view(), name='teacher-evidence-feature'),
]