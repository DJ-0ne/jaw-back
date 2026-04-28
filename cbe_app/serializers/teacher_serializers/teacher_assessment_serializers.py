from rest_framework import serializers
from cbe_app.models import (
    Class, Student, Staff, LearningArea, Exam, ExamResult,
    ClassSubjectAllocation
)


class AssessmentClassSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='class_id.id', read_only=True)
    class_name = serializers.CharField(source='class_id.class_name', read_only=True)
    stream = serializers.CharField(source='class_id.stream', read_only=True)
    numeric_level = serializers.IntegerField(source='class_id.numeric_level', read_only=True)
    
    class Meta:
        model = ClassSubjectAllocation
        fields = ['id', 'class_name', 'stream', 'numeric_level']


class AssessmentSubjectSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source='area_name', read_only=True)
    code = serializers.CharField(source='area_code', read_only=True)
    
    class Meta:
        model = LearningArea
        fields = ['id', 'name', 'code']


class AssessmentListSerializer(serializers.ModelSerializer):
    class_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    total_students = serializers.SerializerMethodField()
    submitted_count = serializers.SerializerMethodField()
    graded_count = serializers.SerializerMethodField()
    due_date = serializers.SerializerMethodField()
    
    class Meta:
        model = Exam
        fields = [
            'id', 'exam_code', 'title', 'exam_type', 'status',
            'class_name', 'subject_name', 'due_date', 'total_marks',
            'total_students', 'submitted_count', 'graded_count'
        ]
    
    def get_class_name(self, obj):
        if obj.classes and len(obj.classes) > 0:
            try:
                class_obj = Class.objects.filter(id=obj.classes[0]).first()
                return class_obj.class_name if class_obj else None
            except:
                pass
        return None
    
    def get_subject_name(self, obj):
        if obj.subjects and len(obj.subjects) > 0:
            return obj.subjects[0]
        return None
    
    def get_due_date(self, obj):
        # Return a default due date or None
        return None
    
    def get_total_students(self, obj):
        if obj.classes and len(obj.classes) > 0:
            try:
                class_obj = Class.objects.filter(id=obj.classes[0]).first()
                if class_obj:
                    return class_obj.current_students.filter(status='Active').count()
            except:
                pass
        return 0
    
    def get_submitted_count(self, obj):
        return ExamResult.objects.filter(exam=obj).count()
    
    def get_graded_count(self, obj):
        return ExamResult.objects.filter(exam=obj, marks_obtained__isnull=False).count()


class CreateAssessmentSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    type = serializers.ChoiceField(choices=['cat', 'assignment', 'project', 'exam'])
    description = serializers.CharField(required=False, allow_blank=True)
    classId = serializers.UUIDField()
    subjectId = serializers.UUIDField()
    dueDate = serializers.DateField()
    dueTime = serializers.CharField(required=False, allow_blank=True)
    maxScore = serializers.IntegerField(min_value=1, max_value=1000)
    instructions = serializers.CharField(required=False, allow_blank=True)
    allowLateSubmission = serializers.BooleanField(default=False)
    latePenalty = serializers.IntegerField(default=10, min_value=0, max_value=100)
    published = serializers.BooleanField(default=False)


class GradeEntrySerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    score = serializers.FloatField(allow_null=True)
    feedback = serializers.CharField(required=False, allow_blank=True)


class SaveGradesSerializer(serializers.Serializer):
    grades = GradeEntrySerializer(many=True)


class AssessmentResultSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    student_name = serializers.CharField()
    admission_no = serializers.CharField()
    score = serializers.FloatField()
    feedback = serializers.CharField()