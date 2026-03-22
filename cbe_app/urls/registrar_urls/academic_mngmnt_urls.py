# cbe_app/urls/registrar_urls/academic_urls.py

from django.urls import path
from cbe_app.views.registrar_views import academic_mngmnt_views as views

urlpatterns = [
    # Academic Years
    path('academic-years/', views.get_academic_years, name='get-academic-years'),
    path('academic-years/create/', views.create_academic_year, name='create-academic-year'),
    path('academic-years/<uuid:year_id>/', views.academic_year_detail, name='academic-year-detail'),
    
    # Terms
    path('terms/', views.get_terms, name='get-terms'),
    path('terms/create/', views.create_term, name='create-term'),
    path('terms/<uuid:term_id>/', views.term_detail, name='term-detail'),
    
    # Learning Areas
    path('learning-areas/', views.get_learning_areas, name='get-learning-areas'),
    path('learning-areas/create/', views.create_learning_area, name='create-learning-area'),
    path('learning-areas/<uuid:area_id>/', views.delete_learning_area, name='delete-learning-area'),
    
    # Strands
    path('strands/', views.get_strands, name='get-strands'),
    path('strands/create/', views.create_strand, name='create-strand'),
    path('strands/<uuid:strand_id>/', views.delete_strand, name='delete-strand'),
    
    # Sub-strands
    path('substrands/', views.get_substrands, name='get-substrands'),
    path('substrands/create/', views.create_substrand, name='create-substrand'),
    path('substrands/<uuid:substrand_id>/', views.delete_substrand, name='delete-substrand'),
    
    # Competencies
    path('competencies/', views.get_competencies, name='get-competencies'),
    path('competencies/create/', views.create_competency, name='create-competency'),
    path('competencies/<uuid:competency_id>/', views.delete_competency, name='delete-competency'),
    
    
    # Grade Levels
    path('grade-levels/', views.get_grade_levels, name='get-grade-levels'),
    
    # Grading Scales
    path('grading-scales/', views.get_grading_scales, name='get-grading-scales'),
    path('grading-scales/create/', views.create_grading_scale, name='create-grading-scale'),
    path('grading-scales/<uuid:scale_id>/', views.grading_scale_detail, name='grading-scale-detail'),
    
    # Curriculum Mappings
    path('curriculum-mappings/', views.get_curriculum_mappings, name='get-curriculum-mappings'),
    path('curriculum-mappings/create/', views.create_curriculum_mapping, name='create-curriculum-mapping'),
    path('curriculum-mappings/<uuid:mapping_id>/', views.delete_curriculum_mapping, name='delete-curriculum-mapping'),
    
    # Student Portfolios
    path('student-portfolios/', views.get_student_portfolios, name='get-student-portfolios'),
    path('student-portfolios/create/', views.create_student_portfolio, name='create-student-portfolio'),
    path('student-portfolios/<uuid:portfolio_id>/', views.update_student_portfolio, name='update-student-portfolio'),
    
    # Class Competencies
    path('class-competencies/', views.get_class_competencies, name='get-class-competencies'),
    
    path('academic/current/', views.get_current_academic_year_and_term, name='current-academic'),
]