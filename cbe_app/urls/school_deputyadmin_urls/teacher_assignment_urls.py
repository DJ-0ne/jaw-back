# cbe_app/urls/school_deputyadmin_urls/teacher_assignment_urls.py

from django.urls import path
from cbe_app.views.school_deputyadmin_views.teacher_assignment_views import (
    QualifiedTeachersView,
    AvailableClassesView,
    SubjectsByGradeView,
    TeacherDepartmentsView,
    CreateTeacherAssignmentView,
    TeacherAssignmentsListView,
    DeleteTeacherAssignmentView,
    TeacherCategoriesView,
    GradeLevelsInfoView,
    UpdateTeacherAssignmentView,
    AcademicYearsListView,
)

urlpatterns = [
    path('qualified-teachers/', QualifiedTeachersView.as_view(), name='qualified-teachers'),
    path('available-classes/', AvailableClassesView.as_view(), name='available-classes'),
    path('subjects-by-grade/', SubjectsByGradeView.as_view(), name='subjects-by-grade'),
    path('departments/', TeacherDepartmentsView.as_view(), name='teacher-departments'),
    path('assignments/', TeacherAssignmentsListView.as_view(), name='teacher-assignments-list'),
    path('assignments/create/', CreateTeacherAssignmentView.as_view(), name='create-teacher-assignment'),
    path('assignments/<uuid:assignment_id>/update/', UpdateTeacherAssignmentView.as_view(), name='update-teacher-assignment'),
    path('assignments/<uuid:assignment_id>/delete/', DeleteTeacherAssignmentView.as_view(), name='delete-teacher-assignment'),
    path('teacher-categories/', TeacherCategoriesView.as_view(), name='teacher-categories'),
    path('grade-levels-info/', GradeLevelsInfoView.as_view(), name='grade-levels-info'),
    path('teacher-assignments/academic-years/', AcademicYearsListView.as_view(), name='assignment-academic-years'),
]