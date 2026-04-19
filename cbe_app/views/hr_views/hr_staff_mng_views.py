# cbe_app/views/hr_views/hr_staff_mng_views.py

import csv
import io
import openpyxl
from datetime import datetime, timezone
from django.db import models
from django.db.models import Q, Count, Sum, Case, When, IntegerField, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from cbe_app.models import (
    GradeLevel, Staff, TeacherCategory, JSSDepartment, Department, 
    DepartmentStaffAssignment, StaffLeave, LeaveBalance, 
    StaffLoan, LoanRepayment, PayrollRecord, LearningArea
)
from cbe_app.serializers.hr_serializers.hr_staff_mng_serializers import (
    StaffListSerializer, StaffDetailSerializer, StaffCreateUpdateSerializer,
    TeacherCategorySerializer, JSSDepartmentSerializer, GradeLevelSerializer,
    DepartmentSerializer, DepartmentAssignmentSerializer,
    StaffLeaveSerializer, LeaveBalanceSerializer, StaffLoanSerializer,
    LoanRepaymentSerializer, PayrollPeriodSerializer, PayrollRecordSerializer,
    StaffStatsSerializer, BulkStaffCreateSerializer
)

User = get_user_model()


# ==================== STAFF CRUD OPERATIONS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_list(request):
    """
    Get paginated list of staff with filtering options
    Query params: search, category, department, status, page, page_size
    """
    try:
        queryset = Staff.objects.select_related('teacher_category').prefetch_related('department_assignments')
        
        # Search filter
        search = request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(middle_name__icontains=search) |
                Q(staff_id__icontains=search) |
                Q(teacher_code__icontains=search) |
                Q(personal_email__icontains=search) |
                Q(personal_phone__icontains=search)
            )
        
        # Category filter
        category = request.query_params.get('category', '')
        if category and category != 'all':
            queryset = queryset.filter(teacher_category__code=category)
        
        # Department filter
        department = request.query_params.get('department', '')
        if department and department != 'all':
            queryset = queryset.filter(
                department_assignments__department_id=department,
                department_assignments__is_active=True
            ).distinct()
        
        # Status filter
        status_filter = request.query_params.get('status', '')
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        total = queryset.count()
        staff_list = queryset.order_by('-created_at')[start:end]
        
        serializer = StaffListSerializer(staff_list, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'pagination': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_detail(request, staff_id):
    """Get detailed information for a specific staff member"""
    try:
        staff = Staff.objects.select_related(
            'teacher_category', 'jss_department', 'assigned_grade_level', 'admin_department'
        ).prefetch_related(
            'department_assignments__department',
            'department_assignments__teaching_subjects'
        ).get(id=staff_id)
        
        serializer = StaffDetailSerializer(staff)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Staff.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Staff member not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_staff(request):
    """Create a new staff member"""
    try:
        serializer = StaffCreateUpdateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        staff = Staff.objects.create(
            **serializer.validated_data,
            created_by=request.user,
            status='Active'
        )
        
        detail_serializer = StaffDetailSerializer(staff)
        return Response({
            'success': True,
            'data': detail_serializer.data,
            'message': f'Staff {staff.full_name} created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_staff(request, staff_id):
    """Update an existing staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        
        serializer = StaffCreateUpdateSerializer(staff, data=request.data, partial=True)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        for attr, value in serializer.validated_data.items():
            setattr(staff, attr, value)
        
        staff.updated_by = request.user
        staff.save()
        
        detail_serializer = StaffDetailSerializer(staff)
        return Response({
            'success': True,
            'data': detail_serializer.data,
            'message': f'Staff {staff.full_name} updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Staff.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Staff member not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_staff(request, staff_id):
    """Delete a staff member (soft delete by setting status to Terminated)"""
    try:
        staff = Staff.objects.get(id=staff_id)
        staff.status = 'Terminated'
        staff.updated_by = request.user
        staff.save()
        
        return Response({
            'success': True,
            'message': f'Staff {staff.full_name} has been terminated'
        }, status=status.HTTP_200_OK)
        
    except Staff.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Staff member not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== DEPARTMENT ASSIGNMENT OPERATIONS ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_department(request, staff_id):
    """Assign a staff member to a department"""
    try:
        from django.utils import timezone as tz
        from datetime import date
        
        staff = Staff.objects.get(id=staff_id)
        
        data = request.data
        department_id = data.get('department_id')
        
        if not department_id:
            return Response({
                'success': False,
                'error': 'department_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Department not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get today's date
        today = tz.now().date()
        
        # Check if assignment already exists
        assignment, created = DepartmentStaffAssignment.objects.get_or_create(
            staff=staff,
            department=department,
            defaults={
                'role': data.get('role', 'member'),
                'assigned_date': today,
                'is_primary': data.get('is_primary', True),
                'is_active': True
            }
        )
        
        if not created:
            # Update existing assignment
            assignment.role = data.get('role', assignment.role)
            assignment.is_primary = data.get('is_primary', assignment.is_primary)
            assignment.is_active = True
            assignment.save()
        
        # If this is primary, remove primary flag from other assignments
        if assignment.is_primary:
            DepartmentStaffAssignment.objects.filter(
                staff=staff, is_primary=True
            ).exclude(id=assignment.id).update(is_primary=False)
        
        # Handle teaching subjects for academic departments
        teaching_subject_ids = data.get('teaching_subjects', [])
        if teaching_subject_ids:
            subjects = LearningArea.objects.filter(id__in=teaching_subject_ids)
            assignment.teaching_subjects.set(subjects)
        
        serializer = DepartmentAssignmentSerializer(assignment)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': f'Staff assigned to {department.department_name} successfully'
        }, status=status.HTTP_200_OK)
        
    except Staff.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Staff member not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print("Error in assign_department:", str(e))
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_assignments(request, staff_id):
    """Get all department assignments for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        assignments = staff.department_assignments.filter(is_active=True).select_related('department')
        
        serializer = DepartmentAssignmentSerializer(assignments, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Staff.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Staff member not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_assignment(request, assignment_id):
    """Remove a department assignment (soft delete)"""
    try:
        assignment = DepartmentStaffAssignment.objects.get(id=assignment_id)
        assignment.is_active = False
        assignment.save()
        
        return Response({
            'success': True,
            'message': 'Department assignment removed successfully'
        }, status=status.HTTP_200_OK)
        
    except DepartmentStaffAssignment.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Assignment not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def set_primary_assignment(request, assignment_id):
    """Set a department assignment as primary"""
    try:
        assignment = DepartmentStaffAssignment.objects.get(id=assignment_id)
        
        # Remove primary from all other assignments of this staff
        DepartmentStaffAssignment.objects.filter(
            staff=assignment.staff, is_primary=True
        ).update(is_primary=False)
        
        # Set this as primary
        assignment.is_primary = True
        assignment.save()
        
        serializer = DepartmentAssignmentSerializer(assignment)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Primary department updated successfully'
        }, status=status.HTTP_200_OK)
        
    except DepartmentStaffAssignment.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Assignment not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== STAFF STATISTICS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_stats(request):
    """Get aggregated staff statistics"""
    try:
        total_staff = Staff.objects.count()
        active_staff = Staff.objects.filter(status='Active').count()
        on_leave_staff = Staff.objects.filter(status='On Leave').count()
        
        # By teacher category
        jss_staff = Staff.objects.filter(teacher_category__code='JSS').count()
        primary_staff = Staff.objects.filter(teacher_category__code='EP').count()
        early_years_staff = Staff.objects.filter(teacher_category__code='PP').count()
        
        # By department (for JSS departments)
        stem_count = Staff.objects.filter(
            department_assignments__department__department_name__icontains='STEM',
            department_assignments__is_active=True
        ).distinct().count()
        
        humanities_count = Staff.objects.filter(
            department_assignments__department__department_name__icontains='Humanities',
            department_assignments__is_active=True
        ).distinct().count()
        
        languages_count = Staff.objects.filter(
            department_assignments__department__department_name__icontains='Languages',
            department_assignments__is_active=True
        ).distinct().count()
        
        technical_count = Staff.objects.filter(
            department_assignments__department__department_name__icontains='Technical',
            department_assignments__is_active=True
        ).distinct().count()
        
        stats = {
            'total': total_staff,
            'active': active_staff,
            'onLeave': on_leave_staff,
            'jss': jss_staff,
            'primary': primary_staff,
            'earlyYears': early_years_staff,
            'stem': stem_count,
            'humanities': humanities_count,
            'languages': languages_count,
            'technical': technical_count
        }
        
        return Response({
            'success': True,
            'data': stats
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== LOOKUP DATA ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_categories(request):
    """Get all teacher categories"""
    try:
        categories = TeacherCategory.objects.filter(is_active=True)
        serializer = TeacherCategorySerializer(categories, many=True)
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
def get_jss_departments(request):
    """Get all JSS departments"""
    try:
        departments = JSSDepartment.objects.filter(is_active=True)
        serializer = JSSDepartmentSerializer(departments, many=True)
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
def get_grade_levels(request):
    """Get all grade levels"""
    try:
        grade_levels = GradeLevel.objects.all().order_by('level')
        serializer = GradeLevelSerializer(grade_levels, many=True)
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
def get_departments(request):
    """Get all departments (academic and administrative)"""
    try:
        departments = Department.objects.filter(is_active=True)
        serializer = DepartmentSerializer(departments, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== BULK OPERATIONS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_create_staff(request):
    """Bulk create staff members from CSV/JSON data"""
    try:
        data = request.data
        
        # Handle CSV upload
        if 'file' in request.FILES:
            file = request.FILES['file']
            file_content = file.read().decode('utf-8')
            
            if file.name.endswith('.csv'):
                csv_reader = csv.DictReader(io.StringIO(file_content))
                staff_data = list(csv_reader)
            elif file.name.endswith(('.xlsx', '.xls')):
                workbook = openpyxl.load_workbook(io.BytesIO(file_content))
                sheet = workbook.active
                headers = [cell.value for cell in sheet[1]]
                staff_data = []
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    staff_data.append(dict(zip(headers, row)))
            else:
                return Response({
                    'success': False,
                    'error': 'Unsupported file format. Use CSV or Excel.'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            staff_data = data.get('staff_members', [])
        
        if not staff_data:
            return Response({
                'success': False,
                'error': 'No staff data provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_staff = []
        errors = []
        
        for idx, staff_info in enumerate(staff_data):
            try:
                serializer = StaffCreateUpdateSerializer(data=staff_info)
                if serializer.is_valid():
                    staff = Staff.objects.create(
                        **serializer.validated_data,
                        created_by=request.user,
                        status='Active'
                    )
                    created_staff.append({
                        'id': str(staff.id),
                        'name': staff.full_name,
                        'teacher_code': staff.teacher_code
                    })
                else:
                    errors.append({
                        'row': idx + 2,  # +2 for header row offset
                        'errors': serializer.errors
                    })
            except Exception as e:
                errors.append({
                    'row': idx + 2,
                    'errors': str(e)
                })
        
        return Response({
            'success': True,
            'created_count': len(created_staff),
            'error_count': len(errors),
            'created_staff': created_staff,
            'errors': errors
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_template(request):
    """Download CSV template for bulk staff upload"""
    try:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="staff_import_template.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'first_name', 'middle_name', 'last_name', 'date_of_birth', 'gender',
            'national_id', 'personal_email', 'personal_phone', 'permanent_address',
            'employment_type', 'employment_date', 'designation', 'teacher_category_code',
            'highest_qualification', 'specialization'
        ])
        
        # Add sample row
        writer.writerow([
            'John', '', 'Doe', '1990-01-15', 'Male',
            '12345678', 'john.doe@example.com', '0712345678', 'Nairobi, Kenya',
            'Permanent', '2024-01-01', 'Senior Teacher', 'JSS',
            'Bachelor of Education', 'Mathematics'
        ])
        
        return response
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_staff(request):
    """Export staff data to CSV"""
    try:
        format_type = request.query_params.get('format', 'csv')
        staff = Staff.objects.select_related('teacher_category').all()
        
        data = []
        for s in staff:
            data.append({
                'Staff ID': s.staff_id,
                'Teacher Code': s.teacher_code,
                'First Name': s.first_name,
                'Middle Name': s.middle_name or '',
                'Last Name': s.last_name,
                'Full Name': s.full_name,
                'Date of Birth': s.date_of_birth,
                'Gender': s.gender,
                'National ID': s.national_id,
                'Email': s.personal_email,
                'Phone': s.personal_phone,
                'Designation': s.designation,
                'Category': s.teacher_category.code if s.teacher_category else '',
                'Employment Type': s.employment_type,
                'Employment Date': s.employment_date,
                'Status': s.status
            })
        
        if format_type == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="staff_export.csv"'
            
            if data:
                writer = csv.DictWriter(response, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            
            return response
        
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unassigned_staff(request):
    """Get staff members not assigned to any active department"""
    try:
        # Get staff with active department assignments
        staff_with_assignments = DepartmentStaffAssignment.objects.filter(
            is_active=True
        ).values_list('staff_id', flat=True).distinct()
        
        # Get active staff without any department assignments
        unassigned_staff = Staff.objects.exclude(
            id__in=staff_with_assignments
        ).filter(
            status='Active'
        ).select_related('teacher_category')
        
        # Apply search if provided
        search = request.query_params.get('search', '')
        if search:
            unassigned_staff = unassigned_staff.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(teacher_code__icontains=search) |
                Q(staff_id__icontains=search) |
                Q(personal_email__icontains=search)
            )
        
        # Also include staff who only have inactive assignments
        staff_with_only_inactive = Staff.objects.filter(
            department_assignments__is_active=False
        ).exclude(
            id__in=Staff.objects.filter(department_assignments__is_active=True)
        ).filter(
            status='Active'
        ).distinct()
        
        # Combine and deduplicate
        all_unassigned = list(unassigned_staff) + list(staff_with_only_inactive)
        unique_unassigned = {s.id: s for s in all_unassigned}.values()
        
        from cbe_app.serializers.hr_serializers.hr_staff_mng_serializers import UnassignedStaffSerializer
        serializer = UnassignedStaffSerializer(unique_unassigned, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)