from rest_framework import serializers
from cbe_app.models import (
    Class, Student, Staff, ClassSubjectAllocation, 
    Term, AcademicYear, Exam, ExamResult, LearningArea
)


class JSSClassSerializer(serializers.ModelSerializer):
    grade_level = serializers.IntegerField(source='numeric_level')
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'grade_level', 'capacity']


class JSSStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name', 'gender']
    
    def get_full_name(self, obj):
        return obj.full_name


class JSSSubjectSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='area_code')
    name = serializers.CharField(source='area_name')
    code = serializers.CharField(source='area_code')
    sba_weight = serializers.IntegerField(default=40)
    exam_weight = serializers.IntegerField(default=60)
    
    class Meta:
        model = LearningArea
        fields = ['id', 'name', 'code', 'sba_weight', 'exam_weight']


class JSSSubjectMarkSerializer(serializers.Serializer):
    sba = serializers.FloatField(allow_null=True, min_value=0, max_value=100)
    exam = serializers.FloatField(allow_null=True, min_value=0, max_value=100)
    weighted_total = serializers.FloatField(allow_null=True)
    level_code = serializers.CharField(allow_null=True)
    grade = serializers.CharField(allow_null=True)


class JSSStudentMarksSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    marks = serializers.DictField(child=JSSSubjectMarkSerializer())


class JSSBulkSaveSerializer(serializers.Serializer):
    class_id = serializers.UUIDField()
    term = serializers.CharField(max_length=20)
    year = serializers.IntegerField()
    marks = serializers.DictField(
        child=serializers.DictField(child=JSSSubjectMarkSerializer())
    )


class JSSMarksRetrieveSerializer(serializers.Serializer):
    class_id = serializers.UUIDField()
    term = serializers.CharField(max_length=20)
    year = serializers.IntegerField()