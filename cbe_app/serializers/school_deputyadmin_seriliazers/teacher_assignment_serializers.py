# serializers.py - Add these serializers

from rest_framework import serializers
from cbe_app.models import *


class TeacherProfileSerializer(serializers.ModelSerializer):
    """Serializer for teacher/staff profile with specialization"""
    full_name = serializers.CharField(source='full_name')
    teacher_category_name = serializers.CharField(source='teacher_category.name', read_only=True)
    teacher_category_code = serializers.CharField(source='teacher_category.code', read_only=True)
    admin_department_name = serializers.CharField(source='admin_department.department_name', read_only=True)
    jss_department_name = serializers.CharField(source='jss_department.name', read_only=True)
    department_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Staff
        fields = ['id', 'staff_id', 'teacher_code', 'full_name', 'first_name', 'last_name',
                  'teacher_category_name', 'teacher_category_code', 'specialization', 
                  'highest_qualification', 'status', 'admin_department_name', 
                  'jss_department_name', 'department_name']
    
    def get_department_name(self, obj):
        if obj.jss_department:
            return obj.jss_department.name
        elif obj.admin_department:
            return obj.admin_department.department_name
        return None


class ClassWithStreamSerializer(serializers.ModelSerializer):
    """Serializer for class with stream and grade info"""
    grade_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    stream_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = ['id', 'class_name', 'class_code', 'numeric_level', 'stream', 
                  'capacity', 'grade_name', 'display_name', 'stream_display', 'is_active']
    
    def get_grade_name(self, obj):
        grade_level = GradeLevel.objects.filter(level=obj.numeric_level).first()
        return grade_level.name if grade_level else f"Grade {obj.numeric_level}"
    
    def get_display_name(self, obj):
        grade_name = self.get_grade_name(obj)
        stream_text = f" - {obj.stream}" if obj.stream else ""
        return f"{grade_name}{stream_text}"
    
    def get_stream_display(self, obj):
        return obj.stream if obj.stream else "No stream assigned"


class SubjectSerializer(serializers.ModelSerializer):
    """Serializer for subjects/learning areas"""
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = LearningArea
        fields = ['id', 'area_code', 'area_name', 'short_name', 'area_type', 
                  'description', 'display_name']
    
    def get_display_name(self, obj):
        return f"{obj.area_name} ({obj.area_code}) - {obj.area_type or 'Core Subject'}"

class TeacherAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for teacher-class-subject assignments with full details"""
    class_name = serializers.CharField(source='class_id.class_name', read_only=True)
    class_display = serializers.SerializerMethodField()
    class_numeric_level = serializers.IntegerField(source='class_id.numeric_level', read_only=True)
    stream = serializers.CharField(source='class_id.stream', read_only=True)
    grade_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.area_name', read_only=True)
    subject_code = serializers.CharField(source='subject.area_code', read_only=True)
    subject_type = serializers.CharField(source='subject.area_type', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_code = serializers.SerializerMethodField()
    teacher_specialization = serializers.SerializerMethodField()
    teacher_category = serializers.SerializerMethodField()
    teacher_department = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassSubjectAllocation
        fields = ['id', 'class_id', 'class_name', 'class_display', 'class_numeric_level', 
                  'stream', 'grade_name', 'subject_id', 'subject_name', 'subject_code', 
                  'subject_type', 'teacher_id', 'teacher_name', 'teacher_code', 
                  'teacher_specialization', 'teacher_category', 'teacher_department',
                  'periods_per_week', 'is_compulsory', 'academic_year']
    
    def get_class_display(self, obj):
        grade_level = GradeLevel.objects.filter(level=obj.class_id.numeric_level).first()
        grade_name = grade_level.name if grade_level else f"Grade {obj.class_id.numeric_level}"
        stream_text = f" - {obj.class_id.stream}" if obj.class_id.stream else ""
        return f"{grade_name}{stream_text}"
    
    def get_grade_name(self, obj):
        grade_level = GradeLevel.objects.filter(level=obj.class_id.numeric_level).first()
        return grade_level.name if grade_level else f"Grade {obj.class_id.numeric_level}"
    
    def get_teacher_name(self, obj):
        """Get teacher name directly from Staff object"""
        if obj.teacher:
            return obj.teacher.full_name
        return "Not Assigned"
    
    def get_teacher_code(self, obj):
        """Get teacher code directly from Staff object"""
        if obj.teacher:
            return obj.teacher.teacher_code or obj.teacher.staff_id
        return None
    
    def get_teacher_specialization(self, obj):
        """Get specialization directly from Staff object"""
        if obj.teacher:
            return obj.teacher.specialization or "Not specified"
        return None
    
    def get_teacher_category(self, obj):
        """Get teacher category name directly from Staff object"""
        if obj.teacher and obj.teacher.teacher_category:
            return obj.teacher.teacher_category.name
        return None
    
    def get_teacher_department(self, obj):
        """Get department name directly from Staff object"""
        if obj.teacher:
            if obj.teacher.jss_department:
                return obj.teacher.jss_department.name
            elif obj.teacher.admin_department:
                return obj.teacher.admin_department.department_name
        return None

class CreateAssignmentSerializer(serializers.Serializer):
    """Serializer for creating a new teacher assignment"""
    class_id = serializers.UUIDField(required=True)
    subject_id = serializers.UUIDField(required=True)
    teacher_id = serializers.UUIDField(required=True)
    academic_year = serializers.CharField(max_length=9, required=True)
    periods_per_week = serializers.IntegerField(min_value=1, max_value=10, default=5, required=False)
    is_compulsory = serializers.BooleanField(default=True, required=False)
    
    def validate_class_id(self, value):
        """Validate class exists"""
        
        if not Class.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Class not found or inactive")
        return value
    
    def validate_subject_id(self, value):
        """Validate subject exists"""
      
        if not LearningArea.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Subject not found or inactive")
        return value
    
    def validate_teacher_id(self, value):
        """Validate teacher exists and has user account"""
      
        staff = Staff.objects.filter(id=value).first()
        if not staff:
            raise serializers.ValidationError("Teacher not found")
        if not staff.user:
            raise serializers.ValidationError(f"Teacher {staff.full_name} does not have a user account")
        return value
    
    def validate_academic_year(self, value):
        """Validate academic year format"""
        import re
        if not re.match(r'^\d{4}-\d{4}$', value):
            raise serializers.ValidationError("Academic year must be in format YYYY-YYYY (e.g., 2024-2025)")
        return value
    
    def validate(self, data):
        """Check for duplicate assignment"""
        
        existing = ClassSubjectAllocation.objects.filter(
            class_id=data['class_id'],
            subject_id=data['subject_id'],
            academic_year=data['academic_year']
        ).first()
        
        if existing:
            raise serializers.ValidationError({
                'non_field_errors': [f"This subject is already assigned to this class for {data['academic_year']}"]
            })
        
        return data

class DepartmentInfoSerializer(serializers.Serializer):
    """Serializer for department information"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    code = serializers.CharField()
    type = serializers.CharField()


class TeacherCategorySerializer(serializers.ModelSerializer):
    """Serializer for teacher categories"""
    class Meta:
        model = TeacherCategory
        fields = ['id', 'name', 'code', 'description']