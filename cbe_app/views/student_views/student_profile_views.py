# cbe_app/views/student_views/profile_views.py

import logging
from django.utils import timezone
from django.db.models import Sum, Q
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import check_password
import os
import uuid

from cbe_app.models import (
    Student, User, StudentAttendance, StudentFeeInvoice, 
    FeeTransaction, StudentEnrollment, DisciplineIncident
)
from cbe_app.serializers.student_serializers.student_profile_serializers import (
    StudentProfileSerializer, StudentProfileUpdateSerializer,
    UserUpdateSerializer, ChangePasswordSerializer, ProfileStatsSerializer
)

logger = logging.getLogger(__name__)


def get_student(user):
    """Helper function to get student profile"""
    try:
        return Student.objects.select_related('user', 'current_class').get(
            user=user, archived=False
        )
    except Student.DoesNotExist:
        return None

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_info(request):
    """Get current user account information"""
    try:
        user = request.user
        data = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone,
            'user_code': user.user_code,
            'role': user.role
        }
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== GET PROFILE ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile(request):
    """
    Get student profile information
    GET /api/profile/
    """
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found. Please contact the registrar.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = StudentProfileSerializer(student)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching profile: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred while fetching profile data.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== UPDATE PROFILE ====================

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update student profile information
    PATCH /api/profile/update/
    """
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Separate student and user fields
        user_fields = ['first_name', 'last_name', 'email', 'phone']
        student_fields = [
            'middle_name', 'address', 'city', 'country',
            'guardian_phone', 'guardian_email', 'guardian_address',
            'emergency_contact', 'emergency_contact_name',
            'medical_conditions', 'allergies', 'medication'
        ]
        
        user_data = {}
        student_data = {}
        
        for key, value in request.data.items():
            if key in user_fields:
                user_data[key] = value
            elif key in student_fields:
                student_data[key] = value
        
        # Update student profile
        if student_data:
            student_serializer = StudentProfileUpdateSerializer(
                student, data=student_data, partial=True
            )
            if student_serializer.is_valid():
                student_serializer.save()
            else:
                return Response({
                    'success': False,
                    'errors': student_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update user account
        if user_data:
            user_serializer = UserUpdateSerializer(
                request.user, data=user_data, partial=True
            )
            if user_serializer.is_valid():
                user_serializer.save()
            else:
                return Response({
                    'success': False,
                    'errors': user_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Return updated profile
        serializer = StudentProfileSerializer(student)
        
        return Response({
            'success': True,
            'message': 'Profile updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred while updating profile.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== CHANGE PASSWORD ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change user password
    POST /api/profile/change-password/
    """
    try:
        serializer = ChangePasswordSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']
        
        # Check current password
        if not check_password(current_password, user.password):
            return Response({
                'success': False,
                'error': 'Current password is incorrect.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update password
        user.set_password(new_password)
        user.last_password_change = timezone.now()
        user.save()
        
        return Response({
            'success': True,
            'message': 'Password changed successfully. Please login again.'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred while changing password.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== UPDATE PROFILE IMAGE ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_profile_image(request):
    """
    Update student profile image
    POST /api/profile/image/
    """
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if 'profile_image' not in request.FILES:
            return Response({
                'success': False,
                'error': 'No image file provided.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        image = request.FILES['profile_image']
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/gif']
        if image.content_type not in allowed_types:
            return Response({
                'success': False,
                'error': 'Invalid file type. Please upload JPEG, PNG, or GIF images.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate file size (max 5MB)
        if image.size > 5 * 1024 * 1024:
            return Response({
                'success': False,
                'error': 'File size too large. Maximum size is 5MB.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate unique filename
        ext = image.name.split('.')[-1]
        filename = f"profile_{student.admission_no}_{uuid.uuid4().hex[:8]}.{ext}"
        
        # Save image
        file_path = f"student_profiles/{filename}"
        saved_path = default_storage.save(file_path, ContentFile(image.read()))
        
        # Update student profile image URL
        student.photo_url = default_storage.url(saved_path)
        student.save()
        
        return Response({
            'success': True,
            'message': 'Profile image updated successfully',
            'data': {
                'image_url': student.photo_url
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error updating profile image: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred while updating profile image.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== GET PROFILE STATISTICS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile_stats(request):
    """
    Get student profile statistics
    GET /api/profile/stats/
    """
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Attendance statistics (last 30 days)
        thirty_days_ago = timezone.now().date() - timezone.timedelta(days=30)
        attendance_records = StudentAttendance.objects.filter(
            student=student,
            session__session_date__gte=thirty_days_ago
        )
        
        total_attendance = attendance_records.count()
        present_count = attendance_records.filter(attendance_status='Present').count()
        attendance_rate = (present_count / total_attendance * 100) if total_attendance > 0 else 0
        
        # Fee statistics
        invoices = StudentFeeInvoice.objects.filter(student=student)
        total_fees = invoices.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = invoices.aggregate(total=Sum('amount_paid'))['total'] or 0
        pending_fees = total_fees - total_paid
        
        # Course statistics
        enrollments = StudentEnrollment.objects.filter(student=student)
        active_courses = enrollments.filter(enrollment_status='Active').count()
        completed_courses = enrollments.filter(enrollment_status='Completed').count()
        
        stats_data = {
            'total_attendance': total_attendance,
            'attendance_rate': round(attendance_rate, 2),
            'total_fees_paid': total_paid,
            'pending_fees': pending_fees,
            'completed_courses': completed_courses,
            'active_courses': active_courses
        }
        
        serializer = ProfileStatsSerializer(stats_data)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching profile stats: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred while fetching statistics.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== GET COMPLETE PROFILE DATA ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_complete_profile(request):
    """
    Get complete profile data including stats
    GET /api/profile/complete/
    """
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get profile data
        profile_serializer = StudentProfileSerializer(student)
        
        # Get statistics
        thirty_days_ago = timezone.now().date() - timezone.timedelta(days=30)
        attendance_records = StudentAttendance.objects.filter(
            student=student,
            session__session_date__gte=thirty_days_ago
        )
        
        total_attendance = attendance_records.count()
        present_count = attendance_records.filter(attendance_status='Present').count()
        attendance_rate = (present_count / total_attendance * 100) if total_attendance > 0 else 0
        
        invoices = StudentFeeInvoice.objects.filter(student=student)
        total_fees = invoices.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = invoices.aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Get discipline summary
        discipline_points = DisciplineIncident.objects.filter(
            student=student
        ).aggregate(total=Sum('points_awarded'))['total'] or 0
        
        return Response({
            'success': True,
            'data': {
                'profile': profile_serializer.data,
                'stats': {
                    'attendance_rate': round(attendance_rate, 2),
                    'attendance_days': total_attendance,
                    'present_days': present_count,
                    'total_fees': total_fees,
                    'total_paid': total_paid,
                    'balance': total_fees - total_paid,
                    'discipline_points': discipline_points
                }
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching complete profile: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred while fetching profile data.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)