# serializers.py - Add to your existing serializers file

from rest_framework import serializers
from cbe_app.models import (
    LearningArea, GradeLevel, Strand, SubStrand, Competency,
    LearningOutcome, CurriculumVersion, CoreCompetency, CoreValue,
    StudentPortfolio, Term, AcademicYear, Class, User
)


# ==================== CURRICULUM SERIALIZERS ====================

class CoreCompetencySerializer(serializers.ModelSerializer):
    """Serializer for KICD Core Competencies"""
    class Meta:
        model = CoreCompetency
        fields = ['id', 'code', 'name', 'description', 'indicators', 'display_order']


class CoreValueSerializer(serializers.ModelSerializer):
    """Serializer for KICD Core Values"""
    class Meta:
        model = CoreValue
        fields = ['id', 'code', 'name', 'description', 'indicators', 'display_order']


class LearningOutcomeSerializer(serializers.ModelSerializer):
    """Serializer for Learning Outcomes"""
    competency_codes = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    competencies_detail = CoreCompetencySerializer(source='competencies', many=True, read_only=True)
    
    class Meta:
        model = LearningOutcome
        fields = ['id', 'description', 'domain', 'competencies', 'competency_codes', 
                  'competencies_detail', 'display_order']
    
    def create(self, validated_data):
        competency_codes = validated_data.pop('competency_codes', [])
        learning_outcome = super().create(validated_data)
        if competency_codes:
            competencies = CoreCompetency.objects.filter(code__in=competency_codes)
            learning_outcome.competencies.set(competencies)
        return learning_outcome


class SubStrandSerializer(serializers.ModelSerializer):
    """Serializer for Sub-Strands"""
    learning_outcomes = LearningOutcomeSerializer(many=True, read_only=True)
    
    class Meta:
        model = SubStrand
        fields = ['id', 'substrand_code', 'substrand_name', 'description', 
                  'display_order', 'learning_outcomes']


class StrandSerializer(serializers.ModelSerializer):
    """Serializer for Strands"""
    substrands = SubStrandSerializer(many=True, read_only=True)
    grade_level_name = serializers.CharField(source='grade_level.name', read_only=True)
    
    class Meta:
        model = Strand
        fields = ['id', 'strand_code', 'strand_name', 'description', 
                  'display_order', 'grade_level', 'grade_level_name', 'substrands']


class LearningAreaSerializer(serializers.ModelSerializer):
    """Serializer for Learning Areas (Subjects)"""
    strands = StrandSerializer(many=True, read_only=True)
    
    class Meta:
        model = LearningArea
        fields = ['id', 'area_code', 'area_name', 'short_name', 'area_type', 
                  'description', 'is_active', 'strands']


class GradeLevelSerializer(serializers.ModelSerializer):
    """Serializer for Grade Levels"""
    class Meta:
        model = GradeLevel
        fields = ['id', 'level', 'name', 'description']


class TeacherSubjectSerializer(serializers.ModelSerializer):
    """Serializer for subjects taught by teacher"""
    is_core = serializers.BooleanField(default=True)
    grade_level_display = serializers.CharField(source='grade_level.name', read_only=True)
    
    class Meta:
        model = LearningArea
        fields = ['id', 'area_code', 'area_name', 'short_name', 'area_type', 
                  'description', 'is_core', 'grade_level_display']


class CurriculumVersionSerializer(serializers.ModelSerializer):
    """Serializer for Curriculum Versions"""
    class Meta:
        model = CurriculumVersion
        fields = ['id', 'name', 'academic_year', 'is_active', 'is_published', 
                  'published_at', 'created_at']


class SyllabusProgressSerializer(serializers.Serializer):
    """Serializer for syllabus progress"""
    strand_id = serializers.IntegerField()
    strand_name = serializers.CharField()
    total_outcomes = serializers.IntegerField()
    covered_outcomes = serializers.IntegerField()
    percentage = serializers.FloatField()
    total_lessons = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()


class LessonPlanSerializer(serializers.Serializer):
    """Serializer for Lesson Plans"""
    id = serializers.UUIDField(required=False)
    topic = serializers.CharField(max_length=200)
    objectives = serializers.ListField(child=serializers.CharField())
    activities = serializers.ListField(child=serializers.CharField())
    resources = serializers.ListField(child=serializers.CharField())
    assessment = serializers.CharField(required=False, allow_blank=True)
    duration = serializers.IntegerField(min_value=1, max_value=180, default=40)
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=['planned', 'completed', 'cancelled'], default='planned')
    subject_id = serializers.UUIDField()
    grade_id = serializers.IntegerField()
    strand_id = serializers.IntegerField(required=False, allow_null=True)
    substrand_id = serializers.IntegerField(required=False, allow_null=True)
    outcome_id = serializers.IntegerField(required=False, allow_null=True)


class LessonPlanResponseSerializer(serializers.Serializer):
    """Serializer for Lesson Plan Response"""
    success = serializers.BooleanField()
    data = LessonPlanSerializer()
    message = serializers.CharField()