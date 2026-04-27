# cbe_app/serializers/teacher_serializers/teacher_class_serializers.py

from rest_framework import serializers
from ...models import (
    Class, Student, Staff, Department, DepartmentStaffAssignment,
    ClassSubjectAllocation, AttendanceSession, StudentAttendance,
    Exam, ExamResult
)


class TeacherClassSerializer(serializers.ModelSerializer):
    """Serializer for classes where teacher is class teacher"""
    current_students = serializers.IntegerField(read_only=True)
    class_teacher_name = serializers.SerializerMethodField()
    class_code = serializers.CharField()
    class_name = serializers.CharField()
    capacity = serializers.IntegerField()
    
    class Meta:
        model = Class
        fields = [
            'id', 'class_code', 'class_name', 'numeric_level', 'stream',
            'capacity', 'current_students', 'class_teacher_name', 'is_active'
        ]
    
    def get_class_teacher_name(self, obj):
        if obj.class_teacher:
            return f"{obj.class_teacher.first_name} {obj.class_teacher.last_name}"
        return None


class TeacherSubjectClassSerializer(serializers.Serializer):
    """Serializer for subject allocations (not a direct model serializer)"""
    id = serializers.CharField()
    class_id = serializers.CharField()
    class_name = serializers.CharField()
    class_code = serializers.CharField()
    subject = serializers.CharField()
    subject_name = serializers.CharField()
    periods_per_week = serializers.IntegerField()
    is_compulsory = serializers.BooleanField()
    students_count = serializers.IntegerField()
    academic_year = serializers.CharField()
    coverage_percentage = serializers.FloatField(default=0)
    topics_covered = serializers.IntegerField(default=0)
    total_topics = serializers.IntegerField(default=0)
    assessments_done = serializers.IntegerField(default=0)
    total_assessments = serializers.IntegerField(default=0)


class TeacherStudentSerializer(serializers.ModelSerializer):
    """Serializer for students in teacher's class"""
    full_name = serializers.SerializerMethodField()
    current_score = serializers.FloatField(default=0)
    attendance_rate = serializers.FloatField(default=0)
    target_level = serializers.CharField(default='ME')
    last_assessment = serializers.FloatField(default=0)
    competency_levels = serializers.DictField(default=dict)
    subject_scores = serializers.DictField(default=dict)
    admission_no = serializers.CharField()
    
    class Meta:
        model = Student
        fields = [
            'id', 'admission_no', 'first_name', 'middle_name', 'last_name', 'full_name',
            'gender', 'date_of_birth', 'current_score', 'attendance_rate', 'target_level',
            'last_assessment', 'competency_levels', 'subject_scores', 'status'
        ]
    
    def get_full_name(self, obj):
        return obj.full_name


class TeacherAssessmentSerializer(serializers.Serializer):
    """Serializer for creating/updating assessments (no model binding)"""
    id = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    subject = serializers.CharField()
    class_id = serializers.UUIDField()
    date = serializers.DateField()
    max_score = serializers.FloatField(default=100)
    assessment_type = serializers.ChoiceField(
        choices=['quiz', 'cat', 'assignment', 'project', 'exam'],
        default='quiz'
    )
    scores = serializers.DictField(child=serializers.FloatField(), required=False)


class TeacherEvidenceSerializer(serializers.Serializer):
    """Serializer for uploading evidence (no model binding)"""
    student_id = serializers.UUIDField()
    description = serializers.CharField()
    competency_code = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField()


class TeacherAttendanceSerializer(serializers.Serializer):
    """Serializer for recording attendance"""
    class_id = serializers.UUIDField()
    date = serializers.DateField()
    session_type = serializers.ChoiceField(choices=['Morning', 'Afternoon', 'Full Day'], default='Morning')
    records = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )