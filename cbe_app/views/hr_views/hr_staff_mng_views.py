# cbe_app/views/hr_views/hr_staff_mng_views.py

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Q, Sum, Count
from datetime import datetime, date, timedelta
import logging
import pandas as pd
import io

from cbe_app.models import Staff, User, StaffLeave, StaffLoan, LoanRepayment, PayrollRecord, PayrollPeriod
from cbe_app.serializers.hr_serializers.hr_staff_mng_serializers import (
    StaffSerializer, StaffCreateSerializer, StaffListSerializer,
    StaffLeaveSerializer, StaffLeaveCreateSerializer,
    StaffLoanSerializer, StaffLoanCreateSerializer,
    PayrollRecordSerializer, LeaveBalanceSerializer
)

logger = logging.getLogger(__name__)


def generate_staff_id():
    """Generate unique staff ID"""
    year = date.today().year
    count = Staff.objects.filter(employment_date__year=year).count() + 1
    return f"STF/{year}/{count:04d}"


def parse_date(date_value):
    """Parse date from various formats"""
    if not date_value or pd.isna(date_value):
        return None
    
    try:
        if isinstance(date_value, datetime):
            return date_value.date()
        elif isinstance(date_value, date):
            return date_value
        elif isinstance(date_value, str):
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(date_value, fmt).date()
                except:
                    continue
        return None
    except:
        return None


# ==================== STAFF CRUD VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_list(request):
    """Get all staff members with filters"""
    try:
        department = request.query_params.get('department')
        role = request.query_params.get('role')
        status_filter = request.query_params.get('status')
        employment_type = request.query_params.get('employment_type')
        search = request.query_params.get('search')
        
        queryset = Staff.objects.filter(archived=False).select_related('user', 'reporting_to').order_by('-created_at')
        
        if department and department != '':
            queryset = queryset.filter(department__iexact=department)
        
        if role and role != '':
            queryset = queryset.filter(designation__iexact=role)
        
        if status_filter and status_filter != '':
            queryset = queryset.filter(status__iexact=status_filter)
        
        if employment_type and employment_type != '':
            queryset = queryset.filter(employment_type__iexact=employment_type)
        
        if search and search.strip() != '':
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(staff_id__icontains=search) |
                Q(personal_email__icontains=search) |
                Q(department__icontains=search) |
                Q(designation__icontains=search)
            )
        
        serializer = StaffListSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_detail(request, staff_id):
    """Get staff member details"""
    try:
        staff = Staff.objects.select_related('user', 'reporting_to').get(id=staff_id, archived=False)
        serializer = StaffSerializer(staff)
        
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
        # Map frontend field names
        data = request.data.copy()
        
        if 'email' in data and 'personal_email' not in data:
            data['personal_email'] = data.pop('email')
        
        if 'phone' in data and 'personal_phone' not in data:
            data['personal_phone'] = data.pop('phone')
        
        # Set employment_date if not provided
        if 'employment_date' not in data or not data['employment_date']:
            data['employment_date'] = date.today().isoformat()
        
        if request.user.role not in ['hr_manager', 'system_admin', 'admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create staff members'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = StaffCreateSerializer(data=data)
        
        if serializer.is_valid():
            with transaction.atomic():
                staff = serializer.save(created_by=request.user)
                response_serializer = StaffSerializer(staff)
                
                return Response({
                    'success': True,
                    'data': response_serializer.data,
                    'message': f'Staff member {staff.full_name} created successfully'
                }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_staff(request, staff_id):
    """Update staff member"""
    try:
        data = request.data.copy()
        
        if 'email' in data and 'personal_email' not in data:
            data['personal_email'] = data.pop('email')
        
        if 'phone' in data and 'personal_phone' not in data:
            data['personal_phone'] = data.pop('phone')
        
        if request.user.role not in ['hr_manager', 'system_admin', 'admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update staff members'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            staff = Staff.objects.select_related('user').get(id=staff_id, archived=False)
        except Staff.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Staff member not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = StaffCreateSerializer(staff, data=data, partial=(request.method == 'PATCH'))
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_staff = serializer.save(updated_by=request.user)
                response_serializer = StaffSerializer(updated_staff)
                
                return Response({
                    'success': True,
                    'data': response_serializer.data,
                    'message': f'Staff member {updated_staff.full_name} updated successfully'
                }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_staff(request, staff_id):
    """Delete staff member (soft delete)"""
    try:
        if request.user.role not in ['hr_manager', 'system_admin', 'admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete staff members'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            staff = Staff.objects.get(id=staff_id, archived=False)
        except Staff.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Staff member not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        with transaction.atomic():
            staff.archived = True
            staff.status = 'Terminated'
            staff.status_date = date.today()
            staff.save()
            
            if staff.user:
                staff.user.is_active = False
                staff.user.save()
        
        return Response({
            'success': True,
            'message': f'Staff member {staff.full_name} has been archived'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== STAFF STATISTICS VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_stats(request):
    """Get staff statistics"""
    try:
        total_staff = Staff.objects.filter(archived=False).count()
        active_staff = Staff.objects.filter(status='Active', archived=False).count()
        teachers = Staff.objects.filter(department='Teaching', archived=False).count()
        admin = Staff.objects.filter(department='Administration', archived=False).count()
        total_salary = Staff.objects.filter(archived=False, basic_salary__isnull=False).aggregate(total=Sum('basic_salary'))['total'] or 0
        
        return Response({
            'success': True,
            'data': {
                'total_staff': total_staff,
                'active_staff': active_staff,
                'teachers': teachers,
                'admin_staff': admin,
                'total_monthly_salary': float(total_salary)
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== LEAVE MANAGEMENT VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_leaves(request, staff_id):
    """Get all leave requests for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        leaves = StaffLeave.objects.filter(staff=staff).order_by('-applied_date')
        serializer = StaffLeaveSerializer(leaves, many=True)
        
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
def create_staff_leave(request, staff_id):
    """Create a leave request for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        
        serializer = StaffLeaveCreateSerializer(data=request.data, context={'staff': staff})
        
        if serializer.is_valid():
            with transaction.atomic():
                leave = serializer.save()
                
                return Response({
                    'success': True,
                    'data': StaffLeaveSerializer(leave).data,
                    'message': 'Leave request submitted successfully'
                }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_leave_balance(request, staff_id):
    """Get leave balance for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        
        # Calculate leave balance based on employment duration
        employment_years = 0
        if staff.employment_date:
            employment_years = (date.today() - staff.employment_date).days // 365
        
        # Default leave entitlements (can be customized based on policies)
        annual_entitlement = 21 + (employment_years // 5)  # Additional day after 5 years
        sick_entitlement = 30
        maternity_entitlement = 90
        paternity_entitlement = 14
        study_entitlement = 10
        compassionate_entitlement = 5
        
        # Get used leaves
        used_leaves = StaffLeave.objects.filter(
            staff=staff,
            status='Approved',
            end_date__year=date.today().year
        )
        
        used_annual = used_leaves.filter(leave_type='Annual').aggregate(total=Sum('total_days'))['total'] or 0
        used_sick = used_leaves.filter(leave_type='Sick').aggregate(total=Sum('total_days'))['total'] or 0
        used_maternity = used_leaves.filter(leave_type='Maternity').aggregate(total=Sum('total_days'))['total'] or 0
        used_paternity = used_leaves.filter(leave_type='Paternity').aggregate(total=Sum('total_days'))['total'] or 0
        used_study = used_leaves.filter(leave_type='Study').aggregate(total=Sum('total_days'))['total'] or 0
        used_compassionate = used_leaves.filter(leave_type='Compassionate').aggregate(total=Sum('total_days'))['total'] or 0
        
        balance = {
            'annual': annual_entitlement - used_annual,
            'sick': sick_entitlement - used_sick,
            'maternity': maternity_entitlement - used_maternity,
            'paternity': paternity_entitlement - used_paternity,
            'study': study_entitlement - used_study,
            'compassionate': compassionate_entitlement - used_compassionate
        }
        
        serializer = LeaveBalanceSerializer(balance)
        
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


# ==================== LOAN MANAGEMENT VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_loans(request, staff_id):
    """Get all loans for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        loans = StaffLoan.objects.filter(staff=staff).order_by('-applied_date')
        serializer = StaffLoanSerializer(loans, many=True)
        
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
# cbe_app/views/hr_views/hr_staff_mng_views.py

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_staff_loan(request, staff_id):
    """Create a loan request for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        
        # Check if staff has active loan
        if StaffLoan.objects.filter(staff=staff, status__in=['Approved', 'Active', 'Disbursed']).exists():
            return Response({
                'success': False,
                'error': 'Staff already has an active loan'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Log the received data for debugging
        print("Received loan data:", request.data)
        
        # Get the data from request
        data = request.data.copy()
        
        # Ensure all required fields are present
        required_fields = ['loan_type', 'loan_amount', 'reason']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        
        if missing_fields:
            return Response({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Convert numeric fields
        try:
            data['loan_amount'] = float(data['loan_amount'])
            if 'interest_rate' in data and data['interest_rate']:
                data['interest_rate'] = float(data['interest_rate'])
            if 'repayment_months' in data and data['repayment_months']:
                data['repayment_months'] = int(data['repayment_months'])
        except ValueError as e:
            return Response({
                'success': False,
                'error': f'Invalid numeric value: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create serializer with context
        serializer = StaffLoanCreateSerializer(data=data, context={'staff': staff})
        
        if serializer.is_valid():
            with transaction.atomic():
                loan = serializer.save()
                
                return Response({
                    'success': True,
                    'data': StaffLoanSerializer(loan).data,
                    'message': 'Loan request submitted successfully'
                }, status=status.HTTP_201_CREATED)
        else:
            print("Serializer errors:", serializer.errors)
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Staff.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Staff member not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        print("Exception:", str(e))
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

# ==================== PAYROLL VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_staff_payroll(request, staff_id):
    """Get payroll records for a staff member"""
    try:
        staff = Staff.objects.get(id=staff_id)
        payroll_records = PayrollRecord.objects.filter(staff=staff).select_related('payroll_period').order_by('-payroll_period__pay_date')
        serializer = PayrollRecordSerializer(payroll_records, many=True)
        
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


# ==================== BULK OPERATIONS VIEWS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_create_staff(request):
    """Bulk create staff from Excel file"""
    try:
        if request.user.role not in ['hr_manager', 'system_admin', 'admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to perform bulk upload'
            }, status=status.HTTP_403_FORBIDDEN)
        
        file = request.FILES.get('file')
        if not file:
            return Response({
                'success': False,
                'error': 'No file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file, engine='openpyxl')
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to read file: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        required_columns = ['first_name', 'last_name', 'email', 'phone', 'department', 'designation']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return Response({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_staff = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                if pd.isna(row.get('first_name')) or pd.isna(row.get('last_name')):
                    continue
                
                staff_data = {
                    'first_name': str(row.get('first_name')).strip(),
                    'last_name': str(row.get('last_name')).strip(),
                    'personal_email': str(row.get('email')).strip() if not pd.isna(row.get('email')) else None,
                    'personal_phone': str(row.get('phone')).strip() if not pd.isna(row.get('phone')) else None,
                    'department': str(row.get('department')).strip() if not pd.isna(row.get('department')) else None,
                    'designation': str(row.get('designation')).strip() if not pd.isna(row.get('designation')) else None,
                    'gender': str(row.get('gender')).strip() if not pd.isna(row.get('gender')) else 'Male',
                    'date_of_birth': parse_date(row.get('date_of_birth')),
                    'national_id': str(row.get('national_id')).strip() if not pd.isna(row.get('national_id')) else None,
                    'employment_type': str(row.get('employment_type')).strip() if not pd.isna(row.get('employment_type')) else 'Permanent',
                    'employment_date': parse_date(row.get('employment_date')) or date.today(),
                    'basic_salary': float(row.get('basic_salary')) if not pd.isna(row.get('basic_salary')) else 0,
                    'bank_name': str(row.get('bank_name')).strip() if not pd.isna(row.get('bank_name')) else None,
                    'account_number': str(row.get('account_number')).strip() if not pd.isna(row.get('account_number')) else None,
                    'kra_pin': str(row.get('kra_pin')).strip() if not pd.isna(row.get('kra_pin')) else None,
                    'nssf_no': str(row.get('nssf_no')).strip() if not pd.isna(row.get('nssf_no')) else None,
                    'nhif_no': str(row.get('nhif_no')).strip() if not pd.isna(row.get('nhif_no')) else None,
                    'emergency_contact': str(row.get('emergency_contact')).strip() if not pd.isna(row.get('emergency_contact')) else None,
                    'emergency_contact_name': str(row.get('emergency_contact_name')).strip() if not pd.isna(row.get('emergency_contact_name')) else None,
                    'status': 'Active'
                }
                
                if not staff_data['personal_email']:
                    raise ValueError("Email is required")
                if not staff_data['personal_phone']:
                    raise ValueError("Phone number is required")
                
                if Staff.objects.filter(personal_email=staff_data['personal_email']).exists():
                    raise ValueError(f"Email {staff_data['personal_email']} already exists")
                
                # Create staff using serializer
                serializer = StaffCreateSerializer(data=staff_data)
                if serializer.is_valid():
                    staff = serializer.save(created_by=request.user)
                    created_staff.append({
                        'staff_id': staff.staff_id,
                        'name': staff.full_name,
                        'email': staff.personal_email
                    })
                else:
                    raise ValueError(f"Validation error: {serializer.errors}")
                
            except Exception as e:
                errors.append({
                    'row': index + 2,
                    'error': str(e)
                })
        
        return Response({
            'success': True,
            'data': {
                'created': created_staff,
                'created_count': len(created_staff),
                'errors': errors,
                'failed_count': len(errors)
            },
            'message': f'Successfully created {len(created_staff)} staff members. {len(errors)} errors.'
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_template(request):
    """Download Excel template for bulk upload"""
    try:
        template_data = {
            'first_name': ['John', 'Mary'],
            'last_name': ['Doe', 'Jane'],
            'email': ['john.doe@example.com', 'mary.jane@example.com'],
            'phone': ['0712345678', '0723456789'],
            'department': ['Teaching', 'Administration'],
            'designation': ['Teacher', 'Accountant'],
            'gender': ['Male', 'Female'],
            'date_of_birth': ['1990-01-01', '1985-05-15'],
            'national_id': ['12345678', '87654321'],
            'employment_type': ['Permanent', 'Contract'],
            'employment_date': ['2024-01-01', '2024-02-01'],
            'basic_salary': [50000, 60000],
            'bank_name': ['Equity Bank', 'KCB Bank'],
            'account_number': ['1234567890', '0987654321'],
            'kra_pin': ['A123456789B', 'B987654321C'],
            'nssf_no': ['NS123456', 'NS654321'],
            'nhif_no': ['NH123456', 'NH654321'],
            'emergency_contact': ['0712345678', '0723456789'],
            'emergency_contact_name': ['Jane Doe', 'John Smith']
        }
        
        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Staff Template', index=False)
            
            # Add instructions sheet
            instructions = pd.DataFrame({
                'Column': list(template_data.keys()),
                'Required': ['Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No'],
                'Description': [
                    'First name of staff member', 'Last name of staff member',
                    'Email address (must be unique)', 'Phone number (must be unique)',
                    'Department (Teaching, Administration, ICT, etc.)', 'Job title/designation',
                    'Male/Female/Other', 'Date of birth (YYYY-MM-DD)', 'National ID number',
                    'Permanent/Contract/Probation/Part-time/Intern', 'Employment start date (YYYY-MM-DD)',
                    'Monthly salary in KES', 'Bank name', 'Bank account number', 'KRA PIN number',
                    'NSSF number', 'NHIF number', 'Emergency contact phone', 'Emergency contact name'
                ]
            })
            instructions.to_excel(writer, sheet_name='Instructions', index=False)
        
        output.seek(0)
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="staff_import_template.xlsx"'
        
        return response
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_staff(request):
    """Export staff data to Excel"""
    try:
        department = request.query_params.get('department')
        status_filter = request.query_params.get('status')
        
        queryset = Staff.objects.filter(archived=False).select_related('user')
        
        if department and department != '':
            queryset = queryset.filter(department__iexact=department)
        
        if status_filter and status_filter != '':
            queryset = queryset.filter(status__iexact=status_filter)
        
        export_data = []
        for staff in queryset:
            export_data.append({
                'Staff ID': staff.staff_id,
                'First Name': staff.first_name,
                'Last Name': staff.last_name,
                'Email': staff.personal_email,
                'Phone': staff.personal_phone,
                'Department': staff.department,
                'Designation': staff.designation,
                'Employment Type': staff.employment_type,
                'Basic Salary': float(staff.basic_salary) if staff.basic_salary else 0,
                'Status': staff.status,
                'Gender': staff.gender,
                'Date of Birth': staff.date_of_birth.strftime('%Y-%m-%d') if staff.date_of_birth else '',
                'National ID': staff.national_id or '',
                'Bank Name': staff.bank_name or '',
                'Account Number': staff.account_number or '',
                'KRA PIN': staff.kra_pin or '',
                'NSSF No': staff.nssf_no or '',
                'NHIF No': staff.nhif_no or '',
                'Emergency Contact': staff.emergency_contact or '',
                'Emergency Contact Name': staff.emergency_contact_name or ''
            })
        
        df = pd.DataFrame(export_data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Staff Export', index=False)
        
        output.seek(0)
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="staff_export_{date.today()}.xlsx"'
        
        return response
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)