# serializers.py - Add these to your existing serializers

from rest_framework import serializers
from django.core.exceptions import ValidationError
from ...models import Student, Class, User
import re
from datetime import datetime

class StudentSerializer(serializers.ModelSerializer):
    class_name = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = '__all__'
        read_only_fields = ['id', 'student_uid', 'created_at', 'updated_at', 'created_by', 'updated_by']
    
    def get_class_name(self, obj):
        if obj.current_class:
            return obj.current_class.class_name
        return None
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def validate_admission_no(self, value):
        # Check if admission number already exists (for updates)
        if self.instance:
            if Student.objects.filter(admission_no=value).exclude(id=self.instance.id).exists():
                raise ValidationError("Admission number already exists")
        else:
            if Student.objects.filter(admission_no=value).exists():
                raise ValidationError("Admission number already exists")
        
        # Validate format (PREFIX-YYYYMM-SEQUENCE)
        pattern = r'^[A-Z]+-\d{6}-\d+$'
        if not re.match(pattern, value):
            raise ValidationError("Admission number must be in format: PREFIX-YYYYMM-SEQUENCE (e.g., ADM-202401-1)")
        
        return value
    
    def validate_phone(self, value):
        if value and not re.match(r'^\+?[0-9\s\-\(\)]+$', value):
            raise ValidationError("Invalid phone number format")
        return value
    
    def validate_email(self, value):
        if value and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            raise ValidationError("Invalid email format")
        return value
    
    def validate_date_of_birth(self, value):
        if value > datetime.now().date():
            raise ValidationError("Date of birth cannot be in the future")
        return value

class StudentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'
        read_only_fields = ['id', 'student_uid', 'created_at', 'updated_at']
        
    def validate_email(self, value):
        if value:  # Only validate if email is provided
            # Check if email already exists (excluding current instance if updating)
            queryset = Student.objects.filter(email=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            
            if queryset.exists():
                raise serializers.ValidationError("A student with this email already exists.")
        return value
    def validate_current_class(self, value):
        if value and isinstance(value, str):
            try:
                from uuid import UUID
                UUID(value)  # This converts "5798865b-b690-47ce-b1c3-72978952c857" to a UUID object
                return value
            except ValueError:
                raise serializers.ValidationError("Invalid class ID format")
        return value
    
    def validate(self, data):
        # Ensure either guardian or parents are provided
        if not data.get('guardian_name') and not (data.get('father_name') or data.get('mother_name')):
            raise ValidationError("Either guardian or parent information must be provided")
        
        # Ensure emergency contact is provided
        if not data.get('emergency_contact') or not data.get('emergency_contact_name'):
            raise ValidationError("Emergency contact information is required")
        
        return data

class StudentImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'
    
    def validate_admission_no(self, value):
        # Allow empty admission_no for import (will be generated)
        if not value:
            return value
        
        if Student.objects.filter(admission_no=value).exists():
            raise ValidationError(f"Admission number {value} already exists")
        
        # Validate format if provided
        pattern = r'^[A-Z]+-\d{6}-\d+$'
        if not re.match(pattern, value):
            raise ValidationError(f"Invalid format for {value}. Must be: PREFIX-YYYYMM-SEQUENCE")
        
        return value

class AdmissionNumberConfigSerializer(serializers.Serializer):
    """Serializer for admission number configuration"""
    last_admission_number = serializers.CharField(required=False, allow_blank=True)
    prefix = serializers.CharField(max_length=10, default='ADM')
    year = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    next_sequence = serializers.IntegerField(min_value=1)
    
    def validate_last_admission_number(self, value):
        if value:
            pattern = r'^[A-Z]+-\d{6}-\d+$'
            if not re.match(pattern, value):
                raise ValidationError("Last admission number must be in format: PREFIX-YYYYMM-SEQUENCE")
        
        # Parse and validate sequence
        if value:
            parts = value.split('-')
            if len(parts) == 3:
                try:
                    sequence = int(parts[2])
                    if sequence < 1:
                        raise ValidationError("Sequence number must be positive")
                except ValueError:
                    raise ValidationError("Invalid sequence number")
        
        return value