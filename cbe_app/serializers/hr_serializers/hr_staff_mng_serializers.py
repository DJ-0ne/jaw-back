# cbe_app/serializers/hr_serializers/staff_serializers.py

from rest_framework import serializers
from cbe_app.models import Staff, User, StaffLeave, StaffLoan, LoanRepayment, PayrollRecord, PayrollPeriod
from django.contrib.auth.hashers import make_password
from datetime import date, datetime, timedelta
import re
import logging

logger = logging.getLogger(__name__)


# ==================== STAFF SERIALIZERS ====================

class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    reporting_to_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Staff
        fields = [
            'id', 'staff_id', 'first_name', 'last_name', 'full_name', 'age',
            'reporting_to', 'reporting_to_name', 'department', 'designation',
            'personal_email', 'personal_phone', 'status', 'employment_type',
            'basic_salary', 'employment_date', 'date_of_birth', 'national_id',
            'gender', 'marital_status', 'bank_name', 'account_number',
            'kra_pin', 'nssf_no', 'nhif_no', 'emergency_contact',
            'emergency_contact_name', 'permanent_address', 'contract_end_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'staff_id', 'created_at', 'updated_at']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_age(self, obj):
        if obj.date_of_birth:
            today = date.today()
            return today.year - obj.date_of_birth.year - ((today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day))
        return None
    
    def get_reporting_to_name(self, obj):
        if obj.reporting_to:
            return obj.reporting_to.full_name
        return None


class StaffCreateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = Staff
        fields = '__all__'
        read_only_fields = ['id', 'staff_id', 'created_at', 'updated_at', 'created_by', 'updated_by']
    
    def validate(self, data):
        # Check required fields
        required_fields = ['first_name', 'last_name', 'personal_email', 'personal_phone', 'department', 'designation']
        for field in required_fields:
            if not data.get(field):
                raise serializers.ValidationError({field: f"{field} is required"})
        
        # Check if email already exists
        email = data.get('personal_email')
        if email:
            if Staff.objects.filter(personal_email=email).exists():
                raise serializers.ValidationError({'personal_email': 'Email already exists in staff records'})
            if User.objects.filter(email=email).exists():
                raise serializers.ValidationError({'personal_email': 'Email already exists in user accounts'})
        
        return data
    
    def create(self, validated_data):
        # Extract user-related fields
        username = validated_data.pop('username', None)
        password = validated_data.pop('password', None)
        
        # Generate username if not provided
        if not username:
            base_username = f"{validated_data['first_name'].lower()}.{validated_data['last_name'].lower()}"
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
        
        # Generate password if not provided
        if not password:
            password = f"Staff@{validated_data['first_name'][0]}{validated_data['last_name'][0]}123"
        
        # Create user account
        user = User.objects.create(
            username=username,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            email=validated_data.get('personal_email'),
            phone=validated_data.get('personal_phone'),
            role='teacher' if validated_data.get('department') == 'Teaching' else 'staff'
        )
        user.set_password(password)
        user.save()
        
        # Generate staff_id
        year = date.today().year
        count = Staff.objects.filter(employment_date__year=year).count() + 1
        validated_data['staff_id'] = f"STF/{year}/{count:04d}"
        
        # Set default employment date if not provided
        if not validated_data.get('employment_date'):
            validated_data['employment_date'] = date.today()
        
        # Set default status if not provided
        if not validated_data.get('status'):
            validated_data['status'] = 'Active'
        
        # Create staff
        validated_data['user'] = user
        staff = Staff.objects.create(**validated_data)
        
        return staff
    
    def update(self, instance, validated_data):
        # Handle user update
        if 'personal_email' in validated_data and instance.user:
            instance.user.email = validated_data['personal_email']
            instance.user.save()
        
        if 'personal_phone' in validated_data and instance.user:
            instance.user.phone = validated_data['personal_phone']
            instance.user.save()
        
        # Update staff instance
        for attr, value in validated_data.items():
            if attr not in ['username', 'password']:
                setattr(instance, attr, value)
        
        instance.save()
        return instance


class StaffListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Staff
        fields = ['id', 'staff_id', 'first_name', 'last_name', 'full_name', 'department', 
                  'designation', 'personal_email', 'personal_phone', 'status', 
                  'employment_type', 'basic_salary', 'employment_date']
    
    def get_full_name(self, obj):
        return obj.full_name


# ==================== LEAVE SERIALIZERS ====================

class StaffLeaveSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_id = serializers.SerializerMethodField()
    total_days = serializers.SerializerMethodField()
    
    class Meta:
        model = StaffLeave
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'applied_date', 'status']
    
    def get_staff_name(self, obj):
        return obj.staff.full_name
    
    def get_staff_id(self, obj):
        return obj.staff.staff_id
    
    def get_total_days(self, obj):
        return obj.total_days
    
    def validate(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date:
            if start_date > end_date:
                raise serializers.ValidationError("Start date cannot be after end date")
            
            # Check for overlapping leave requests
            existing_leaves = StaffLeave.objects.filter(
                staff=data.get('staff'),
                status__in=['Pending', 'Approved'],
                start_date__lte=end_date,
                end_date__gte=start_date
            )
            if self.instance:
                existing_leaves = existing_leaves.exclude(id=self.instance.id)
            
            if existing_leaves.exists():
                raise serializers.ValidationError("You have an overlapping leave request")
        
        return data


class StaffLeaveCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffLeave
        fields = ['leave_type', 'start_date', 'end_date', 'reason', 'contact_during_leave']
    
    def create(self, validated_data):
        validated_data['staff'] = self.context['staff']
        validated_data['status'] = 'Pending'
        validated_data['applied_date'] = date.today()
        return super().create(validated_data)


# ==================== LOAN SERIALIZERS ====================

class LoanRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanRepayment
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class StaffLoanSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_id = serializers.SerializerMethodField()
    monthly_installment = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()
    repayments = LoanRepaymentSerializer(many=True, read_only=True)
    
    class Meta:
        model = StaffLoan
        fields = '__all__'
        read_only_fields = ['id', 'loan_id', 'created_at', 'updated_at', 'status', 
                           'total_paid', 'total_interest_paid', 'total_principal_paid',
                           'outstanding_balance', 'overdue_amount', 'overdue_days']
    
    def get_staff_name(self, obj):
        return obj.staff.full_name
    
    def get_staff_id(self, obj):
        return obj.staff.staff_id
    
    def get_monthly_installment(self, obj):
        return float(obj.monthly_installment) if obj.monthly_installment else 0
    
    def get_outstanding_balance(self, obj):
        return float(obj.outstanding_balance) if obj.outstanding_balance else obj.loan_amount
    
    def validate(self, data):
        loan_amount = data.get('loan_amount', 0)
        repayment_months = data.get('repayment_months', 1)
        
        if loan_amount <= 0:
            raise serializers.ValidationError("Loan amount must be greater than 0")
        
        if repayment_months <= 0:
            raise serializers.ValidationError("Repayment months must be greater than 0")
        
        # Check if staff already has active loan
        staff = data.get('staff')
        if staff and StaffLoan.objects.filter(staff=staff, status__in=['Approved', 'Active', 'Disbursed']).exists():
            raise serializers.ValidationError("Staff already has an active loan")
        
        return data



class StaffLoanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffLoan
        fields = ['loan_type', 'loan_amount', 'interest_rate', 'repayment_months', 
                'guarantor_name', 'guarantor_contact']
    
    def validate_loan_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Loan amount must be greater than 0")
        return value
    
    def validate_repayment_months(self, value):
        if value <= 0:
            raise serializers.ValidationError("Repayment months must be greater than 0")
        return value
    
    def create(self, validated_data):
        from datetime import date
        import uuid
        
        validated_data['staff'] = self.context['staff']
        validated_data['status'] = 'Pending'
        validated_data['applied_date'] = date.today()
        validated_data['loan_id'] = f"LN-{date.today().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        
        # Calculate monthly installment
        loan_amount = validated_data.get('loan_amount', 0)
        repayment_months = validated_data.get('repayment_months', 1)
        interest_rate = validated_data.get('interest_rate', 0)
        
        if interest_rate and interest_rate > 0:
            total_interest = float(loan_amount) * (float(interest_rate) / 100) * (float(repayment_months) / 12)
            total_repayment = float(loan_amount) + total_interest
            validated_data['monthly_installment'] = total_repayment / repayment_months
        else:
            validated_data['monthly_installment'] = float(loan_amount) / repayment_months
        
        validated_data['outstanding_balance'] = loan_amount
        
        return super().create(validated_data)

# ==================== PAYROLL SERIALIZERS ====================

class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class PayrollRecordSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_id = serializers.SerializerMethodField()
    period_name = serializers.SerializerMethodField()
    
    class Meta:
        model = PayrollRecord
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'gross_salary', 'total_deductions', 'net_salary']
    
    def get_staff_name(self, obj):
        return obj.staff.full_name
    
    def get_staff_id(self, obj):
        return obj.staff.staff_id
    
    def get_period_name(self, obj):
        return obj.payroll_period.period_name if obj.payroll_period else None


# ==================== LEAVE BALANCE SERIALIZER ====================

class LeaveBalanceSerializer(serializers.Serializer):
    annual = serializers.IntegerField()
    sick = serializers.IntegerField()
    maternity = serializers.IntegerField()
    paternity = serializers.IntegerField()
    study = serializers.IntegerField()
    compassionate = serializers.IntegerField()