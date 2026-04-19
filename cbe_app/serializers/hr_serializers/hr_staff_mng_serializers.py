# cbe_app/serializers/hr_serializers/hr_staff_mng_serializers.py

from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal
from cbe_app.models import (
    Staff, TeacherCategory, JSSDepartment, Department, 
    DepartmentStaffAssignment, StaffLeave, LeaveBalance, 
    StaffLoan, LoanRepayment, PayrollComponent, StaffPayrollComponent,
    PayrollPeriod, PayrollRecord, User, GradeLevel, LearningArea
)


# ==================== STAFF SERIALIZERS ====================

class TeacherCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherCategory
        fields = ['id', 'name', 'code', 'description', 'is_active']


class JSSDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = JSSDepartment
        fields = ['id', 'name', 'code', 'description', 'is_active']


class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = ['id', 'level', 'name', 'description']


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'department_code', 'department_name', 'description', 'department_type', 'is_active']


class DepartmentStaffAssignmentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_code = serializers.CharField(source='department.department_code', read_only=True)
    department_type = serializers.CharField(source='department.department_type', read_only=True)
    teaching_subjects = serializers.SerializerMethodField()
    
    class Meta:
        model = DepartmentStaffAssignment
        fields = [
            'id', 'department', 'department_name', 'department_code', 'department_type',
            'role', 'teaching_subjects', 'assigned_date', 'end_date', 
            'is_primary', 'is_active'
        ]
    
    def get_teaching_subjects(self, obj):
        return [{'id': s.id, 'area_name': s.area_name, 'area_code': s.area_code} 
                for s in obj.teaching_subjects.all()]


class StaffListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    full_name = serializers.SerializerMethodField()
    teacher_category_code = serializers.CharField(source='teacher_category.code', read_only=True, allow_null=True)
    teacher_category_name = serializers.CharField(source='teacher_category.name', read_only=True, allow_null=True)
    primary_department = serializers.SerializerMethodField()
    
    class Meta:
        model = Staff
        fields = [
            'id', 'staff_id', 'teacher_code', 'first_name', 'middle_name', 'last_name',
            'full_name', 'designation', 'personal_email', 'personal_phone',
            'status', 'teacher_category_code', 'teacher_category_name',
            'primary_department', 'employment_type', 'gender'
        ]
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_primary_department(self, obj):
        primary = obj.department_assignments.filter(is_primary=True, is_active=True).first()
        if primary:
            return primary.department.department_name
        return None


class StaffDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single staff view"""
    full_name = serializers.SerializerMethodField()
    teacher_category = TeacherCategorySerializer(read_only=True)
    teacher_category_id = serializers.PrimaryKeyRelatedField(
        source='teacher_category', queryset=TeacherCategory.objects.filter(is_active=True),
        write_only=True, required=False, allow_null=True
    )
    jss_department = JSSDepartmentSerializer(read_only=True)
    jss_department_id = serializers.PrimaryKeyRelatedField(
        source='jss_department', queryset=JSSDepartment.objects.filter(is_active=True),
        write_only=True, required=False, allow_null=True
    )
    assigned_grade_level = GradeLevelSerializer(read_only=True)
    assigned_grade_level_id = serializers.PrimaryKeyRelatedField(
        source='assigned_grade_level', queryset=GradeLevel.objects.all(),
        write_only=True, required=False, allow_null=True
    )
    admin_department = DepartmentSerializer(read_only=True)
    admin_department_id = serializers.PrimaryKeyRelatedField(
        source='admin_department', queryset=Department.objects.filter(is_active=True),
        write_only=True, required=False, allow_null=True
    )
    department_assignments = DepartmentStaffAssignmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Staff
        fields = [
            'id', 'staff_id', 'teacher_code', 'user',
            'first_name', 'middle_name', 'last_name', 'full_name',
            'date_of_birth', 'gender', 'national_id',
            'personal_email', 'personal_phone', 'permanent_address',
            'employment_type', 'employment_date', 'contract_end_date',
            'designation', 'status',
            'teacher_category', 'teacher_category_id',
            'jss_department', 'jss_department_id',
            'assigned_grade_level', 'assigned_grade_level_id',
            'admin_department', 'admin_department_id',
            'highest_qualification', 'specialization',
            'department_assignments', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'staff_id', 'teacher_code', 'created_at', 'updated_at']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def validate(self, data):
        """Validate business rules"""
        teacher_category = data.get('teacher_category')
        jss_department = data.get('jss_department')
        assigned_grade_level = data.get('assigned_grade_level')
        
        # JSS teachers must have a JSS department
        if teacher_category and teacher_category.code == 'JSS' and not jss_department:
            raise serializers.ValidationError({
                'jss_department_id': 'JSS teachers must be assigned to a JSS department'
            })
        
        # Non-JSS teachers should not have JSS department
        if teacher_category and teacher_category.code != 'JSS' and jss_department:
            raise serializers.ValidationError({
                'jss_department_id': 'Only JSS teachers can be assigned to JSS departments'
            })
        
        # PP and EP teachers should have grade level assigned
        if teacher_category and teacher_category.code in ['PP', 'EP'] and not assigned_grade_level:
            raise serializers.ValidationError({
                'assigned_grade_level_id': f'{teacher_category.code} teachers must be assigned a grade level'
            })
        
        return data


class StaffCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating staff"""
    
    class Meta:
        model = Staff
        fields = [
            'first_name', 'middle_name', 'last_name', 'date_of_birth', 'gender',
            'national_id', 'personal_email', 'personal_phone', 'permanent_address',
            'employment_type', 'employment_date', 'contract_end_date',
            'designation', 'teacher_category', 'jss_department',
            'assigned_grade_level', 'admin_department',
            'highest_qualification', 'specialization'
        ]
    
    def validate_personal_email(self, value):
        """Check email uniqueness for new staff only"""
        if self.instance is None and Staff.objects.filter(personal_email=value).exists():
            raise serializers.ValidationError("Staff with this email already exists")
        elif self.instance and self.instance.personal_email != value and Staff.objects.filter(personal_email=value).exists():
            raise serializers.ValidationError("Staff with this email already exists")
        return value
    
    def validate_personal_phone(self, value):
        """Check phone uniqueness for new staff only"""
        if self.instance is None and Staff.objects.filter(personal_phone=value).exists():
            raise serializers.ValidationError("Staff with this phone number already exists")
        elif self.instance and self.instance.personal_phone != value and Staff.objects.filter(personal_phone=value).exists():
            raise serializers.ValidationError("Staff with this phone number already exists")
        return value
    
    def validate_national_id(self, value):
        """Check national ID uniqueness for new staff only"""
        if self.instance is None and Staff.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("Staff with this National ID already exists")
        elif self.instance and self.instance.national_id != value and Staff.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("Staff with this National ID already exists")
        return value


# ==================== DEPARTMENT ASSIGNMENT SERIALIZERS ====================

class DepartmentAssignmentSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    teaching_subject_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=LearningArea.objects.filter(is_active=True),
        write_only=True
    )
    teaching_subjects = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = DepartmentStaffAssignment
        fields = [
            'id', 'staff', 'staff_name', 'department', 'department_name',
            'role', 'teaching_subjects', 'teaching_subject_ids',
            'assigned_date', 'end_date', 'is_primary', 'is_active'
        ]
        read_only_fields = ['id', 'assigned_date']
    
    def get_teaching_subjects(self, obj):
        return [{'id': s.id, 'area_name': s.area_name, 'area_code': s.area_code} 
                for s in obj.teaching_subjects.all()]
    
    def validate(self, data):
        """Ensure only one primary department per staff"""
        staff = data.get('staff')
        is_primary = data.get('is_primary', False)
        
        if staff and is_primary:
            existing_primary = DepartmentStaffAssignment.objects.filter(
                staff=staff, is_primary=True, is_active=True
            ).exclude(id=getattr(self.instance, 'id', None))
            
            if existing_primary.exists():
                raise serializers.ValidationError({
                    'is_primary': 'Staff already has a primary department. Set existing primary to false first.'
                })
        
        return data
    
    def create(self, validated_data):
        teaching_subject_ids = validated_data.pop('teaching_subject_ids', [])
        assignment = DepartmentStaffAssignment.objects.create(**validated_data)
        if teaching_subject_ids:
            assignment.teaching_subjects.set(teaching_subject_ids)
        return assignment
    
    def update(self, instance, validated_data):
        teaching_subject_ids = validated_data.pop('teaching_subject_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if teaching_subject_ids is not None:
            instance.teaching_subjects.set(teaching_subject_ids)
        return instance


# ==================== UNASSIGNED STAFF SERIALIZER ====================

class UnassignedStaffSerializer(serializers.ModelSerializer):
    """Serializer for staff without department assignments"""
    full_name = serializers.SerializerMethodField()
    teacher_category_code = serializers.CharField(source='teacher_category.code', read_only=True, allow_null=True)
    teacher_category_name = serializers.CharField(source='teacher_category.name', read_only=True, allow_null=True)
    
    class Meta:
        model = Staff
        fields = [
            'id', 'staff_id', 'teacher_code', 'first_name', 'last_name', 'full_name',
            'designation', 'personal_email', 'personal_phone', 'status',
            'teacher_category_code', 'teacher_category_name'
        ]
    
    def get_full_name(self, obj):
        return obj.full_name


# ==================== LEAVE MANAGEMENT SERIALIZERS ====================

class StaffLeaveSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    staff_id = serializers.CharField(source='staff.staff_id', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True, allow_null=True)
    handover_to_name = serializers.CharField(source='handover_to.full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = StaffLeave
        fields = [
            'id', 'staff', 'staff_name', 'staff_id', 'leave_type',
            'start_date', 'end_date', 'total_days', 'reason',
            'contact_during_leave', 'status', 'applied_date',
            'approved_by', 'approved_by_name', 'approved_date',
            'rejection_reason', 'handover_notes', 'handover_to', 'handover_to_name'
        ]
        read_only_fields = ['id', 'total_days', 'applied_date', 'status']


class LeaveBalanceSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    
    class Meta:
        model = LeaveBalance
        fields = [
            'id', 'staff', 'staff_name', 'leave_year', 'leave_type',
            'total_entitled', 'taken_so_far', 'balance', 'carried_over', 'expires_on'
        ]
        read_only_fields = ['id', 'balance']


# ==================== LOAN MANAGEMENT SERIALIZERS ====================

class StaffLoanSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    staff_id = serializers.CharField(source='staff.staff_id', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True, allow_null=True)
    monthly_installment_display = serializers.DecimalField(
        source='monthly_installment', max_digits=12, decimal_places=2, read_only=True
    )
    
    class Meta:
        model = StaffLoan
        fields = [
            'id', 'loan_id', 'staff', 'staff_name', 'staff_id',
            'loan_type', 'loan_amount', 'interest_rate', 'interest_type',
            'repayment_months', 'reason', 'monthly_installment', 'monthly_installment_display',
            'start_date', 'end_date', 'status', 'approved_amount', 'disbursed_amount',
            'disbursement_date', 'disbursement_method', 'total_paid',
            'total_interest_paid', 'total_principal_paid', 'outstanding_balance',
            'overdue_amount', 'overdue_days', 'applied_date', 'approved_by',
            'approved_by_name', 'approved_date', 'rejection_reason',
            'guarantor_name', 'guarantor_contact', 'security_details'
        ]
        read_only_fields = ['id', 'loan_id', 'total_paid', 'total_interest_paid', 
                           'total_principal_paid', 'outstanding_balance', 'applied_date']


class LoanRepaymentSerializer(serializers.ModelSerializer):
    loan_info = StaffLoanSerializer(source='loan', read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = LoanRepayment
        fields = [
            'id', 'loan', 'loan_info', 'repayment_date', 'amount_paid',
            'principal_amount', 'interest_amount', 'payment_method',
            'payment_reference', 'is_overdue', 'overdue_days',
            'processed_by', 'processed_by_name', 'processed_date', 'remarks'
        ]
        read_only_fields = ['id', 'processed_date']


# ==================== PAYROLL SERIALIZERS ====================

class PayrollComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollComponent
        fields = [
            'id', 'component_code', 'component_name', 'component_type',
            'calculation_type', 'fixed_amount', 'percentage_rate',
            'is_taxable', 'is_pensionable', 'frequency', 'is_active'
        ]


class StaffPayrollComponentSerializer(serializers.ModelSerializer):
    component_details = PayrollComponentSerializer(source='component', read_only=True)
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    
    class Meta:
        model = StaffPayrollComponent
        fields = [
            'id', 'staff', 'staff_name', 'component', 'component_details',
            'custom_amount', 'custom_percentage', 'effective_from',
            'effective_to', 'is_active', 'approved_by', 'approved_date'
        ]


class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = [
            'id', 'period_code', 'period_name', 'start_date', 'end_date',
            'pay_date', 'status', 'total_staff', 'processed_staff',
            'total_gross', 'total_deductions', 'total_net',
            'total_paye', 'total_nssf', 'total_nhif', 'is_locked'
        ]
        read_only_fields = ['period_code']


class PayrollRecordSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    staff_id = serializers.CharField(source='staff.staff_id', read_only=True)
    payroll_period_name = serializers.CharField(source='payroll_period.period_name', read_only=True)
    
    class Meta:
        model = PayrollRecord
        fields = [
            'id', 'payroll_period', 'payroll_period_name', 'staff', 'staff_name', 'staff_id',
            'basic_salary', 'allowances_total', 'overtime_total', 'bonus_total',
            'other_earnings', 'gross_salary', 'paye_tax', 'nssf_deduction',
            'nhif_deduction', 'pension_deduction', 'loan_deductions',
            'other_deductions', 'total_deductions', 'net_salary',
            'payment_status', 'payment_method', 'payment_reference',
            'payment_date', 'days_worked', 'days_absent', 'leave_days',
            'overtime_hours', 'is_calculated', 'is_approved', 'is_paid'
        ]
        read_only_fields = ['gross_salary', 'total_deductions', 'net_salary']


# ==================== STATS SERIALIZER ====================

class StaffStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    onLeave = serializers.IntegerField()
    jss = serializers.IntegerField()
    primary = serializers.IntegerField()
    earlyYears = serializers.IntegerField()
    stem = serializers.IntegerField()
    humanities = serializers.IntegerField()
    languages = serializers.IntegerField()
    technical = serializers.IntegerField()


# ==================== BULK OPERATIONS SERIALIZER ====================

class BulkStaffCreateSerializer(serializers.Serializer):
    staff_members = StaffCreateUpdateSerializer(many=True)
    
    def validate(self, data):
        """Validate all staff members before bulk create"""
        staff_members = data.get('staff_members', [])
        emails = []
        phones = []
        national_ids = []
        
        for idx, staff in enumerate(staff_members):
            email = staff.get('personal_email')
            phone = staff.get('personal_phone')
            national_id = staff.get('national_id')
            
            if email:
                if email in emails:
                    raise serializers.ValidationError(f"Duplicate email at row {idx + 1}: {email}")
                emails.append(email)
            
            if phone:
                if phone in phones:
                    raise serializers.ValidationError(f"Duplicate phone at row {idx + 1}: {phone}")
                phones.append(phone)
            
            if national_id:
                if national_id in national_ids:
                    raise serializers.ValidationError(f"Duplicate National ID at row {idx + 1}: {national_id}")
                national_ids.append(national_id)
        
        return data


# ==================== DEPARTMENT MANAGEMENT SERIALIZERS ====================

class DepartmentListSerializer(serializers.ModelSerializer):
    staff_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = ['id', 'department_code', 'department_name', 'department_type', 'description', 'is_active', 'staff_count']
    
    def get_staff_count(self, obj):
        return obj.staff_assignments.filter(is_active=True).count()
        


class DepartmentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single department view"""
    staff_assignments = DepartmentStaffAssignmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Department
        fields = [
            'id', 'department_code', 'department_name', 'department_type',
            'description', 'is_active', 'staff_assignments', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DepartmentCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating departments"""
    
    class Meta:
        model = Department
        fields = [
            'department_code', 'department_name', 'department_type',
            'description', 'is_active'
        ]
    
    def validate_department_code(self, value):
        """Check code uniqueness for new departments only"""
        value = value.upper()
        if self.instance is None and Department.objects.filter(department_code=value).exists():
            raise serializers.ValidationError("Department with this code already exists")
        elif self.instance and self.instance.department_code != value and Department.objects.filter(department_code=value).exists():
            raise serializers.ValidationError("Department with this code already exists")
        return value
    
    def validate_department_name(self, value):
        """Check name uniqueness for new departments only"""
        if self.instance is None and Department.objects.filter(department_name=value).exists():
            raise serializers.ValidationError("Department with this name already exists")
        elif self.instance and self.instance.department_name != value and Department.objects.filter(department_name=value).exists():
            raise serializers.ValidationError("Department with this name already exists")
        return value