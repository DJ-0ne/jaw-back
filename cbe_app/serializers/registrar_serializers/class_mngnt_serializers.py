from rest_framework import serializers
from django.core.exceptions import ValidationError
from cbe_app.models import Class, User, Student, Staff


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'full_name']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


class ClassSerializer(serializers.ModelSerializer):
    class_teacher_name = serializers.SerializerMethodField()
    current_students = serializers.SerializerMethodField()
    total_capacity_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = [
            'id', 'class_code', 'class_name', 'numeric_level', 'stream',
            'capacity', 'class_teacher', 'class_teacher_name', 'is_active',
            'created_at', 'updated_at', 'current_students', 'total_capacity_percentage'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_class_teacher_name(self, obj):
        if obj.class_teacher:
            return obj.class_teacher.full_name
        return None
    
    def get_current_students(self, obj):
        return Student.objects.filter(current_class=obj, status='Active').count()
    
    def get_total_capacity_percentage(self, obj):
        current = self.get_current_students(obj)
        if obj.capacity > 0:
            return round((current / obj.capacity) * 100, 1)
        return 0
    
    def validate_class_code(self, value):
        if Class.objects.filter(class_code=value).exists():
            raise ValidationError("Class code already exists")
        return value
    
    def validate_numeric_level(self, value):
        if value < 1 or value > 12:
            raise ValidationError("Numeric level must be between 1 and 12")
        return value


class ClassCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = [
            'class_code', 'class_name', 'numeric_level', 'stream',
            'capacity', 'class_teacher', 'is_active'
        ]
    
    def validate_numeric_level(self, value):
        if value < 1 or value > 12:
            raise serializers.ValidationError("Numeric level must be between 1 and 12")
        return value
    
    def validate_capacity(self, value):
        if value < 1 or value > 100:
            raise serializers.ValidationError("Capacity must be between 1 and 100")
        return value
    
    def validate_class_code(self, value):
        if Class.objects.filter(class_code=value).exists():
            raise serializers.ValidationError("Class code already exists")
        return value


class StreamSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    code = serializers.CharField()


class NumericLevelSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    label = serializers.CharField()


class TeacherSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Staff
        fields = ['id', 'first_name', 'last_name', 'email', 'full_name', 'staff_id', 'teacher_code', 'specialization']
    
    def get_full_name(self, obj):
        return obj.full_name