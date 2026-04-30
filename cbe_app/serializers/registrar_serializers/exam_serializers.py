from rest_framework import serializers
from cbe_app.models import Exam, ExamSchedule, ExamMarker, ExamModeration, ExamPermission, Staff


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = [
            'id', 'exam_code', 'title', 'exam_type', 'grade_level', 
            'academic_year', 'term', 'start_date', 'end_date', 
            'duration_minutes', 'total_marks', 'passing_marks', 
            'status', 'instructions', 'subjects', 'classes', 
            'marking_scheme', 'weighting', 'room_allocation', 
            'invigilators', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExamScheduleSerializer(serializers.ModelSerializer):
    invigilator_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamSchedule
        fields = '__all__'
        read_only_fields = ['id']
    
    def get_invigilator_name(self, obj):
        if obj.invigilator:
            return f"{obj.invigilator.first_name} {obj.invigilator.last_name}"
        return None


class ExamMarkerSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamMarker
        fields = '__all__'
        read_only_fields = ['id']
    
    def get_teacher_name(self, obj):
        if obj.teacher:
            return f"{obj.teacher.first_name} {obj.teacher.last_name}"
        return None


class ExamModerationSerializer(serializers.ModelSerializer):
    moderator_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamModeration
        fields = '__all__'
        read_only_fields = ['id', 'moderated_at']
    
    def get_moderator_name(self, obj):
        if obj.moderator:
            return f"{obj.moderator.first_name} {obj.moderator.last_name}"
        return None


class ExamPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamPermission
        fields = '__all__'
        read_only_fields = ['id', 'created_at']