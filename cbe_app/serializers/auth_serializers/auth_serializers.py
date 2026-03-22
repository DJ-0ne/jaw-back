# serializers/auth_serializers/auth_serializers.py

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from ...models import User, UserSession
import uuid


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'first_name', 'last_name', 'phone')
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        # Check if email already exists
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})
        
        # Check if username already exists
        if User.objects.filter(username=attrs['username']).exists():
            raise serializers.ValidationError({"username": "This username is already taken."})
        
        return attrs

    def create(self, validated_data):
        # Remove password2 from validated_data
        validated_data.pop('password2')
        
        # Set default role - using a valid role from your ROLE_CHOICES
        # Choose one that makes sense for your app
        validated_data['role'] = 'student'  # Options: 'student', 'parent', 'teacher', etc.
        
        # Create user
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=validated_data['phone'],
            role=validated_data['role']
        )
        
        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            # Try to find the user by email (case-insensitive)
            try:
                user = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                raise serializers.ValidationError("Invalid email or password")

            # Check if account is locked
            if user.locked_until and user.locked_until > timezone.now():
                local_locked_time = timezone.localtime(user.locked_until)
                
                # Using %I for 12-hour, %M for minutes, and %p for AM/PM
                formatted_time = local_locked_time.strftime('%Y-%m-%d %I:%M:%S %p')
                
                raise serializers.ValidationError(
                    f"Account is locked. Try again after {formatted_time}"
                )

            # Check if user is active
            if not user.is_active:
                raise serializers.ValidationError("Account is inactive. Please contact administrator.")

            # Check password manually
            if not user.check_password(password):
                # Increment failed attempts
                user.failed_attempts += 1
                
                # Lock account after 5 failed attempts
                if user.failed_attempts >= 5:
                    user.locked_until = timezone.now() + timezone.timedelta(minutes=30)
                
                user.save(update_fields=['failed_attempts', 'locked_until'])
                raise serializers.ValidationError("Invalid email or password")

            # Reset failed attempts on successful login
            if user.failed_attempts > 0:
                user.failed_attempts = 0
                user.locked_until = None
                user.save(update_fields=['failed_attempts', 'locked_until'])
            
            # Update last_login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            attrs['user'] = user
            return attrs
        
        raise serializers.ValidationError("Both email and password are required")


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'full_name', 
                 'phone', 'role', 'is_active', 'is_staff', 'is_superuser', 'user_code')
        read_only_fields = ('id', 'user_code', 'is_staff', 'is_superuser')
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


class UserSessionSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = UserSession
        fields = ('id', 'user', 'user_username', 'access_token', 'refresh_token', 
                 'login_time', 'last_activity', 'expires_at', 'client_ip', 'user_agent', 'revoked')
        read_only_fields = ('id', 'login_time', 'last_activity', 'user_username')


class CheckUsernameSerializer(serializers.Serializer):
    username = serializers.CharField(required=True, min_length=3)
    
    def validate(self, attrs):
        username = attrs.get('username')
        exists = User.objects.filter(username=username).exists()
        return {
            'username': username,
            'available': not exists
        }


class CheckEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        exists = User.objects.filter(email__iexact=email).exists()
        return {
            'email': email,
            'available': not exists
        }


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'email')
        extra_kwargs = {
            'email': {'read_only': True},  # Email shouldn't be changed directly
        }

    def validate_phone(self, value):
        if value and len(value) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits")
        return value