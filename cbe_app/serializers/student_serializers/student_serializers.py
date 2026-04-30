from rest_framework import serializers
from cbe_app.models import Student, StudentFeeInvoice, FeeTransaction, StudentAttendance, DisciplineIncident, TermlySummary, Class, User
from datetime import date, datetime

class StudentProfileSerializer(serializers.ModelSerializer):
    """Serializer for student profile"""
    full_name = serializers.SerializerMethodField()
    current_class_name = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            'id', 'admission_no', 'student_uid', 'first_name', 'middle_name', 'last_name',
            'full_name', 'date_of_birth', 'age', 'gender', 'nationality', 'religion',
            'address', 'city', 'country', 'phone', 'email', 'current_class', 'current_class_name',
            'admission_date', 'admission_type', 'status',
            'father_name', 'father_phone', 'father_email', 'mother_name', 'mother_phone',
            'mother_email', 'guardian_name', 'guardian_relation', 'guardian_phone',
            'guardian_email', 'guardian_address', 'medical_conditions', 'allergies',
            'emergency_contact', 'emergency_contact_name'
        ]
        read_only_fields = ['id', 'admission_no', 'student_uid', 'created_at', 'updated_at']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_current_class_name(self, obj):
        return obj.current_class.class_name if obj.current_class else None
    
    def get_age(self, obj):
        if obj.date_of_birth:
            today = date.today()
            return today.year - obj.date_of_birth.year - ((today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day))
        return None

class FeeSummarySerializer(serializers.Serializer):
    """Serializer for fee summary"""
    total_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_days = serializers.IntegerField()
    academic_year = serializers.CharField()
    term = serializers.CharField()
    recent_transactions = serializers.ListField(child=serializers.DictField(), required=False)

class FeeTransactionSerializer(serializers.ModelSerializer):
    """Serializer for fee transactions"""
    class Meta:
        model = FeeTransaction
        fields = [
            'transaction_no', 'payment_date', 'payment_mode', 'amount',
            'amount_kes', 'status', 'payment_reference', 'receipt_printed'
        ]

class AttendanceRecordSerializer(serializers.ModelSerializer):
    """Serializer for attendance records"""
    subject_name = serializers.SerializerMethodField()
    session_type = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentAttendance
        fields = [
            'id', 'attendance_status', 'date', 'subject_name', 'session_type',
            'check_in_time', 'check_out_time', 'late_minutes', 'remarks'
        ]
    
    def get_subject_name(self, obj):
        if obj.session and obj.session.subject:
            return obj.session.subject.area_name
        return 'General'
    
    def get_session_type(self, obj):
        if obj.session:
            return obj.session.session_type
        return 'Full Day'

class DisciplineRecordSerializer(serializers.ModelSerializer):
    """Serializer for discipline records"""
    category_name = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    
    class Meta:
        model = DisciplineIncident
        fields = [
            'id', 'incident_code', 'incident_date', 'description', 'category_name',
            'severity', 'points_awarded', 'status', 'location', 'resolution'
        ]
    
    def get_category_name(self, obj):
        return obj.category.category_name if obj.category else 'General'
    
    def get_severity(self, obj):
        return obj.category.severity_level if obj.category else 'Medium'

class PerformanceSubjectSerializer(serializers.Serializer):
    """Serializer for individual subject performance"""
    learning_area = serializers.CharField()
    score = serializers.DecimalField(max_digits=5, decimal_places=2)
    grade = serializers.CharField()
    rating = serializers.CharField()
    trend = serializers.CharField(required=False, allow_blank=True)

class AcademicPerformanceSerializer(serializers.Serializer):
    """Serializer for academic performance"""
    term = serializers.CharField()
    academic_year = serializers.CharField()
    subjects = PerformanceSubjectSerializer(many=True)
    overall_grade = serializers.CharField()
    overall_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    class_position = serializers.IntegerField(required=False)
    total_students = serializers.IntegerField(required=False)

class TimetableSlotSerializer(serializers.Serializer):
    """Serializer for timetable slots"""
    day = serializers.IntegerField()
    day_name = serializers.CharField()
    period = serializers.IntegerField()
    subject = serializers.CharField()
    teacher = serializers.CharField()
    room = serializers.CharField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()