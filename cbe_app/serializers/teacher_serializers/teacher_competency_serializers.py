from rest_framework import serializers
from cbe_app.models import (
    Class, Student, Staff, CoreCompetency, StudentPortfolio, Term, AcademicYear,
    LearningArea, Strand, SubStrand, Competency
)


class CompetencyClassSerializer(serializers.ModelSerializer):
    grade_level = serializers.IntegerField(source='numeric_level')
    class_name_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'grade_level', 'numeric_level', 'capacity', 'class_name_display']
    
    def get_class_name_display(self, obj):
        if obj.numeric_level == 9:
            grade = 7
        elif obj.numeric_level == 10:
            grade = 8
        elif obj.numeric_level == 11:
            grade = 9
        else:
            grade = obj.numeric_level
        stream_text = f" - {obj.stream}" if obj.stream else ""
        return f"Grade {grade}{stream_text}"


class CompetencyStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    assessment_number = serializers.CharField(source='admission_no')
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'assessment_number', 'first_name', 'last_name', 'full_name', 'gender']
    
    def get_full_name(self, obj):
        return obj.full_name


class CoreCompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = CoreCompetency
        fields = ['id', 'code', 'name', 'description', 'indicators']


class StudentCompetencySerializer(serializers.Serializer):
    score = serializers.IntegerField(allow_null=True, min_value=0, max_value=100)
    level = serializers.IntegerField(allow_null=True)
    level_label = serializers.CharField(allow_null=True)
    last_updated = serializers.DateTimeField(allow_null=True)
    updated_by = serializers.CharField(allow_null=True)


class CompetencyMatrixDataSerializer(serializers.Serializer):
    class_id = serializers.UUIDField()
    term_id = serializers.UUIDField()
    subject_id = serializers.UUIDField(required=False, allow_null=True)


class UpdateCompetencySerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    competency_id = serializers.UUIDField()
    level = serializers.IntegerField(min_value=1, max_value=5)
    score = serializers.IntegerField(min_value=0, max_value=100)
    subject_id = serializers.UUIDField(required=False, allow_null=True)


class EvidenceSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    competency_id = serializers.UUIDField()
    description = serializers.CharField()
    evidence_type = serializers.ChoiceField(choices=['observation', 'project', 'portfolio', 'presentation', 'test'])
    date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True)


class PCISerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    issue_id = serializers.CharField()
    level = serializers.IntegerField(min_value=1, max_value=5)


class CompetencySummarySerializer(serializers.Serializer):
    competency_id = serializers.CharField()
    competency_name = serializers.CharField()
    average_score = serializers.FloatField()
    counts_by_level = serializers.DictField()