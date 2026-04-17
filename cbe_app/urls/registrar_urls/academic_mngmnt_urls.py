# cbe_app/urls/registrar_urls/academic_mngmnt_urls.py

from django.urls import path
from cbe_app.views.registrar_views import academic_mngmnt_views as views

urlpatterns = [
    # Curriculum Core
    path('curriculum/', views.get_full_curriculum, name='get-full-curriculum'),
    path('curriculum/versions/', views.get_curriculum_versions, name='get-curriculum-versions'),
    path('curriculum/versions/create/', views.create_curriculum_version, name='create-curriculum-version'),
    path('curriculum/versions/<uuid:version_id>/activate/', views.activate_curriculum_version, name='activate-curriculum-version'),
    path('curriculum/versions/<uuid:version_id>/publish/', views.publish_curriculum_version, name='publish-curriculum-version'),
    path('curriculum/clone/', views.clone_curriculum, name='clone-curriculum'),
    
    # Academic Years
    path('academic-years/', views.get_academic_years, name='get-academic-years'),
    path('academic-years/create/', views.create_academic_year, name='create-academic-year'),
    path('academic-years/<uuid:year_id>/', views.academic_year_detail, name='academic-year-detail'),
    
    # Terms
    path('terms/', views.get_terms, name='get-terms'),
    path('terms/create/', views.create_term, name='create-term'),
    path('terms/<uuid:term_id>/', views.term_detail, name='term-detail'),
    path('academic/current/', views.get_current_academic_year_and_term, name='current-academic'),
    
    # Learning Areas (Subjects)
    path('learning-areas/', views.get_learning_areas, name='get-learning-areas'),
    path('learning-areas/create/', views.create_learning_area, name='create-learning-area'),
    path('learning-areas/<uuid:area_id>/', views.learning_area_detail, name='learning-area-detail'),
    
    # Strands
    path('strands/', views.get_strands, name='get-strands'),
    path('strands/create/', views.create_strand, name='create-strand'),
    path('strands/<uuid:strand_id>/', views.strand_detail, name='strand-detail'),
    
    # Sub-strands
    path('substrands/', views.get_substrands, name='get-substrands'),
    path('substrands/create/', views.create_substrand, name='create-substrand'),
    path('substrands/<uuid:substrand_id>/', views.substrand_detail, name='substrand-detail'),
    
    # Learning Outcomes
    path('outcomes/', views.get_learning_outcomes, name='get-learning-outcomes'),
    path('outcomes/create/', views.create_learning_outcome, name='create-learning-outcome'),
    path('outcomes/<uuid:outcome_id>/', views.learning_outcome_detail, name='learning-outcome-detail'),
    
    # Competencies (Subject-specific within substrands)
    path('competencies/', views.get_competencies, name='get-competencies'),
    path('competencies/create/', views.create_competency, name='create-competency'),
    path('competencies/<uuid:competency_id>/', views.delete_competency, name='delete-competency'),
    
    # KICD Core Competencies (7 cross-cutting)
    path('core-competencies/', views.get_core_competencies, name='get-core-competencies'),
    path('core-competencies/create/', views.create_core_competency, name='create-core-competency'),
    path('core-competencies/<uuid:competency_id>/', views.core_competency_detail, name='core-competency-detail'),
    
    # KICD Core Values (7 cross-cutting)
    path('core-values/', views.get_core_values, name='get-core-values'),
    path('core-values/create/', views.create_core_value, name='create-core-value'),
    path('core-values/<uuid:value_id>/', views.core_value_detail, name='core-value-detail'),
    
    # Grade Levels
    path('grade-levels/', views.get_grade_levels, name='get-grade-levels'),
    path('grade-levels/<uuid:grade_id>/', views.grade_level_detail, name='grade-level-detail'),
    
    # Grading Scales
    path('grading-scales/', views.get_grading_scales, name='get-grading-scales'),
    path('grading-scales/create/', views.create_grading_scale, name='create-grading-scale'),
    path('grading-scales/<uuid:scale_id>/', views.grading_scale_detail, name='grading-scale-detail'),
    
    # Weight Configuration
    path('weight-config/', views.get_weight_config, name='get-weight-config'),
    path('weight-config/update/', views.update_weight_config, name='update-weight-config'),
    
    # Curriculum Mappings
    path('curriculum-mappings/', views.get_curriculum_mappings, name='get-curriculum-mappings'),
    path('curriculum-mappings/create/', views.create_curriculum_mapping, name='create-curriculum-mapping'),
    path('curriculum-mappings/<uuid:mapping_id>/', views.delete_curriculum_mapping, name='delete-curriculum-mapping'),
    
    # Student Portfolios
    path('student-portfolios/', views.get_student_portfolios, name='get-student-portfolios'),
    path('student-portfolios/create/', views.create_student_portfolio, name='create-student-portfolio'),
    path('student-portfolios/<uuid:portfolio_id>/', views.update_student_portfolio, name='update-student-portfolio'),
    
    # Bulk Operations
    path('bulk-import/', views.bulk_import_curriculum, name='bulk-import-curriculum'),
    path('export/', views.export_curriculum, name='export-curriculum'),
]