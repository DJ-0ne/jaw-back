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

# Helper function to parse admission number - NEW FORMAT
def parse_admission_number(adm_no):
    """Parse admission number - New format: PREFIX-XXX (e.g., ADM/JWB-001)"""
    if not adm_no:
        return None
    
    # New format: PREFIX-XXX
    pattern = r'^([A-Z/]+)-(\d+)$'
    match = re.match(pattern, adm_no)
    
    if match:
        return {
            'prefix': match.group(1),
            'sequence': int(match.group(2))
        }
    return None

# Helper function to generate admission number - NEW FORMAT
def generate_admission_number(prefix='ADM/JWB', next_sequence=1):
    """Generate admission number in format: PREFIX-XXX (e.g., ADM/JWB-001)"""
    sequence_str = str(next_sequence).zfill(3)
    return f"{prefix}-{sequence_str}"

# Helper function to get next admission sequence - NEW FORMAT
def get_next_admission_sequence(students_queryset, prefix='ADM/JWB'):
    """Get the next sequence number for admission numbers"""
    highest_sequence = 0
    
    for student in students_queryset:
        if student.admission_no:
            parsed = parse_admission_number(student.admission_no)
            if parsed and parsed['prefix'] == prefix:
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
        status_param = request.query_params.get('status')
        class_id = request.query_params.get('class_id')
        search = request.query_params.get('search')
        limit = request.query_params.get('limit')
        
        queryset = Student.objects.select_related('current_class', 'created_by').all().order_by('-created_at')
        
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
                Q(upi_number__icontains=search) |
                Q(knec_number__icontains=search) |
                Q(guardian_phone__icontains=search)
            )
        
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
        
        return Response({
            'success': True,
            'data': serializer.data
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
    Create a new student record with NEMIS fields
    """
    try:
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal', 'director_studies']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create student records'
            }, status=status.HTTP_403_FORBIDDEN)
        
        student_data = {
            # NEMIS Fields
            'upi_number': request.data.get('upi_number', ''),
            'knec_number': request.data.get('knec_number', ''),
            'birth_certificate_no': request.data.get('birth_certificate_no', ''),
            
            # Admission
            'admission_no': request.data.get('admission_no'),
            
            # Personal
            'first_name': request.data.get('first_name'),
            'middle_name': request.data.get('middle_name', ''),
            'last_name': request.data.get('last_name'),
            'date_of_birth': request.data.get('date_of_birth'),
            'gender': request.data.get('gender'),
            'nationality': request.data.get('nationality', 'Kenyan'),
            'religion': request.data.get('religion', ''),
            'blood_group': request.data.get('blood_group', ''),
            
            # Contact
            'address': request.data.get('address'),
            'city': request.data.get('city', ''),
            'country': request.data.get('country', 'Kenya'),
            'phone': request.data.get('phone'),
            'email': request.data.get('email', ''),
            
            # Academic (removed section, stream, roll_number)
            'current_class': request.data.get('current_class'),
            'admission_date': request.data.get('admission_date'),
            'admission_type': request.data.get('admission_type', 'Regular'),
            
            # Parents
            'father_name': request.data.get('father_name', ''),
            'father_phone': request.data.get('father_phone', ''),
            'father_email': request.data.get('father_email', ''),
            'father_occupation': request.data.get('father_occupation', ''),
            'mother_name': request.data.get('mother_name', ''),
            'mother_phone': request.data.get('mother_phone', ''),
            'mother_email': request.data.get('mother_email', ''),
            'mother_occupation': request.data.get('mother_occupation', ''),
            
            # Guardian
            'guardian_name': request.data.get('guardian_name'),
            'guardian_relation': request.data.get('guardian_relation'),
            'guardian_phone': request.data.get('guardian_phone'),
            'guardian_email': request.data.get('guardian_email', ''),
            'guardian_address': request.data.get('guardian_address', ''),
            
            # Medical
            'medical_conditions': request.data.get('medical_conditions', ''),
            'allergies': request.data.get('allergies', ''),
            'medication': request.data.get('medication', ''),
            'emergency_contact': request.data.get('emergency_contact'),
            'emergency_contact_name': request.data.get('emergency_contact_name'),
            
            # Previous School
            'previous_school': request.data.get('previous_school', ''),
            'previous_class': request.data.get('previous_class', ''),
            'transfer_certificate_no': request.data.get('transfer_certificate_no', ''),
            
            'status': request.data.get('status', 'Active'),
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
        
        # Check for duplicate UPI
        if student_data.get('upi_number'):
            if Student.objects.filter(upi_number=student_data['upi_number']).exists():
                return Response({
                    'success': False,
                    'error': f'A student with UPI number "{student_data["upi_number"]}" already exists.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for duplicate KNEC
        if student_data.get('knec_number'):
            if Student.objects.filter(knec_number=student_data['knec_number']).exists():
                return Response({
                    'success': False,
                    'error': f'A student with KNEC number "{student_data["knec_number"]}" already exists.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for duplicate Birth Certificate
        if student_data.get('birth_certificate_no'):
            if Student.objects.filter(birth_certificate_no=student_data['birth_certificate_no']).exists():
                return Response({
                    'success': False,
                    'error': f'A student with Birth Certificate number "{student_data["birth_certificate_no"]}" already exists.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
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
        if request.user.role not in ['registrar', 'system_admin', 'principal', 'deputy_principal', 'director_studies']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update student records'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        request.data['updated_by'] = request.user.id
        
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
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete student records'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
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
    Generate a new admission number based on configuration - NEW FORMAT
    """
    try:
        prefix = request.query_params.get('prefix', 'ADM/JWB')
        
        next_sequence = get_next_admission_sequence(
            Student.objects.filter(archived=False),
            prefix=prefix
        )
        
        admission_no = generate_admission_number(
            prefix=prefix,
            next_sequence=next_sequence
        )
        
        return Response({
            'success': True,
            'admission_no': admission_no,
            'next_sequence': next_sequence,
            'prefix': prefix,
            'format': f"{prefix}-XXX"
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
    Import students from Excel file with new format and NEMIS fields
    """
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to import students'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if 'excelFile' not in request.FILES:
            return Response({
                'success': False,
                'error': 'No file uploaded'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        excel_file = request.FILES['excelFile']
        
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response({
                'success': False,
                'error': 'Invalid file format. Please upload .xlsx or .xls file'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to read Excel file: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Updated field mapping with NEMIS fields
        field_mapping = {
            'upi_number': 'upi_number',
            'knec_number': 'knec_number',
            'birth_certificate_no': 'birth_certificate_no',
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
            'current_class': 'current_class',
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
        }
        
        students_data = []
        for _, row in df.iterrows():
            student_dict = {}
            for excel_col, model_field in field_mapping.items():
                if excel_col in df.columns:
                    value = row[excel_col]
                    if pd.isna(value):
                        student_dict[model_field] = None
                    else:
                        student_dict[model_field] = value
            
            student_dict['created_by'] = request.user.id
            students_data.append(student_dict)
        
        imported_count = 0
        errors = []
        
        with transaction.atomic():
            for index, student_data in enumerate(students_data):
                try:
                    if student_data.get('email'):
                        email = student_data['email'].lower().strip()
                        if Student.objects.filter(email=email).exists():
                            errors.append({
                                'row': index + 2,
                                'error': f'Email "{email}" already exists',
                                'data': student_data
                            })
                            continue
                        student_data['email'] = email
                    
                    if student_data.get('upi_number'):
                        if Student.objects.filter(upi_number=student_data['upi_number']).exists():
                            errors.append({
                                'row': index + 2,
                                'error': f'UPI number "{student_data["upi_number"]}" already exists',
                                'data': student_data
                            })
                            continue
                    
                    if student_data.get('knec_number'):
                        if Student.objects.filter(knec_number=student_data['knec_number']).exists():
                            errors.append({
                                'row': index + 2,
                                'error': f'KNEC number "{student_data["knec_number"]}" already exists',
                                'data': student_data
                            })
                            continue
                    
                    if student_data.get('birth_certificate_no'):
                        if Student.objects.filter(birth_certificate_no=student_data['birth_certificate_no']).exists():
                            errors.append({
                                'row': index + 2,
                                'error': f'Birth Certificate number "{student_data["birth_certificate_no"]}" already exists',
                                'data': student_data
                            })
                            continue
                    
                    if not student_data.get('admission_no'):
                        prefix = 'ADM/JWB'
                        next_sequence = get_next_admission_sequence(
                            Student.objects.all(),
                            prefix=prefix
                        ) + imported_count
                        
                        student_data['admission_no'] = generate_admission_number(
                            prefix=prefix,
                            next_sequence=next_sequence
                        )
                    
                    if student_data.get('current_class'):
                        class_id = student_data['current_class']
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
                    
                    serializer = StudentCreateSerializer(data=student_data)
                    
                    if serializer.is_valid():
                        serializer.save()
                        imported_count += 1
                    else:
                        errors.append({
                            'row': index + 2,
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
        
        male_count = Student.objects.filter(gender='Male', archived=False).count()
        female_count = Student.objects.filter(gender='Female', archived=False).count()
        other_count = Student.objects.filter(gender='Other', archived=False).count()
        
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
    Validate and parse an admission number - NEW FORMAT
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
            exists = Student.objects.filter(admission_no=admission_no).exists()
            
            return Response({
                'success': True,
                'data': {
                    'admission_no': admission_no,
                    'prefix': parsed['prefix'],
                    'sequence': parsed['sequence'],
                    'exists': exists,
                    'format_valid': True,
                    'expected_format': f"{parsed['prefix']}-XXX"
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': 'Invalid admission number format. Must be: PREFIX-XXX (e.g., ADM/JWB-001)',
                'format_valid': False
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error validating admission number: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to validate admission number'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)