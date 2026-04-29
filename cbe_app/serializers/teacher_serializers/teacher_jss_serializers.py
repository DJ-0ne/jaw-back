from rest_framework import serializers
from cbe_app.models import (
    Class, Student, Staff, ClassSubjectAllocation, 
    Term, AcademicYear, LearningArea, Strand,
    SummativeAssessment, SummativeRating, AssessmentWindow
)


class JSSClassSerializer(serializers.ModelSerializer):
    grade_level = serializers.IntegerField(source='numeric_level')
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'grade_level', 'numeric_level', 'capacity', 'display_name']
    
    def get_display_name(self, obj):
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


class JSSStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    admission_no = serializers.CharField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name', 'gender']
    
    def get_full_name(self, obj):
        return obj.full_name


class JSSSubjectSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    code = serializers.CharField()
    sba_weight = serializers.IntegerField(default=40)
    exam_weight = serializers.IntegerField(default=60)


class JSSTermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = ['id', 'term', 'start_date', 'end_date', 'is_current']


class JSSSubjectMarkSerializer(serializers.Serializer):
    sba = serializers.FloatField(allow_null=True)
    exam = serializers.FloatField(allow_null=True)
    weighted_total = serializers.FloatField(allow_null=True)
    grade = serializers.CharField(allow_null=True)
    level_code = serializers.CharField(allow_null=True)


class JSSMarksDataSerializer(serializers.Serializer):
    class_id = serializers.UUIDField()
    term = serializers.CharField()
    year = serializers.IntegerField()
    marks = serializers.DictField(
        child=serializers.DictField(
            child=JSSSubjectMarkSerializer()
        )
    )