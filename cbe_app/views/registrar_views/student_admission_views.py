from rest_framework import request, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
import logging
import pandas as pd
import re
from datetime import datetime
import os
import uuid

from ...models import Student, Class, User
from ...serializers.registrar_serializers.student_admission_serializers import (
    StudentSerializer, StudentCreateSerializer, StudentImportSerializer,
    AdmissionNumberConfigSerializer
)

logger = logging.getLogger(__name__)

# Helper function to parse admission number
def parse_admission_number(adm_no):
    """Parse admission number and return components"""
    if not adm_no:
        return None
    
    # Match format: PREFIX-YYYYMM-SEQUENCE
    pattern = r'^([A-Z]+)-(\d{4})(\d{2})-(\d+)$'
    match = re.match(pattern, adm_no)
    
    if match:
        return {
            'prefix': match.group(1),
            'year': int(match.group(2)),
            'month': int(match.group(3)),
            'sequence': int(match.group(4))
        }
    return None

# Helper function to generate admission number
def generate_admission_number(prefix='ADM', year=None, month=None, next_sequence=1):
    """Generate admission number in format: PREFIX-YYYYMM-SEQUENCE"""
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month
    
    year_str = str(year)
    month_str = str(month).zfill(2)
    
    return f"{prefix}-{year_str}{month_str}-{next_sequence}"

# Helper function to get next admission sequence
def get_next_admission_sequence(students_queryset, prefix='ADM', year=None, month=None):
    """Get the next sequence number for admission numbers"""
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month
    
    highest_sequence = 0
    
    for student in students_queryset:
        if student.admission_no:
            parsed = parse_admission_number(student.admission_no)
            if parsed and parsed['prefix'] == prefix and parsed['year'] == year and parsed['month'] == month:
                if parsed['sequence'] > highest_sequence:
                    highest_sequence = parsed['sequence']
    
    return highest_sequence + 1

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_students(request):
    """
    Get all students with optional filtering
    """
    try:
        # Get query parameters
        status_param = request.query_params.get('status')
        class_id = request.query_params.get('class_id')
        search = request.query_params.get('search')
        limit = request.query_params.get('limit')
        
        # Base queryset
        queryset = Student.objects.select_related('current_class', 'created_by').all().order_by('-created_at')
        
        # Apply filters
        if status_param:
            queryset = queryset.filter(status__iexact=status_param)
        
        if class_id:
            queryset = queryset.filter(current_class_id=class_id)
        
        if search:
            queryset = queryset.filter(
                Q(admission_no__icontains=search) |
                Q(first_name__icontains=search) |
                Q(middle_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(guardian_phone__icontains=search)
            )
        
        # Apply limit if specified
        if limit:
            try:
                limit = int(limit)
                queryset = queryset[:limit]
            except ValueError:
                pass
        
        serializer = StudentSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching students: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch students'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_detail(request, student_id):
    """
    Get detailed information about a specific student
    """
    try:
        try:
            student = Student.objects.select_related('current_class', 'created_by').get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = StudentSerializer(student)
        
        # Add additional information
        data = serializer.data
        data['academic_history'] = []  # You can add academic history if needed
        
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching student detail {student_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch student details'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_student(request):
    """
    Create a new student record
    """
    try:
        # Check if user has permission
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal', 'director_studies']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create student records'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Create a clean mapped dictionary (just like import)
        student_data = {
            'admission_no': request.data.get('admission_no'),
            'first_name': request.data.get('first_name'),
            'middle_name': request.data.get('middle_name', ''),
            'last_name': request.data.get('last_name'),
            'date_of_birth': request.data.get('date_of_birth'),
            'gender': request.data.get('gender'),
            'nationality': request.data.get('nationality', 'Kenyan'),
            'religion': request.data.get('religion', ''),
            'blood_group': request.data.get('blood_group', ''),
            'address': request.data.get('address'),
            'city': request.data.get('city', ''),
            'country': request.data.get('country', 'Kenya'),
            'phone': request.data.get('phone'),
            'email': request.data.get('email', ''),
            'current_class': request.data.get('current_class'),
            'current_section': request.data.get('current_section', ''),
            'stream': request.data.get('stream', ''),
            'roll_number': request.data.get('roll_number'),
            'admission_date': request.data.get('admission_date'),
            'admission_type': request.data.get('admission_type', 'Regular'),
            'father_name': request.data.get('father_name', ''),
            'father_phone': request.data.get('father_phone', ''),
            'father_email': request.data.get('father_email', ''),
            'father_occupation': request.data.get('father_occupation', ''),
            'mother_name': request.data.get('mother_name', ''),
            'mother_phone': request.data.get('mother_phone', ''),
            'mother_email': request.data.get('mother_email', ''),
            'mother_occupation': request.data.get('mother_occupation', ''),
            'guardian_name': request.data.get('guardian_name'),
            'guardian_relation': request.data.get('guardian_relation'),
            'guardian_phone': request.data.get('guardian_phone'),
            'guardian_email': request.data.get('guardian_email', ''),
            'guardian_address': request.data.get('guardian_address', ''),
            'medical_conditions': request.data.get('medical_conditions', ''),
            'allergies': request.data.get('allergies', ''),
            'medication': request.data.get('medication', ''),
            'emergency_contact': request.data.get('emergency_contact'),
            'emergency_contact_name': request.data.get('emergency_contact_name'),
            'previous_school': request.data.get('previous_school', ''),
            'previous_class': request.data.get('previous_class', ''),
            'transfer_certificate_no': request.data.get('transfer_certificate_no', ''),
            'status': request.data.get('status', 'Active'),
            'expected_graduation_date': request.data.get('expected_graduation_date', None),
            'created_by': request.user.id
        }
        
        # Check for duplicate email
        if student_data.get('email'):
            email = student_data['email'].lower().strip()
            if Student.objects.filter(email=email).exists():
                return Response({
                    'success': False,
                    'error': f'A student with email "{email}" already exists.'
                }, status=status.HTTP_400_BAD_REQUEST)
            student_data['email'] = email
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'gender', 'date_of_birth', 'address', 'phone']
        for field in required_fields:
            if not student_data.get(field):
                return Response({
                    'success': False,
                    'error': f'{field.replace("_", " ").title()} is required'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate class exists
        if student_data.get('current_class'):
            try:
                class_obj = Class.objects.filter(id=student_data['current_class']).first()
                if not class_obj:
                    return Response({
                        'success': False,
                        'error': f'Class with ID "{student_data["current_class"]}" not found'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({
                    'success': False,
                    'error': 'Invalid class ID format'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create student with transaction
        with transaction.atomic():
            serializer = StudentCreateSerializer(data=student_data)
            
            if serializer.is_valid():
                student = serializer.save()
                
                logger.info(f"Student created: {student.admission_no} by user {request.user.username}")
                
                response_serializer = StudentSerializer(student)
                return Response({
                    'success': True,
                    'data': response_serializer.data,
                    'message': f'Student {student.full_name} registered successfully with admission number {student.admission_no}'
                }, status=status.HTTP_201_CREATED)
            else:
                
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
    
    except ValidationError as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating student: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create student. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_student(request, student_id):
    """
    Update an existing student record
    """
    try:
        # Check if user has permission
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal', 'director_studies']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update student records'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get student
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Set updated_by
        request.data['updated_by'] = request.user.id
        
        # Update student
        with transaction.atomic():
            serializer = StudentCreateSerializer(student, data=request.data, partial=True)
            
            if serializer.is_valid():
                updated_student = serializer.save()
                
                logger.info(f"Student updated: {updated_student.admission_no} by user {request.user.username}")
                
                response_serializer = StudentSerializer(updated_student)
                return Response({
                    'success': True,
                    'data': response_serializer.data,
                    'message': f'Student {updated_student.full_name} updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error updating student {student_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to update student. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_student(request, student_id):
    """
    Delete a student record (soft delete by setting archived=True)
    """
    try:
        # Check if user has permission
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete student records'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get student
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Soft delete by setting archived=True
        student.archived = True
        student.archived_at = datetime.now()
        student.save()
        
        logger.info(f"Student deleted: {student.admission_no} by user {request.user.username}")
        
        return Response({
            'success': True,
            'message': f'Student {student.full_name} deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting student {student_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete student. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_admission_number_view(request):
    """
    Generate a new admission number based on configuration
    """
    try:
        # Get parameters from request
        prefix = request.query_params.get('prefix', 'ADM')
        
        # Get current year and month
        year = datetime.now().year
        month = datetime.now().month
        
        # Get next sequence
        next_sequence = get_next_admission_sequence(
            Student.objects.filter(archived=False),
            prefix=prefix,
            year=year,
            month=month
        )
        
        admission_no = generate_admission_number(
            prefix=prefix,
            year=year,
            month=month,
            next_sequence=next_sequence
        )
        
        return Response({
            'success': True,
            'admission_no': admission_no,
            'next_sequence': next_sequence,
            'prefix': prefix,
            'year': year,
            'month': month
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error generating admission number: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to generate admission number'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_students(request):
    """
    Import students from Excel file
    """
    try:
        # Check if user has permission
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to import students'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if file was uploaded
        if 'excelFile' not in request.FILES:
            return Response({
                'success': False,
                'error': 'No file uploaded'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        excel_file = request.FILES['excelFile']
        
        # Check file extension
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response({
                'success': False,
                'error': 'Invalid file format. Please upload .xlsx or .xls file'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Read Excel file
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to read Excel file: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Log the columns found in Excel
        logger.info(f"Excel columns found: {list(df.columns)}")
        
        # Field mapping (adjust based on your Excel template)
        field_mapping = {
            'admission_no': 'admission_no',
            'first_name': 'first_name',
            'middle_name': 'middle_name',
            'last_name': 'last_name',
            'date_of_birth': 'date_of_birth',
            'gender': 'gender',
            'nationality': 'nationality',
            'religion': 'religion',
            'blood_group': 'blood_group',
            'address': 'address',
            'city': 'city',
            'country': 'country',
            'phone': 'phone',
            'email': 'email',
            'current_class': 'current_class',  # This might need to be current_class_id
            'current_section': 'current_section',
            'stream': 'stream',
            'roll_number': 'roll_number',
            'admission_date': 'admission_date',
            'admission_type': 'admission_type',
            'father_name': 'father_name',
            'father_phone': 'father_phone',
            'father_email': 'father_email',
            'father_occupation': 'father_occupation',
            'mother_name': 'mother_name',
            'mother_phone': 'mother_phone',
            'mother_email': 'mother_email',
            'mother_occupation': 'mother_occupation',
            'guardian_name': 'guardian_name',
            'guardian_relation': 'guardian_relation',
            'guardian_phone': 'guardian_phone',
            'guardian_email': 'guardian_email',
            'guardian_address': 'guardian_address',
            'medical_conditions': 'medical_conditions',
            'allergies': 'allergies',
            'medication': 'medication',
            'emergency_contact': 'emergency_contact',
            'emergency_contact_name': 'emergency_contact_name',
            'previous_school': 'previous_school',
            'previous_class': 'previous_class',
            'transfer_certificate_no': 'transfer_certificate_no',
            'status': 'status',
            'expected_graduation_date': 'expected_graduation_date'
        }
        
        # Convert DataFrame to list of dictionaries with proper field mapping
        students_data = []
        for _, row in df.iterrows():
            student_dict = {}
            for excel_col, model_field in field_mapping.items():
                if excel_col in df.columns:
                    value = row[excel_col]
                    # Handle NaN values
                    if pd.isna(value):
                        student_dict[model_field] = None
                    else:
                        student_dict[model_field] = value
            
            # Add created_by
            student_dict['created_by'] = request.user.id
            
            students_data.append(student_dict)
        
        imported_count = 0
        errors = []
        
        # Process each row
        with transaction.atomic():
            for index, student_data in enumerate(students_data):
                try:
                    # Check for duplicate email
                    if student_data.get('email'):
                        email = student_data['email'].lower().strip()
                        
                        # Check if email already exists in database
                        if Student.objects.filter(email=email).exists():
                            errors.append({
                                'row': index + 2,
                                'error': f'Email "{email}" already exists in the database',
                                'data': student_data
                            })
                            continue  # Skip this row
                        
                        # Check if email already used in this batch (prevents duplicates within same file)
                        if 'emails_in_batch' not in locals():
                            emails_in_batch = set()
                        
                        if email in emails_in_batch:
                            errors.append({
                                'row': index + 2,
                                'error': f'Duplicate email "{email}" in the same import file',
                                'data': student_data
                            })
                            continue
                        
                        emails_in_batch.add(email)
                        student_data['email'] = email
                    # Generate admission number if not provided
                    if not student_data.get('admission_no'):
                        # Get current year and month
                        year = datetime.now().year
                        month = datetime.now().month
                        
                        # Get next sequence
                        next_sequence = get_next_admission_sequence(
                            Student.objects.all(),
                            prefix='ADM',
                            year=year,
                            month=month
                        ) + imported_count
                        
                        student_data['admission_no'] = generate_admission_number(
                            prefix='ADM',
                            year=year,
                            month=month,
                            next_sequence=next_sequence
                        )
                    
                    # Handle class field - accept UUID directly
                    if student_data.get('current_class'):
                        class_id = student_data['current_class']
                        try:
                            # Check if it's a valid UUID and exists
                            class_obj = Class.objects.filter(id=class_id).first()
                            if class_obj:
                                student_data['current_class'] = class_obj.id
                            else:
                                errors.append({
                                    'row': index + 2,
                                    'error': f'Class with ID "{class_id}" not found',
                                    'data': student_data
                                })
                                continue
                        except Exception as e:
                            errors.append({
                                'row': index + 2,
                                'error': f'Invalid class ID format: {class_id}',
                                'data': student_data
                            })
                            continue
                    
                    # Validate and create student
                    serializer = StudentCreateSerializer(data=student_data)
                    
                    if serializer.is_valid():
                        serializer.save()
                        imported_count += 1
                    else:
                        errors.append({
                            'row': index + 2,  # +2 for header row and 1-based indexing
                            'errors': serializer.errors,
                            'data': student_data
                        })
                        logger.error(f"Validation error for row {index + 2}: {serializer.errors}")
                
                except Exception as e:
                    errors.append({
                        'row': index + 2,
                        'error': str(e),
                        'data': student_data if 'student_data' in locals() else {}
                    })
                    logger.error(f"Error importing row {index + 2}: {str(e)}")
        
        logger.info(f"Imported {imported_count} students by user {request.user.username}. Errors: {len(errors)}")
        
        return Response({
            'success': True,
            'importedCount': imported_count,
            'errors': errors,
            'message': f'Successfully imported {imported_count} students. {len(errors)} errors.'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error importing students: {str(e)}")
        return Response({
            'success': False,
            'error': f'Failed to import students: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_admission_stats(request):
    """
    Get admission statistics
    """
    try:
        total_students = Student.objects.filter(archived=False).count()
        active_students = Student.objects.filter(status='Active', archived=False).count()
        
        # Get class distribution
        class_distribution = []
        classes = Class.objects.filter(is_active=True)
        for cls in classes:
            count = Student.objects.filter(current_class=cls, status='Active', archived=False).count()
            if count > 0:
                class_distribution.append({
                    'class_id': str(cls.id),
                    'class_name': cls.class_name,
                    'class_code': cls.class_code,
                    'student_count': count,
                    'capacity': cls.capacity,
                    'percentage_filled': round((count / cls.capacity) * 100, 1) if cls.capacity > 0 else 0
                })
        
        # Get gender distribution
        male_count = Student.objects.filter(gender='Male', archived=False).count()
        female_count = Student.objects.filter(gender='Female', archived=False).count()
        other_count = Student.objects.filter(gender='Other', archived=False).count()
        
        # Get admission type distribution
        admission_types = {}
        for choice in Student.ADMISSION_TYPE_CHOICES:
            count = Student.objects.filter(admission_type=choice[0], archived=False).count()
            if count > 0:
                admission_types[choice[0]] = count
        
        return Response({
            'success': True,
            'data': {
                'total_students': total_students,
                'active_students': active_students,
                'class_distribution': class_distribution,
                'gender_distribution': {
                    'male': male_count,
                    'female': female_count,
                    'other': other_count
                },
                'admission_type_distribution': admission_types
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching admission stats: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch admission statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_admission_number(request):
    """
    Validate and parse an admission number
    """
    try:
        admission_no = request.data.get('admission_no')
        
        if not admission_no:
            return Response({
                'success': False,
                'error': 'Admission number is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        parsed = parse_admission_number(admission_no)
        
        if parsed:
            # Check if admission number exists
            exists = Student.objects.filter(admission_no=admission_no).exists()
            
            return Response({
                'success': True,
                'data': {
                    'admission_no': admission_no,
                    'prefix': parsed['prefix'],
                    'year': parsed['year'],
                    'month': parsed['month'],
                    'sequence': parsed['sequence'],
                    'exists': exists,
                    'format_valid': True
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': 'Invalid admission number format. Must be: PREFIX-YYYYMM-SEQUENCE',
                'format_valid': False
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error validating admission number: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to validate admission number'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)