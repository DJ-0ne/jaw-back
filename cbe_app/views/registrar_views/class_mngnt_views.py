# views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

from ...models import Class, User, Student
from ...serializers.registrar_serializers.class_mngnt_serializers import (
    ClassSerializer, ClassCreateSerializer, StreamSerializer,
    NumericLevelSerializer, TeacherSerializer
)

logger = logging.getLogger(__name__)

# Predefined streams for CBE system
STREAMS = [
    {'id': 'blue', 'name': 'Blue', 'code': 'BL'},
    {'id': 'red', 'name': 'Red', 'code': 'RD'},
    {'id': 'green', 'name': 'Green', 'code': 'GN'},
    {'id': 'yellow', 'name': 'Yellow', 'code': 'YL'},
    {'id': 'purple', 'name': 'Purple', 'code': 'PR'},
    {'id': 'orange', 'name': 'Orange', 'code': 'OR'},
]

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_streams(request):
    """
    Get available streams for class creation
    """
    try:
        serializer = StreamSerializer(STREAMS, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error fetching streams: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch streams'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_numeric_levels(request):
    """
    Get available numeric levels (1-12) for class creation
    """
    try:
        levels = []
        for i in range(1, 13):
            levels.append({
                'level': i,
                'label': f'Level {i}'
            })
        
        serializer = NumericLevelSerializer(levels, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error fetching numeric levels: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch numeric levels'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teachers(request):
    """
    Get all teachers for class teacher assignment
    """
    try:
        teachers = User.objects.filter(
            role='teacher',
            is_active=True
        ).order_by('first_name', 'last_name')
        
        serializer = TeacherSerializer(teachers, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error fetching teachers: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch teachers'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_classes(request):
    """
    Get all classes with optional filtering
    """
    try:
        # Get query parameters
        is_active = request.query_params.get('is_active')
        numeric_level = request.query_params.get('numeric_level')
        stream = request.query_params.get('stream')
        
        # Base queryset
        queryset = Class.objects.all().select_related('class_teacher').order_by('numeric_level', 'stream')
        
        # Apply filters
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        if numeric_level:
            queryset = queryset.filter(numeric_level=numeric_level)
        
        if stream:
            queryset = queryset.filter(stream__iexact=stream)
        
        serializer = ClassSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching classes: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch classes'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_class(request):
    """
    Create a new class
    """
    try:
        # Check if user has permission (registrar or admin)
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create classes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Validate required fields exist
        required_fields = ['class_code', 'class_name', 'numeric_level']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'error': f'{field.replace("_", " ").title()} is required'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if class code already exists
        if Class.objects.filter(class_code=request.data['class_code']).exists():
            return Response({
                'success': False,
                'error': 'Class code already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate numeric level
        try:
            numeric_level = int(request.data['numeric_level'])
            if numeric_level < 1 or numeric_level > 12:
                return Response({
                    'success': False,
                    'error': 'Numeric level must be between 1 and 12'
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'error': 'Invalid numeric level'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate capacity
        capacity = request.data.get('capacity', 40)
        try:
            capacity = int(capacity)
            if capacity < 1 or capacity > 100:
                return Response({
                    'success': False,
                    'error': 'Capacity must be between 1 and 100'
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'error': 'Invalid capacity value'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate teacher if provided
        class_teacher_id = request.data.get('class_teacher_id')
        class_teacher = None
        if class_teacher_id:
            try:
                class_teacher = User.objects.get(id=class_teacher_id, role='teacher', is_active=True)
            except User.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Selected teacher not found or is not active'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create class with transaction to ensure data integrity
        with transaction.atomic():
            new_class = Class.objects.create(
                class_code=request.data['class_code'].upper(),
                class_name=request.data['class_name'],
                numeric_level=numeric_level,
                stream=request.data.get('stream', '').capitalize() or None,
                capacity=capacity,
                class_teacher=class_teacher,
                is_active=request.data.get('is_active', True)
            )
            
            logger.info(f"Class created: {new_class.class_code} by user {request.user.username}")
            
            serializer = ClassSerializer(new_class)
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Class "{new_class.class_name}" created successfully'
            }, status=status.HTTP_201_CREATED)
    
    except ValidationError as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating class: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create class. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_class(request, class_id):
    """
    Update an existing class
    """
    try:
        # Check if user has permission
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update classes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get class
        try:
            class_obj = Class.objects.get(id=class_id)
        except Class.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Class not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Validate numeric level if provided
        if 'numeric_level' in request.data:
            try:
                numeric_level = int(request.data['numeric_level'])
                if numeric_level < 1 or numeric_level > 12:
                    return Response({
                        'success': False,
                        'error': 'Numeric level must be between 1 and 12'
                    }, status=status.HTTP_400_BAD_REQUEST)
                request.data['numeric_level'] = numeric_level
            except (ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Invalid numeric level'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate capacity if provided
        if 'capacity' in request.data:
            try:
                capacity = int(request.data['capacity'])
                if capacity < 1 or capacity > 100:
                    return Response({
                        'success': False,
                        'error': 'Capacity must be between 1 and 100'
                    }, status=status.HTTP_400_BAD_REQUEST)
                request.data['capacity'] = capacity
            except (ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Invalid capacity value'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate teacher if provided
        if 'class_teacher_id' in request.data:
            teacher_id = request.data['class_teacher_id']
            if teacher_id:
                try:
                    teacher = User.objects.get(id=teacher_id, role='teacher', is_active=True)
                    request.data['class_teacher'] = teacher
                except User.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': 'Selected teacher not found or is not active'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                request.data['class_teacher'] = None
            del request.data['class_teacher_id']
        
        # Handle is_active toggle
        if 'is_active' in request.data:
            class_obj.is_active = request.data['is_active']
            class_obj.save()
            
            logger.info(f"Class {class_obj.class_code} active status toggled to {class_obj.is_active} by {request.user.username}")
            
            serializer = ClassSerializer(class_obj)
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Class {"activated" if class_obj.is_active else "deactivated"} successfully'
            }, status=status.HTTP_200_OK)
        
        # Update other fields
        for field, value in request.data.items():
            if hasattr(class_obj, field) and field not in ['id', 'created_at', 'updated_at']:
                setattr(class_obj, field, value)
        
        class_obj.save()
        
        serializer = ClassSerializer(class_obj)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Class updated successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error updating class {class_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to update class. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_class(request, class_id):
    """
    Delete a class
    """
    try:
        # Check if user has permission
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete classes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get class
        try:
            class_obj = Class.objects.get(id=class_id)
        except Class.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Class not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if class has students
        student_count = Student.objects.filter(current_class=class_obj).count()
        if student_count > 0:
            return Response({
                'success': False,
                'error': f'Cannot delete class with {student_count} enrolled students. Please reassign students first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete class
        class_name = class_obj.class_name
        class_code = class_obj.class_code
        class_obj.delete()
        
        logger.info(f"Class deleted: {class_code} by user {request.user.username}")
        
        return Response({
            'success': True,
            'message': f'Class "{class_name}" deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting class {class_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete class. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_class_detail(request, class_id):
    """
    Get detailed information about a specific class
    """
    try:
        try:
            class_obj = Class.objects.select_related('class_teacher').get(id=class_id)
        except Class.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Class not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = ClassSerializer(class_obj)
        
        # Add additional statistics
        data = serializer.data
        data['student_count'] = Student.objects.filter(current_class=class_obj, status='Active').count()
        data['available_slots'] = class_obj.capacity - data['student_count']
        
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching class detail {class_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch class details'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)