from rest_framework import serializers
from cbe_app.models import (
    Class, Student, Staff, ClassSubjectAllocation, 
    AttendanceSession, StudentAttendance, LearningArea,
    Term, AcademicYear
)


class TeacherClassSerializer(serializers.ModelSerializer):
    class_id = serializers.UUIDField(source='class_id.id', read_only=True)
    class_name = serializers.CharField(source='class_id.class_name', read_only=True)
    class_code = serializers.CharField(source='class_id.class_code', read_only=True)
    stream = serializers.CharField(source='class_id.stream', read_only=True)
    numeric_level = serializers.IntegerField(source='class_id.numeric_level', read_only=True)
    subject_name = serializers.CharField(source='subject.area_name', read_only=True)
    subject_id = serializers.UUIDField(source='subject.id', read_only=True)
    
    class Meta:
        model = ClassSubjectAllocation
        fields = ['id', 'class_id', 'class_name', 'class_code', 'stream', 
                  'numeric_level', 'subject_name', 'subject_id']


class TeacherSubjectSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='area_name', read_only=True)
    code = serializers.CharField(source='area_code', read_only=True)
    
    class Meta:
        model = LearningArea
        fields = ['id', 'name', 'code']


class AttendanceStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    attendance_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name', 
                  'gender', 'attendance_rate']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_attendance_rate(self, obj):
        current_term = Term.objects.filter(is_current=True).first()
        if not current_term:
            return 0
        
        sessions = AttendanceSession.objects.filter(
            session_date__gte=current_term.start_date,
            session_date__lte=current_term.end_date
        )
        total_sessions = sessions.count()
        if total_sessions == 0:
            return 0
        
        present_count = obj.attendance_records.filter(
            session__in=sessions,
            attendance_status='Present'
        ).count()
        
        return round((present_count / total_sessions) * 100)


class AttendanceRecordSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    class_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    date = serializers.DateField()
    period = serializers.ChoiceField(choices=['morning', 'afternoon', 'full'])
    status = serializers.ChoiceField(choices=['present', 'absent'])


class BulkAttendanceSaveSerializer(serializers.Serializer):
    records = AttendanceRecordSerializer(many=True)


class AttendanceHistorySerializer(serializers.Serializer):
    date = serializers.DateField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    percentage = serializers.IntegerField()