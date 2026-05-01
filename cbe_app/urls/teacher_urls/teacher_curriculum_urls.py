from django.urls import path
from cbe_app.views.teacher_views.teacher_curriculum_views import (
    LessonPlanDetailView,
    TeacherSubjectsView,
    TeacherGradeLevelsView,
    CurriculumStrandsView,
    SyllabusProgressView,
    CoreCompetenciesView,
    CoreValuesView,
    TeacherLessonPlansView,
    CurriculumVersionsView
)

urlpatterns = [
    path('subjects/', TeacherSubjectsView.as_view(), name='teacher-curriculum-subjects'),
    path('grade-levels/', TeacherGradeLevelsView.as_view(), name='teacher-curriculum-grade-levels'),
    path('strands/', CurriculumStrandsView.as_view(), name='teacher-curriculum-strands'),
    path('syllabus-progress/', SyllabusProgressView.as_view(), name='teacher-curriculum-syllabus-progress'),
    path('core-competencies/', CoreCompetenciesView.as_view(), name='teacher-curriculum-core-competencies'),
    path('core-values/', CoreValuesView.as_view(), name='teacher-curriculum-core-values'),
    path('lesson-plans/', TeacherLessonPlansView.as_view(), name='teacher-curriculum-lesson-plans'),  # Changed: now handles both GET and POST
    path('lesson-plans/<uuid:lesson_id>/', LessonPlanDetailView.as_view(), name='lesson-plan-detail'),
    path('versions/', CurriculumVersionsView.as_view(), name='teacher-curriculum-versions'),
]