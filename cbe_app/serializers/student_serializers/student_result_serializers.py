from rest_framework import serializers
from cbe_app.models import Term, ExamResult


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = ['id', 'term', 'academic_year', 'is_current', 'start_date', 'end_date']


class ExamResultSerializer(serializers.ModelSerializer):
    subject_name   = serializers.SerializerMethodField()
    exam_title     = serializers.SerializerMethodField()
    exam_type      = serializers.SerializerMethodField()
    exam_grade_level = serializers.SerializerMethodField()

    class Meta:
        model = ExamResult
        fields = [
            'id', 'subject', 'subject_name', 'marks_obtained',
            'percentage', 'grade', 'remarks', 'marked_at',
            'exam_title', 'exam_type', 'exam_grade_level',
        ]

    def get_subject_name(self, obj):
        return obj.subject or ''

    def get_exam_title(self, obj):
        return obj.exam.title if obj.exam else ''

    def get_exam_type(self, obj):
        return obj.exam.exam_type if obj.exam else ''

    def get_exam_grade_level(self, obj):
        return obj.exam.grade_level if obj.exam else ''