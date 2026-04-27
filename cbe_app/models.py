# models.py
import random
import string
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone
import datetime
from django.core.exceptions import ValidationError
import uuid
from decimal import Decimal
# ==================== UTILITY FUNCTIONS ====================
def generate_inv_id():
    return f"INV-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def generate_txn_id():
    return f"TXN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def generate_inc_id():
    return f"INC-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

def generate_assessment_code():
    return f"ASS-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def generate_report_id():
    return f"REP-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

class BaseModel(models.Model):
    """Abstract base model with UUID as primary key"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ==================== DEPARTMENT MANAGEMENT ====================

class Department(BaseModel):
    """School Departments - Academic, Sports, Administrative, etc."""
    
    department_code = models.CharField(max_length=20, unique=True)
    department_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    department_type = models.CharField(max_length=50, blank=True, null=True)  # e.g., Academic, Sports, Admin
    
    # Subjects under this department (for academic departments)
    subjects = models.ManyToManyField('LearningArea', blank=True, related_name='departments')
    
    # Department Head (Staff member who leads this department)
    head_of_department = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True, related_name='headed_department')
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['department_name']
    
    def __str__(self):
        return self.department_name

class DepartmentStaffAssignment(BaseModel):
    """Track which staff belong to which department"""
    
    ROLE_CHOICES = [
        ('head', 'Head of Department'),
        ('deputy_head', 'Deputy Head'),
        ('member', 'Member'),
    ]
    
    staff = models.ForeignKey('Staff', on_delete=models.CASCADE, related_name='department_assignments')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='staff_assignments')
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    
    # For teachers: which subjects they teach in this department
    teaching_subjects = models.ManyToManyField('LearningArea', blank=True)
    
    # For sports: which sports they handle (simple text field)
    sports_responsibility = models.CharField(max_length=100, blank=True, null=True)
    
    # Assignment tracking
    assigned_date = models.DateField(default=timezone.now)  # Add this field
    end_date = models.DateField(blank=True, null=True)  # Optional: when assignment ends
    
    # Is this their primary department? (A staff can belong to multiple departments but one primary)
    is_primary = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['staff', 'department']
    
    def __str__(self):
        return f"{self.staff.full_name} - {self.department.department_name}"
    
    def save(self, *args, **kwargs):
        # If this staff is marked as Head, update the Department model
        if self.role == 'head' and self.is_active:
            self.department.head_of_department = self.staff
            self.department.save()
        super().save(*args, **kwargs)
# ==================== USER MANAGEMENT ====================

class User(AbstractUser):
    # Override the default id with UUID as primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Human-readable user code for display purposes
    user_code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    
    ROLE_CHOICES = [
        ('system_admin', 'System Administrator'),
        ('principal', 'Principal'),
        ('deputy_principal', 'Deputy Principal'),
        ('director_studies', 'Director of Studies'),
        ('registrar', 'Registrar'),
        ('bursar', 'Bursar'),
        ('accountant', 'Accountant'),
        ('teacher', 'Teacher'),
        ('hr_manager', 'HR Manager'),
        ('student', 'Student'),
    ]
    
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True, null=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=32, blank=True, null=True)
    last_password_change = models.DateTimeField(default=timezone.now)
    failed_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['is_active'], name='idx_active_users'),
            models.Index(fields=['user_code']),
            models.Index(fields=['email']),  # Add email index for faster lookups
        ]
    
    def save(self, *args, **kwargs):
        # Generate user_code only if not set (for new users)
        if not self.user_code:
            date_part = timezone.now().strftime('%Y%m%d')
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.user_code = f"USR-{date_part}-{random_part}"
        
        # Ensure email is always lowercase for consistency
        if self.email:
            self.email = self.email.lower()
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.username} ({self.user_code})"
    
    @property
    def is_locked(self):
        """Check if account is currently locked"""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False
    @property
    def department(self):
        """Get user's primary department name (only for staff)"""
        if hasattr(self, 'staff_profile'):
            primary_dept = self.staff_profile.department_assignments.filter(is_primary=True, is_active=True).first()
            if primary_dept:
                return primary_dept.department.department_name
        return None

    @property
    def department_object(self):
        """Get the actual Department object"""
        if hasattr(self, 'staff_profile'):
            primary_dept = self.staff_profile.department_assignments.filter(is_primary=True, is_active=True).first()
            if primary_dept:
                return primary_dept.department
        return None

class UserSession(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    access_token = models.TextField()
    refresh_token = models.TextField()
    client_ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    device_fingerprint = models.CharField(max_length=64, blank=True, null=True)
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['access_token']),
            models.Index(fields=['expires_at']),
        ]

class PasswordHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    password_hash = models.CharField(max_length=255)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='changed_passwords')
    
    
# ==================== OTP MANAGEMENT ====================

class OTPCode(BaseModel):
    """OTP codes for force logout and password reset verification"""
    
    OTP_TYPE_CHOICES = [
        ('force_logout', 'Force Logout Verification'),
        ('password_reset', 'Password Reset Verification'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    otp_code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=20, choices=OTP_TYPE_CHOICES)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['otp_code']),
            models.Index(fields=['otp_type']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.otp_code} - {self.user.email} - {self.otp_type}"
    
    def is_valid(self):
        """Check if OTP is still valid (not used and not expired)"""
        return not self.is_used and self.expires_at > timezone.now()
    
# ==================== STUDENT MANAGEMENT ====================
class Student(BaseModel):
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Graduated', 'Graduated'),
        ('Transferred', 'Transferred'),
        ('Inactive', 'Inactive'),
        ('Withdrawn', 'Withdrawn'),
        ('Suspended', 'Suspended'),
    ]
    ADMISSION_TYPE_CHOICES = [
        ('Regular', 'Regular'),
        ('Transfer', 'Transfer'),
        ('Re-admission', 'Re-admission'),
    ]
    
    # Core Information
    admission_no = models.CharField(max_length=30, unique=True)
    student_uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # NEMIS Compliance Fields (NEW)
    upi_number = models.CharField(max_length=50, unique=True, blank=True, null=True, 
                                   help_text="Unique Personal Identifier from NEMIS")
    knec_number = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                    help_text="KNEC registration number")
    birth_certificate_no = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                             help_text="Birth certificate number")
    
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    nationality = models.CharField(max_length=50, default='Kenya')
    religion = models.CharField(max_length=30, blank=True, null=True)
    blood_group = models.CharField(max_length=5, blank=True, null=True)
    
    # User account for portal access
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='student_profile')
    
    # Contact Information
    address = models.TextField(validators=[RegexValidator(regex='.{5,}', message='Address must be at least 10 characters')])
    city = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=50, default='Kenya')
    phone = models.CharField(max_length=20, blank=True, null=True, 
                             validators=[RegexValidator(regex=r'^\+?[0-9\s\-\(\)]+$')])
    email = models.EmailField(unique=True, blank=True, null=True)
    
    # Academic Information (REMOVED: current_section, stream, roll_number, expected_graduation_date)
    current_class = models.ForeignKey('Class', on_delete=models.SET_NULL, null=True, related_name='current_students')
    admission_date = models.DateField(default=timezone.now)
    admission_type = models.CharField(max_length=20, choices=ADMISSION_TYPE_CHOICES, default='Regular')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    status_reason = models.TextField(blank=True, null=True)
    status_changed_date = models.DateField(blank=True, null=True)
    
    # Guardian Information
    father_name = models.CharField(max_length=100, blank=True, null=True)
    father_phone = models.CharField(max_length=20, blank=True, null=True)
    father_email = models.EmailField(blank=True, null=True)
    father_occupation = models.CharField(max_length=50, blank=True, null=True)
    mother_name = models.CharField(max_length=100, blank=True, null=True)
    mother_phone = models.CharField(max_length=20, blank=True, null=True)
    mother_email = models.EmailField(blank=True, null=True)
    mother_occupation = models.CharField(max_length=50, blank=True, null=True)
    
    guardian_name = models.CharField(max_length=100)
    guardian_relation = models.CharField(max_length=30)
    guardian_phone = models.CharField(max_length=20)
    guardian_email = models.EmailField(blank=True, null=True)
    guardian_address = models.TextField(blank=True, null=True)
    
    # Medical & Emergency
    medical_conditions = models.TextField(blank=True, null=True)
    allergies = models.TextField(blank=True, null=True)
    medication = models.TextField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=20)
    emergency_contact_name = models.CharField(max_length=100)
    
    # Academic History
    previous_school = models.CharField(max_length=100, blank=True, null=True)
    previous_class = models.CharField(max_length=20, blank=True, null=True)
    transfer_certificate_no = models.CharField(max_length=50, blank=True, null=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_students')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_students')
    archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(blank=True, null=True)
    
    # Full name property
    @property
    def full_name(self):
        return f"{self.first_name} {self.middle_name + ' ' if self.middle_name else ''}{self.last_name}"
    
    @classmethod
    def get_next_admission_number(cls, prefix='ADM/JWB'):
        """
        Get the next admission number in sequence for new format: PREFIX-XXX
        """
        # Get the highest sequence number
        students = cls.objects.filter(admission_no__startswith=f"{prefix}-")
        
        highest_sequence = 0
        for student in students:
            try:
                parts = student.admission_no.split('-')
                if len(parts) == 2:
                    sequence = int(parts[1])
                    if sequence > highest_sequence:
                        highest_sequence = sequence
            except (ValueError, IndexError):
                continue
        
        next_sequence = highest_sequence + 1
        sequence_str = str(next_sequence).zfill(3)
        return f"{prefix}-{sequence_str}"
    
    class Meta:
        indexes = [
            models.Index(fields=['admission_no']),
            models.Index(fields=['current_class']),
            models.Index(fields=['status']),
            models.Index(fields=['guardian_phone']),
            models.Index(fields=['user']),
            models.Index(fields=['upi_number']),
            models.Index(fields=['knec_number']),
            models.Index(fields=['birth_certificate_no']),
        ]
    
    def __str__(self):
        return f"{self.full_name} ({self.admission_no})"

class StudentAcademicHistory(BaseModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='academic_history')
    academic_year = models.CharField(max_length=9)  # Format: 2024-2025
    class_id = models.ForeignKey('Class', on_delete=models.CASCADE)
    section = models.CharField(max_length=10, blank=True, null=True)
    stream = models.CharField(max_length=20, blank=True, null=True)
    roll_number = models.IntegerField(blank=True, null=True)
    class_teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    promoted = models.BooleanField(default=False)
    promotion_date = models.DateField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['student', 'academic_year']
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['academic_year']),
        ]

# ==================== CBE ACADEMIC STRUCTURE ====================
class AcademicYear(BaseModel):
    """Academic Year e.g., 2024-2025"""
    year_code = models.CharField(max_length=9, unique=True)  # Format: 2024-2025
    year_name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-start_date']
        unique_together = ['year_code', 'year_name']   # safetyunique_together = ['year_code', 'year_name']   # safety
    
    def __str__(self):
        return f"{self.year_name} ({self.year_code})"   # much clearer

class Term(BaseModel):
    """School Terms (1, 2, 3)"""
    TERM_CHOICES = [
        ('Term 1', 'Term 1'),
        ('Term 2', 'Term 2'),
        ('Term 3', 'Term 3'),
    ]
    
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='terms')
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['academic_year', 'term']
        ordering = ['academic_year', 'term']
    
    def __str__(self):
        return f"{self.term} - {self.academic_year.year_name}"

class LearningArea(BaseModel):
    """CBE Learning Areas (Core, Optional, Extracurricular)"""
    AREA_TYPE_CHOICES = [
        ('Core', 'Core'),
        ('Optional', 'Optional'),
        ('Extracurricular', 'Extracurricular'),
    ]
    
    area_code = models.CharField(max_length=10, unique=True)
    area_name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True, null=True)
    area_type = models.CharField(max_length=20, choices=AREA_TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['area_code']
        indexes = [
            models.Index(fields=['area_code']),
            models.Index(fields=['area_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.area_code} - {self.area_name}"

class Strand(BaseModel):
    """Strands within Learning Areas — NOW GRADE-SPECIFIC (fixes shared substrands bug)"""
    learning_area = models.ForeignKey(LearningArea, on_delete=models.CASCADE, related_name='strands')
    
    # ── NEW FIELD (this fixes the error) ──
    grade_level = models.ForeignKey(
        'GradeLevel', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='strands'
    )
    
    strand_code = models.CharField(max_length=10)
    strand_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        unique_together = ['learning_area', 'strand_code', 'grade_level']
        ordering = ['learning_area', 'grade_level', 'display_order']
        indexes = [
            models.Index(fields=['learning_area']),
            models.Index(fields=['grade_level']),
            models.Index(fields=['strand_code']),
        ]

    def __str__(self):
        grade = f" (Grade {self.grade_level.level})" if self.grade_level else ""
        return f"{self.strand_code}: {self.strand_name}{grade}"
    

class SubStrand(BaseModel):
    """Sub-Strands within Strands"""
    strand = models.ForeignKey(Strand, on_delete=models.CASCADE, related_name='substrands')
    substrand_code = models.CharField(max_length=15)
    substrand_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['strand', 'substrand_code']
        ordering = ['strand', 'display_order']
        indexes = [
            models.Index(fields=['strand']),
            models.Index(fields=['substrand_code']),
        ]
    
    def __str__(self):
        return f"{self.substrand_code}: {self.substrand_name}"


class Competency(BaseModel):
    """Specific Competencies within Sub-Strands"""
    substrand = models.ForeignKey(
        SubStrand, 
        on_delete=models.CASCADE, 
        related_name='competencies'
    )
    competency_code = models.CharField(max_length=20)
    competency_statement = models.TextField()
    performance_indicator = models.TextField(blank=True, null=True)
    
    # Existing fields
    is_core_competency = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # NEW FIELDS - This fixes the "unexpected keyword arguments" error
    core_competencies = models.JSONField(
        default=list,
        blank=True,
        null=False,
        help_text="List of KICD core competency codes e.g. ['CC01', 'CC02']"
    )
    values = models.JSONField(
        default=list,
        blank=True,
        null=False,
        help_text="List of value codes e.g. ['VAL01', 'VAL03']"
    )

    class Meta:
        unique_together = ['substrand', 'competency_code']
        ordering = ['substrand', 'display_order']
        indexes = [
            models.Index(fields=['substrand']),
            models.Index(fields=['competency_code']),
            models.Index(fields=['is_core_competency']),
        ]
    
    def __str__(self):
        return f"{self.competency_code}: {self.competency_statement[:100]}..."
    
# ==================== SUMMATIVE ASSESSMENT MODELS (CBE) ====================
class AssessmentWindow(BaseModel):
    """Pre-defined assessment windows (Opener, Mid-Term, End-Term)"""
    ASSESSMENT_TYPE_CHOICES = [
        ('Opener', 'Opener'),
        ('Mid-Term', 'Mid-Term'),
        ('End-Term', 'End-Term'),
    ]
    
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='assessment_windows')
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPE_CHOICES)
    weight_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                           validators=[MinValueValidator(0), MaxValueValidator(100)])
    open_date = models.DateField()
    close_date = models.DateField()
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['term', 'assessment_type']
        ordering = ['term', 'open_date']
    
    def __str__(self):
        return f"{self.assessment_type} - {self.term}"

class SummativeAssessment(BaseModel):
    """Summative Assessment Definition for CBE"""
    assessment_code = models.CharField(max_length=30, unique=True, default=generate_assessment_code)
    assessment_window = models.ForeignKey(AssessmentWindow, on_delete=models.CASCADE, related_name='assessments')
    class_id = models.ForeignKey('Class', on_delete=models.CASCADE, related_name='summative_assessments')
    learning_area = models.ForeignKey(LearningArea, on_delete=models.CASCADE, related_name='cbe_assessments')
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_summative_assessments')
    
    # Competencies being assessed
    competencies = models.ManyToManyField(Competency, related_name='summative_assessments', blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('Draft', 'Draft'),
        ('Published', 'Published'),
        ('Locked', 'Locked'),
        ('Archived', 'Archived'),
    ], default='Draft')
    
    class Meta:
        indexes = [
            models.Index(fields=['assessment_code']),
            models.Index(fields=['class_id']),
            models.Index(fields=['learning_area']),
        ]
    
    def __str__(self):
        return f"{self.assessment_window.assessment_type} - {self.class_id.class_name} - {self.learning_area.area_name}"

class SummativeRating(BaseModel):
    """Individual competency ratings for summative assessments"""
    RATING_CHOICES = [
        ('EE1', 'Exceptional (90-100%)'),
        ('EE2', 'Very Good (75-89%)'),
        ('ME1', 'Good (58-74%)'),
        ('ME2', 'Fair (41-57%)'),
        ('AE1', 'Needs Improvement (31-40%)'),
        ('AE2', 'Below Average (21-30%)'),
        ('BE1', 'Well Below Average (11-20%)'),
        ('BE2', 'Minimal (1-10%)'),
    ]

    RATING_VALUES = {
        'EE1': 8,
        'EE2': 7,
        'ME1': 6,
        'ME2': 5,
        'AE1': 4,
        'AE2': 3,
        'BE1': 2,
        'BE2': 1,
    }

    assessment = models.ForeignKey(SummativeAssessment, on_delete=models.CASCADE, related_name='ratings')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='summative_ratings')
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='student_ratings')

    rating = models.CharField(max_length=3, choices=RATING_CHOICES)  # ← 2 → 3
    teacher_comment = models.TextField(blank=True, null=True)

    # Auto-calculated internal value
    internal_value = models.IntegerField(default=0)

    # Audit
    rated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='given_ratings')
    rated_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['assessment', 'student', 'competency']
        indexes = [
            models.Index(fields=['assessment']),
            models.Index(fields=['student']),
            models.Index(fields=['competency']),
            models.Index(fields=['rating']),
        ]

    def save(self, *args, **kwargs):
        self.internal_value = self.RATING_VALUES.get(self.rating, 1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.admission_no} - {self.competency.competency_code}: {self.rating}"

        
class TermlySummary(BaseModel):
    """Aggregated termly results for each student per learning area"""
    PROGRESSION_STATUS_CHOICES = [
        ('Ready', 'Ready'),
        ('Needs Support', 'Needs Support'),
        ('Intervention Required', 'Intervention Required'),
    ]
    PROMOTION_STATUS_CHOICES = [
        ('Promoted', 'Promoted'),
        ('Retained', 'Retained'),
        ('Under Review', 'Under Review'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='termly_summaries')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='student_summaries')
    learning_area = models.ForeignKey(LearningArea, on_delete=models.CASCADE, related_name='student_summaries')
    
    # Weighted calculations
    opener_weighted = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    midterm_weighted = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    endterm_weighted = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    final_internal_value = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    final_rating = models.CharField(max_length=3, choices=SummativeRating.RATING_CHOICES,blank=True, null=True)    
    # Competency summary
    total_competencies = models.IntegerField(default=0)
    be_count = models.IntegerField(default=0)
    ae_count = models.IntegerField(default=0)
    me_count = models.IntegerField(default=0)
    ee_count = models.IntegerField(default=0)
    
    # Flags
    flags = models.JSONField(default=list, blank=True)  # List of flagged competencies
    progression_status = models.CharField(max_length=30, choices=PROGRESSION_STATUS_CHOICES, default='Under Review')
    promotion_status = models.CharField(max_length=30, choices=PROMOTION_STATUS_CHOICES, default='Under Review')
    
    # Teacher feedback
    teacher_comment = models.TextField(blank=True, null=True)
    promotion_recommendation = models.TextField(blank=True, null=True)
    
    # Approval
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_summaries')
    approved_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ['student', 'term', 'learning_area']
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['term']),
            models.Index(fields=['final_rating']),
        ]
    
    def calculate_final_rating(self):
        """Calculate final rating based on internal value"""
        if self.final_internal_value >= 3.5:
            return 'EE'
        elif self.final_internal_value >= 2.5:
            return 'ME'
        elif self.final_internal_value >= 1.5:
            return 'AE'
        else:
            return 'BE'
    
    def save(self, *args, **kwargs):
        # Auto-calculate final rating
        if self.final_internal_value > 0:
            self.final_rating = self.calculate_final_rating()
        super().save(*args, **kwargs)

# ==================== ACADEMICS MODULE ====================
class Class(BaseModel):
    class_code = models.CharField(max_length=10, unique=True)
    class_name = models.CharField(max_length=50)
    numeric_level = models.IntegerField()
    stream = models.CharField(max_length=20, blank=True, null=True)
    capacity = models.IntegerField(default=40, validators=[MinValueValidator(1)])
    class_teacher = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True, related_name='classes_taught')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['numeric_level']),
        ]
        ordering = ['numeric_level', 'stream']
    
    def __str__(self):
        return f"{self.class_name} ({self.class_code})"



# ==================== E-LEARNING MODELS ====================
class Course(BaseModel):
    """E-Learning Courses"""
    course_code = models.CharField(max_length=20, unique=True)
    course_title = models.CharField(max_length=200)
    learning_area = models.ForeignKey(LearningArea, on_delete=models.SET_NULL, null=True, blank=True, 
                                     related_name='elearning_courses')
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='elearning_courses', null=True, blank=True)
    
    description = models.TextField(blank=True, null=True)
    course_image = models.CharField(max_length=255, blank=True, null=True)
    
    # Course details
    credit_hours = models.IntegerField(default=0)
    duration_weeks = models.IntegerField(default=12)
    
    # Status
    is_published = models.BooleanField(default=False)
    published_date = models.DateTimeField(blank=True, null=True)
    
    # Creator
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_courses')
    
    class Meta:
        ordering = ['course_code']
    
    def __str__(self):
        return f"{self.course_code}: {self.course_title}"

class CourseModule(BaseModel):
    """Modules within a Course"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    module_title = models.CharField(max_length=200)
    module_order = models.IntegerField(default=0)
    description = models.TextField(blank=True, null=True)
    learning_objectives = models.TextField(blank=True, null=True)
    
    # Duration
    estimated_hours = models.IntegerField(default=2)
    
    # Competencies covered
    competencies = models.ManyToManyField(Competency, related_name='course_modules', blank=True)
    
    class Meta:
        ordering = ['course', 'module_order']
        unique_together = ['course', 'module_order']
    
    def __str__(self):
        return f"Module {self.module_order}: {self.module_title}"

class LearningContent(BaseModel):
    """Learning Content within Modules"""
    CONTENT_TYPE_CHOICES = [
        ('Video', 'Video'),
        ('Document', 'Document'),
        ('Presentation', 'Presentation'),
        ('Quiz', 'Quiz'),
        ('Assignment', 'Assignment'),
        ('Link', 'External Link'),
        ('Audio', 'Audio'),
        ('Image', 'Image'),
    ]
    
    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='contents')
    content_title = models.CharField(max_length=200)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_order = models.IntegerField(default=0)
    
    # Content details
    description = models.TextField(blank=True, null=True)
    content_url = models.CharField(max_length=500, blank=True, null=True)
    file_path = models.CharField(max_length=255, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)
    duration_minutes = models.IntegerField(blank=True, null=True)  # For videos/audio
    
    # Access control
    is_published = models.BooleanField(default=True)
    publish_date = models.DateTimeField(auto_now_add=True)
    requires_completion = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['module', 'content_order']
    
    def __str__(self):
        return f"{self.content_type}: {self.content_title}"

class StudentEnrollment(BaseModel):
    """Student enrollment in e-learning courses"""
    ENROLLMENT_STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Dropped', 'Dropped'),
        ('Suspended', 'Suspended'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='elearning_enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    
    enrollment_date = models.DateTimeField(auto_now_add=True)
    enrollment_status = models.CharField(max_length=20, choices=ENROLLMENT_STATUS_CHOICES, default='Active')
    
    # Progress tracking
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_accessed = models.DateTimeField(blank=True, null=True)
    
    # Completion
    completed_at = models.DateTimeField(blank=True, null=True)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    class Meta:
        unique_together = ['student', 'course']
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['course']),
            models.Index(fields=['enrollment_status']),
        ]
    
    def __str__(self):
        return f"{self.student.admission_no} - {self.course.course_code}"

class ContentProgress(BaseModel):
    """Track student progress through learning content"""
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='content_progress')
    content = models.ForeignKey(LearningContent, on_delete=models.CASCADE, related_name='student_progress')
    
    # Progress tracking
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(blank=True, null=True)
    time_spent_minutes = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)
    
    # For quizzes/assignments
    score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    attempts = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['enrollment', 'content']
        indexes = [
            models.Index(fields=['enrollment']),
            models.Index(fields=['content']),
            models.Index(fields=['is_completed']),
        ]
    
    def __str__(self):
        return f"{self.enrollment.student.admission_no} - {self.content.content_title}"

class ELearningQuiz(BaseModel):
    """E-Learning Quizzes"""
    content = models.OneToOneField(LearningContent, on_delete=models.CASCADE, related_name='quiz')
    quiz_title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Quiz settings
    time_limit_minutes = models.IntegerField(blank=True, null=True)
    max_attempts = models.IntegerField(default=1)
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    randomize_questions = models.BooleanField(default=False)
    show_results = models.BooleanField(default=True)
    
    # Status
    is_published = models.BooleanField(default=True)
    published_date = models.DateTimeField(auto_now_add=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return self.quiz_title

class QuizQuestion(BaseModel):
    """Questions for quizzes"""
    QUESTION_TYPE_CHOICES = [
        ('MCQ', 'Multiple Choice'),
        ('TrueFalse', 'True/False'),
        ('ShortAnswer', 'Short Answer'),
        ('Essay', 'Essay'),
        ('Matching', 'Matching'),
    ]
    
    quiz = models.ForeignKey(ELearningQuiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='MCQ')
    question_order = models.IntegerField(default=0)
    points = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    
    # For MCQ
    options = models.JSONField(default=list, blank=True)  # [{'text': 'Option A', 'is_correct': true}, ...]
    
    # For all types
    correct_answer = models.TextField(blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['quiz', 'question_order']
    
    def __str__(self):
        return f"Q{self.question_order}: {self.question_text[:100]}..."

class QuizAttempt(BaseModel):
    """Student quiz attempts"""
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(ELearningQuiz, on_delete=models.CASCADE, related_name='attempts')
    
    attempt_number = models.IntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Results
    score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    is_passed = models.BooleanField(default=False)
    
    # Detailed responses
    responses = models.JSONField(default=dict, blank=True)
    
    class Meta:
        unique_together = ['enrollment', 'quiz', 'attempt_number']
        indexes = [
            models.Index(fields=['enrollment']),
            models.Index(fields=['quiz']),
        ]
    
    def save(self, *args, **kwargs):
        if self.score is not None and self.max_score is not None and self.max_score > 0:
            self.percentage = (self.score / self.max_score) * 100
            if self.percentage >= self.quiz.passing_score:
                self.is_passed = True
        super().save(*args, **kwargs)

class DiscussionForum(BaseModel):
    """Discussion forums for courses"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='forums')
    forum_title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    is_moderated = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return self.forum_title

class ForumPost(BaseModel):
    """Posts in discussion forums"""
    forum = models.ForeignKey(DiscussionForum, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_posts')
    parent_post = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    post_title = models.CharField(max_length=200, blank=True, null=True)
    content = models.TextField()
    
    # Moderation
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    
    # Engagement
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-is_pinned', '-created_at']
    
    def __str__(self):
        return f"Post by {self.author.username}: {self.content[:100]}..."

# ==================== FINANCE MODULE ====================
class FeeCategory(BaseModel):
    FREQUENCY_CHOICES = [
        ('One-Time', 'One-Time'),
        ('Monthly', 'Monthly'),
        ('Termly', 'Termly'),
        ('Annual', 'Annual'),
    ]
    
    category_code = models.CharField(max_length=20, unique=True)
    category_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    gl_account_code = models.CharField(max_length=30, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.category_code} - {self.category_name}"

class FeeStructure(BaseModel):
    TERM_CHOICES = [('Term 1', 'Term 1'), ('Term 2', 'Term 2'), ('Term 3', 'Term 3')]
    
    academic_year = models.CharField(max_length=9)
    term = models.CharField(max_length=20, choices=TERM_CHOICES)
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE)
    category = models.ForeignKey(FeeCategory, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    due_date = models.DateField()
    late_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, 
                                               validators=[MinValueValidator(0)])
    late_fee_after_days = models.IntegerField(default=30)
    installment_allowed = models.BooleanField(default=False)
    max_installments = models.IntegerField(default=1)
    discount_allowed = models.BooleanField(default=False)
    max_discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        unique_together = ['academic_year', 'term', 'class_id', 'category']
        indexes = [
            models.Index(fields=['academic_year']),
            models.Index(fields=['class_id']),
        ]
    
    def __str__(self):
        return f"{self.academic_year} {self.term} - {self.class_id.class_name} - {self.category.category_name}"

class StudentFeeInvoice(BaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Partial', 'Partial'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
        ('Cancelled', 'Cancelled'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('Unpaid', 'Unpaid'),
        ('Partially Paid', 'Partially Paid'),
        ('Fully Paid', 'Fully Paid'),
    ]
    
    invoice_no = models.CharField(max_length=30, unique=True, default=generate_inv_id)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='invoices')
    academic_year = models.CharField(max_length=9)
    term = models.CharField(max_length=20)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    
    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    late_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Unpaid')
    
    # Audit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cancelled_invoices')
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['status']),
            models.Index(fields=['invoice_date']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-calculate totals
        self.total_amount = self.subtotal - self.discount_amount + self.late_fee_amount
        self.balance_amount = self.total_amount - self.amount_paid
        
        # Auto-update status
        if self.balance_amount <= 0 and self.total_amount > 0:
            self.status = 'Paid'
            self.payment_status = 'Fully Paid'
        elif self.amount_paid > 0 and self.balance_amount > 0:
            self.status = 'Partial'
            self.payment_status = 'Partially Paid'
        elif self.due_date < timezone.now().date() and self.balance_amount > 0:
            self.status = 'Overdue'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.invoice_no} - {self.student.admission_no}"

class InvoiceItem(BaseModel):
    invoice = models.ForeignKey(StudentFeeInvoice, on_delete=models.CASCADE, related_name='items')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT)
    description = models.CharField(max_length=200)
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        self.discount_amount = self.amount * (self.discount_percentage / 100)
        self.net_amount = self.amount - self.discount_amount
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.description} - {self.net_amount}"

class FeeTransaction(BaseModel):
    PAYMENT_MODE_CHOICES = [
        ('Cash', 'Cash'),
        ('Cheque', 'Cheque'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Mobile Money', 'Mobile Money'),
        ('Credit Card', 'Credit Card'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
        ('Reversed', 'Reversed'),
    ]
    CURRENCY_CHOICES = [('KES', 'KES'), ('USD', 'USD'), ('EUR', 'EUR')]
    
    transaction_no = models.CharField(max_length=30, unique=True, default=generate_txn_id)
    invoice = models.ForeignKey(StudentFeeInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='fee_transactions')
    
    # Payment details
    payment_date = models.DateTimeField(default=timezone.now)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    cheque_no = models.CharField(max_length=50, blank=True, null=True)
    mobile_money_no = models.CharField(max_length=20, blank=True, null=True)
    
    # Amounts
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='KES')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=1)
    amount_kes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status and audit
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Completed')
    collected_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='collected_transactions')
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_transactions')
    verified_at = models.DateTimeField(blank=True, null=True)
    reversal_reason = models.TextField(blank=True, null=True)
    reversed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reversed_transactions')
    reversed_at = models.DateTimeField(blank=True, null=True)
    
    # Receipt
    receipt_printed = models.BooleanField(default=False)
    receipt_printed_at = models.DateTimeField(blank=True, null=True)
    receipt_printed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='printed_receipts')
    
    class Meta:
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['payment_mode']),
        ]
    
    def save(self, *args, **kwargs):
        self.amount_kes = self.amount * self.exchange_rate
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.transaction_no} - {self.amount_kes}"

class GeneralLedger(BaseModel):
    transaction_date = models.DateField(default=timezone.now)
    gl_date = models.DateField(default=timezone.now)
    account_code = models.CharField(max_length=30)
    account_name = models.CharField(max_length=100)
    debit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField()
    reference_no = models.CharField(max_length=50, blank=True, null=True)
    reference_type = models.CharField(max_length=30, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['gl_date']),
            models.Index(fields=['account_code']),
        ]
    
    def __str__(self):
        return f"{self.gl_date} - {self.account_code}"

# ==================== ATTENDANCE & DISCIPLINE ====================
class AttendanceSession(BaseModel):
    SESSION_TYPE_CHOICES = [
        ('Morning', 'Morning'),
        ('Afternoon', 'Afternoon'),
        ('Full Day', 'Full Day'),
        ('Evening', 'Evening'),
    ]
    
    session_date = models.DateField(default=timezone.now)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES)
    class_id = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(LearningArea, on_delete=models.SET_NULL, null=True, blank=True)
    period_number = models.IntegerField(blank=True, null=True)
    start_time = models.TimeField()
    end_time = models.TimeField(blank=True, null=True)
    conducted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='attendance_conducted_sessions')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['session_date', 'class_id', 'period_number', 'session_type']
        indexes = [
            models.Index(fields=['session_date']),
        ]
    
    def __str__(self):
        return f"{self.session_date} - {self.class_id.class_name if self.class_id else 'General'} - {self.session_type}"

class StudentAttendance(BaseModel):
    ATTENDANCE_STATUS_CHOICES = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
        ('Excused', 'Excused'),
        ('Half-day', 'Half-day'),
    ]
    
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    attendance_status = models.CharField(max_length=15, choices=ATTENDANCE_STATUS_CHOICES)
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_out_time = models.DateTimeField(blank=True, null=True)
    late_minutes = models.IntegerField(default=0)
    remarks = models.TextField(blank=True, null=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['session', 'student']
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['attendance_status']),
        ]
    
    def __str__(self):
        return f"{self.student.admission_no} - {self.session.session_date} - {self.attendance_status}"

class DisciplineCategory(BaseModel):
    SEVERITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]
    
    category_code = models.CharField(max_length=20, unique=True)
    category_name = models.CharField(max_length=100)
    severity_level = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    default_points = models.IntegerField(default=1, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.category_name} ({self.severity_level})"

class DisciplineIncident(BaseModel):
    STATUS_CHOICES = [
        ('Reported', 'Reported'),
        ('Under Investigation', 'Under Investigation'),
        ('Resolved', 'Resolved'),
        ('Escalated', 'Escalated'),
        ('Closed', 'Closed'),
    ]
    
    incident_code = models.CharField(max_length=30, unique=True, default=generate_inc_id)
    incident_date = models.DateField(default=timezone.now)
    incident_time = models.TimeField(default=timezone.now)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='discipline_incidents')
    category = models.ForeignKey(DisciplineCategory, on_delete=models.PROTECT)
    reported_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='reported_incidents')
    
    # Incident details
    description = models.TextField()
    location = models.CharField(max_length=100, blank=True, null=True)
    witnesses = models.TextField(blank=True, null=True)
    evidence_urls = models.JSONField(default=list, blank=True)
    
    # Resolution tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Reported')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_incidents')
    investigation_notes = models.TextField(blank=True, null=True)
    resolution = models.TextField(blank=True, null=True)
    resolution_date = models.DateField(blank=True, null=True)
    points_awarded = models.IntegerField(validators=[MinValueValidator(0)])
    
    # Parent communication
    parent_notified = models.BooleanField(default=False)
    parent_notification_date = models.DateField(blank=True, null=True)
    parent_response = models.TextField(blank=True, null=True)
    
    # Audit
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_incidents')
    closed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['incident_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.incident_code} - {self.student.admission_no}"

class StudentDisciplinePoints(BaseModel):
    STATUS_CHOICES = [
        ('Excellent', 'Excellent'),
        ('Good', 'Good'),
        ('Warning', 'Warning'),
        ('Probation', 'Probation'),
        ('Suspension', 'Suspension'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='discipline_points')
    academic_year = models.CharField(max_length=9)
    term = models.CharField(max_length=20)
    total_points = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    warnings_count = models.IntegerField(default=0)
    suspensions_count = models.IntegerField(default=0)
    last_incident_date = models.DateField(blank=True, null=True)
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Good')
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['student', 'academic_year', 'term']
        indexes = [
            models.Index(fields=['student']),
        ]
    
    def __str__(self):
        return f"{self.student.admission_no} - {self.academic_year} {self.term}"
    
    
# ==================== DISCIPLINE MODELS ADDITIONS ====================

class ConductRecord(BaseModel):
    """Student conduct record tracking merits and demerits"""
    
    CONDUCT_GRADE_CHOICES = [
        ('A', 'Excellent'),
        ('B', 'Good'),
        ('C', 'Satisfactory'),
        ('D', 'Needs Improvement'),
        ('F', 'Poor'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='conduct_records')
    academic_year = models.CharField(max_length=9)
    term = models.CharField(max_length=20)
    conduct_grade = models.CharField(max_length=1, choices=CONDUCT_GRADE_CHOICES, default='C')
    merits = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    demerits = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_points = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=StudentDisciplinePoints.STATUS_CHOICES, default='Good')
    remarks = models.TextField(blank=True, null=True)
    last_updated = models.DateField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'academic_year', 'term']
        ordering = ['-last_updated']
    
    def save(self, *args, **kwargs):
        self.total_points = self.merits - self.demerits
        if self.total_points >= 20:
            self.conduct_grade = 'A'
            self.status = 'Excellent'
        elif self.total_points >= 10:
            self.conduct_grade = 'B'
            self.status = 'Good'
        elif self.total_points >= 0:
            self.conduct_grade = 'C'
            self.status = 'Good'
        elif self.total_points >= -10:
            self.conduct_grade = 'D'
            self.status = 'Warning'
        else:
            self.conduct_grade = 'F'
            self.status = 'Probation'
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student.full_name} - {self.academic_year} {self.term}: {self.conduct_grade}"


class InterventionProgram(BaseModel):
    """Intervention programs for students"""
    
    PROGRAM_TYPE_CHOICES = [
        ('Behavioral', 'Behavioral'),
        ('Academic', 'Academic'),
        ('Social', 'Social'),
        ('Counseling', 'Counseling'),
    ]
    
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Scheduled', 'Scheduled'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    
    program_code = models.CharField(max_length=20, unique=True)
    program_name = models.CharField(max_length=200)
    program_type = models.CharField(max_length=20, choices=PROGRAM_TYPE_CHOICES)
    description = models.TextField()
    duration_weeks = models.IntegerField(default=4)
    facilitator = models.CharField(max_length=100)
    max_students = models.IntegerField(default=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')
    start_date = models.DateField()
    end_date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.program_code} - {self.program_name}"


class InterventionEnrollment(BaseModel):
    """Student enrollment in intervention programs"""
    
    ENROLLMENT_STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Dropped', 'Dropped'),
        ('On Hold', 'On Hold'),
    ]
    
    program = models.ForeignKey(InterventionProgram, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='interventions')
    enrollment_date = models.DateField(auto_now_add=True)
    completion_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=ENROLLMENT_STATUS_CHOICES, default='Active')
    progress_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['program', 'student']
    
    def __str__(self):
        return f"{self.student.full_name} - {self.program.program_name}"


class CounselingSession(BaseModel):
    """Counseling sessions for students"""
    
    SESSION_TYPE_CHOICES = [
        ('Academic Guidance', 'Academic Guidance'),
        ('Personal Counseling', 'Personal Counseling'),
        ('Career Counseling', 'Career Counseling'),
        ('Crisis Intervention', 'Crisis Intervention'),
        ('Group Session', 'Group Session'),
    ]
    
    SESSION_STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
        ('No Show', 'No Show'),
    ]
    
    session_code = models.CharField(max_length=20, unique=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='counseling_sessions')
    counselor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conducted_sessions')
    session_type = models.CharField(max_length=30, choices=SESSION_TYPE_CHOICES)
    session_date = models.DateField()
    session_time = models.TimeField()
    duration_minutes = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, default='Scheduled')
    notes = models.TextField(blank=True, null=True)
    follow_up_needed = models.BooleanField(default=False)
    follow_up_date = models.DateField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_sessions')
    
    class Meta:
        ordering = ['-session_date', '-session_time']
    
    def __str__(self):
        return f"{self.session_code} - {self.student.full_name} - {self.session_type}"


class Suspension(BaseModel):
    """Student suspension records"""
    
    SUSPENSION_TYPE_CHOICES = [
        ('In-School', 'In-School Suspension'),
        ('Out-of-School', 'Out-of-School Suspension'),
    ]
    
    SUSPENSION_STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Appealed', 'Appealed'),
        ('Overturned', 'Overturned'),
    ]
    
    suspension_code = models.CharField(max_length=20, unique=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='suspensions')
    incident = models.ForeignKey(DisciplineIncident, on_delete=models.CASCADE, related_name='suspensions')
    suspension_type = models.CharField(max_length=20, choices=SUSPENSION_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.IntegerField()
    reason = models.TextField()
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_suspensions')
    status = models.CharField(max_length=20, choices=SUSPENSION_STATUS_CHOICES, default='Active')
    parent_notified = models.BooleanField(default=False)
    parent_notification_date = models.DateField(blank=True, null=True)
    reentry_meeting_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            self.total_days = delta.days + 1
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.suspension_code} - {self.student.full_name} ({self.suspension_type})"


class DisciplineReport(BaseModel):
    """Generated discipline reports"""
    
    REPORT_TYPE_CHOICES = [
        ('Daily', 'Daily Summary'),
        ('Weekly', 'Weekly Analysis'),
        ('Monthly', 'Monthly Report'),
        ('Quarterly', 'Quarterly Review'),
        ('Custom', 'Custom Report'),
    ]
    
    REPORT_FORMAT_CHOICES = [
        ('PDF', 'PDF'),
        ('Excel', 'Excel'),
        ('CSV', 'CSV'),
    ]
    
    report_code = models.CharField(max_length=20, unique=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_reports')
    generated_date = models.DateTimeField(auto_now_add=True)
    date_range_start = models.DateField()
    date_range_end = models.DateField()
    format = models.CharField(max_length=10, choices=REPORT_FORMAT_CHOICES, default='PDF')
    file_url = models.CharField(max_length=500, blank=True, null=True)
    file_size = models.IntegerField(blank=True, null=True)
    download_count = models.IntegerField(default=0)
    includes_charts = models.BooleanField(default=True)
    includes_summary = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default='Completed')
    
    class Meta:
        ordering = ['-generated_date']
    
    def __str__(self):
        return f"{self.report_code} - {self.title} ({self.generated_date.date()})"


# ==================== HR & STAFF MANAGEMENT MODELS ====================

class TeacherCategory(models.Model):
    """CBE Teacher Categories"""
    name = models.CharField(max_length=50, unique=True)  # PP, Early Primary, JSS
    code = models.CharField(max_length=10, unique=True)  # PP, EP, JSS
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Teacher Categories"
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class JSSDepartment(models.Model):
    """Departments for JSS Teachers (STEM, Humanities, Languages, etc.)"""
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Staff(BaseModel):
    """Staff Model - Clean version with proper relationships"""
    
    EMPLOYMENT_TYPE_CHOICES = [
        ('Permanent', 'Permanent'),
        ('Contract', 'Contract'),
        ('Probation', 'Probation'),
        ('Part-time', 'Part-time'),
        ('Intern', 'Intern'),
    ]
    
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('On Leave', 'On Leave'),
        ('Suspended', 'Suspended'),
        ('Terminated', 'Terminated'),
        ('Resigned', 'Resigned'),
    ]
    
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
    ]
    
    # Basic Information
    staff_id = models.CharField(max_length=30, unique=True)
    user = models.OneToOneField('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_profile')
    
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    
    # Contact
    personal_email = models.EmailField(unique=True)
    personal_phone = models.CharField(max_length=20, unique=True)
    permanent_address = models.TextField(blank=True, null=True)
    
    # Identification
    national_id = models.CharField(max_length=20, unique=True)
    
    # Employment
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='Permanent')
    employment_date = models.DateField(default=timezone.now)
    contract_end_date = models.DateField(blank=True, null=True)
    
    # CBE Teacher Categorization
    teacher_category = models.ForeignKey(
        TeacherCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members'
    )
    
    # For JSS Teachers only
    jss_department = models.ForeignKey(
        JSSDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members'
    )
    
    # For PP and Early Primary Teachers only
    assigned_grade_level = models.ForeignKey(
        'GradeLevel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_teachers'
    )
    
    # Auto-generated Teacher Code (Immutable)
    teacher_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    
    # General Department (Administrative)
    admin_department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members'
    )
    
    designation = models.CharField(max_length=50)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    
    # Qualifications
    highest_qualification = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.TextField(blank=True, null=True)
    
    # Audit
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='created_staff')
    updated_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='updated_staff')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['staff_id']),
            models.Index(fields=['teacher_code']),
            models.Index(fields=['teacher_category']),
            models.Index(fields=['status']),
        ]
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.middle_name + ' ' if self.middle_name else ''}{self.last_name}"
    
    def save(self, *args, **kwargs):
        # ========== AUTO-CREATE USER ACCOUNT FOR STAFF ==========
        if not self.user and self.personal_email:
            # Try to find existing user by email
            existing_user = User.objects.filter(email=self.personal_email).first()
            
            if existing_user:
                # Link to existing user
                self.user = existing_user
            else:
                # Create a new user account
                username = self.personal_email.split('@')[0]
                base_username = username
                counter = 1
                
                # Ensure username is unique
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Create the user
                user = User.objects.create(
                    username=username,
                    email=self.personal_email,
                    first_name=self.first_name,
                    last_name=self.last_name,
                    role='teacher',
                    is_active=True
                )
                # Set a default password (user must change on first login)
                user.set_password('staff@123')
                user.save()
                
                self.user = user
        
        # Auto-generate teacher_code based on category
        if not self.teacher_code and self.teacher_category:
            prefix = self.teacher_category.code  # PP, EP, or JSS
            
            # Get highest sequence number for this prefix
            existing = Staff.objects.filter(teacher_code__startswith=prefix)
            max_num = 0
            for staff in existing:
                if staff.teacher_code and staff.teacher_code.startswith(prefix):
                    try:
                        num = int(staff.teacher_code[len(prefix):])
                        if num > max_num:
                            max_num = num
                    except ValueError:
                        pass
            
            sequence = max_num + 1
            self.teacher_code = f"{prefix}{sequence:03d}"
        
        # Auto-generate staff_id if not set
        if not self.staff_id:
            date_part = timezone.now().strftime('%Y%m')
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            self.staff_id = f"STF-{date_part}-{random_part}"
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.full_name} ({self.teacher_code or self.staff_id})"
    
class StaffLeave(BaseModel):
    LEAVE_TYPE_CHOICES = [
        ('Annual', 'Annual'),
        ('Sick', 'Sick'),
        ('Maternity', 'Maternity'),
        ('Paternity', 'Paternity'),
        ('Study', 'Study'),
        ('Compassionate', 'Compassionate'),
        ('Unpaid', 'Unpaid'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]
    
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=30, choices=LEAVE_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.IntegerField(default=0)
    reason = models.TextField()
    contact_during_leave = models.CharField(max_length=20, blank=True, null=True)
    
    # Approval workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    applied_date = models.DateField(default=timezone.now)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    approved_date = models.DateField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Handover
    handover_notes = models.TextField(blank=True, null=True)
    handover_to = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='handover_leaves')
    
    class Meta:
        indexes = [
            models.Index(fields=['staff']),
            models.Index(fields=['status']),
        ]
    
    def save(self, *args, **kwargs):
        # Calculate total days excluding weekends and holidays
        from datetime import timedelta
        total = 0
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5:  # Monday=0, Friday=4
                total += 1
            current += timedelta(days=1)
        self.total_days = total
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.staff.staff_id} - {self.leave_type} - {self.start_date} to {self.end_date}"

class LeaveBalance(BaseModel):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='leave_balances')
    leave_year = models.IntegerField()
    leave_type = models.CharField(max_length=30)
    total_entitled = models.IntegerField(default=0)
    taken_so_far = models.IntegerField(default=0)
    balance = models.IntegerField(default=0)
    carried_over = models.IntegerField(default=0)
    expires_on = models.DateField(blank=True, null=True)
    
    class Meta:
        unique_together = ['staff', 'leave_year', 'leave_type']
        indexes = [
            models.Index(fields=['staff']),
        ]
    
    def save(self, *args, **kwargs):
        self.balance = self.total_entitled - self.taken_so_far + self.carried_over
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.staff.staff_id} - {self.leave_year} - {self.leave_type}: {self.balance}"

# ==================== PAYROLL MANAGEMENT ====================
class PayrollComponent(BaseModel):
    COMPONENT_TYPE_CHOICES = [
        ('Earning', 'Earning'),
        ('Deduction', 'Deduction'),
        ('Benefit', 'Benefit'),
        ('Allowance', 'Allowance'),
    ]
    
    CALCULATION_TYPE_CHOICES = [
        ('Fixed Amount', 'Fixed Amount'),
        ('Percentage of Basic', 'Percentage of Basic'),
        ('Per Unit', 'Per Unit'),
        ('Formula', 'Formula'),
    ]
    
    FREQUENCY_CHOICES = [
        ('Monthly', 'Monthly'),
        ('One-Time', 'One-Time'),
        ('Annual', 'Annual'),
        ('Quarterly', 'Quarterly'),
    ]
    
    component_code = models.CharField(max_length=20, unique=True)
    component_name = models.CharField(max_length=100)
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPE_CHOICES)
    calculation_type = models.CharField(max_length=30, choices=CALCULATION_TYPE_CHOICES)
    
    # Calculation Details
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    percentage_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    formula = models.TextField(blank=True, null=True)
    
    # Taxation
    is_taxable = models.BooleanField(default=True)
    is_pensionable = models.BooleanField(default=True)
    statutory_component = models.BooleanField(default=False)
    
    # Application
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='Monthly')
    applies_to_all = models.BooleanField(default=False)
    applies_to_staff_type = models.JSONField(default=list, blank=True)
    
    # Limits
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    max_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    # Accounting
    gl_account_code = models.CharField(max_length=30, blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    effective_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(blank=True, null=True)
    
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_payroll_components')
    
    def __str__(self):
        return f"{self.component_code} - {self.component_name}"

class StaffPayrollComponent(BaseModel):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='payroll_components')
    component = models.ForeignKey(PayrollComponent, on_delete=models.CASCADE, related_name='staff_components')
    
    # Customized Values (overrides default)
    custom_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    custom_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    custom_formula = models.TextField(blank=True, null=True)
    
    # Effective Dates
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_staff_components')
    approved_date = models.DateField(blank=True, null=True)
    
    # Audit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_staff_payroll_components')
    
    class Meta:
        unique_together = ['staff', 'component']
        indexes = [
            models.Index(fields=['staff']),
            models.Index(fields=['component']),
        ]
    
    def __str__(self):
        return f"{self.staff.staff_id} - {self.component.component_name}"

class PayrollPeriod(BaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Processing', 'Processing'),
        ('Calculated', 'Calculated'),
        ('Approved', 'Approved'),
        ('Paid', 'Paid'),
        ('Closed', 'Closed'),
    ]
    
    period_code = models.CharField(max_length=30, unique=True)
    period_name = models.CharField(max_length=100)
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    pay_date = models.DateField()
    
    # Processing Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    # Staff Coverage
    total_staff = models.IntegerField(default=0)
    processed_staff = models.IntegerField(default=0)
    
    # Financial Summary
    total_gross = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Tax Summary
    total_paye = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_nssf = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_nhif = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Processing Details
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_payroll_periods')
    processed_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payroll_periods')
    approved_date = models.DateTimeField(blank=True, null=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_payroll_periods')
    closed_date = models.DateTimeField(blank=True, null=True)
    
    # Locking
    is_locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_payroll_periods')
    locked_date = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['period_code']),
            models.Index(fields=['status']),
            models.Index(fields=['pay_date']),
        ]
    
    def __str__(self):
        return f"{self.period_name} ({self.start_date} to {self.end_date})"

class PayrollRecord(BaseModel):
    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Partially Paid', 'Partially Paid'),
        ('On Hold', 'On Hold'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('Bank Transfer', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Cash', 'Cash'),
        ('Mobile Money', 'Mobile Money'),
    ]
    
    payroll_period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name='records')
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='payroll_records')
    
    # Earnings
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Deductions
    paye_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nssf_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nhif_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pension_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    loan_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Net Amount
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Payment Details
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)
    bank_account = models.CharField(max_length=50, blank=True, null=True)
    
    # Breakdown (JSON for flexibility)
    allowances_breakdown = models.JSONField(default=list, blank=True)
    deductions_breakdown = models.JSONField(default=list, blank=True)
    
    # Attendance & Leaves
    days_worked = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    leave_days = models.IntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    
    # Statutory Information
    taxable_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pensionable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    is_calculated = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payroll_records')
    approved_date = models.DateTimeField(blank=True, null=True)
    
    # Audit
    calculated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='calculated_payroll_records')
    calculated_date = models.DateTimeField(blank=True, null=True)
    paid_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='paid_payroll_records')
    paid_date = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ['payroll_period', 'staff']
        indexes = [
            models.Index(fields=['payroll_period']),
            models.Index(fields=['staff']),
            models.Index(fields=['payment_status']),
        ]
    
    def save(self, *args, **kwargs):
        self.gross_salary = self.basic_salary + self.allowances_total + self.overtime_total + self.bonus_total + self.other_earnings
        self.total_deductions = self.paye_tax + self.nssf_deduction + self.nhif_deduction + self.pension_deduction + self.loan_deductions + self.other_deductions
        self.net_salary = self.gross_salary - self.total_deductions
        
        if self.is_paid:
            self.payment_status = 'Paid'
        elif self.net_salary > 0:
            self.payment_status = 'Pending'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.staff.staff_id} - {self.payroll_period.period_name} - {self.net_salary}"

class StaffLoan(BaseModel):
    LOAN_TYPE_CHOICES = [
        ('Emergency', 'Emergency'),
        ('Salary Advance', 'Salary Advance'),
        ('Housing', 'Housing'),
        ('Vehicle', 'Vehicle'),
        ('Education', 'Education'),
        ('Other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Disbursed', 'Disbursed'),
        ('Active', 'Active'),
        ('Settled', 'Settled'),
        ('Defaulted', 'Defaulted'),
        ('Written Off', 'Written Off'),
    ]
    
    loan_id = models.CharField(max_length=30, unique=True, default=generate_inc_id)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='loans')
    
    # Loan Details
    loan_type = models.CharField(max_length=30, choices=LOAN_TYPE_CHOICES)
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(1)])
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    interest_type = models.CharField(max_length=20, choices=[('Flat', 'Flat'), ('Reducing', 'Reducing')], default='Flat')
    
    # Repayment Terms
    repayment_months = models.IntegerField(default=12)
    reason = models.TextField(null=True, blank=True)
    monthly_installment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Disbursement
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    disbursement_date = models.DateField(blank=True, null=True)
    disbursement_method = models.CharField(max_length=30, blank=True, null=True)
    
    # Repayment Tracking
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_interest_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_principal_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    outstanding_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_days = models.IntegerField(default=0)
    
    # Approval Workflow
    applied_date = models.DateField(default=timezone.now)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_staff_loans')
    approved_date = models.DateField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Guarantor/Security
    guarantor_name = models.CharField(max_length=100, blank=True, null=True)
    guarantor_contact = models.CharField(max_length=20, blank=True, null=True)
    security_details = models.TextField(blank=True, null=True)
    
    # Audit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_staff_loans')
    
    class Meta:
        indexes = [
            models.Index(fields=['loan_id']),
            models.Index(fields=['staff']),
            models.Index(fields=['status']),
        ]
    
    def save(self, *args, **kwargs):
        if self.loan_amount and self.repayment_months:
            # Convert everything to Decimal once
            loan_amount = Decimal(str(self.loan_amount))
            interest_rate = Decimal(str(self.interest_rate or 0))
            repayment_months = Decimal(str(self.repayment_months))
            total_principal_paid = Decimal(str(self.total_principal_paid or 0))

            # === CALCULATE MONTHLY INSTALLMENT (only if not already set by serializer) ===
            if not self.monthly_installment or self.monthly_installment == 0:
                if self.interest_type == 'Flat' and interest_rate > 0:
                    years = repayment_months / Decimal('12')
                    total_interest = loan_amount * (interest_rate / Decimal('100')) * years
                    total_repayment = loan_amount + total_interest
                    self.monthly_installment = total_repayment / repayment_months
                else:
                    self.monthly_installment = loan_amount / repayment_months

            # === OUTSTANDING BALANCE ===
            if not self.outstanding_balance or self.outstanding_balance == 0:
                self.outstanding_balance = loan_amount - total_principal_paid

        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.loan_id} - {self.staff.staff_id} - {self.loan_amount}"

class LoanRepayment(BaseModel):
    loan = models.ForeignKey(StaffLoan, on_delete=models.CASCADE, related_name='repayments')
    
    # Payment Details
    repayment_date = models.DateField(default=timezone.now)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Payment Method
    payment_method = models.CharField(max_length=20, choices=[
        ('Salary Deduction', 'Salary Deduction'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cash', 'Cash'),
        ('Cheque', 'Cheque'),
        ('Mobile Money', 'Mobile Money'),
    ])
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    
    # Status
    is_overdue = models.BooleanField(default=False)
    overdue_days = models.IntegerField(default=0)
    
    # Processing
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='processed_loan_repayments')
    processed_date = models.DateTimeField(default=timezone.now)
    
    # Remarks
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['loan']),
            models.Index(fields=['repayment_date']),
        ]
    
    def __str__(self):
        return f"{self.loan.loan_id} - {self.repayment_date} - {self.amount_paid}"

# ==================== LIBRARY MODULE ====================
class BookResource(BaseModel):
    CONDITION_STATUS_CHOICES = [
        ('New', 'New'),
        ('Good', 'Good'),
        ('Worn', 'Worn'),
        ('Damaged', 'Damaged'),
        ('Lost', 'Lost'),
    ]
    
    BOOK_CATEGORY_CHOICES = [
        ('Textbook', 'Textbook'),
        ('Storybook', 'Storybook'),
        ('Reference', 'Reference'),
        ('Teacher Guide', 'Teacher Guide'),
        ('Digital Resource', 'Digital Resource'),
        ('Journal', 'Journal'),
        ('Magazine', 'Magazine'),
        ('Newspaper', 'Newspaper'),
        ('Audio Book', 'Audio Book'),
        ('Video', 'Video'),
    ]
    
    LANGUAGE_CHOICES = [
        ('English', 'English'),
        ('Kiswahili', 'Kiswahili'),
        ('French', 'French'),
        ('German', 'German'),
        ('Arabic', 'Arabic'),
        ('Other', 'Other'),
    ]
    
    # Identification
    isbn = models.CharField(max_length=20, blank=True, null=True, verbose_name="ISBN")
    school_code = models.CharField(max_length=30, unique=True)
    accession_number = models.CharField(max_length=30, unique=True)
    
    # Basic Information
    title = models.CharField(max_length=200)
    authors = models.CharField(max_length=300)
    publisher = models.CharField(max_length=100, blank=True, null=True)
    edition = models.CharField(max_length=20, blank=True, null=True)
    year_of_publication = models.IntegerField(blank=True, null=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='English')
    
    # Classification
    subject = models.ForeignKey(LearningArea, on_delete=models.SET_NULL, null=True, blank=True, 
                               verbose_name="Kenya CBE Learning Area")
    grade_levels = models.ManyToManyField(Class, blank=True, related_name='books')
    book_category = models.CharField(max_length=30, choices=BOOK_CATEGORY_CHOICES)
    
    # Physical Details
    shelf_location = models.CharField(max_length=50)
    call_number = models.CharField(max_length=30, blank=True, null=True)
    pages = models.IntegerField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Inventory
    total_copies = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    available_copies = models.IntegerField(default=1)
    reserved_copies = models.IntegerField(default=0)
    condition_status = models.CharField(max_length=20, choices=CONDITION_STATUS_CHOICES, default='Good')
    
    # Digital Resources
    digital_file_url = models.CharField(max_length=255, blank=True, null=True)
    thumbnail_url = models.CharField(max_length=255, blank=True, null=True)
    has_digital_version = models.BooleanField(default=False)
    
    # Metadata
    keywords = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    table_of_contents = models.TextField(blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_reference_only = models.BooleanField(default=False)
    
    # Audit
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='added_books')
    added_date = models.DateField(default=timezone.now)
    
    class Meta:
        indexes = [
            models.Index(fields=['school_code']),
            models.Index(fields=['title']),
            models.Index(fields=['authors']),
            models.Index(fields=['subject']),
            models.Index(fields=['book_category']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['title']
    
    def __str__(self):
        return f"{self.title} - {self.school_code}"
    
    def save(self, *args, **kwargs):
        if not self.available_copies:
            self.available_copies = self.total_copies
        super().save(*args, **kwargs)

# ==================== SYSTEM & AUDIT ====================
class AuditLog(BaseModel):
    EVENT_TYPE_CHOICES = [
        ('USER_LOGIN', 'User Login'),
        ('USER_LOGOUT', 'User Logout'),
        ('USER_CREATE', 'User Create'),
        ('USER_UPDATE', 'User Update'),
        ('USER_DELETE', 'User Delete'),
        ('STUDENT_CREATE', 'Student Create'),
        ('STUDENT_UPDATE', 'Student Update'),
        ('STUDENT_DELETE', 'Student Delete'),
        ('FEE_CREATE', 'Fee Create'),
        ('FEE_UPDATE', 'Fee Update'),
        ('FEE_DELETE', 'Fee Delete'),
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('EXAM_CREATE', 'Exam Create'),
        ('EXAM_UPDATE', 'Exam Update'),
        ('MARKS_ENTERED', 'Marks Entered'),
        ('MARKS_MODIFIED', 'Marks Modified'),
        ('ATTENDANCE_MARKED', 'Attendance Marked'),
        ('DISCIPLINE_INCIDENT', 'Discipline Incident'),
        ('SYSTEM_BACKUP', 'System Backup'),
        ('SYSTEM_RESTORE', 'System Restore'),
        ('CONFIG_CHANGE', 'Config Change'),
        ('CBE_RATING_ENTERED', 'CBE Rating Entered'),
        ('CBE_REPORT_GENERATED', 'CBE Report Generated'),
    ]
    OPERATION_CHOICES = [
        ('INSERT', 'Insert'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('SELECT', 'Select'),
    ]
    
    event_time = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES)
    
    # Who
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    username = models.CharField(max_length=50, blank=True, null=True)
    user_role = models.CharField(max_length=30, blank=True, null=True)
    
    # What
    table_name = models.CharField(max_length=50)
    record_id = models.UUIDField(blank=True, null=True)  # Changed to UUIDField
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES, blank=True, null=True)
    
    # Changes
    old_values = models.JSONField(blank=True, null=True)
    new_values = models.JSONField(blank=True, null=True)
    changed_fields = models.JSONField(default=list, blank=True)
    
    # Context
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    endpoint = models.CharField(max_length=255, blank=True, null=True)
    http_method = models.CharField(max_length=10, blank=True, null=True)
    request_id = models.UUIDField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['event_time']),
            models.Index(fields=['user']),
            models.Index(fields=['table_name']),
            models.Index(fields=['event_type']),
        ]
    
    def __str__(self):
        return f"{self.event_time} - {self.event_type} - {self.username}"

class BackupHistory(BaseModel):
    BACKUP_TYPE_CHOICES = [
        ('Full', 'Full'),
        ('Incremental', 'Incremental'),
        ('Differential', 'Differential'),
        ('Manual', 'Manual'),
        ('Scheduled', 'Scheduled'),
    ]
    STATUS_CHOICES = [
        ('Started', 'Started'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
        ('Verified', 'Verified'),
    ]
    
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPE_CHOICES)
    backup_name = models.CharField(max_length=100)
    file_path = models.TextField()
    file_size = models.BigIntegerField(blank=True, null=True)
    database_version = models.CharField(max_length=20, blank=True, null=True)
    backup_start = models.DateTimeField()
    backup_end = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    verification_status = models.BooleanField(blank=True, null=True)
    verification_time = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    initiated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    restore_point = models.BooleanField(default=False)
    retention_days = models.IntegerField(default=30)
    expires_on = models.DateField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['backup_start']),
            models.Index(fields=['status']),
            models.Index(fields=['expires_on']),
        ]
    
    def __str__(self):
        return f"{self.backup_name} - {self.backup_start.date()} - {self.status}"

class SystemSetting(BaseModel):
    SETTING_TYPE_CHOICES = [
        ('String', 'String'),
        ('Number', 'Number'),
        ('Boolean', 'Boolean'),
        ('JSON', 'JSON'),
        ('Encrypted', 'Encrypted'),
    ]
    
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.TextField()
    setting_type = models.CharField(max_length=20, choices=SETTING_TYPE_CHOICES)
    category = models.CharField(max_length=50, default='General')
    description = models.TextField(blank=True, null=True)
    is_public = models.BooleanField(default=False)
    is_encrypted = models.BooleanField(default=False)
    encrypted_value = models.BinaryField(blank=True, null=True)
    min_value = models.TextField(blank=True, null=True)
    max_value = models.TextField(blank=True, null=True)
    validation_regex = models.TextField(blank=True, null=True)
    options = models.JSONField(blank=True, null=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    requires_restart = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.setting_key}: {self.setting_value[:50]}..."

# ==================== UTILITY TABLES ====================
class Holiday(BaseModel):
    HOLIDAY_TYPE_CHOICES = [
        ('Public Holiday', 'Public Holiday'),
        ('School Holiday', 'School Holiday'),
        ('Exam Holiday', 'Exam Holiday'),
        ('Other', 'Other'),
    ]
    
    holiday_date = models.DateField(unique=True)
    holiday_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    holiday_type = models.CharField(max_length=30, choices=HOLIDAY_TYPE_CHOICES)
    is_working_day = models.BooleanField(default=False)
    academic_year = models.CharField(max_length=9, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.holiday_name} ({self.holiday_date})"

class Notification(BaseModel):
    RECIPIENT_TYPE_CHOICES = [
        ('User', 'User'),
        ('Role', 'Role'),
        ('Class', 'Class'),
        ('All', 'All'),
    ]
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Normal', 'Normal'),
        ('High', 'High'),
        ('Urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('Unread', 'Unread'),
        ('Read', 'Read'),
        ('Archived', 'Archived'),
    ]
    
    notification_type = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    message = models.TextField()
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_TYPE_CHOICES)
    recipient_id = models.UUIDField(blank=True, null=True)  # Changed to UUIDField
    recipient_role = models.CharField(max_length=30, blank=True, null=True) 
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unread')
    action_url = models.CharField(max_length=255, blank=True, null=True)
    related_table = models.CharField(max_length=50, blank=True, null=True)
    related_id = models.UUIDField(blank=True, null=True)  # Changed to UUIDField
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['recipient_type', 'recipient_id']),
            models.Index(fields=['status']),
            models.Index(fields=['sent_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.recipient_type}"

class Timetable(BaseModel):
    DAY_CHOICES = [(1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'), 
                   (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'), (7, 'Sunday')]
    
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE)
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    period = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    subject = models.ForeignKey(LearningArea, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='timetable_slots')
    room = models.CharField(max_length=20, blank=True, null=True)
    academic_year = models.CharField(max_length=9)
    term = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['class_id', 'day_of_week', 'period', 'academic_year', 'term']
        ordering = ['day_of_week', 'period']
    
    def __str__(self):
        return f"{self.class_id.class_name} - Day {self.day_of_week} - Period {self.period}"



# ==================== CBE REPORT CARDS ====================
class CBEReportCard(BaseModel):
    """CBE Report Card Structure"""
    REPORT_TYPE_CHOICES = [
        ('Learner Progress Report', 'Learner Progress Report'),
        ('Parent Summary Report', 'Parent Summary Report'),
        ('Teacher Class Performance Report', 'Teacher Class Performance Report'),
        ('School-Wide CBE Report', 'School-Wide CBE Report'),
    ]
    
    report_id = models.CharField(max_length=30, unique=True, default=generate_report_id)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)
    
    # Scope
    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True, related_name='cbe_report_cards')
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE, null=True, blank=True, related_name='cbe_report_cards')
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='cbe_report_cards')
    
    # Period
    academic_year = models.CharField(max_length=9)
    term = models.CharField(max_length=20)
    reporting_date = models.DateField(default=timezone.now)
    
    # Learner Details Section
    learner_photo_url = models.CharField(max_length=255, blank=True, null=True)
    learner_attendance_summary = models.TextField(blank=True, null=True)
    
    # Learning Area Performance Section (JSON for flexibility)
    learning_area_performance = models.JSONField(default=list)
    
    # Competency Levels Summary
    competency_summary = models.JSONField(default=dict)
    
    # Core Competencies Progress
    core_competencies = models.JSONField(default=list)
    
    # Values Development
    values_assessment = models.JSONField(default=list)
    
    # Remarks Section
    teacher_remarks = models.TextField(blank=True, null=True)
    head_teacher_remarks = models.TextField(blank=True, null=True)
    head_teacher_signature = models.CharField(max_length=100, blank=True, null=True)
    
    # Parent Feedback Section
    parent_feedback_section = models.TextField(blank=True, null=True)
    parent_signature = models.CharField(max_length=100, blank=True, null=True)
    parent_date = models.DateField(blank=True, null=True)
    
    # Report Generation
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_cbe_reports')
    generated_date = models.DateTimeField(default=timezone.now)
    
    # Status
    is_published = models.BooleanField(default=False)
    published_date = models.DateTimeField(blank=True, null=True)
    is_printed = models.BooleanField(default=False)
    printed_date = models.DateTimeField(blank=True, null=True)
    
    # Storage
    report_file_url = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['report_id']),
            models.Index(fields=['student']),
            models.Index(fields=['class_id']),
            models.Index(fields=['academic_year', 'term']),
            models.Index(fields=['is_published']),
        ]
    
    def __str__(self):
        return f"{self.report_type} - {self.student.full_name if self.student else self.class_id.class_name}"

class StudentCredit(BaseModel):
    CREDIT_TYPE_CHOICES = [
        ('EXCESS_PAYMENT', 'Excess Payment'),
        ('REFUND', 'Refund'),
        ('ADJUSTMENT', 'Adjustment'),
        ('DISCOUNT', 'Discount'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='credits')
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    credit_type = models.CharField(max_length=20, choices=CREDIT_TYPE_CHOICES)
    original_transaction = models.ForeignKey(FeeTransaction, on_delete=models.SET_NULL, 
                                           null=True, blank=True, related_name='original_credits')
    credit_date = models.DateField(default=timezone.now)
    credit_expiry = models.DateField()
    is_utilized = models.BooleanField(default=False)
    utilized_date = models.DateField(null=True, blank=True)
    utilized_for_transaction = models.ForeignKey(FeeTransaction, on_delete=models.SET_NULL,
                                               null=True, blank=True, related_name='utilized_credits')
    academic_year = models.CharField(max_length=9, null=True, blank=True)
    term = models.CharField(max_length=20, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['student', 'is_utilized']),
            models.Index(fields=['credit_expiry']),
            models.Index(fields=['student', 'credit_expiry', 'is_utilized']),
        ]
        ordering = ['-credit_date']
    
    def __str__(self):
        return f"Credit {self.id}: {self.student.admission_no} - KSh {self.credit_amount}"
    
    @property
    def is_expired(self):
        return self.credit_expiry < timezone.now().date()
    
    @property
    def is_active(self):
        return not self.is_utilized and not self.is_expired

# ==================== PARENT MODEL ====================
class Parent(BaseModel):
    """Parent/Guardian model for portal access"""
    parent_id = models.CharField(max_length=30, unique=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, 
                               related_name='parent_profile')
    
    # Personal Information
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    relation_to_student = models.CharField(max_length=30)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    occupation = models.CharField(max_length=50, blank=True, null=True)
    
    # Address
    address = models.TextField()
    city = models.CharField(max_length=50)
    country = models.CharField(max_length=50, default='Kenya')
    
    # Students associated with this parent
    students = models.ManyToManyField(Student, related_name='parents')
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['parent_id']),
            models.Index(fields=['phone']),
            models.Index(fields=['email']),
        ]
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.middle_name + ' ' if self.middle_name else ''}{self.last_name}"
    
    def __str__(self):
        return f"{self.full_name} ({self.parent_id})"

class GradeLevel(models.Model):
    """Grade levels for CBC (1-12)"""
    level = models.IntegerField(unique=True, validators=[MinValueValidator(1), MaxValueValidator(12)])
    name = models.CharField(max_length=50)  # e.g., "Grade 1", "Grade 7"
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name


class GradingScale(models.Model):
    """CBC 4-point grading scale with sub-levels"""
    RATING_CHOICES = [
        ('EE', 'Exceeding Expectations'),
        ('ME', 'Meeting Expectations'),
        ('AE', 'Approaching Expectations'),
        ('BE', 'Below Expectations'),
    ]
    
    rating = models.CharField(max_length=2, choices=RATING_CHOICES)
    sub_level = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(2)])  # 1 or 2
    min_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    max_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    points = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(8)])
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['rating', '-sub_level']
    
    def __str__(self):
        return f"{self.rating}{self.sub_level} ({self.min_percentage}% - {self.max_percentage}%)"


class CurriculumMapping(models.Model):
    """Map learning areas to specific grade levels"""
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.CASCADE, related_name='curriculum')
    learning_area = models.ForeignKey(LearningArea, on_delete=models.CASCADE, related_name='grade_mappings')
    is_compulsory = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['grade_level', 'learning_area']
    
    def __str__(self):
        return f"{self.grade_level.name} - {self.learning_area.area_name}"


# ==================== CURRICULUM MANAGEMENT MODELS ====================

class CurriculumVersion(BaseModel):
    """Curriculum version for different academic years"""
    name = models.CharField(max_length=100)
    academic_year = models.CharField(max_length=9)
    is_active = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_curriculum_versions')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['academic_year']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_published']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class LearningOutcome(BaseModel):
    """Learning outcomes for sub-strands"""
    DOMAIN_CHOICES = [
        ('cognitive', 'Cognitive (Knowledge)'),
        ('psychomotor', 'Psychomotor (Skills)'),
        ('affective', 'Affective (Values/Attitudes)'),
    ]
    
    substrand = models.ForeignKey(SubStrand, on_delete=models.CASCADE, related_name='learning_outcomes')
    description = models.TextField()
    domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES, default='cognitive')
    competencies = models.JSONField(default=list, blank=True, help_text="List of competency codes associated")
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['substrand', 'display_order']
        indexes = [
            models.Index(fields=['substrand']),
            models.Index(fields=['domain']),
        ]
    
    def __str__(self):
        return self.description[:100]


class CoreCompetency(BaseModel):
    """KICD Core Competencies (7 competencies)"""
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    indicators = models.JSONField(default=list, blank=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        verbose_name_plural = "Core Competencies"
        ordering = ['display_order', 'code']
    
    def __str__(self):
        return f"{self.code}: {self.name}"


class CoreValue(BaseModel):
    """KICD Core Values (7 values)"""
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=10, blank=True)
    description = models.TextField(blank=True, null=True)
    indicators = models.JSONField(default=list, blank=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name


class WeightConfiguration(BaseModel):
    """SBA vs Summative weight configuration"""
    sba_weight = models.IntegerField(default=40, validators=[MinValueValidator(0), MaxValueValidator(100)])
    exam_weight = models.IntegerField(default=60, validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_weight_configs')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_weight_configs')
    
    class Meta:
        ordering = ['-created_at']
    
    def clean(self):
        if self.sba_weight + self.exam_weight != 100:
            raise ValidationError("SBA weight and Exam weight must add up to 100%")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"SBA: {self.sba_weight}% | Exam: {self.exam_weight}%"

class StudentPortfolio(models.Model):
    """Track student progress on competencies"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='portfolios')
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='student_portfolios')
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    
    # Assessment ratings
    rating = models.CharField(max_length=2, choices=GradingScale.RATING_CHOICES, blank=True, null=True)
    sub_level = models.IntegerField(blank=True, null=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    # Evidence
    evidence_url = models.CharField(max_length=500, blank=True, null=True)
    evidence_type = models.CharField(max_length=50, blank=True, null=True)  # photo, video, document, etc.
    teacher_comment = models.TextField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('assessed', 'Assessed'),
        ('reviewed', 'Reviewed'),
    ], default='pending')
    
    assessed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessed_portfolios')
    assessed_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'competency', 'term', 'academic_year']
    
    def __str__(self):
        return f"{self.student.full_name} - {self.competency.competency_code} - {self.rating}{self.sub_level if self.sub_level else ''}"
    
# Add to your models.py - after the SystemSetting model or create a new one

class FinancialSetting(BaseModel):
    """Financial settings for the school"""
    
    SETTING_TYPES = [
        ('MONTHLY_TARGET', 'Monthly Collection Target'),
        ('YEARLY_TARGET', 'Yearly Collection Target'),
        ('LATE_FEE_PERCENTAGE', 'Default Late Fee Percentage'),
        ('MINIMUM_PAYMENT', 'Minimum Payment Amount'),
        ('DEFAULT_CURRENCY', 'Default Currency'),
    ]
    
    setting_key = models.CharField(max_length=50, choices=SETTING_TYPES, unique=True)
    setting_value = models.DecimalField(max_digits=15, decimal_places=2, default=1000000)
    description = models.TextField(blank=True, null=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Financial Setting'
        verbose_name_plural = 'Financial Settings'
        ordering = ['setting_key']
    
    def __str__(self):
        return f"{self.get_setting_key_display()}: {self.setting_value}"
    
    
    
# ==================== EXAM MANAGEMENT MODELS ====================

class Exam(BaseModel):
    """Main Exam/Assessment Model - Compatible with frontend"""
    
    EXAM_TYPE_CHOICES = [
        ('cba', 'Classroom-Based Assessment (CBA)'),
        ('sba', 'School-Based Assessment (SBA)'),
        ('cat', 'Continuous Assessment Test (CAT)'),
        ('end_term', 'End of Term Exam'),
        ('mock', 'Mock Exam'),
        ('kpsea', 'KPSEA (Grade 6)'),
        ('kjsea', 'KJSEA (Grade 9)'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('marking', 'Marking'),
        ('moderation', 'Moderation'),
        ('published', 'Published'),
        ('archived', 'Archived'),
        ('cancelled', 'Cancelled'),
    ]
    
    GRADE_LEVEL_CHOICES = [
        ('pp1', 'Pre-Primary 1'),
        ('pp2', 'Pre-Primary 2'),
        ('1', 'Grade 1'),
        ('2', 'Grade 2'),
        ('3', 'Grade 3'),
        ('4', 'Grade 4'),
        ('5', 'Grade 5'),
        ('6', 'Grade 6'),
        ('7', 'Grade 7'),
        ('8', 'Grade 8'),
        ('9', 'Grade 9'),
    ]
    
    # Basic Information
    exam_code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES)
    grade_level = models.CharField(max_length=10, choices=GRADE_LEVEL_CHOICES)
    academic_year = models.IntegerField(default=timezone.now().year)
    term = models.IntegerField(choices=[(1, 'Term 1'), (2, 'Term 2'), (3, 'Term 3')], default=1)
    
    # Dates & Duration
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=180)
    
    # Marks
    total_marks = models.IntegerField(default=100)
    passing_marks = models.IntegerField(default=50)
    
    # Status & Workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Content
    instructions = models.TextField(blank=True, null=True)
    subjects = models.JSONField(default=list, blank=True)  # List of subject names
    classes = models.JSONField(default=list, blank=True)   # List of class IDs
    marking_scheme = models.TextField(blank=True, null=True)
    weighting = models.JSONField(default=dict, blank=True)  # {subject: weight}
    
    # Schedule
    room_allocation = models.JSONField(default=list, blank=True)  # [{subject, room, date, time}]
    invigilators = models.JSONField(default=list, blank=True)     # List of teacher IDs
    
    # Audit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_exams')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_exams')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['exam_code']),
            models.Index(fields=['status']),
            models.Index(fields=['exam_type']),
            models.Index(fields=['academic_year', 'term']),
        ]
    
    def __str__(self):
        return f"{self.exam_code} - {self.title}"


class ExamSchedule(BaseModel):
    """Individual subject schedule for an exam"""
    
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='exam_schedules')
    subject = models.CharField(max_length=100)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True, null=True)
    invigilator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='invigilated_schedules')
    class_id = models.CharField(max_length=50, blank=True, null=True)  # Class ID for this schedule
    
    class Meta:
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['exam', 'date']),
            models.Index(fields=['subject']),
        ]
    
    def __str__(self):
        return f"{self.exam.exam_code} - {self.subject} on {self.date}"


class ExamMarker(BaseModel):
    """Teacher assigned to mark a specific exam subject"""
    
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='markers')
    subject = models.CharField(max_length=100)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marking_assignments')
    
    class Meta:
        unique_together = ['exam', 'subject', 'teacher']
    
    def __str__(self):
        return f"{self.exam.exam_code} - {self.subject} - {self.teacher.get_full_name()}"


class ExamModeration(BaseModel):
    """Moderation record for an exam"""
    
    exam = models.OneToOneField(Exam, on_delete=models.CASCADE, related_name='moderation')
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='moderated_exams')
    notes = models.TextField(blank=True, null=True)
    approved = models.BooleanField(default=False)
    moderated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Moderation for {self.exam.exam_code}"


class ExamPermission(BaseModel):
    """Global or exam-specific permissions"""
    
    PERMISSION_TYPE_CHOICES = [
        ('global', 'Global'),
        ('exam', 'Exam Specific'),
    ]
    
    permission_type = models.CharField(max_length=10, choices=PERMISSION_TYPE_CHOICES, default='global')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, null=True, blank=True, related_name='permissions')
    
    # Settings
    school_wide_mark_uploading = models.BooleanField(default=False)
    require_moderation = models.BooleanField(default=True)
    auto_publish = models.BooleanField(default=False)
    
    # Grade level permissions (JSON: {class_id: true/false})
    grade_level_permissions = models.JSONField(default=dict, blank=True)
    
    # Subject teacher permissions (JSON: {subject: [teacher_ids]})
    subject_teacher_permissions = models.JSONField(default=dict, blank=True)
    
    # Scheduled lock
    lock_enabled = models.BooleanField(default=False)
    lock_until = models.DateTimeField(null=True, blank=True)
    
    # Audit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_permissions')
    
    class Meta:
        unique_together = ['permission_type', 'exam']
    
    def __str__(self):
        if self.permission_type == 'global':
            return "Global Exam Permissions"
        return f"Permissions for {self.exam.exam_code}"


class ExamResult(BaseModel):
    """Student results for an exam subject"""
    
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_results')
    subject = models.CharField(max_length=100)
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    grade = models.CharField(max_length=10, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    
    # Marking
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='marked_results')
    marked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['exam', 'student', 'subject']
        indexes = [
            models.Index(fields=['exam', 'student']),
            models.Index(fields=['subject']),
        ]
    
    def save(self, *args, **kwargs):
        # Calculate percentage
        if self.marks_obtained and self.exam.total_marks:
            self.percentage = (self.marks_obtained / self.exam.total_marks) * 100
        
        # Calculate grade based on exam's grade level
        if self.percentage:
            if self.exam.grade_level in ['pp1', 'pp2', '1', '2', '3', '4', '5']:
                # 4-point scale
                if self.percentage >= 90:
                    self.grade = 'EE'
                elif self.percentage >= 75:
                    self.grade = 'ME'
                elif self.percentage >= 58:
                    self.grade = 'AE'
                else:
                    self.grade = 'BE'
            else:
                # 8-point scale
                if self.percentage >= 90:
                    self.grade = 'EE1'
                elif self.percentage >= 75:
                    self.grade = 'EE2'
                elif self.percentage >= 58:
                    self.grade = 'ME1'
                elif self.percentage >= 41:
                    self.grade = 'ME2'
                elif self.percentage >= 31:
                    self.grade = 'AE1'
                elif self.percentage >= 21:
                    self.grade = 'AE2'
                elif self.percentage >= 11:
                    self.grade = 'BE1'
                else:
                    self.grade = 'BE2'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.exam.exam_code} - {self.student.admission_no} - {self.subject}: {self.marks_obtained}"
    
    
class ClassSubjectAllocation(BaseModel):
    academic_year = models.CharField(max_length=9)
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE)
    subject = models.ForeignKey(LearningArea, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='allocated_subjects')
    periods_per_week = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    is_compulsory = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['academic_year', 'class_id', 'subject']
        indexes = [
            models.Index(fields=['teacher']),
        ]