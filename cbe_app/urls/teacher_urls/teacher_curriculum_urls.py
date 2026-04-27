from django.urls import path
from cbe_app.views.teacher_views.teacher_curriculum_views import (
    TeacherSubjectsView,
    TeacherGradeLevelsView,
    CurriculumStrandsView,
    SyllabusProgressView,
    CoreCompetenciesView,
    CoreValuesView,
    LessonPlanCreateView,
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
    path('lesson-plans/', LessonPlanCreateView.as_view(), name='teacher-curriculum-lesson-plans-create'),
    path('lesson-plans/list/', TeacherLessonPlansView.as_view(), name='teacher-curriculum-lesson-plans-list'),
    path('versions/', CurriculumVersionsView.as_view(), name='teacher-curriculum-versions'),
]