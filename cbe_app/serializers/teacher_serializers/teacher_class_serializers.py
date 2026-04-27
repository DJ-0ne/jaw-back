from rest_framework import serializers
from django.db.models import Avg
from cbe_app.models import (
    Class, Student, Staff, ClassSubjectAllocation, 
    Term, AttendanceSession, StudentAttendance, LearningArea,
    Exam, ExamResult, StudentPortfolio, Competency, AcademicYear
)


class ClassListSerializer(serializers.ModelSerializer):
    class_teacher_name = serializers.SerializerMethodField()
    students_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'numeric_level', 
                  'capacity', 'class_teacher_name', 'students_count']
    
    def get_class_teacher_name(self, obj):
        if obj.class_teacher:
            return f"{obj.class_teacher.first_name} {obj.class_teacher.last_name}"
        return "Not Assigned"
    
    def get_students_count(self, obj):
        return obj.current_students.filter(status='Active').count()


class SubjectClassSerializer(serializers.ModelSerializer):
    class_id = serializers.UUIDField(source='class_id.id', read_only=True)
    class_name = serializers.CharField(source='class_id.class_name', read_only=True)
    class_code = serializers.CharField(source='class_id.class_code', read_only=True)
    stream = serializers.CharField(source='class_id.stream', read_only=True)
    numeric_level = serializers.IntegerField(source='class_id.numeric_level', read_only=True)
    subject_name = serializers.CharField(source='subject.area_name', read_only=True)
    subject_id = serializers.UUIDField(source='subject.id', read_only=True)
    students_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassSubjectAllocation
        fields = ['id', 'class_id', 'class_name', 'class_code', 'stream', 
                  'numeric_level', 'subject_name', 'subject_id', 'students_count']
    
    def get_students_count(self, obj):
        return obj.class_id.current_students.filter(status='Active').count()


class StudentListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    current_score = serializers.SerializerMethodField()
    attendance_rate = serializers.SerializerMethodField()
    last_assessment = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name',
                  'gender', 'current_score', 'attendance_rate', 'last_assessment']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_current_score(self, obj):
        current_term = Term.objects.filter(is_current=True).first()
        if current_term:
            summaries = obj.termly_summaries.filter(term=current_term)
            if summaries.exists():
                avg_internal = summaries.aggregate(avg=Avg('final_internal_value'))['avg']
                if avg_internal:
                    return round(float(avg_internal) / 8 * 100)
        return 0
    
    def get_attendance_rate(self, obj):
        current_term = Term.objects.filter(is_current=True).first()
        if current_term:
            sessions = AttendanceSession.objects.filter(
                session_date__gte=current_term.start_date,
                session_date__lte=current_term.end_date
            )
            total_sessions = sessions.count()
            if total_sessions > 0:
                present_count = obj.attendance_records.filter(
                    session__in=sessions,
                    attendance_status='Present'
                ).count()
                return round((present_count / total_sessions) * 100)
        return 0
    
    def get_last_assessment(self, obj):
        last_result = obj.exam_results.order_by('-marked_at').first()
        if last_result:
            return round(float(last_result.marks_obtained))
        return 0


# Attendance Serializers
class AttendanceRecordSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['present', 'absent', 'late', 'excused'])
    remarks = serializers.CharField(required=False, allow_blank=True)


class AttendanceSubmitSerializer(serializers.Serializer):
    date = serializers.DateField()
    period = serializers.ChoiceField(choices=['morning', 'afternoon', 'full'])
    class_id = serializers.UUIDField(required=False, allow_null=True)
    subject_id = serializers.UUIDField(required=False, allow_null=True)
    records = AttendanceRecordSerializer(many=True)


# Assessment Serializers
class AssessmentScoreSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    score = serializers.IntegerField(min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)


class AssessmentSubmitSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    max_score = serializers.IntegerField(min_value=1, max_value=1000)
    date = serializers.DateField()
    class_id = serializers.UUIDField()
    subject = serializers.CharField(max_length=100)
    scores = AssessmentScoreSerializer(many=True)


# Evidence Serializers
class EvidenceUploadSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    description = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField()


class StudentPortfolioSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    
    class Meta:
        model = StudentPortfolio
        fields = ['id', 'student', 'student_name', 'evidence_url', 'evidence_type', 
                  'teacher_comment', 'assessed_date']