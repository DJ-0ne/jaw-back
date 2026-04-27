from rest_framework import serializers
from django.utils import timezone
from cbe_app.models import (
    DisciplineIncident, DisciplineCategory, StudentDisciplinePoints,
    ConductRecord, InterventionProgram, InterventionEnrollment,
    CounselingSession, Suspension, DisciplineReport, Student, User
)


class DisciplineCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DisciplineCategory
        fields = ['id', 'category_code', 'category_name', 'severity_level', 'default_points', 'is_active']


class StudentDisciplinePointsSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    
    class Meta:
        model = StudentDisciplinePoints
        fields = ['id', 'student', 'student_name', 'academic_year', 'term', 
                  'total_points', 'warnings_count', 'suspensions_count', 
                  'last_incident_date', 'current_status', 'remarks']


class DisciplineIncidentListSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission = serializers.CharField(source='student.admission_no', read_only=True)
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    severity = serializers.CharField(source='category.severity_level', read_only=True)
    grade = serializers.CharField(source='student.current_class.class_name', read_only=True, allow_null=True)
    
    class Meta:
        model = DisciplineIncident
        fields = ['id', 'incident_code', 'student', 'student_name', 'student_admission', 'grade',
                  'category', 'category_name', 'severity', 'incident_date', 'description',
                  'status', 'points_awarded', 'reported_by']


class DisciplineIncidentDetailSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission = serializers.CharField(source='student.admission_no', read_only=True)
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    severity = serializers.CharField(source='category.severity_level', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.get_full_name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True, allow_null=True)
    closed_by_name = serializers.CharField(source='closed_by.get_full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = DisciplineIncident
        fields = '__all__'


class DisciplineIncidentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisciplineIncident
        fields = ['student', 'category', 'description', 'location', 'witnesses', 
                  'evidence_urls', 'incident_date', 'incident_time']
    
    def create(self, validated_data):
        validated_data['reported_by'] = self.context['request'].user
        validated_data['incident_code'] = None
        return super().create(validated_data)


class ConductRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    grade = serializers.CharField(source='student.current_class.class_name', read_only=True, allow_null=True)
    
    class Meta:
        model = ConductRecord
        fields = ['id', 'student', 'student_name', 'grade', 'academic_year', 'term',
                  'conduct_grade', 'merits', 'demerits', 'total_points', 'status', 'remarks', 'last_updated']


class InterventionProgramSerializer(serializers.ModelSerializer):
    enrolled_count = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = InterventionProgram
        fields = ['id', 'program_code', 'program_name', 'program_type', 'description',
                  'duration_weeks', 'facilitator', 'max_students', 'status',
                  'start_date', 'end_date', 'enrolled_count', 'progress_percentage']
    
    def get_enrolled_count(self, obj):
        return obj.enrollments.filter(status='Active').count()
    
    def get_progress_percentage(self, obj):
        enrollments = obj.enrollments.filter(status='Active')
        if not enrollments.exists():
            return 0
        total_progress = sum(e.progress_percentage for e in enrollments)
        return int(total_progress / enrollments.count())


class InterventionProgramCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterventionProgram
        fields = ['program_name', 'program_type', 'description', 'duration_weeks',
                  'facilitator', 'max_students', 'start_date']
    
    def create(self, validated_data):
        validated_data['program_code'] = None
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class CounselingSessionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    counselor_name = serializers.CharField(source='counselor.get_full_name', read_only=True)
    grade = serializers.CharField(source='student.current_class.class_name', read_only=True, allow_null=True)
    
    class Meta:
        model = CounselingSession
        fields = ['id', 'session_code', 'student', 'student_name', 'grade', 'counselor', 'counselor_name',
                  'session_type', 'session_date', 'session_time', 'duration_minutes',
                  'status', 'notes', 'follow_up_needed', 'follow_up_date']


class CounselingSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CounselingSession
        fields = ['student', 'session_type', 'session_date', 'session_time', 
                  'duration_minutes', 'notes', 'follow_up_needed', 'follow_up_date']
    
    def create(self, validated_data):
        validated_data['counselor'] = self.context['request'].user
        validated_data['session_code'] = None
        return super().create(validated_data)


class SuspensionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    grade = serializers.CharField(source='student.current_class.class_name', read_only=True, allow_null=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)
    
    class Meta:
        model = Suspension
        fields = ['id', 'suspension_code', 'student', 'student_name', 'grade', 'incident',
                  'suspension_type', 'start_date', 'end_date', 'total_days', 'reason',
                  'assigned_by', 'assigned_by_name', 'status', 'parent_notified',
                  'parent_notification_date', 'reentry_meeting_date', 'notes']


class DisciplineStatsSerializer(serializers.Serializer):
    totalCases = serializers.IntegerField()
    activeCases = serializers.IntegerField()
    resolvedCases = serializers.IntegerField()
    totalInterventions = serializers.IntegerField()
    activeSuspensions = serializers.IntegerField()
    totalCounseling = serializers.IntegerField()