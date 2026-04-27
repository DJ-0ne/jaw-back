# serializers.py - Add to your existing serializers file

from rest_framework import serializers
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import datetime, timedelta
from cbe_app.models import (
    Class, Student, LearningArea, StudentAttendance, 
    AttendanceSession, User, ClassSubjectAllocation,
    Term, AcademicYear
)


# ==================== ATTENDANCE SERIALIZERS ====================

class TeacherSubjectSerializer(serializers.ModelSerializer):
    """Serializer for subjects taught by a teacher"""
    name = serializers.CharField(source='area_name')
    code = serializers.CharField(source='area_code')
    
    class Meta:
        model = LearningArea
        fields = ['id', 'name', 'code', 'description']


class TeacherClassWithSubjectSerializer(serializers.ModelSerializer):
    """Serializer for classes with subject info for teacher"""
    subject_name = serializers.SerializerMethodField()
    subject_id = serializers.SerializerMethodField()
    period = serializers.SerializerMethodField()
    room = serializers.SerializerMethodField()
    students_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'numeric_level',
                  'subject_name', 'subject_id', 'period', 'room', 'students_count']
    
    def get_subject_name(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            return allocation.subject.area_name if allocation and allocation.subject else None
        return None
    
    def get_subject_id(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            return str(allocation.subject.id) if allocation and allocation.subject else None
        return None
    
    def get_period(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            from cbe_app.models import Timetable
            timetable = Timetable.objects.filter(
                class_id=obj,
                teacher=request.user,
                is_active=True
            ).first()
            if timetable:
                return f"Period {timetable.period}"
        return None
    
    def get_room(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            from cbe_app.models import Timetable
            timetable = Timetable.objects.filter(
                class_id=obj,
                teacher=request.user,
                is_active=True
            ).first()
            return timetable.room if timetable else None
        return None
    
    def get_students_count(self, obj):
        return obj.current_students.filter(status='Active').count()


class StudentForAttendanceSerializer(serializers.ModelSerializer):
    """Serializer for student list in attendance"""
    full_name = serializers.SerializerMethodField()
    attendance_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name', 
                  'gender', 'attendance_rate']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_attendance_rate(self, obj):
        """Calculate student's overall attendance rate for current term"""
        current_term = Term.objects.filter(is_current=True).first()
        if current_term:
            sessions = AttendanceSession.objects.filter(
                session_date__gte=current_term.start_date,
                session_date__lte=current_term.end_date
            )
            if sessions.exists():
                present_count = obj.attendance_records.filter(
                    session__in=sessions,
                    attendance_status='Present'
                ).count()
                total_sessions = sessions.count()
                if total_sessions > 0:
                    return round((present_count / total_sessions) * 100)
        return 0


class AttendanceRecordSerializer(serializers.Serializer):
    """Serializer for individual attendance record submission"""
    student_id = serializers.UUIDField()
    class_id = serializers.UUIDField(required=False)
    subject_id = serializers.UUIDField(required=False)
    date = serializers.DateField()
    period = serializers.ChoiceField(choices=['morning', 'afternoon', 'full'])
    status = serializers.ChoiceField(choices=['present', 'absent'])


class BulkAttendanceSaveSerializer(serializers.Serializer):
    """Serializer for bulk attendance save"""
    records = AttendanceRecordSerializer(many=True)
    
    def validate(self, data):
        if not data.get('records'):
            raise serializers.ValidationError("At least one attendance record is required")
        return data


class AttendanceHistorySerializer(serializers.Serializer):
    """Serializer for attendance history"""
    date = serializers.DateField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    percentage = serializers.FloatField()


class AttendanceStatsSerializer(serializers.Serializer):
    """Serializer for attendance statistics"""
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    total = serializers.IntegerField()
    percentage = serializers.FloatField()


class DailyAttendanceRecordSerializer(serializers.ModelSerializer):
    """Serializer for daily attendance records"""
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    admission_no = serializers.CharField(source='student.admission_no', read_only=True)
    status_display = serializers.CharField(source='get_attendance_status_display', read_only=True)
    
    class Meta:
        model = StudentAttendance
        fields = ['id', 'student', 'student_name', 'admission_no', 'attendance_status', 
                  'status_display', 'remarks', 'late_minutes']


class AttendanceSessionSerializer(serializers.ModelSerializer):
    """Serializer for attendance session"""
    class_name = serializers.CharField(source='class_id.class_name', read_only=True)
    subject_name = serializers.CharField(source='subject.area_name', read_only=True)
    conducted_by_name = serializers.CharField(source='conducted_by.get_full_name', read_only=True)
    records = DailyAttendanceRecordSerializer(source='attendance_records', many=True, read_only=True)
    
    class Meta:
        model = AttendanceSession
        fields = ['id', 'session_date', 'session_type', 'class_id', 'class_name',
                  'subject', 'subject_name', 'period_number', 'start_time', 'end_time',
                  'conducted_by', 'conducted_by_name', 'records']