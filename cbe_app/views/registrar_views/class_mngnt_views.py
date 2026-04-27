from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

from ...models import Class, User, Student, Staff
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
    try:
        teachers = Staff.objects.filter(
            user__isnull=False,
            user__role='teacher',
            status='Active'
        ).select_related('user')
        
        data = []
        for teacher in teachers:
            data.append({
                'id': str(teacher.id),
                'first_name': teacher.first_name,
                'last_name': teacher.last_name,
                'full_name': teacher.full_name,
                'email': teacher.personal_email,
                'specialization': teacher.specialization or 'General'
            })
        
        return Response({
            'success': True,
            'data': data
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
    try:
        is_active = request.query_params.get('is_active')
        numeric_level = request.query_params.get('numeric_level')
        stream = request.query_params.get('stream')
        
        queryset = Class.objects.all().select_related('class_teacher').order_by('numeric_level', 'stream')
        
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
    try:
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create classes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        required_fields = ['class_code', 'class_name', 'numeric_level']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'error': f'{field.replace("_", " ").title()} is required'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if Class.objects.filter(class_code=request.data['class_code']).exists():
            return Response({
                'success': False,
                'error': 'Class code already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # FIXED: Get Staff instead of User
        class_teacher_id = request.data.get('class_teacher_id')
        class_teacher = None
        if class_teacher_id:
            try:
                class_teacher = Staff.objects.get(id=class_teacher_id, status='Active')
            except Staff.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Selected teacher not found or is not active'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            new_class = Class.objects.create(
                class_code=request.data['class_code'].upper(),
                class_name=request.data['class_name'],
                numeric_level=numeric_level,
                stream=request.data.get('stream', '').capitalize() or None,
                capacity=capacity,
                class_teacher=class_teacher,  # Now assigning Staff
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
    try:
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update classes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            class_obj = Class.objects.get(id=class_id)
        except Class.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Class not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if 'numeric_level' in request.data:
            try:
                numeric_level = int(request.data['numeric_level'])
                if numeric_level < 1 or numeric_level > 12:
                    return Response({
                        'success': False,
                        'error': 'Numeric level must be between 1 and 12'
                    }, status=status.HTTP_400_BAD_REQUEST)
                class_obj.numeric_level = numeric_level
            except (ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Invalid numeric level'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if 'capacity' in request.data:
            try:
                capacity = int(request.data['capacity'])
                if capacity < 1 or capacity > 100:
                    return Response({
                        'success': False,
                        'error': 'Capacity must be between 1 and 100'
                    }, status=status.HTTP_400_BAD_REQUEST)
                class_obj.capacity = capacity
            except (ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Invalid capacity value'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # FIXED: Handle BOTH User ID and Staff ID for class_teacher
        if 'class_teacher_id' in request.data:
            teacher_id = request.data['class_teacher_id']
            if teacher_id:
                # First try to find as Staff ID
                try:
                    staff = Staff.objects.get(id=teacher_id, status='Active')
                    class_obj.class_teacher = staff
                except Staff.DoesNotExist:
                    # If not found, try to find as User ID and get linked Staff
                    try:
                        user = User.objects.get(id=teacher_id)
                        staff = Staff.objects.get(user=user, status='Active')
                        class_obj.class_teacher = staff
                    except (User.DoesNotExist, Staff.DoesNotExist):
                        return Response({
                            'success': False,
                            'error': 'Teacher not found'
                        }, status=status.HTTP_400_BAD_REQUEST)
            else:
                class_obj.class_teacher = None
        
        if 'class_code' in request.data:
            class_obj.class_code = request.data['class_code']
        
        if 'class_name' in request.data:
            class_obj.class_name = request.data['class_name']
        
        if 'stream' in request.data:
            class_obj.stream = request.data['stream']
        
        if 'is_active' in request.data:
            class_obj.is_active = request.data['is_active']
        
        class_obj.save()
        
        logger.info(f"Class {class_obj.class_code} updated by {request.user.username}")
        
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
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_class(request, class_id):
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete classes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            class_obj = Class.objects.get(id=class_id)
        except Class.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Class not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        student_count = Student.objects.filter(current_class=class_obj).count()
        if student_count > 0:
            return Response({
                'success': False,
                'error': f'Cannot delete class with {student_count} enrolled students. Please reassign students first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
    try:
        try:
            class_obj = Class.objects.select_related('class_teacher').get(id=class_id)
        except Class.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Class not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = ClassSerializer(class_obj)
        
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