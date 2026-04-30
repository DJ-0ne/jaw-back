from rest_framework import serializers
from cbe_app.models import ExamResult, Exam, Student, Class, LearningArea


class ExamResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_admission = serializers.SerializerMethodField()
    exam_title = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamResult
        fields = [
            'id', 'exam', 'exam_title', 'student', 'student_name', 'student_admission',
            'subject', 'marks_obtained', 'percentage', 'grade', 'remarks',
            'marked_by', 'marked_at', 'class_name'
        ]
        read_only_fields = ['id', 'marked_at']
    
    def get_student_name(self, obj):
        return obj.student.full_name
    
    def get_student_admission(self, obj):
        return obj.student.admission_no
    
    def get_exam_title(self, obj):
        return obj.exam.title if obj.exam else None
    
    def get_class_name(self, obj):
        if obj.student and obj.student.current_class:
            return obj.student.current_class.class_name
        return None


class ResultAnalyticsSerializer(serializers.Serializer):
    total_results = serializers.IntegerField()
    average_score = serializers.FloatField()
    pass_rate = serializers.FloatField()
    total_students = serializers.IntegerField()
    grade_distribution = serializers.DictField()
    top_performers = serializers.ListField()
    subject_performance = serializers.ListField()
    class_performance = serializers.ListField()


class BulkUploadResultSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    subject = serializers.CharField()
    marks_obtained = serializers.FloatField()
    exam_id = serializers.CharField()