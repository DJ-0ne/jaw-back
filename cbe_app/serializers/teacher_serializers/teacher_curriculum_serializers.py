from rest_framework import serializers
from cbe_app.models import (
    LearningArea, GradeLevel, LessonPlan, Strand, SubStrand, LearningOutcome,
    CurriculumVersion, CoreCompetency, CoreValue
)


class CoreCompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = CoreCompetency
        fields = ['id', 'code', 'name', 'description', 'indicators', 'display_order']


class CoreValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoreValue
        fields = ['id', 'code', 'name', 'description', 'indicators', 'display_order']


class LearningOutcomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningOutcome
        fields = ['id', 'description', 'domain', 'display_order']


class SubStrandSerializer(serializers.ModelSerializer):
    learning_outcomes = LearningOutcomeSerializer(many=True, read_only=True)
    
    class Meta:
        model = SubStrand
        fields = ['id', 'substrand_code', 'substrand_name', 'description', 
                  'display_order', 'learning_outcomes']


class StrandSerializer(serializers.ModelSerializer):
    substrands = SubStrandSerializer(many=True, read_only=True)
    
    class Meta:
        model = Strand
        fields = ['id', 'strand_code', 'strand_name', 'description', 
                  'display_order', 'substrands']


class LearningAreaSerializer(serializers.ModelSerializer):
    strands = StrandSerializer(many=True, read_only=True)
    
    class Meta:
        model = LearningArea
        fields = ['id', 'area_code', 'area_name', 'short_name', 'area_type', 
                  'description', 'is_active', 'strands']


class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = ['id', 'level', 'name', 'description']


class TeacherSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningArea
        fields = ['id', 'area_code', 'area_name', 'short_name', 'area_type', 'description']


class CurriculumVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumVersion
        fields = ['id', 'name', 'academic_year', 'is_active', 'is_published', 
                  'published_at', 'created_at']
        
class LessonPlanSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.area_name', read_only=True)
    grade_name = serializers.CharField(source='grade_level.name', read_only=True)
    strand_name = serializers.CharField(source='strand.strand_name', read_only=True, allow_null=True)
    substrand_name = serializers.CharField(source='substrand.substrand_name', read_only=True, allow_null=True)
    
    class Meta:
        model = LessonPlan
        fields = [
            'id', 'topic', 'objectives', 'activities', 'resources', 'assessment',
            'duration', 'lesson_date', 'status', 'subject_id', 'subject_name',
            'grade_level_id', 'grade_name', 'strand_id', 'strand_name',
            'substrand_id', 'substrand_name', 'outcome_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']