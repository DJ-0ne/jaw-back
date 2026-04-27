# serializers.py - Add to your existing serializers file

from rest_framework import serializers
from django.db.models import Avg, Count, Sum, Q, F, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
from ...models import (
    Class, Student, Staff, LearningArea, StudentAttendance, 
    AttendanceSession, SummativeRating, SummativeAssessment,
    Term, AcademicYear, TermlySummary, User, Competency,
    StudentPortfolio, ClassSubjectAllocation, ExamResult,
    Exam, GradingScale, StudentEnrollment
)


# ==================== CLASS SERIALIZERS ====================

class ClassListSerializer(serializers.ModelSerializer):
    """Serializer for class list view - Teacher's own classes"""
    class_teacher_name = serializers.SerializerMethodField()
    current_students = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'capacity', 
                  'numeric_level', 'class_teacher_name', 'current_students', 'subject']
    
    def get_class_teacher_name(self, obj):
        if obj.class_teacher and hasattr(obj.class_teacher, 'staff_profile'):
            staff = obj.class_teacher.staff_profile
            return f"{staff.first_name} {staff.last_name}"
        return None
    
    def get_current_students(self, obj):
        return obj.current_students.filter(status='Active').count()
    
    def get_subject(self, obj):
        """Get subject taught by this teacher in this class"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            # Find the subject this teacher teaches in this class
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            if allocation and allocation.subject:
                return allocation.subject.area_name
        return None


class SubjectClassSerializer(serializers.ModelSerializer):
    """Serializer for subject classes - Classes where teacher teaches a subject"""
    students_count = serializers.SerializerMethodField()
    period = serializers.SerializerMethodField()
    room = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    subject_id = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'stream', 'subject_id', 
                  'subject_name', 'students_count', 'period', 'room', 'numeric_level']
    
    def get_students_count(self, obj):
        return obj.current_students.filter(status='Active').count()
    
    def get_subject_id(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            if allocation and allocation.subject:
                return str(allocation.subject.id)
        return None
    
    def get_subject_name(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            if allocation and allocation.subject:
                return allocation.subject.area_name
        return None
    
    def get_period(self, obj):
        """Get timetable period for this class and subject"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            if allocation and allocation.subject:
                from ...models import Timetable
                timetable = Timetable.objects.filter(
                    class_id=obj,
                    subject=allocation.subject,
                    is_active=True,
                    academic_year=self.context.get('academic_year', ''),
                    term=self.context.get('term', '')
                ).first()
                if timetable:
                    return f"Period {timetable.period}"
        return None
    
    def get_room(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            allocation = ClassSubjectAllocation.objects.filter(
                class_id=obj,
                teacher=request.user,
                academic_year=self.context.get('academic_year', '')
            ).first()
            if allocation and allocation.subject:
                from ...models import Timetable
                timetable = Timetable.objects.filter(
                    class_id=obj,
                    subject=allocation.subject,
                    is_active=True,
                    academic_year=self.context.get('academic_year', ''),
                    term=self.context.get('term', '')
                ).first()
                return timetable.room if timetable else None
        return None


class StudentCompetencySerializer(serializers.Serializer):
    """Serializer for student competency levels"""
    collaboration = serializers.IntegerField()
    communication = serializers.IntegerField()
    critical_thinking = serializers.IntegerField()
    creativity = serializers.IntegerField()


class StudentListSerializer(serializers.ModelSerializer):
    """Serializer for student list in class"""
    full_name = serializers.SerializerMethodField()
    current_score = serializers.SerializerMethodField()
    target_level = serializers.SerializerMethodField()
    competency_levels = serializers.SerializerMethodField()
    attendance_rate = serializers.SerializerMethodField()
    last_assessment = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name',
                  'gender', 'current_score', 'target_level', 'competency_levels',
                  'attendance_rate', 'last_assessment']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_current_score(self, obj):
        """Get student's current average score across all subjects"""
        current_term = self.context.get('current_term')
        if current_term:
            summaries = obj.termly_summaries.filter(term=current_term)
            if summaries.exists():
                avg_internal = summaries.aggregate(avg=Avg('final_internal_value'))['avg']
                if avg_internal:
                    return round(float(avg_internal) / 8 * 100)
        
        # Get from exam results
        current_exam = Exam.objects.filter(
            status='published',
            academic_year=self.context.get('academic_year'),
            term=self.context.get('term')
        ).first()
        if current_exam:
            results = obj.exam_results.filter(exam=current_exam)
            if results.exists():
                avg = results.aggregate(avg=Avg('percentage'))['avg']
                if avg:
                    return round(float(avg))
        
        return 0
    
    def get_target_level(self, obj):
        """Get student's target level from academic history"""
        # Try to get from termly summary target
        current_term = self.context.get('current_term')
        if current_term:
            summary = obj.termly_summaries.filter(term=current_term).first()
            if summary and summary.promotion_status:
                if summary.promotion_status == 'Promoted':
                    return 'EE'  # or get from grade
        return 'ME'  # Default
    
    def get_competency_levels(self, obj):
        """Get student's competency levels from portfolio"""
        result = {
            'collaboration': 3,
            'communication': 3,
            'critical_thinking': 3,
            'creativity': 3
        }
        
        current_term = self.context.get('current_term')
        academic_year = self.context.get('academic_year_obj')
        
        if current_term and academic_year:
            portfolios = StudentPortfolio.objects.filter(
                student=obj,
                term=current_term,
                academic_year=academic_year
            ).select_related('competency')
            
            for portfolio in portfolios:
                comp_name = portfolio.competency.competency_statement.lower()
                if 'collaboration' in comp_name:
                    result['collaboration'] = portfolio.sub_level or 3
                elif 'communication' in comp_name:
                    result['communication'] = portfolio.sub_level or 3
                elif 'critical' in comp_name:
                    result['critical_thinking'] = portfolio.sub_level or 3
                elif 'creativ' in comp_name:
                    result['creativity'] = portfolio.sub_level or 3
        
        return result
    
    def get_attendance_rate(self, obj):
        """Get student's attendance rate for current term"""
        current_term = self.context.get('current_term')
        if current_term:
            sessions = AttendanceSession.objects.filter(
                session_date__gte=current_term.start_date,
                session_date__lte=current_term.end_date,
                class_id=self.context.get('class_obj')
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
    
    def get_last_assessment(self, obj):
        """Get student's last assessment score"""
        # Get from exam results
        last_result = obj.exam_results.order_by('-marked_at').first()
        if last_result:
            return round(float(last_result.marks_obtained))
        
        # Get from summative ratings
        last_rating = obj.summative_ratings.order_by('-rated_at').first()
        if last_rating:
            return int(last_rating.internal_value * 12.5)  # Convert 1-8 to percentage
        
        return 0


class SubjectMasterySerializer(serializers.Serializer):
    """Serializer for subject mastery data"""
    subject = serializers.CharField()
    score = serializers.IntegerField()
    class_avg = serializers.IntegerField()
    rank = serializers.IntegerField()


class TopPerformerSerializer(serializers.Serializer):
    """Serializer for top performer data"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    score = serializers.IntegerField()
    improvement = serializers.CharField()


class MostImprovedSerializer(serializers.Serializer):
    """Serializer for most improved student data"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    improvement = serializers.IntegerField()
    from_score = serializers.IntegerField()
    to_score = serializers.IntegerField()


class ClassAnalyticsSerializer(serializers.Serializer):
    """Serializer for class analytics data"""
    mean_score = serializers.FloatField()
    class_rank = serializers.IntegerField()
    total_streams = serializers.IntegerField()
    performance_distribution = serializers.DictField()
    subject_mastery = SubjectMasterySerializer(many=True)
    top_performers = TopPerformerSerializer(many=True)
    most_improved = MostImprovedSerializer(many=True)


# ==================== ATTENDANCE SERIALIZERS ====================

class AttendanceRecordSerializer(serializers.Serializer):
    """Serializer for attendance record entry"""
    student_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['present', 'absent', 'late', 'excused'])
    remarks = serializers.CharField(required=False, allow_blank=True)


class AttendanceFormSerializer(serializers.Serializer):
    """Serializer for attendance form submission"""
    date = serializers.DateField()
    period = serializers.ChoiceField(choices=['morning', 'afternoon', 'full'])
    class_id = serializers.UUIDField(required=False)
    subject_id = serializers.UUIDField(required=False)
    records = AttendanceRecordSerializer(many=True)
    
    def validate(self, data):
        if not data.get('class_id') and not data.get('subject_id'):
            raise serializers.ValidationError("Either class_id or subject_id is required")
        return data


class StudentAttendanceSerializer(serializers.ModelSerializer):
    """Serializer for student attendance records"""
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    admission_no = serializers.CharField(source='student.admission_no', read_only=True)
    
    class Meta:
        model = StudentAttendance
        fields = ['id', 'student', 'student_name', 'admission_no', 'attendance_status',
                  'check_in_time', 'check_out_time', 'late_minutes', 'remarks']


# ==================== ASSESSMENT SERIALIZERS ====================

class AssessmentScoreSerializer(serializers.Serializer):
    """Serializer for individual assessment score"""
    student_id = serializers.UUIDField()
    score = serializers.IntegerField(min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)


class AssessmentFormSerializer(serializers.Serializer):
    """Serializer for assessment form submission"""
    title = serializers.CharField(max_length=200)
    max_score = serializers.IntegerField(min_value=1, max_value=1000)
    date = serializers.DateField()
    class_id = serializers.UUIDField()
    subject = serializers.CharField(max_length=100)
    scores = AssessmentScoreSerializer(many=True)
    
    def validate_scores(self, value):
        if not value:
            raise serializers.ValidationError("At least one score is required")
        return value


# ==================== EVIDENCE SERIALIZERS ====================

class EvidenceUploadSerializer(serializers.Serializer):
    """Serializer for evidence upload"""
    student_id = serializers.UUIDField()
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    file = serializers.FileField()
    
    def validate_file(self, value):
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf', 
                        'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(f"Unsupported file type. Allowed: {', '.join(allowed_types)}")
        
        if value.size > 10 * 1024 * 1024:  # 10MB
            raise serializers.ValidationError("File size too large. Maximum 10MB")
        return value


class StudentPortfolioSerializer(serializers.ModelSerializer):
    """Serializer for student portfolio/evidence"""
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    competency_name = serializers.CharField(source='competency.competency_statement', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentPortfolio
        fields = ['id', 'student', 'student_name', 'competency', 'competency_name',
                  'rating', 'sub_level', 'percentage', 'evidence_url', 'file_url',
                  'evidence_type', 'teacher_comment', 'assessed_by', 'assessed_date', 
                  'created_at', 'updated_at']
    
    def get_file_url(self, obj):
        if obj.evidence_url:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.evidence_url)
        return None