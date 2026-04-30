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
        # New format: PREFIX-XXX (e.g., ADM/JWB-001)
        if self.instance:
            if Student.objects.filter(admission_no=value).exclude(id=self.instance.id).exists():
                raise ValidationError("Admission number already exists")
        else:
            if Student.objects.filter(admission_no=value).exists():
                raise ValidationError("Admission number already exists")
        
        # Validate new format: PREFIX-XXX (letters, slash, hyphen, numbers)
        pattern = r'^[A-Z/]+-\d{3}$'
        if not re.match(pattern, value):
            raise ValidationError("Admission number must be in format: PREFIX-XXX (e.g., ADM/JWB-001)")
        
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
    
    def validate_upi_number(self, value):
        if value:
            queryset = Student.objects.filter(upi_number=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise ValidationError("UPI number already exists")
        return value
    
    def validate_knec_number(self, value):
        if value:
            queryset = Student.objects.filter(knec_number=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise ValidationError("KNEC number already exists")
        return value
    
    def validate_birth_certificate_no(self, value):
        if value:
            queryset = Student.objects.filter(birth_certificate_no=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise ValidationError("Birth certificate number already exists")
        return value


class StudentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'
        read_only_fields = ['id', 'student_uid', 'created_at', 'updated_at']
        
    def validate_email(self, value):
        if value:
            queryset = Student.objects.filter(email=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise serializers.ValidationError("A student with this email already exists.")
        return value
    
    def validate_upi_number(self, value):
        if value:
            queryset = Student.objects.filter(upi_number=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise serializers.ValidationError("A student with this UPI number already exists.")
        return value
    
    def validate_knec_number(self, value):
        if value:
            queryset = Student.objects.filter(knec_number=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise serializers.ValidationError("A student with this KNEC number already exists.")
        return value
    
    def validate_birth_certificate_no(self, value):
        if value:
            queryset = Student.objects.filter(birth_certificate_no=value)
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise serializers.ValidationError("A student with this birth certificate number already exists.")
        return value
    
    def validate_current_class(self, value):
        if value and isinstance(value, str):
            try:
                from uuid import UUID
                UUID(value)
                return value
            except ValueError:
                raise serializers.ValidationError("Invalid class ID format")
        return value
    
    def validate(self, data):
    # For partial updates, fall back to existing instance values
        guardian_name = data.get('guardian_name') or (self.instance.guardian_name if self.instance else None)
        father_name = data.get('father_name') or (self.instance.father_name if self.instance else None)
        mother_name = data.get('mother_name') or (self.instance.mother_name if self.instance else None)
        emergency_contact = data.get('emergency_contact') or (self.instance.emergency_contact if self.instance else None)
        emergency_contact_name = data.get('emergency_contact_name') or (self.instance.emergency_contact_name if self.instance else None)

        if not guardian_name and not (father_name or mother_name):
            raise ValidationError("Either guardian or parent information must be provided")

        if not emergency_contact or not emergency_contact_name:
            raise ValidationError("Emergency contact information is required")

        return data


class StudentImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'
    
    def validate_admission_no(self, value):
        if not value:
            return value
        
        if Student.objects.filter(admission_no=value).exists():
            raise ValidationError(f"Admission number {value} already exists")
        
        pattern = r'^[A-Z/]+-\d{3}$'
        if not re.match(pattern, value):
            raise ValidationError(f"Invalid format for {value}. Must be: PREFIX-XXX (e.g., ADM/JWB-001)")
        
        return value
    
    def validate_upi_number(self, value):
        if value and Student.objects.filter(upi_number=value).exists():
            raise ValidationError(f"UPI number {value} already exists")
        return value
    
    def validate_knec_number(self, value):
        if value and Student.objects.filter(knec_number=value).exists():
            raise ValidationError(f"KNEC number {value} already exists")
        return value
    
    def validate_birth_certificate_no(self, value):
        if value and Student.objects.filter(birth_certificate_no=value).exists():
            raise ValidationError(f"Birth certificate number {value} already exists")
        return value


class AdmissionNumberConfigSerializer(serializers.Serializer):
    """Serializer for admission number configuration - New format"""
    last_admission_number = serializers.CharField(required=False, allow_blank=True)
    prefix = serializers.CharField(max_length=20, default='ADM/JWB')
    next_sequence = serializers.IntegerField(min_value=1)
    
    def validate_last_admission_number(self, value):
        if value:
            pattern = r'^[A-Z/]+-\d{3}$'
            if not re.match(pattern, value):
                raise ValidationError("Last admission number must be in format: PREFIX-XXX (e.g., ADM/JWB-001)")
        
        if value:
            parts = value.split('-')
            if len(parts) == 2:
                try:
                    sequence = int(parts[1])
                    if sequence < 1:
                        raise ValidationError("Sequence number must be positive")
                except ValueError:
                    raise ValidationError("Invalid sequence number")
        
        return value