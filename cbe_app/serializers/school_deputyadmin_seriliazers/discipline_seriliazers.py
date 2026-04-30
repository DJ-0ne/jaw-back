from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
import uuid
from cbe_app.models import (
    DisciplineIncident, DisciplineCategory, StudentDisciplinePoints,
    ConductRecord, InterventionProgram, InterventionEnrollment,
    CounselingSession, Suspension, DisciplineReport, Student, User
)


# ---------- Discipline Category ----------
class DisciplineCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DisciplineCategory
        fields = ['id', 'category_code', 'category_name', 'severity_level', 'default_points', 'is_active']
        read_only_fields = ['category_code']


class DisciplineCategoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisciplineCategory
        fields = ['category_name', 'severity_level', 'default_points', 'is_active']

    def create(self, validated_data):
        # Generate unique category_code (model requires it)
        date_part = timezone.now().strftime('%Y%m%d')
        random_part = uuid.uuid4().hex[:4].upper()
        validated_data['category_code'] = f"CAT-{date_part}-{random_part}"
        return super().create(validated_data)


# ---------- Student Discipline Points ----------
class StudentDisciplinePointsSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    
    class Meta:
        model = StudentDisciplinePoints
        fields = ['id', 'student', 'student_name', 'academic_year', 'term', 
                  'total_points', 'warnings_count', 'suspensions_count', 
                  'last_incident_date', 'current_status', 'remarks']


# ---------- Discipline Incidents ----------
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
    incident_date = serializers.DateField(required=False)

    class Meta:
        model = DisciplineIncident
        fields = ['student', 'category', 'description', 'location', 'witnesses',
                  'evidence_urls', 'incident_date', 'incident_time']

    def create(self, validated_data):
        validated_data['reported_by'] = self.context['request'].user
        validated_data.setdefault('incident_date', timezone.now().date())
        category = validated_data.get('category')
        validated_data['points_awarded'] = category.default_points if category else 0
        return super().create(validated_data)


# ---------- Conduct Records ----------
class ConductRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    grade = serializers.CharField(source='student.current_class.class_name', read_only=True, allow_null=True)
    
    class Meta:
        model = ConductRecord
        fields = ['id', 'student', 'student_name', 'grade', 'academic_year', 'term',
                  'conduct_grade', 'merits', 'demerits', 'total_points', 'status', 'remarks', 'last_updated']


# ---------- Intervention Program ----------
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
        extra_kwargs = {
            'max_students': {'required': False, 'default': 0},
            'description':     {'required': False, 'default': ''},
            'facilitator':     {'required': False, 'default': ''},
        }
    
    def create(self, validated_data):
        # Generate unique program_code
        date_part = timezone.now().strftime('%Y%m%d')
        random_part = uuid.uuid4().hex[:4].upper()
        validated_data['program_code'] = f"PRG-{date_part}-{random_part}"
        
        # Calculate end_date from start_date + duration_weeks
        start_date = validated_data.get('start_date')
        weeks = validated_data.get('duration_weeks', 4)
        if start_date:
            validated_data['end_date'] = start_date + timedelta(weeks=weeks)
        else:
            validated_data['end_date'] = timezone.now().date() + timedelta(weeks=weeks)
        
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


# ---------- Counseling Session ----------
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
        extra_kwargs = {
            'duration_minutes':  {'required': False, 'default': 30},
            'session_time':      {'required': False, 'default': ''},
            'notes':             {'required': False, 'default': ''},
            'follow_up_needed':  {'required': False, 'default': False},
            'follow_up_date':    {'required': False, 'default': None},
        }
    
    def create(self, validated_data):
        # Generate unique session_code
        date_part = timezone.now().strftime('%Y%m%d')
        random_part = uuid.uuid4().hex[:4].upper()
        validated_data['session_code'] = f"SES-{date_part}-{random_part}"
        
        validated_data['counselor'] = self.context['request'].user
        return super().create(validated_data)


# ---------- Suspension ----------
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


# ---------- Stats ----------
class DisciplineStatsSerializer(serializers.Serializer):
    totalCases = serializers.IntegerField()
    activeCases = serializers.IntegerField()
    resolvedCases = serializers.IntegerField()
    totalInterventions = serializers.IntegerField()
    activeSuspensions = serializers.IntegerField()
    totalCounseling = serializers.IntegerField()