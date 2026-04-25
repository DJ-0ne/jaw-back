# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Count, Sum, Avg
from django.contrib import messages
from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
import json

from .models import (
    Department, DepartmentStaffAssignment,
    # User Management
    User, UserSession, PasswordHistory,
    
    # Student Management
    Student, StudentAcademicHistory,
    
    # CBE Academic Structure
    AcademicYear, Term, LearningArea, Strand, SubStrand, Competency,
    
    #examination
    Exam, ExamSchedule, ExamMarker, ExamModeration, 
    ExamPermission, ExamResult,
    # Summative Assessment
    AssessmentWindow, SummativeAssessment, SummativeRating, TermlySummary,
    
    # Academics
    Class, ClassSubjectAllocation,CurriculumVersion, LearningOutcome, CoreCompetency, 
    CoreValue, WeightConfiguration,
    
    # E-Learning
    Course, CourseModule, LearningContent, StudentEnrollment, ContentProgress,
    ELearningQuiz, QuizQuestion, QuizAttempt, DiscussionForum, ForumPost,
    
    # Finance
    FeeCategory, FeeStructure, StudentFeeInvoice, InvoiceItem, FeeTransaction,
    GeneralLedger, StudentCredit,FinancialSetting,
    
    # Attendance & Discipline
    AttendanceSession, StudentAttendance, DisciplineCategory, DisciplineIncident,
    StudentDisciplinePoints,ConductRecord, InterventionProgram, InterventionEnrollment,
    CounselingSession, Suspension, DisciplineReport,
    
    # Human Resources
    Staff,  TeacherCategory, JSSDepartment, StaffLeave, LeaveBalance,
    PayrollComponent, StaffPayrollComponent, PayrollPeriod, PayrollRecord,
    StaffLoan, LoanRepayment,
    
    # Library
    BookResource,
    
    # Parent
    Parent,
    
    # System & Audit
    AuditLog, BackupHistory, SystemSetting, Holiday, Notification, Timetable, OTPCode,
    
    # CBE Report Cards
    CBEReportCard,
)

# ==================== ADMIN SITE CONFIGURATION ====================
admin.site.site_header = 'Jawabu School System Administration'
admin.site.site_title = 'Jawabu School Admin'
admin.site.index_title = 'Dashboard'
admin.site.enable_nav_sidebar = True

# ==================== MIXINS ====================

class BaseModelAdmin(admin.ModelAdmin):
    """Base admin class with common functionality"""
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 25
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Filter based on user role/permissions
        return qs
    
    def save_model(self, request, obj, form, change):
        if not change:  # New object
            if hasattr(obj, 'created_by'):
                obj.created_by = request.user
        if hasattr(obj, 'updated_by'):
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)

class ExportCsvMixin:
    """Mixin to add CSV export functionality"""
    def export_as_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse
        
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={meta}.csv'
        writer = csv.writer(response)
        
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])
        
        return response
    
    export_as_csv.short_description = "Export Selected as CSV"

# ==================== USER MANAGEMENT ADMIN ====================

class UserSessionInline(admin.TabularInline):
    model = UserSession
    extra = 0
    readonly_fields = ['access_token', 'refresh_token', 'client_ip', 'user_agent', 
                      'login_time', 'last_activity', 'expires_at', 'revoked']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

class PasswordHistoryInline(admin.TabularInline):
    model = PasswordHistory
    extra = 0
    fk_name = 'user'  # Specify the ForeignKey name since there might be multiple
    readonly_fields = ['password_hash', 'changed_at', 'changed_by']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

# ==================== DEPARTMENT ADMIN ====================

@admin.register(Department)
class DepartmentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['department_code', 'department_name', 'department_type', 
                   'head_of_department', 'staff_count', 'is_active']
    list_filter = ['department_type', 'is_active']
    search_fields = ['department_code', 'department_name', 'description']
    filter_horizontal = ['subjects']
    raw_id_fields = ['head_of_department']
    actions = ['export_as_csv', 'activate_departments', 'deactivate_departments']
    
    fieldsets = (
        ('Department Information', {
            'fields': ('department_code', 'department_name', 'department_type', 'description')
        }),
        ('Academic Subjects', {
            'fields': ('subjects',)
        }),
        ('Leadership', {
            'fields': ('head_of_department',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Audit', {
            'fields': ('id', 'created_at', 'updated_at')
        }),
    )
    
    def staff_count(self, obj):
        return obj.staff_count
    staff_count.short_description = 'Staff Count'
    
    def activate_departments(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} departments activated.')
    activate_departments.short_description = "Activate selected departments"
    
    def deactivate_departments(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} departments deactivated.')
    deactivate_departments.short_description = "Deactivate selected departments"


@admin.register(DepartmentStaffAssignment)
class DepartmentStaffAssignmentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['staff', 'staff_department', 'role', 'is_primary', 'is_active']
    list_filter = ['role', 'is_primary', 'is_active', 'department']
    search_fields = ['staff__first_name', 'staff__last_name', 'staff__staff_id', 'department__department_name']
    raw_id_fields = ['staff', 'department']
    filter_horizontal = ['teaching_subjects']
    actions = ['export_as_csv', 'set_as_primary', 'activate_assignments', 'deactivate_assignments']
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('staff', 'department', 'role')
        }),
        ('Responsibilities', {
            'fields': ('teaching_subjects', 'sports_responsibility')
        }),
        ('Assignment Status', {
            'fields': ('is_primary', 'is_active')
        }),
        ('Audit', {
            'fields': ('id', 'assigned_date', 'created_at', 'updated_at')
        }),
    )
    
    def staff_department(self, obj):
        return obj.department.department_name
    staff_department.short_description = 'Department'
    
    def set_as_primary(self, request, queryset):
        # First, remove primary flag from other assignments for these staff
        for assignment in queryset:
            DepartmentStaffAssignment.objects.filter(
                staff=assignment.staff, 
                is_primary=True
            ).exclude(id=assignment.id).update(is_primary=False)
        
        # Then set selected as primary
        updated = queryset.update(is_primary=True)
        self.message_user(request, f'{updated} assignments set as primary.')
    set_as_primary.short_description = "Set as primary department"
    
    def activate_assignments(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} assignments activated.')
    activate_assignments.short_description = "Activate selected assignments"
    
    def deactivate_assignments(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} assignments deactivated.')
    deactivate_assignments.short_description = "Deactivate selected assignments"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # If this assignment is primary, ensure other assignments for this staff are not primary
        if obj.is_primary:
            DepartmentStaffAssignment.objects.filter(
                staff=obj.staff, 
                is_primary=True
            ).exclude(id=obj.id).update(is_primary=False)

@admin.register(User)
class UserAdmin(BaseUserAdmin, BaseModelAdmin, ExportCsvMixin):
    list_display = ['username', 'email', 'user_code', 'role', 'get_department', 
                   'is_active', 'is_locked', 'mfa_enabled', 'last_login']
    list_filter = ['role', 'is_active', 'mfa_enabled', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'user_code', 'first_name', 'last_name']
    ordering = ['username']
    
    # Define fieldsets WITHOUT department field
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'user_code')}),
        ('Role & Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Security', {'fields': ('mfa_enabled', 'mfa_secret', 'last_password_change', 
                                'failed_attempts', 'locked_until')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    readonly_fields = ['last_login', 'date_joined', 'last_password_change', 
                      'failed_attempts', 'locked_until', 'user_code']
    
    inlines = [UserSessionInline, PasswordHistoryInline]
    actions = ['export_as_csv', 'unlock_accounts', 'enable_mfa', 'disable_mfa']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing object
            return self.readonly_fields + ['username']
        return self.readonly_fields
    
    def get_department(self, obj):
        """Get department from staff profile"""
        if hasattr(obj, 'staff_profile'):
            primary_dept = obj.staff_profile.department_assignments.filter(is_primary=True, is_active=True).first()
            if primary_dept:
                return primary_dept.department.department_name
        return '-'
    get_department.short_description = 'Department'
    get_department.admin_order_field = 'staff_profile__department_assignments__department__department_name'
    
    def unlock_accounts(self, request, queryset):
        updated = queryset.update(failed_attempts=0, locked_until=None)
        self.message_user(request, f'{updated} accounts unlocked successfully.')
    unlock_accounts.short_description = "Unlock selected accounts"
    
    def enable_mfa(self, request, queryset):
        updated = queryset.update(mfa_enabled=True)
        self.message_user(request, f'MFA enabled for {updated} users.')
    enable_mfa.short_description = "Enable MFA for selected users"
    
    def disable_mfa(self, request, queryset):
        updated = queryset.update(mfa_enabled=False, mfa_secret=None)
        self.message_user(request, f'MFA disabled for {updated} users.')
    disable_mfa.short_description = "Disable MFA for selected users"
    
    def is_locked(self, obj):
        return obj.is_locked
    is_locked.boolean = True
    is_locked.short_description = 'Locked'

@admin.register(UserSession)
class UserSessionAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['user', 'login_time', 'last_activity', 'expires_at', 
                   'client_ip', 'revoked']
    list_filter = ['revoked', 'login_time', 'last_activity']
    search_fields = ['user__username', 'client_ip']
    readonly_fields = ['id', 'access_token', 'refresh_token', 'user', 'client_ip', 
                      'user_agent', 'login_time', 'last_activity', 'expires_at', 
                      'created_at', 'updated_at']
    actions = ['export_as_csv', 'revoke_sessions']
    
    def revoke_sessions(self, request, queryset):
        updated = queryset.update(revoked=True)
        self.message_user(request, f'{updated} sessions revoked.')
    revoke_sessions.short_description = "Revoke selected sessions"
    
    def has_add_permission(self, request):
        return False

# ==================== STUDENT MANAGEMENT ADMIN ====================

class StudentAcademicHistoryInline(admin.TabularInline):
    model = StudentAcademicHistory
    extra = 0
    fields = ['academic_year', 'class_id', 'section', 'stream', 'roll_number', 
             'class_teacher', 'promoted']
    raw_id_fields = ['class_teacher']

@admin.register(Student)
class StudentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['admission_no', 'full_name', 'current_class', 'upi_number', 'knec_number',
                   'status', 'gender', 'guardian_phone', 'user_link']
    list_filter = ['status', 'gender', 'current_class', 'admission_type', 
                  'nationality', 'religion']
    search_fields = ['admission_no', 'first_name', 'middle_name', 'last_name', 
                    'upi_number', 'knec_number', 'birth_certificate_no',
                    'guardian_phone', 'guardian_email']
    readonly_fields = ['id', 'student_uid', 'created_at', 'updated_at', 'full_name_display']
    
    fieldsets = (
        ('Student Identification', {
            'fields': ('id', 'student_uid', 'admission_no', 'user', 'full_name_display')
        }),
        ('NEMIS Compliance (Government Identifiers)', {
            'fields': ('upi_number', 'knec_number', 'birth_certificate_no'),
            'classes': ('wide',),
            'description': 'Unique identifiers from NEMIS system - Optional but must be unique if provided'
        }),
        ('Personal Information', {
            'fields': ('first_name', 'middle_name', 'last_name', 'date_of_birth', 
                      'gender', 'nationality', 'religion', 'blood_group')
        }),
        ('Contact Information', {
            'fields': ('address', 'city', 'country', 'phone', 'email')
        }),
        ('Academic Information', {
            'fields': ('current_class', 'admission_date', 'admission_type')
        }),
        ('Status', {
            'fields': ('status', 'status_reason', 'status_changed_date')
        }),
        ('Guardian Information', {
            'fields': ('guardian_name', 'guardian_relation', 'guardian_phone', 
                      'guardian_email', 'guardian_address')
        }),
        ('Parents Information', {
            'fields': ('father_name', 'father_phone', 'father_email', 'father_occupation',
                      'mother_name', 'mother_phone', 'mother_email', 'mother_occupation')
        }),
        ('Medical & Emergency', {
            'fields': ('medical_conditions', 'allergies', 'medication',
                      'emergency_contact_name', 'emergency_contact')
        }),
        ('Previous School', {
            'fields': ('previous_school', 'previous_class', 'transfer_certificate_no')
        }),
        ('Audit', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at',
                      'archived', 'archived_at')
        }),
    )
    
    inlines = [StudentAcademicHistoryInline]
    actions = ['export_as_csv', 'activate_students', 'graduate_students', 
              'withdraw_students', 'generate_user_accounts']
    raw_id_fields = ['user', 'current_class', 'created_by', 'updated_by']
    
    def full_name_display(self, obj):
        return obj.full_name
    full_name_display.short_description = 'Full Name'
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:cbe_app_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = 'User Account'
    
    def activate_students(self, request, queryset):
        updated = queryset.update(status='Active', status_changed_date=timezone.now())
        self.message_user(request, f'{updated} students activated.')
    activate_students.short_description = "Activate selected students"
    
    def graduate_students(self, request, queryset):
        updated = queryset.update(status='Graduated', status_changed_date=timezone.now())
        self.message_user(request, f'{updated} students marked as graduated.')
    graduate_students.short_description = "Graduate selected students"
    
    def withdraw_students(self, request, queryset):
        updated = queryset.update(status='Withdrawn', status_changed_date=timezone.now())
        self.message_user(request, f'{updated} students withdrawn.')
    withdraw_students.short_description = "Withdraw selected students"
    
    def generate_user_accounts(self, request, queryset):
        from django.contrib.auth.hashers import make_password
        import secrets
        
        count = 0
        for student in queryset:
            if not student.user:
                # Create user account
                username = f"student_{student.admission_no.lower().replace('/', '_')}"
                password = secrets.token_urlsafe(8)
                
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=student.email,
                    first_name=student.first_name,
                    last_name=student.last_name,
                    role='student'
                )
                student.user = user
                student.save()
                count += 1
                
                self.message_user(request, f'Created account for {student.full_name} - Username: {username}, Password: {password}', level=messages.INFO)
        
        self.message_user(request, f'Created {count} student user accounts.')
    generate_user_accounts.short_description = "Generate user accounts for selected students"
    
    def save_model(self, request, obj, form, change):
        if not change:  # New student
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(StudentAcademicHistory)
class StudentAcademicHistoryAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'academic_year', 'class_id', 'section', 
                   'roll_number', 'promoted']
    list_filter = ['academic_year', 'promoted', 'class_id']
    search_fields = ['student__admission_no', 'student__first_name', 'student__last_name']
    raw_id_fields = ['student', 'class_id', 'class_teacher']
    actions = ['export_as_csv']

# ==================== CBE ACADEMIC STRUCTURE ADMIN ====================

@admin.register(AcademicYear)
class AcademicYearAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['year_code', 'year_name', 'start_date', 'end_date', 'is_current']
    list_filter = ['is_current']
    search_fields = ['year_code', 'year_name']
    actions = ['export_as_csv', 'set_as_current']
    
    def set_as_current(self, request, queryset):
        # Reset all to False first
        AcademicYear.objects.update(is_current=False)
        # Set selected to True
        updated = queryset.update(is_current=True)
        self.message_user(request, f'{updated} academic year(s) set as current.')
    set_as_current.short_description = "Set as current academic year"

@admin.register(Term)
class TermAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['term', 'academic_year', 'start_date', 'end_date', 'is_current']
    list_filter = ['term', 'academic_year', 'is_current']
    search_fields = ['academic_year__year_name']
    actions = ['export_as_csv', 'set_as_current']
    
    def set_as_current(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Please select only one term to set as current.', level=messages.ERROR)
            return
        
        term = queryset.first()
        # Reset all terms in this academic year
        Term.objects.filter(academic_year=term.academic_year).update(is_current=False)
        # Set selected to True
        term.is_current = True
        term.save()
        self.message_user(request, f'{term} set as current term.')
    set_as_current.short_description = "Set as current term"

class StrandInline(admin.TabularInline):
    model = Strand
    extra = 1
    fields = ['strand_code', 'strand_name', 'display_order']

@admin.register(LearningArea)
class LearningAreaAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['area_code', 'area_name', 'short_name', 'area_type', 'is_active']
    list_filter = ['area_type', 'is_active']
    search_fields = ['area_code', 'area_name', 'short_name']
    inlines = [StrandInline]
    actions = ['export_as_csv', 'activate_areas', 'deactivate_areas']
    
    def activate_areas(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} learning areas activated.')
    activate_areas.short_description = "Activate selected learning areas"
    
    def deactivate_areas(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} learning areas deactivated.')
    deactivate_areas.short_description = "Deactivate selected learning areas"

class SubStrandInline(admin.TabularInline):
    model = SubStrand
    extra = 1
    fields = ['substrand_code', 'substrand_name', 'display_order']

@admin.register(Strand)
class StrandAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['strand_code', 'strand_name', 'learning_area', 'display_order']
    list_filter = ['learning_area']
    search_fields = ['strand_code', 'strand_name']
    inlines = [SubStrandInline]
    actions = ['export_as_csv']

class CompetencyInline(admin.TabularInline):
    model = Competency
    extra = 1
    fields = ['competency_code', 'competency_statement', 'is_core_competency', 'display_order']

@admin.register(SubStrand)
class SubStrandAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['substrand_code', 'substrand_name', 'strand', 'display_order']
    list_filter = ['strand__learning_area']
    search_fields = ['substrand_code', 'substrand_name']
    inlines = [CompetencyInline]
    actions = ['export_as_csv']

@admin.register(Competency)
class CompetencyAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['competency_code', 'short_statement', 'substrand', 'is_core_competency', 'display_order']
    list_filter = ['is_core_competency', 'substrand__strand__learning_area']
    search_fields = ['competency_code', 'competency_statement']
    raw_id_fields = ['substrand']
    actions = ['export_as_csv']
    
    def short_statement(self, obj):
        return obj.competency_statement[:75] + '...' if len(obj.competency_statement) > 75 else obj.competency_statement
    short_statement.short_description = 'Competency Statement'

# ==================== SUMMATIVE ASSESSMENT ADMIN ====================

@admin.register(AssessmentWindow)
class AssessmentWindowAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['assessment_type', 'term', 'weight_percentage', 'open_date', 
                   'close_date', 'is_active']
    list_filter = ['assessment_type', 'is_active', 'term__academic_year']
    search_fields = ['term__term']
    raw_id_fields = ['term']
    actions = ['export_as_csv', 'activate_windows', 'deactivate_windows']
    
    def activate_windows(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} assessment windows activated.')
    activate_windows.short_description = "Activate selected windows"
    
    def deactivate_windows(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} assessment windows deactivated.')
    deactivate_windows.short_description = "Deactivate selected windows"

class SummativeRatingInline(admin.TabularInline):
    model = SummativeRating
    extra = 0
    fields = ['student', 'competency', 'rating', 'teacher_comment', 'rated_by']
    readonly_fields = ['rated_by', 'rated_at', 'modified_at']
    raw_id_fields = ['student', 'competency']
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            # Filter competencies by learning area
            formset.form.base_fields['competency'].queryset = Competency.objects.filter(
                substrand__strand__learning_area=obj.learning_area
            )
        return formset

@admin.register(SummativeAssessment)
class SummativeAssessmentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['assessment_code', 'assessment_window', 'class_id', 
                   'learning_area', 'teacher', 'status']
    list_filter = ['status', 'assessment_window__assessment_type', 'learning_area']
    search_fields = ['assessment_code', 'class_id__class_name', 'teacher__username']
    raw_id_fields = ['assessment_window', 'class_id', 'learning_area', 'teacher', 'competencies']
    inlines = [SummativeRatingInline]
    actions = ['export_as_csv', 'publish_assessments', 'lock_assessments', 'archive_assessments']
    
    fieldsets = (
        ('Assessment Details', {
            'fields': ('id', 'assessment_code', 'assessment_window', 'class_id', 
                      'learning_area', 'teacher')
        }),
        ('Competencies', {
            'fields': ('competencies',)
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def publish_assessments(self, request, queryset):
        updated = queryset.update(status='Published')
        self.message_user(request, f'{updated} assessments published.')
    publish_assessments.short_description = "Publish selected assessments"
    
    def lock_assessments(self, request, queryset):
        updated = queryset.update(status='Locked')
        self.message_user(request, f'{updated} assessments locked.')
    lock_assessments.short_description = "Lock selected assessments"
    
    def archive_assessments(self, request, queryset):
        updated = queryset.update(status='Archived')
        self.message_user(request, f'{updated} assessments archived.')
    archive_assessments.short_description = "Archive selected assessments"

@admin.register(SummativeRating)
class SummativeRatingAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'assessment', 'competency', 'rating', 
                   'internal_value', 'rated_by', 'rated_at']
    list_filter = ['rating', 'assessment__assessment_window__assessment_type']
    search_fields = ['student__admission_no', 'student__first_name', 'student__last_name']
    raw_id_fields = ['assessment', 'student', 'competency', 'rated_by']
    readonly_fields = ['internal_value', 'rated_at', 'modified_at']
    actions = ['export_as_csv']

@admin.register(TermlySummary)
class TermlySummaryAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'term', 'learning_area', 'final_rating', 
                   'progression_status', 'promotion_status', 'is_approved']
    list_filter = ['term', 'final_rating', 'progression_status', 'promotion_status', 'is_approved']
    search_fields = ['student__admission_no', 'student__first_name', 'student__last_name']
    raw_id_fields = ['student', 'term', 'learning_area', 'approved_by']
    readonly_fields = ['final_internal_value', 'final_rating']
    actions = ['export_as_csv', 'approve_summaries']
    
    fieldsets = (
        ('Student & Term', {
            'fields': ('id', 'student', 'term', 'learning_area')
        }),
        ('Weighted Scores', {
            'fields': ('opener_weighted', 'midterm_weighted', 'endterm_weighted')
        }),
        ('Final Results', {
            'fields': ('final_internal_value', 'final_rating')
        }),
        ('Competency Summary', {
            'fields': ('total_competencies', 'be_count', 'ae_count', 'me_count', 'ee_count')
        }),
        ('Status & Flags', {
            'fields': ('flags', 'progression_status', 'promotion_status')
        }),
        ('Feedback', {
            'fields': ('teacher_comment', 'promotion_recommendation')
        }),
        ('Approval', {
            'fields': ('is_approved', 'approved_by', 'approved_at')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def approve_summaries(self, request, queryset):
        updated = queryset.update(is_approved=True, approved_by=request.user, 
                                  approved_at=timezone.now())
        self.message_user(request, f'{updated} summaries approved.')
    approve_summaries.short_description = "Approve selected summaries"

# ==================== ACADEMICS ADMIN ====================

@admin.register(Class)
class ClassAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['class_code', 'class_name', 'numeric_level', 'stream', 
                   'capacity', 'class_teacher', 'is_active']
    list_filter = ['is_active', 'numeric_level']
    search_fields = ['class_code', 'class_name', 'stream']
    raw_id_fields = ['class_teacher']
    actions = ['export_as_csv', 'activate_classes', 'deactivate_classes']
    
    def activate_classes(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} classes activated.')
    activate_classes.short_description = "Activate selected classes"
    
    def deactivate_classes(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} classes deactivated.')
    deactivate_classes.short_description = "Deactivate selected classes"

@admin.register(ClassSubjectAllocation)
class ClassSubjectAllocationAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['academic_year', 'class_id', 'subject', 'teacher', 
                   'periods_per_week', 'is_compulsory']
    list_filter = ['academic_year', 'is_compulsory']
    search_fields = ['class_id__class_name', 'subject__area_name', 'teacher__username']
    raw_id_fields = ['class_id', 'subject', 'teacher']
    actions = ['export_as_csv']

# ==================== E-LEARNING ADMIN ====================

class CourseModuleInline(admin.TabularInline):
    model = CourseModule
    extra = 0
    fields = ['module_title', 'module_order', 'estimated_hours']
    show_change_link = True

@admin.register(Course)
class CourseAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['course_code', 'course_title', 'learning_area', 'class_id',
                   'credit_hours', 'is_published', 'created_by']
    list_filter = ['is_published', 'learning_area']
    search_fields = ['course_code', 'course_title']
    raw_id_fields = ['learning_area', 'class_id', 'created_by']
    inlines = [CourseModuleInline]
    actions = ['export_as_csv', 'publish_courses', 'unpublish_courses']
    
    def publish_courses(self, request, queryset):
        updated = queryset.update(is_published=True, published_date=timezone.now())
        self.message_user(request, f'{updated} courses published.')
    publish_courses.short_description = "Publish selected courses"
    
    def unpublish_courses(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f'{updated} courses unpublished.')
    unpublish_courses.short_description = "Unpublish selected courses"

class LearningContentInline(admin.TabularInline):
    model = LearningContent
    extra = 0
    fields = ['content_title', 'content_type', 'content_order', 'is_published']
    show_change_link = True

@admin.register(CourseModule)
class CourseModuleAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['module_title', 'course', 'module_order', 'estimated_hours']
    list_filter = ['course']
    search_fields = ['module_title', 'course__course_title']
    raw_id_fields = ['course', 'competencies']
    inlines = [LearningContentInline]
    actions = ['export_as_csv']

@admin.register(LearningContent)
class LearningContentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['content_title', 'content_type', 'module', 'content_order', 
                   'is_published', 'created_by']
    list_filter = ['content_type', 'is_published']
    search_fields = ['content_title']
    raw_id_fields = ['module', 'created_by']
    actions = ['export_as_csv']

@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'course', 'enrollment_date', 'enrollment_status',
                   'progress_percentage', 'completed_at']
    list_filter = ['enrollment_status', 'course']
    search_fields = ['student__admission_no', 'student__first_name', 'student__last_name']
    raw_id_fields = ['student', 'course']
    actions = ['export_as_csv']

@admin.register(ContentProgress)
class ContentProgressAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['enrollment', 'content', 'is_completed', 'completed_at',
                   'time_spent_minutes', 'score']
    list_filter = ['is_completed']
    search_fields = ['enrollment__student__admission_no']
    raw_id_fields = ['enrollment', 'content']
    actions = ['export_as_csv']

class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 1
    fields = ['question_text', 'question_type', 'question_order', 'points']

@admin.register(ELearningQuiz)
class ELearningQuizAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['quiz_title', 'content', 'time_limit_minutes', 'max_attempts',
                   'passing_score', 'is_published']
    list_filter = ['is_published']
    search_fields = ['quiz_title']
    raw_id_fields = ['content', 'created_by']
    inlines = [QuizQuestionInline]
    actions = ['export_as_csv']

@admin.register(QuizQuestion)
class QuizQuestionAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['short_question', 'quiz', 'question_type', 'question_order', 'points']
    list_filter = ['question_type']
    search_fields = ['question_text']
    raw_id_fields = ['quiz']
    actions = ['export_as_csv']
    
    def short_question(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    short_question.short_description = 'Question'

@admin.register(QuizAttempt)
class QuizAttemptAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['enrollment', 'quiz', 'attempt_number', 'score', 'percentage',
                   'is_passed', 'completed_at']
    list_filter = ['is_passed', 'quiz']
    search_fields = ['enrollment__student__admission_no']
    raw_id_fields = ['enrollment', 'quiz']
    readonly_fields = ['score', 'percentage', 'is_passed']
    actions = ['export_as_csv']

# ==================== FINANCE ADMIN ====================


@admin.register(FinancialSetting)
class FinancialSettingAdmin(admin.ModelAdmin):
    list_display = ['setting_key', 'setting_value', 'updated_at']
    list_editable = ['setting_value']
    search_fields = ['setting_key']
    readonly_fields = ['updated_at']

@admin.register(FeeCategory)
class FeeCategoryAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['category_code', 'category_name', 'frequency', 
                   'is_mandatory', 'is_active']
    list_filter = ['frequency', 'is_mandatory', 'is_active']
    search_fields = ['category_code', 'category_name']
    actions = ['export_as_csv', 'activate_categories', 'deactivate_categories']
    
    def activate_categories(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} fee categories activated.')
    activate_categories.short_description = "Activate selected categories"
    
    def deactivate_categories(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} fee categories deactivated.')
    deactivate_categories.short_description = "Deactivate selected categories"

@admin.register(FeeStructure)
class FeeStructureAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['academic_year', 'term', 'class_id', 'category', 
                   'amount', 'due_date', 'is_active']
    list_filter = ['academic_year', 'term', 'is_active']
    search_fields = ['class_id__class_name', 'category__category_name']
    raw_id_fields = ['class_id', 'category', 'created_by']
    actions = ['export_as_csv', 'activate_fees', 'deactivate_fees']
    
    def activate_fees(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} fee structures activated.')
    activate_fees.short_description = "Activate selected fee structures"
    
    def deactivate_fees(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} fee structures deactivated.')
    deactivate_fees.short_description = "Deactivate selected fee structures"

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ['fee_structure', 'description', 'quantity', 'unit_price', 
             'amount', 'discount_percentage', 'discount_amount', 'net_amount']
    readonly_fields = ['amount', 'discount_amount', 'net_amount']
    raw_id_fields = ['fee_structure']

@admin.register(StudentFeeInvoice)
class StudentFeeInvoiceAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['invoice_no', 'student', 'academic_year', 'term', 'invoice_date',
                   'due_date', 'total_amount', 'amount_paid', 'balance_amount', 'status']
    list_filter = ['status', 'payment_status', 'academic_year', 'term']
    search_fields = ['invoice_no', 'student__admission_no', 'student__first_name']
    raw_id_fields = ['student', 'created_by', 'cancelled_by']
    readonly_fields = ['invoice_no', 'subtotal', 'discount_amount', 'late_fee_amount',
                      'total_amount', 'amount_paid', 'balance_amount']
    inlines = [InvoiceItemInline]
    actions = ['export_as_csv', 'mark_as_paid', 'mark_as_overdue', 'cancel_invoices']
    
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(status='Paid', payment_status='Fully Paid')
        self.message_user(request, f'{updated} invoices marked as paid.')
    mark_as_paid.short_description = "Mark selected invoices as paid"
    
    def mark_as_overdue(self, request, queryset):
        updated = queryset.update(status='Overdue')
        self.message_user(request, f'{updated} invoices marked as overdue.')
    mark_as_overdue.short_description = "Mark selected invoices as overdue"
    
    def cancel_invoices(self, request, queryset):
        updated = queryset.update(status='Cancelled', cancelled_by=request.user,
                                 cancelled_at=timezone.now())
        self.message_user(request, f'{updated} invoices cancelled.')
    cancel_invoices.short_description = "Cancel selected invoices"

@admin.register(FeeTransaction)
class FeeTransactionAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['transaction_no', 'student', 'payment_date', 'payment_mode',
                   'amount', 'amount_kes', 'status', 'collected_by']
    list_filter = ['status', 'payment_mode', 'currency', 'payment_date']
    search_fields = ['transaction_no', 'student__admission_no', 'payment_reference']
    raw_id_fields = ['invoice', 'student', 'collected_by', 'verified_by', 'reversed_by']
    readonly_fields = ['transaction_no', 'amount_kes']
    actions = ['export_as_csv', 'verify_transactions', 'reverse_transactions']
    
    def verify_transactions(self, request, queryset):
        updated = queryset.update(verified_by=request.user, verified_at=timezone.now())
        self.message_user(request, f'{updated} transactions verified.')
    verify_transactions.short_description = "Verify selected transactions"
    
    def reverse_transactions(self, request, queryset):
        for transaction in queryset:
            transaction.status = 'Reversed'
            transaction.reversed_by = request.user
            transaction.reversed_at = timezone.now()
            transaction.save()
        self.message_user(request, f'{queryset.count()} transactions reversed.')
    reverse_transactions.short_description = "Reverse selected transactions"

@admin.register(StudentCredit)
class StudentCreditAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'credit_amount', 'credit_type', 'credit_date', 
                   'credit_expiry', 'is_utilized', 'is_active']
    list_filter = ['credit_type', 'is_utilized', 'academic_year']
    search_fields = ['student__admission_no', 'student__first_name']
    raw_id_fields = ['student', 'original_transaction', 'utilized_for_transaction']
    actions = ['export_as_csv']
    
    def is_active(self, obj):
        return obj.is_active
    is_active.boolean = True
    is_active.short_description = 'Active'

# ==================== ATTENDANCE & DISCIPLINE ADMIN ====================

class StudentAttendanceInline(admin.TabularInline):
    model = StudentAttendance
    extra = 0
    fields = ['student', 'attendance_status', 'check_in_time', 'check_out_time', 'remarks']
    raw_id_fields = ['student']

@admin.register(AttendanceSession)
class AttendanceSessionAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['session_date', 'session_type', 'class_id', 'subject',
                   'period_number', 'start_time', 'end_time', 'conducted_by']
    list_filter = ['session_type', 'session_date']
    search_fields = ['class_id__class_name']
    raw_id_fields = ['class_id', 'subject', 'conducted_by']
    inlines = [StudentAttendanceInline]
    actions = ['export_as_csv']

@admin.register(StudentAttendance)
class StudentAttendanceAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'session', 'attendance_status', 'check_in_time',
                   'late_minutes', 'recorded_by']
    list_filter = ['attendance_status', 'session__session_date']
    search_fields = ['student__admission_no', 'student__first_name']
    raw_id_fields = ['session', 'student', 'recorded_by']
    actions = ['export_as_csv']

@admin.register(DisciplineCategory)
class DisciplineCategoryAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['category_code', 'category_name', 'severity_level', 
                   'default_points', 'is_active']
    list_filter = ['severity_level', 'is_active']
    search_fields = ['category_code', 'category_name']
    actions = ['export_as_csv']

@admin.register(DisciplineIncident)
class DisciplineIncidentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['incident_code', 'student', 'incident_date', 'category',
                   'reported_by', 'status', 'points_awarded']
    list_filter = ['status', 'category', 'incident_date']
    search_fields = ['incident_code', 'student__admission_no', 'description']
    raw_id_fields = ['student', 'category', 'reported_by', 'assigned_to', 'closed_by']
    actions = ['export_as_csv', 'mark_as_resolved', 'mark_as_closed']
    
    fieldsets = (
        ('Incident Details', {
            'fields': ('id', 'incident_code', 'incident_date', 'incident_time', 
                      'student', 'category', 'reported_by')
        }),
        ('Description', {
            'fields': ('description', 'location', 'witnesses', 'evidence_urls')
        }),
        ('Investigation', {
            'fields': ('status', 'assigned_to', 'investigation_notes')
        }),
        ('Resolution', {
            'fields': ('resolution', 'resolution_date', 'points_awarded')
        }),
        ('Parent Communication', {
            'fields': ('parent_notified', 'parent_notification_date', 'parent_response')
        }),
        ('Audit', {
            'fields': ('closed_by', 'closed_at', 'created_at', 'updated_at')
        }),
    )
    
    def mark_as_resolved(self, request, queryset):
        updated = queryset.update(status='Resolved', resolution_date=timezone.now())
        self.message_user(request, f'{updated} incidents marked as resolved.')
    mark_as_resolved.short_description = "Mark as resolved"
    
    def mark_as_closed(self, request, queryset):
        updated = queryset.update(status='Closed', closed_by=request.user, 
                                  closed_at=timezone.now())
        self.message_user(request, f'{updated} incidents closed.')
    mark_as_closed.short_description = "Mark as closed"

@admin.register(StudentDisciplinePoints)
class StudentDisciplinePointsAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'academic_year', 'term', 'total_points',
                   'warnings_count', 'suspensions_count', 'current_status']
    list_filter = ['academic_year', 'term', 'current_status']
    search_fields = ['student__admission_no', 'student__first_name']
    raw_id_fields = ['student']
    actions = ['export_as_csv']


@admin.register(ConductRecord)
class ConductRecordAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['student', 'academic_year', 'term', 'conduct_grade', 
                   'merits', 'demerits', 'total_points', 'status', 'last_updated']
    list_filter = ['conduct_grade', 'status', 'academic_year', 'term']
    search_fields = ['student__admission_no', 'student__first_name', 'student__last_name']
    raw_id_fields = ['student']
    actions = ['export_as_csv', 'add_merits', 'add_demerits']
    
    fieldsets = (
        ('Student Information', {
            'fields': ('student', 'academic_year', 'term')
        }),
        ('Points Summary', {
            'fields': ('merits', 'demerits', 'total_points')
        }),
        ('Conduct Grade', {
            'fields': ('conduct_grade', 'status')
        }),
        ('Remarks', {
            'fields': ('remarks',)
        }),
        ('Audit', {
            'fields': ('id', 'last_updated', 'created_at', 'updated_at')
        }),
    )
    
    def add_merits(self, request, queryset):
        for record in queryset:
            record.merits += 5
            record.save()
        self.message_user(request, f'Added 5 merits to {queryset.count()} record(s).')
    add_merits.short_description = "Add 5 merits"
    
    def add_demerits(self, request, queryset):
        for record in queryset:
            record.demerits += 5
            record.save()
        self.message_user(request, f'Added 5 demerits to {queryset.count()} record(s).')
    add_demerits.short_description = "Add 5 demerits"


@admin.register(InterventionProgram)
class InterventionProgramAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['program_code', 'program_name', 'program_type', 'facilitator',
                   'max_students', 'status', 'start_date', 'end_date']
    list_filter = ['program_type', 'status']
    search_fields = ['program_code', 'program_name', 'facilitator']
    actions = ['export_as_csv', 'activate_programs', 'complete_programs']
    
    fieldsets = (
        ('Program Details', {
            'fields': ('program_code', 'program_name', 'program_type', 'description')
        }),
        ('Schedule', {
            'fields': ('duration_weeks', 'start_date', 'end_date')
        }),
        ('Resources', {
            'fields': ('facilitator', 'max_students')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )
    
    def activate_programs(self, request, queryset):
        updated = queryset.update(status='Active')
        self.message_user(request, f'{updated} program(s) activated.')
    activate_programs.short_description = "Activate selected programs"
    
    def complete_programs(self, request, queryset):
        updated = queryset.update(status='Completed')
        self.message_user(request, f'{updated} program(s) marked as completed.')
    complete_programs.short_description = "Mark as completed"


@admin.register(InterventionEnrollment)
class InterventionEnrollmentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['program', 'student', 'enrollment_date', 'completion_date', 
                   'status', 'progress_percentage']
    list_filter = ['status', 'program__program_type']
    search_fields = ['program__program_name', 'student__admission_no', 'student__first_name']
    raw_id_fields = ['program', 'student']
    actions = ['export_as_csv', 'update_progress']
    
    def update_progress(self, request, queryset):
        for enrollment in queryset:
            if enrollment.progress_percentage < 100:
                enrollment.progress_percentage = min(100, enrollment.progress_percentage + 10)
                if enrollment.progress_percentage == 100:
                    enrollment.status = 'Completed'
                    enrollment.completion_date = timezone.now().date()
                enrollment.save()
        self.message_user(request, f'Updated progress for {queryset.count()} enrollment(s).')
    update_progress.short_description = "Increase progress by 10%"


@admin.register(CounselingSession)
class CounselingSessionAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['session_code', 'student', 'counselor', 'session_type',
                   'session_date', 'session_time', 'status', 'follow_up_needed']
    list_filter = ['session_type', 'status', 'follow_up_needed', 'session_date']
    search_fields = ['session_code', 'student__admission_no', 'student__first_name', 
                    'counselor__username']
    raw_id_fields = ['student', 'counselor', 'created_by']
    actions = ['export_as_csv', 'mark_as_completed', 'mark_as_no_show']
    
    fieldsets = (
        ('Session Details', {
            'fields': ('session_code', 'student', 'counselor', 'session_type')
        }),
        ('Schedule', {
            'fields': ('session_date', 'session_time', 'duration_minutes')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Notes & Follow-up', {
            'fields': ('notes', 'follow_up_needed', 'follow_up_date')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='Completed')
        self.message_user(request, f'{updated} session(s) marked as completed.')
    mark_as_completed.short_description = "Mark as completed"
    
    def mark_as_no_show(self, request, queryset):
        updated = queryset.update(status='No Show')
        self.message_user(request, f'{updated} session(s) marked as no show.')
    mark_as_no_show.short_description = "Mark as no show"


@admin.register(Suspension)
class SuspensionAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['suspension_code', 'student', 'suspension_type', 'start_date',
                   'end_date', 'total_days', 'status', 'parent_notified']
    list_filter = ['suspension_type', 'status', 'parent_notified']
    search_fields = ['suspension_code', 'student__admission_no', 'student__first_name']
    raw_id_fields = ['student', 'incident', 'assigned_by']
    actions = ['export_as_csv', 'complete_suspensions', 'notify_parents']
    
    fieldsets = (
        ('Suspension Details', {
            'fields': ('suspension_code', 'student', 'incident', 'suspension_type')
        }),
        ('Duration', {
            'fields': ('start_date', 'end_date', 'total_days')
        }),
        ('Reason', {
            'fields': ('reason',)
        }),
        ('Assignment', {
            'fields': ('assigned_by',)
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Parent Communication', {
            'fields': ('parent_notified', 'parent_notification_date', 'reentry_meeting_date')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('id', 'created_at', 'updated_at')
        }),
    )
    
    def complete_suspensions(self, request, queryset):
        updated = queryset.update(status='Completed')
        self.message_user(request, f'{updated} suspension(s) marked as completed.')
    complete_suspensions.short_description = "Mark as completed"
    
    def notify_parents(self, request, queryset):
        updated = queryset.update(parent_notified=True, parent_notification_date=timezone.now().date())
        self.message_user(request, f'Parent notification recorded for {updated} suspension(s).')
    notify_parents.short_description = "Mark parent as notified"


@admin.register(DisciplineReport)
class DisciplineReportAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['report_code', 'title', 'report_type', 'generated_by',
                   'generated_date', 'date_range_start', 'date_range_end', 
                   'format', 'download_count']
    list_filter = ['report_type', 'format', 'generated_date']
    search_fields = ['report_code', 'title', 'generated_by__username']
    readonly_fields = ['generated_date', 'download_count']
    actions = ['export_as_csv', 'increment_download_count']
    
    fieldsets = (
        ('Report Details', {
            'fields': ('report_code', 'title', 'report_type')
        }),
        ('Date Range', {
            'fields': ('date_range_start', 'date_range_end')
        }),
        ('Generation', {
            'fields': ('generated_by', 'generated_date', 'format')
        }),
        ('Content Options', {
            'fields': ('includes_charts', 'includes_summary')
        }),
        ('File Information', {
            'fields': ('file_url', 'file_size')
        }),
        ('Statistics', {
            'fields': ('download_count', 'status')
        }),
        ('Audit', {
            'fields': ('id', 'created_at', 'updated_at')
        }),
    )
    
    def increment_download_count(self, request, queryset):
        for report in queryset:
            report.download_count += 1
            report.save()
        self.message_user(request, f'Download count incremented for {queryset.count()} report(s).')
    increment_download_count.short_description = "Increment download count"
    
# ==================== HR & STAFF MANAGEMENT ADMIN ====================

@admin.register(TeacherCategory)
class TeacherCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']
    ordering = ['code']


@admin.register(JSSDepartment)
class JSSDepartmentAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']
    ordering = ['name']


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['staff_id', 'teacher_code', 'full_name', 'teacher_category', 'jss_department', 'status', 'employment_type']
    list_filter = ['status', 'employment_type', 'teacher_category', 'gender']
    search_fields = ['staff_id', 'teacher_code', 'first_name', 'last_name', 'personal_email', 'personal_phone', 'national_id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'teacher_code']
    raw_id_fields = ['user', 'teacher_category', 'jss_department', 'assigned_grade_level', 'admin_department', 'created_by', 'updated_by']
    
    fieldsets = (
        ('Identification', {
            'fields': ('staff_id', 'teacher_code', 'user', 'first_name', 'middle_name', 'last_name', 'date_of_birth', 'gender')
        }),
        ('Contact & ID', {
            'fields': ('personal_email', 'personal_phone', 'permanent_address', 'national_id')
        }),
        ('Employment', {
            'fields': ('employment_type', 'employment_date', 'contract_end_date', 'designation', 'status')
        }),
        ('CBE Teacher Categorization', {
            'fields': ('teacher_category', 'jss_department', 'assigned_grade_level', 'admin_department'),
            'classes': ('collapse',)
        }),
        ('Qualifications', {
            'fields': ('highest_qualification', 'specialization'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Full Name'


@admin.register(StaffLeave)
class StaffLeaveAdmin(admin.ModelAdmin):
    list_display = ['staff', 'leave_type', 'start_date', 'end_date', 'total_days', 'status', 'applied_date']
    list_filter = ['status', 'leave_type']
    search_fields = ['staff__staff_id', 'staff__first_name', 'staff__last_name', 'reason']
    raw_id_fields = ['staff', 'approved_by', 'handover_to']
    readonly_fields = ['id', 'created_at', 'updated_at', 'total_days', 'applied_date']
    
    fieldsets = (
        ('Leave Details', {
            'fields': ('staff', 'leave_type', 'start_date', 'end_date', 'total_days', 'reason', 'contact_during_leave')
        }),
        ('Approval', {
            'fields': ('status', 'approved_by', 'approved_date', 'rejection_reason')
        }),
        ('Handover', {
            'fields': ('handover_notes', 'handover_to')
        }),
    )


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ['staff', 'leave_year', 'leave_type', 'total_entitled', 'taken_so_far', 'balance', 'carried_over']
    list_filter = ['leave_year', 'leave_type']
    search_fields = ['staff__staff_id', 'staff__first_name', 'staff__last_name']
    raw_id_fields = ['staff']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(PayrollComponent)
class PayrollComponentAdmin(admin.ModelAdmin):
    list_display = ['component_code', 'component_name', 'component_type', 'calculation_type', 'is_active']
    list_filter = ['component_type', 'calculation_type', 'is_active', 'frequency', 'is_taxable']
    search_fields = ['component_code', 'component_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['created_by']


@admin.register(StaffPayrollComponent)
class StaffPayrollComponentAdmin(admin.ModelAdmin):
    list_display = ['staff', 'component', 'is_active']
    list_filter = ['is_active']
    search_fields = ['staff__staff_id', 'staff__first_name', 'staff__last_name', 'component__component_code']
    raw_id_fields = ['staff', 'component', 'approved_by', 'created_by']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ['period_code', 'period_name', 'start_date', 'end_date', 'pay_date', 'status', 'total_staff']
    list_filter = ['status', 'is_locked']
    search_fields = ['period_code', 'period_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'total_gross', 'total_deductions', 'total_net', 'total_paye', 'total_nssf', 'total_nhif']
    raw_id_fields = ['processed_by', 'approved_by', 'closed_by', 'locked_by']


@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    list_display = ['payroll_period', 'staff', 'gross_salary', 'net_salary', 'payment_status', 'is_paid']
    list_filter = ['payment_status', 'is_paid', 'is_calculated', 'is_approved']
    search_fields = ['staff__staff_id', 'staff__first_name', 'staff__last_name', 'payroll_period__period_code']
    raw_id_fields = ['payroll_period', 'staff', 'approved_by', 'calculated_by', 'paid_by']
    readonly_fields = ['id', 'created_at', 'updated_at', 'gross_salary', 'total_deductions', 'net_salary']


@admin.register(StaffLoan)
class StaffLoanAdmin(admin.ModelAdmin):
    list_display = ['loan_id', 'staff', 'loan_type', 'loan_amount', 'status', 'outstanding_balance']
    list_filter = ['status', 'loan_type', 'interest_type']
    search_fields = ['loan_id', 'staff__staff_id', 'staff__first_name', 'staff__last_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'loan_id', 'outstanding_balance']
    raw_id_fields = ['staff', 'approved_by', 'created_by']


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = ['loan', 'repayment_date', 'amount_paid', 'principal_amount', 'interest_amount', 'is_overdue']
    list_filter = ['is_overdue', 'payment_method']
    search_fields = ['loan__loan_id', 'loan__staff__staff_id']
    raw_id_fields = ['loan', 'processed_by']
    readonly_fields = ['id', 'created_at', 'updated_at', 'processed_date']

# ==================== LIBRARY ADMIN ====================

@admin.register(BookResource)
class BookResourceAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['title', 'authors', 'isbn', 'school_code', 'accession_number',
                   'subject', 'total_copies', 'available_copies', 'condition_status']
    list_filter = ['book_category', 'condition_status', 'language', 'subject']
    search_fields = ['title', 'authors', 'isbn', 'school_code']
    raw_id_fields = ['subject', 'added_by']
    filter_horizontal = ['grade_levels']
    actions = ['export_as_csv']
    
    fieldsets = (
        ('Identification', {
            'fields': ('id', 'isbn', 'school_code', 'accession_number')
        }),
        ('Basic Information', {
            'fields': ('title', 'authors', 'publisher', 'edition', 'year_of_publication',
                      'language')
        }),
        ('Classification', {
            'fields': ('subject', 'grade_levels', 'book_category')
        }),
        ('Physical Details', {
            'fields': ('shelf_location', 'call_number', 'pages', 'price')
        }),
        ('Inventory', {
            'fields': ('total_copies', 'available_copies', 'reserved_copies', 'condition_status')
        }),
        ('Digital Resources', {
            'fields': ('digital_file_url', 'thumbnail_url', 'has_digital_version')
        }),
        ('Metadata', {
            'fields': ('keywords', 'summary', 'table_of_contents')
        }),
        ('Status', {
            'fields': ('is_active', 'is_reference_only')
        }),
        ('Audit', {
            'fields': ('added_by', 'added_date', 'created_at', 'updated_at')
        }),
    )

# ==================== PARENT ADMIN ====================

@admin.register(Parent)
class ParentAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['parent_id', 'full_name', 'relation_to_student', 'phone',
                   'email', 'user_link', 'is_active']
    list_filter = ['is_active', 'relation_to_student']
    search_fields = ['parent_id', 'first_name', 'last_name', 'phone', 'email']
    raw_id_fields = ['user']
    filter_horizontal = ['students']
    actions = ['export_as_csv', 'activate_parents', 'deactivate_parents']
    
    fieldsets = (
        ('Parent Identification', {
            'fields': ('id', 'parent_id', 'user')
        }),
        ('Personal Information', {
            'fields': ('first_name', 'middle_name', 'last_name', 'relation_to_student')
        }),
        ('Contact', {
            'fields': ('phone', 'email', 'occupation')
        }),
        ('Address', {
            'fields': ('address', 'city', 'country')
        }),
        ('Associated Students', {
            'fields': ('students',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Full Name'
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:cbe_app_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = 'User Account'
    
    def activate_parents(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} parents activated.')
    activate_parents.short_description = "Activate selected parents"
    
    def deactivate_parents(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} parents deactivated.')
    deactivate_parents.short_description = "Deactivate selected parents"

# ==================== SYSTEM & AUDIT ADMIN ====================

@admin.register(AuditLog)
class AuditLogAdmin(BaseModelAdmin):
    list_display = ['event_time', 'event_type', 'username', 'user_role',
                   'table_name', 'operation', 'ip_address']
    list_filter = ['event_type', 'user_role', 'operation', 'event_time']
    search_fields = ['username', 'table_name', 'ip_address']
    readonly_fields = ['id', 'event_time', 'event_type', 'user', 'username',
                      'user_role', 'table_name', 'record_id', 'operation',
                      'old_values', 'new_values', 'changed_fields', 'ip_address',
                      'user_agent', 'endpoint', 'http_method', 'request_id',
                      'created_at', 'updated_at']
    actions = ['export_as_csv']
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(BackupHistory)
class BackupHistoryAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['backup_name', 'backup_type', 'backup_start', 'backup_end',
                   'file_size', 'status', 'verification_status']
    list_filter = ['backup_type', 'status', 'verification_status', 'backup_start']
    search_fields = ['backup_name']
    readonly_fields = ['id', 'file_path', 'file_size', 'database_version',
                      'backup_start', 'backup_end', 'status', 'verification_status',
                      'verification_time', 'error_message', 'expires_on']
    actions = ['export_as_csv', 'create_backup']
    
    def create_backup(self, request, queryset):
        # This would trigger a backup creation
        self.message_user(request, 'Backup creation initiated.')
    create_backup.short_description = "Create new backup"
    
    def has_add_permission(self, request):
        return False

@admin.register(SystemSetting)
class SystemSettingAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['setting_key', 'setting_value_preview', 'setting_type',
                   'category', 'is_public', 'requires_restart']
    list_filter = ['setting_type', 'category', 'is_public', 'requires_restart']
    search_fields = ['setting_key', 'description']
    raw_id_fields = ['updated_by']
    actions = ['export_as_csv']
    
    def setting_value_preview(self, obj):
        if obj.setting_type == 'Encrypted':
            return '[ENCRYPTED]'
        return obj.setting_value[:50] + '...' if len(obj.setting_value) > 50 else obj.setting_value
    setting_value_preview.short_description = 'Setting Value'

@admin.register(Holiday)
class HolidayAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['holiday_date', 'holiday_name', 'holiday_type', 'is_working_day']
    list_filter = ['holiday_type', 'is_working_day', 'academic_year']
    search_fields = ['holiday_name']
    actions = ['export_as_csv']

@admin.register(Notification)
class NotificationAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['title', 'notification_type', 'recipient_type', 'priority',
                   'status', 'sent_at']
    list_filter = ['notification_type', 'recipient_type', 'priority', 'status']
    search_fields = ['title', 'message']
    raw_id_fields = ['sent_by']
    actions = ['export_as_csv', 'mark_as_read', 'archive_notifications']
    
    def mark_as_read(self, request, queryset):
        updated = queryset.update(status='Read', read_at=timezone.now())
        self.message_user(request, f'{updated} notifications marked as read.')
    mark_as_read.short_description = "Mark as read"
    
    def archive_notifications(self, request, queryset):
        updated = queryset.update(status='Archived')
        self.message_user(request, f'{updated} notifications archived.')
    archive_notifications.short_description = "Archive selected notifications"

@admin.register(Timetable)
class TimetableAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['class_id', 'day_display', 'period', 'subject', 'teacher', 'room']
    list_filter = ['academic_year', 'term', 'day_of_week', 'class_id']
    search_fields = ['class_id__class_name', 'subject__area_name', 'teacher__username']
    raw_id_fields = ['class_id', 'subject', 'teacher']
    actions = ['export_as_csv']
    
    def day_display(self, obj):
        return obj.get_day_of_week_display()
    day_display.short_description = 'Day'
    day_display.admin_order_field = 'day_of_week'

# ==================== CBE REPORT CARDS ADMIN ====================

@admin.register(CBEReportCard)
class CBEReportCardAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['report_id', 'report_type', 'student', 'class_id', 'teacher',
                   'academic_year', 'term', 'reporting_date', 'is_published']
    list_filter = ['report_type', 'academic_year', 'term', 'is_published']
    search_fields = ['report_id', 'student__first_name', 'student__last_name']
    raw_id_fields = ['student', 'class_id', 'teacher', 'generated_by']
    actions = ['export_as_csv', 'publish_reports', 'generate_pdf']
    
    fieldsets = (
        ('Report Details', {
            'fields': ('id', 'report_id', 'report_type')
        }),
        ('Scope', {
            'fields': ('student', 'class_id', 'teacher')
        }),
        ('Period', {
            'fields': ('academic_year', 'term', 'reporting_date')
        }),
        ('Learner Details', {
            'fields': ('learner_photo_url', 'learner_attendance_summary')
        }),
        ('Performance Data', {
            'fields': ('learning_area_performance', 'competency_summary',
                      'core_competencies', 'values_assessment')
        }),
        ('Remarks', {
            'fields': ('teacher_remarks', 'head_teacher_remarks', 'head_teacher_signature')
        }),
        ('Parent Feedback', {
            'fields': ('parent_feedback_section', 'parent_signature', 'parent_date')
        }),
        ('Publication', {
            'fields': ('is_published', 'published_date', 'is_printed', 'printed_date')
        }),
        ('Generation', {
            'fields': ('generated_by', 'generated_date')
        }),
        ('Storage', {
            'fields': ('report_file_url',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def publish_reports(self, request, queryset):
        updated = queryset.update(is_published=True, published_date=timezone.now())
        self.message_user(request, f'{updated} reports published.')
    publish_reports.short_description = "Publish selected reports"
    
    def generate_pdf(self, request, queryset):
        # This would trigger PDF generation
        self.message_user(request, f'PDF generation initiated for {queryset.count()} reports.')
    generate_pdf.short_description = "Generate PDF for selected reports"


@admin.register(GeneralLedger)
class GeneralLedgerAdmin(BaseModelAdmin, ExportCsvMixin):
    list_display = ['gl_date', 'account_code', 'account_name', 'debit_amount', 
                   'credit_amount', 'description', 'reference_no']
    list_filter = ['gl_date', 'account_code']
    search_fields = ['account_code', 'account_name', 'description']
    raw_id_fields = ['created_by']
    actions = ['export_as_csv']

    
# Register new models
@admin.register(CurriculumVersion)
class CurriculumVersionAdmin(admin.ModelAdmin):
    list_display = ['name', 'academic_year', 'is_active', 'is_published', 'created_at']
    list_filter = ['is_active', 'is_published']
    search_fields = ['name', 'academic_year']


@admin.register(LearningOutcome)
class LearningOutcomeAdmin(admin.ModelAdmin):
    list_display = ['description', 'substrand', 'domain']
    list_filter = ['domain']
    search_fields = ['description', 'substrand__substrand_name']
    raw_id_fields = ['substrand']


@admin.register(CoreCompetency)
class CoreCompetencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']


@admin.register(CoreValue)
class CoreValueAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code']


@admin.register(WeightConfiguration)
class WeightConfigurationAdmin(admin.ModelAdmin):
    list_display = ['sba_weight', 'exam_weight', 'is_active', 'created_at']
    list_filter = ['is_active']
    
###############################EXAM ADMIN################################
    
@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['exam_code', 'title', 'exam_type', 'grade_level', 'academic_year', 'term', 'status', 'created_at']
    list_filter = ['status', 'exam_type', 'grade_level', 'academic_year', 'term']
    search_fields = ['exam_code', 'title']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('exam_code', 'title', 'exam_type', 'grade_level', 'academic_year', 'term')
        }),
        ('Dates & Duration', {
            'fields': ('start_date', 'end_date', 'duration_minutes')
        }),
        ('Marks', {
            'fields': ('total_marks', 'passing_marks')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Content', {
            'fields': ('instructions', 'subjects', 'classes', 'marking_scheme', 'weighting')
        }),
        ('Schedule', {
            'fields': ('room_allocation', 'invigilators')
        }),
        ('Audit', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ['exam_link', 'subject', 'date', 'start_time', 'end_time', 'room', 'invigilator_link']
    list_filter = ['date', 'subject']
    search_fields = ['exam__exam_code', 'subject', 'room']
    raw_id_fields = ['exam', 'invigilator']
    
    def exam_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:cbe_app_exam_change', args=[obj.exam.id])
        return format_html('<a href="{}">{}</a>', url, obj.exam.exam_code)
    exam_link.short_description = 'Exam'
    
    def invigilator_link(self, obj):
        if obj.invigilator:
            from django.urls import reverse
            url = reverse('admin:cbe_app_user_change', args=[obj.invigilator.id])
            return format_html('<a href="{}">{}</a>', url, obj.invigilator.get_full_name())
        return '-'
    invigilator_link.short_description = 'Invigilator'


@admin.register(ExamMarker)
class ExamMarkerAdmin(admin.ModelAdmin):
    list_display = ['exam_link', 'subject', 'teacher_link']
    list_filter = ['subject']
    search_fields = ['exam__exam_code', 'subject', 'teacher__first_name', 'teacher__last_name']
    raw_id_fields = ['exam', 'teacher']
    
    def exam_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:cbe_app_exam_change', args=[obj.exam.id])
        return format_html('<a href="{}">{}</a>', url, obj.exam.exam_code)
    exam_link.short_description = 'Exam'
    
    def teacher_link(self, obj):
        if obj.teacher:
            from django.urls import reverse
            url = reverse('admin:cbe_app_user_change', args=[obj.teacher.id])
            return format_html('<a href="{}">{}</a>', url, obj.teacher.get_full_name())
        return '-'
    teacher_link.short_description = 'Teacher'


@admin.register(ExamModeration)
class ExamModerationAdmin(admin.ModelAdmin):
    list_display = ['exam_link', 'moderator_link', 'approved', 'moderated_at']
    list_filter = ['approved']
    search_fields = ['exam__exam_code', 'notes']
    raw_id_fields = ['exam', 'moderator']
    readonly_fields = ['moderated_at']
    
    def exam_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:cbe_app_exam_change', args=[obj.exam.id])
        return format_html('<a href="{}">{}</a>', url, obj.exam.exam_code)
    exam_link.short_description = 'Exam'
    
    def moderator_link(self, obj):
        if obj.moderator:
            from django.urls import reverse
            url = reverse('admin:cbe_app_user_change', args=[obj.moderator.id])
            return format_html('<a href="{}">{}</a>', url, obj.moderator.get_full_name())
        return '-'
    moderator_link.short_description = 'Moderator'


@admin.register(ExamPermission)
class ExamPermissionAdmin(admin.ModelAdmin):
    list_display = ['permission_type', 'exam_link', 'school_wide_mark_uploading', 'require_moderation', 'lock_enabled']
    list_filter = ['permission_type', 'school_wide_mark_uploading', 'require_moderation', 'lock_enabled']
    raw_id_fields = ['exam', 'created_by']
    
    def exam_link(self, obj):
        if obj.exam:
            from django.urls import reverse
            url = reverse('admin:cbe_app_exam_change', args=[obj.exam.id])
            return format_html('<a href="{}">{}</a>', url, obj.exam.exam_code)
        return 'Global'
    exam_link.short_description = 'Exam'


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ['exam_link', 'student_link', 'subject', 'marks_obtained', 'percentage', 'grade']
    list_filter = ['subject', 'grade']
    search_fields = ['exam__exam_code', 'student__admission_no', 'student__first_name', 'student__last_name', 'subject']
    raw_id_fields = ['exam', 'student', 'marked_by']
    readonly_fields = ['percentage', 'marked_at']
    
    def exam_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:cbe_app_exam_change', args=[obj.exam.id])
        return format_html('<a href="{}">{}</a>', url, obj.exam.exam_code)
    exam_link.short_description = 'Exam'
    
    def student_link(self, obj):
        if obj.student:
            from django.urls import reverse
            url = reverse('admin:cbe_app_student_change', args=[obj.student.id])
            return format_html('<a href="{}">{}</a>', url, obj.student.full_name)
        return '-'
    student_link.short_description = 'Student'