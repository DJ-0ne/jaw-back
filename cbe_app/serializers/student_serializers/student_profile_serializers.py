# cbe_app/serializers/student_serializers/profile_serializers.py

from rest_framework import serializers
from cbe_app.models import Student, User
from datetime import date

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user account information"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'role', 'user_code']
        read_only_fields = ['id', 'username', 'role', 'user_code']


class StudentProfileSerializer(serializers.ModelSerializer):
    """Complete student profile serializer"""
    user = UserProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()
    current_class_name = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    formatted_dob = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            # Basic Info
            'id', 'admission_no', 'student_uid', 'first_name', 'middle_name', 'last_name',
            'full_name', 'date_of_birth', 'formatted_dob', 'age', 'gender', 
            'nationality', 'religion', 'blood_group',
            
            # Contact Info
            'address', 'city', 'country', 'phone', 'email',
            
            # Academic Info
            'current_class', 'current_class_name', 'roll_number',
            'admission_date', 'admission_type', 'status',
            
            # Guardian Info
            'father_name', 'father_phone', 'father_email', 'father_occupation',
            'mother_name', 'mother_phone', 'mother_email', 'mother_occupation',
            'guardian_name', 'guardian_relation', 'guardian_phone', 'guardian_email',
            'guardian_address',
            
            # Medical Info
            'medical_conditions', 'allergies', 'medication',
            'emergency_contact', 'emergency_contact_name',
            
            # User Account
            'user'
        ]
        read_only_fields = ['id', 'admission_no', 'student_uid', 'admission_date', 'user']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_current_class_name(self, obj):
        return obj.current_class.class_name if obj.current_class else 'Not Assigned'
    
    def get_age(self, obj):
        if obj.date_of_birth:
            today = date.today()
            return today.year - obj.date_of_birth.year - (
                (today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day)
            )
        return None
    
    def get_formatted_dob(self, obj):
        if obj.date_of_birth:
            return obj.date_of_birth.strftime('%B %d, %Y')
        return None


class StudentProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating student profile"""
    class Meta:
        model = Student
        fields = [
            'first_name', 'middle_name', 'last_name', 
            'phone', 'email', 'address', 'city', 'country',
            'guardian_phone', 'guardian_email', 'guardian_address',
            'emergency_contact', 'emergency_contact_name',
            'medical_conditions', 'allergies', 'medication'
        ]
    
    def validate_email(self, value):
        """Validate email uniqueness"""
        if value:
            # Check if email is already used by another active student
            student_id = self.instance.id if self.instance else None
            if Student.objects.exclude(id=student_id).filter(
                email=value, archived=False
            ).exists():
                raise serializers.ValidationError(
                    "This email is already in use by another student."
                )
        return value
    
    def validate_phone(self, value):
        """Validate phone number format"""
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise serializers.ValidationError(
                "Phone number should contain only digits, +, - and spaces."
            )
        return value


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user account"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone']
    
    def validate_email(self, value):
        """Validate email uniqueness"""
        if value:
            user_id = self.instance.id if self.instance else None
            if User.objects.exclude(id=user_id).filter(email=value).exists():
                raise serializers.ValidationError("This email is already in use.")
        return value


class ProfileImageSerializer(serializers.Serializer):
    """Serializer for profile image upload"""
    profile_image = serializers.ImageField()
    
    class Meta:
        fields = ['profile_image']


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change"""
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)
    confirm_password = serializers.CharField(required=True)
    
    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("New passwords do not match.")
        if data['current_password'] == data['new_password']:
            raise serializers.ValidationError(
                "New password must be different from current password."
            )
        return data


class ProfileStatsSerializer(serializers.Serializer):
    """Serializer for profile statistics"""
    total_attendance = serializers.IntegerField()
    attendance_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_fees_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    completed_courses = serializers.IntegerField()
    active_courses = serializers.IntegerField()