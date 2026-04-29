from rest_framework import serializers
from cbe_app.models import (
    Student, Class, Staff, StudentPortfolio, CoreCompetency,
    LearningArea, Term, AcademicYear
)


class EvidenceStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name']
    
    def get_full_name(self, obj):
        return obj.full_name


class EvidenceClassSerializer(serializers.ModelSerializer):
    class_name_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'numeric_level', 'class_name_display']
    
    def get_class_name_display(self, obj):
        grade = obj.numeric_level
        stream_text = f" - {obj.stream}" if obj.stream else ""
        return f"Grade {grade}{stream_text}"


class CoreCompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = CoreCompetency
        fields = ['id', 'code', 'name', 'description']


class EvidenceListSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_id = serializers.UUIDField(source='student.id', read_only=True)
    competency_name = serializers.CharField(source='core_competency.name', read_only=True)
    competency_code = serializers.CharField(source='core_competency.code', read_only=True)
    subject_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    featured = serializers.BooleanField(default=False)
    
    class Meta:
        model = StudentPortfolio
        fields = [
            'id', 'title', 'description', 'student_id', 'student_name',
            'competency_name', 'competency_code', 'subject_name', 'date',
            'file_url', 'evidence_type', 'teacher_comment', 'student_reflection',
            'teacher_feedback', 'featured', 'created_at', 'updated_at'
        ]
    
    def get_subject_name(self, obj):
        # Extract subject from teacher_comment or determine from context
        return "General"
    
    def get_file_url(self, obj):
        if obj.evidence_url:
            return obj.evidence_url
        return None


class CreateEvidenceSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    student_id = serializers.UUIDField()
    subject = serializers.CharField(max_length=100, required=False, allow_blank=True)
    competencies = serializers.ListField(child=serializers.UUIDField(), required=False)
    date = serializers.DateField()
    student_reflection = serializers.CharField(required=False, allow_blank=True)
    teacher_feedback = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(required=False, allow_null=True)


class AddCommentSerializer(serializers.Serializer):
    comment = serializers.CharField()
    type = serializers.ChoiceField(choices=['teacher', 'parent', 'student'])


class ToggleFeatureSerializer(serializers.Serializer):
    featured = serializers.BooleanField()


class PortfolioAuditSerializer(serializers.Serializer):
    total_students = serializers.IntegerField()
    students_with_evidence = serializers.IntegerField()
    total_evidence = serializers.IntegerField()
    featured_count = serializers.IntegerField()
    missing_evidence = serializers.IntegerField()
    evidence_by_subject = serializers.ListField()