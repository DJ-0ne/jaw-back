# cbe_app/views/hr_views/hr_department_views.py

from django.db.models import Q, Count
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cbe_app.models import Department, DepartmentStaffAssignment, Staff
from cbe_app.serializers.hr_serializers.hr_staff_mng_serializers import (
    DepartmentListSerializer, DepartmentDetailSerializer, 
    DepartmentCreateUpdateSerializer, DepartmentStaffAssignmentSerializer
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_departments(request):
    """Get list of departments with optional filtering"""
    try:
        queryset = Department.objects.filter(is_active=True)
        
        # Filter by department type
        dept_type = request.query_params.get('type', '')
        if dept_type and dept_type != 'all':
            queryset = queryset.filter(department_type=dept_type)
        
        # Search filter
        search = request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(department_name__icontains=search) |
                Q(department_code__icontains=search)
            )
        
        # Order by name
        departments = queryset.order_by('department_name')
        
        # Serialize with staff assignments
        serializer = DepartmentListSerializer(departments, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_detail(request, department_id):
    """Get detailed information for a specific department"""
    try:
        department = Department.objects.prefetch_related(
            'staff_assignments__staff',
            'staff_assignments__teaching_subjects'
        ).get(id=department_id, is_active=True)
        
        serializer = DepartmentDetailSerializer(department)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_department(request):
    """Create a new department"""
    try:
        serializer = DepartmentCreateUpdateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        department = Department.objects.create(**serializer.validated_data)
        
        detail_serializer = DepartmentDetailSerializer(department)
        return Response({
            'success': True,
            'data': detail_serializer.data,
            'message': f'Department {department.department_name} created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_department(request, department_id):
    """Update an existing department"""
    try:
        department = Department.objects.get(id=department_id)
        
        serializer = DepartmentCreateUpdateSerializer(department, data=request.data, partial=True)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        for attr, value in serializer.validated_data.items():
            setattr(department, attr, value)
        
        department.save()
        
        detail_serializer = DepartmentDetailSerializer(department)
        return Response({
            'success': True,
            'data': detail_serializer.data,
            'message': f'Department {department.department_name} updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_department(request, department_id):
    """Soft delete a department (set is_active=False)"""
    try:
        department = Department.objects.get(id=department_id)
        department.is_active = False
        department.save()
        
        # Also deactivate all staff assignments for this department
        DepartmentStaffAssignment.objects.filter(department=department, is_active=True).update(is_active=False)
        
        return Response({
            'success': True,
            'message': f'Department {department.department_name} has been deactivated'
        }, status=status.HTTP_200_OK)
        
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_stats(request):
    """Get aggregated department statistics"""
    try:
        total_departments = Department.objects.filter(is_active=True).count()
        academic_depts = Department.objects.filter(is_active=True, department_type='Academic').count()
        sports_depts = Department.objects.filter(is_active=True, department_type='Sports').count()
        admin_depts = Department.objects.filter(is_active=True, department_type='Administrative').count()
        
        # Staff distribution by department type
        staff_in_academic = DepartmentStaffAssignment.objects.filter(
            department__department_type='Academic',
            is_active=True
        ).values('staff').distinct().count()
        
        staff_in_sports = DepartmentStaffAssignment.objects.filter(
            department__department_type='Sports',
            is_active=True
        ).values('staff').distinct().count()
        
        staff_in_admin = DepartmentStaffAssignment.objects.filter(
            department__department_type='Administrative',
            is_active=True
        ).values('staff').distinct().count()
        
        # Departments with most staff
        top_departments = Department.objects.filter(is_active=True).annotate(
            staff_count=Count('staff_assignments', filter=Q(staff_assignments__is_active=True))
        ).order_by('-staff_count')[:5].values('department_name', 'staff_count')
        
        return Response({
            'success': True,
            'data': {
                'total': total_departments,
                'academic': academic_depts,
                'sports': sports_depts,
                'administrative': admin_depts,
                'staff_in_academic': staff_in_academic,
                'staff_in_sports': staff_in_sports,
                'staff_in_administrative': staff_in_admin,
                'top_departments': list(top_departments)
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_department_head(request, department_id):
    """Set a staff member as Head of Department"""
    try:
        department = Department.objects.get(id=department_id, is_active=True)
        staff_id = request.data.get('staff_id')
        
        if not staff_id:
            return Response({
                'success': False,
                'error': 'staff_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = Staff.objects.get(id=staff_id, status='Active')
        except Staff.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Staff member not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if staff is already assigned to this department
        assignment, created = DepartmentStaffAssignment.objects.get_or_create(
            staff=staff,
            department=department,
            defaults={
                'role': 'head',
                'is_primary': not DepartmentStaffAssignment.objects.filter(staff=staff, is_primary=True).exists()
            }
        )
        
        if not created:
            assignment.role = 'head'
            assignment.save()
        
        # Update department head reference
        department.head_of_department = staff
        department.save()
        
        return Response({
            'success': True,
            'message': f'{staff.full_name} is now Head of {department.department_name}'
        }, status=status.HTTP_200_OK)
        
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_department_head(request, department_id):
    """Remove the Head of Department"""
    try:
        department = Department.objects.get(id=department_id, is_active=True)
        
        if department.head_of_department:
            # Update the staff assignment role from 'head' to 'member'
            DepartmentStaffAssignment.objects.filter(
                department=department,
                staff=department.head_of_department,
                role='head'
            ).update(role='member')
            
            department.head_of_department = None
            department.save()
        
        return Response({
            'success': True,
            'message': f'Head of Department removed from {department.department_name}'
        }, status=status.HTTP_200_OK)
        
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)