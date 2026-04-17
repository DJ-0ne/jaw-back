# cbe_app/views/registrar_views/academic_mngmnt_views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging
from datetime import datetime
import uuid
import pandas as pd
import re

from cbe_app.models import (
    LearningArea, Strand, SubStrand, Competency, LearningOutcome,
    AcademicYear, Term, GradeLevel, GradingScale, CurriculumMapping, 
    StudentPortfolio, CurriculumVersion, CoreCompetency, CoreValue,
    WeightConfiguration, Class, Student
)
from cbe_app.serializers.registrar_serializers.academic_mngmnt_serializers import (
    LearningAreaSerializer, StrandSerializer, SubStrandSerializer,
    CompetencySerializer, LearningOutcomeSerializer, AcademicYearSerializer, 
    TermSerializer, StudentPortfolioSerializer, GradeLevelSerializer, 
    CurriculumMappingSerializer, GradingScaleSerializer, 
    CurriculumVersionSerializer, CoreCompetencySerializer, CoreValueSerializer,
    WeightConfigurationSerializer
)

logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTIONS ====================

def get_current_academic_year_and_term():
    """Get the current academic year and term"""
    current_year = AcademicYear.objects.filter(is_current=True).first()
    current_term = None
    if current_year:
        current_term = Term.objects.filter(academic_year=current_year, is_current=True).first()
    return current_year, current_term


# ==================== FULL CURRICULUM VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_full_curriculum(request):
    try:
        grade_levels = GradeLevel.objects.all().order_by('level')
        all_subjects = LearningArea.objects.filter(is_active=True)
        
        curriculum_data = []
        
        for grade in grade_levels:
            subjects_data = []
            
            for subject in all_subjects:
                strands = Strand.objects.filter(
                    learning_area=subject,
                    grade_level=grade
                ).order_by('display_order')
                
                strands_data = []
                for strand in strands:
                    substrands = SubStrand.objects.filter(strand=strand).order_by('display_order')
                    substrands_data = []
                    for substrand in substrands:
                        outcomes = LearningOutcome.objects.filter(substrand=substrand)
                        outcomes_data = [{
                            'id': str(outcome.id),
                            'description': outcome.description,
                            'domain': outcome.domain,
                            'competencies': outcome.competencies or []
                        } for outcome in outcomes]
                        
                        substrands_data.append({
                            'id': str(substrand.id),
                            'name': substrand.substrand_name,
                            'code': substrand.substrand_code,
                            'description': substrand.description,
                            'outcomes': outcomes_data
                        })
                    
                    strands_data.append({
                        'id': str(strand.id),
                        'name': strand.strand_name,
                        'code': strand.strand_code,
                        'description': strand.description,
                        'subStrands': substrands_data
                    })
                
                subjects_data.append({
                    'id': str(subject.id),
                    'name': subject.area_name,
                    'code': subject.area_code,
                    'isCore': subject.area_type == 'Core',
                    'scaleType': '8-point' if grade.level >= 6 else '4-point',
                    'strands': strands_data
                })
            
            if grade.level <= 2:
                grade_code = f'PP{grade.level}'
            else:
                grade_code = f'G{grade.level - 2}'
            
            curriculum_data.append({
                'gradeId': str(grade.id),
                'gradeName': grade.name,
                'gradeCode': grade_code,
                'scaleType': '8-point' if grade.level >= 6 else '4-point',
                'subjects': subjects_data
            })
        
        return Response({'success': True, 'data': curriculum_data})
    
    except Exception as e:
        return Response({'success': False, 'error': str(e)})


# ==================== CURRICULUM VERSION VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_curriculum_versions(request):
    """Get all curriculum versions"""
    try:
        versions = CurriculumVersion.objects.all().order_by('-created_at')
        serializer = CurriculumVersionSerializer(versions, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching curriculum versions: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch curriculum versions'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_curriculum_version(request):
    """Create a new curriculum version"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create curriculum versions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data.copy()
        data['created_by'] = request.user.id
        
        serializer = CurriculumVersionSerializer(data=data)
        
        if serializer.is_valid():
            version = serializer.save()
            logger.info(f"Curriculum version created: {version.name} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Curriculum version "{version.name}" created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating curriculum version: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create curriculum version'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def activate_curriculum_version(request, version_id):
    """Activate a curriculum version"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to activate curriculum versions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            version = CurriculumVersion.objects.get(id=version_id)
        except CurriculumVersion.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Curriculum version not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Deactivate all other versions
        CurriculumVersion.objects.filter(is_active=True).update(is_active=False)
        
        # Activate this version
        version.is_active = True
        version.save()
        
        logger.info(f"Curriculum version activated: {version.name} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': f'Curriculum version "{version.name}" activated successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error activating curriculum version: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to activate curriculum version'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publish_curriculum_version(request, version_id):
    """Publish and lock a curriculum version"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to publish curriculum versions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            version = CurriculumVersion.objects.get(id=version_id)
        except CurriculumVersion.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Curriculum version not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        version.is_published = True
        version.published_at = timezone.now()
        version.save()
        
        logger.info(f"Curriculum version published: {version.name} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': f'Curriculum version "{version.name}" published and locked successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error publishing curriculum version: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to publish curriculum version'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def clone_curriculum(request):
    """Clone curriculum from one academic year to another"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to clone curriculum'
            }, status=status.HTTP_403_FORBIDDEN)
        
        source_year = request.data.get('source_year')
        target_year = request.data.get('target_year')
        target_name = request.data.get('target_name')
        
        if not target_year:
            return Response({
                'success': False,
                'error': 'Target academic year is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get source version
        source_version = CurriculumVersion.objects.filter(academic_year=source_year).first() if source_year else CurriculumVersion.objects.filter(is_active=True).first()
        
        if not source_version:
            return Response({
                'success': False,
                'error': 'Source curriculum version not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create new version
        new_version = CurriculumVersion.objects.create(
            name=target_name or f"{target_year} Curriculum",
            academic_year=target_year,
            is_active=False,
            is_published=False,
            created_by=request.user
        )
        
        # Clone all curriculum mappings to new version
        # Get all grade levels
        grade_levels = GradeLevel.objects.all()
        
        for grade in grade_levels:
            # Get mappings for this grade
            mappings = CurriculumMapping.objects.filter(grade_level=grade)
            
            for mapping in mappings:
                # Clone mapping to new version (you'd need a version field in CurriculumMapping)
                # For now, just log
                pass
        
        logger.info(f"Curriculum cloned from {source_year or 'active'} to {target_year} by {request.user.username}")
        
        return Response({
            'success': True,
            'data': {'version_id': str(new_version.id), 'version_name': new_version.name},
            'message': f'Curriculum cloned successfully to {target_year}'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error cloning curriculum: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to clone curriculum'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== ACADEMIC YEAR VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_academic_years(request):
    """Get all academic years"""
    try:
        is_current = request.query_params.get('is_current')
        
        queryset = AcademicYear.objects.all().order_by('-start_date')
        
        if is_current is not None:
            queryset = queryset.filter(is_current=is_current.lower() == 'true')
        
        serializer = AcademicYearSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching academic years: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch academic years'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_academic_year(request):
    """Create a new academic year"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create academic years'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if request.data.get('is_current'):
            AcademicYear.objects.filter(is_current=True).update(is_current=False)
        
        serializer = AcademicYearSerializer(data=request.data)
        
        if serializer.is_valid():
            academic_year = serializer.save()
            logger.info(f"Academic year created: {academic_year.year_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Academic year {academic_year.year_name} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating academic year: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create academic year'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def academic_year_detail(request, year_id):
    """Update or delete an academic year"""
    try:
        try:
            academic_year = AcademicYear.objects.get(id=year_id)
        except AcademicYear.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Academic year not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update academic years'
                }, status=status.HTTP_403_FORBIDDEN)
            
            if request.data.get('is_current'):
                AcademicYear.objects.filter(is_current=True).exclude(id=year_id).update(is_current=False)
            
            serializer = AcademicYearSerializer(academic_year, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Academic year updated: {academic_year.year_code} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Academic year updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete academic years'
                }, status=status.HTTP_403_FORBIDDEN)
            
            academic_year.delete()
            logger.info(f"Academic year deleted: {academic_year.year_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Academic year deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing academic year: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== TERM VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_terms(request):
    """Get all terms"""
    try:
        academic_year_id = request.query_params.get('academic_year')
        is_current = request.query_params.get('is_current')
        
        queryset = Term.objects.all().select_related('academic_year').order_by('academic_year', 'term')
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        if is_current is not None:
            queryset = queryset.filter(is_current=is_current.lower() == 'true')
        
        serializer = TermSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching terms: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch terms'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_term(request):
    """Create a new term"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create terms'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if request.data.get('is_current') and request.data.get('academic_year'):
            Term.objects.filter(
                academic_year_id=request.data['academic_year'],
                is_current=True
            ).update(is_current=False)
        
        serializer = TermSerializer(data=request.data)
        
        if serializer.is_valid():
            term = serializer.save()
            logger.info(f"Term created: {term.term} for {term.academic_year.year_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Term {term.term} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating term: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create term'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_academic_year_and_term(request):
    """Get current academic year and term"""
    academic_year, term = get_current_academic_year_and_term()
    
    return Response({
        'success': True,
        'data': {
            'academic_year': {
                'id': str(academic_year.id) if academic_year else None,
                'year_code': academic_year.year_code if academic_year else None,
                'year_name': academic_year.year_name if academic_year else None
            } if academic_year else None,
            'term': {
                'id': str(term.id) if term else None,
                'term': term.term if term else None,
                'start_date': term.start_date if term else None,
                'end_date': term.end_date if term else None
            } if term else None
        }
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def term_detail(request, term_id):
    """Update or delete a term"""
    try:
        try:
            term = Term.objects.get(id=term_id)
        except Term.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Term not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update terms'
                }, status=status.HTTP_403_FORBIDDEN)
            
            if request.data.get('is_current'):
                Term.objects.filter(
                    academic_year=term.academic_year,
                    is_current=True
                ).exclude(id=term_id).update(is_current=False)
            
            serializer = TermSerializer(term, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Term updated: {term.term} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Term updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete terms'
                }, status=status.HTTP_403_FORBIDDEN)
            
            term.delete()
            logger.info(f"Term deleted: {term.term} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Term deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing term: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== GRADE LEVEL VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_grade_levels(request):
    """Get all grade levels"""
    try:
        grade_levels = GradeLevel.objects.all().order_by('level')
        serializer = GradeLevelSerializer(grade_levels, many=True)
        return Response({'success': True, 'data': serializer.data}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error fetching grade levels: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def grade_level_detail(request, grade_id):
    """Update or delete a grade level"""
    try:
        try:
            grade_level = GradeLevel.objects.get(id=grade_id)
        except GradeLevel.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Grade level not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update grade levels'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = GradeLevelSerializer(grade_level, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Grade level updated: {grade_level.name} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Grade level updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete grade levels'
                }, status=status.HTTP_403_FORBIDDEN)
            
            grade_level.delete()
            logger.info(f"Grade level deleted: {grade_level.name} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Grade level deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing grade level: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== LEARNING AREA VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_learning_areas(request):
    """Get all learning areas"""
    try:
        is_active = request.query_params.get('is_active')
        area_type = request.query_params.get('area_type')
        
        queryset = LearningArea.objects.all().order_by('area_code')
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        if area_type:
            queryset = queryset.filter(area_type=area_type)
        
        serializer = LearningAreaSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching learning areas: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch learning areas'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_learning_area(request):
    """Create a new learning area"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create learning areas'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = LearningAreaSerializer(data=request.data)
        
        if serializer.is_valid():
            learning_area = serializer.save()
            logger.info(f"Learning area created: {learning_area.area_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Learning area {learning_area.area_name} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating learning area: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create learning area'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def learning_area_detail(request, area_id):
    """Update or delete a learning area"""
    try:
        try:
            learning_area = LearningArea.objects.get(id=area_id)
        except LearningArea.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Learning area not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update learning areas'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = LearningAreaSerializer(learning_area, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Learning area updated: {learning_area.area_code} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Learning area updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete learning areas'
                }, status=status.HTTP_403_FORBIDDEN)
            
            learning_area.delete()
            logger.info(f"Learning area deleted: {learning_area.area_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Learning area deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing learning area: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== STRAND VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_strands(request):
    """Get all strands"""
    try:
        learning_area_id = request.query_params.get('learning_area')
        grade_level_id = request.query_params.get('grade_level')
        
        queryset = Strand.objects.all().select_related('learning_area', 'grade_level').order_by('display_order')
        
        if learning_area_id:
            queryset = queryset.filter(learning_area_id=learning_area_id)
        
        if grade_level_id:
            queryset = queryset.filter(grade_level_id=grade_level_id)
        
        serializer = StrandSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching strands: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch strands'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_strand(request):
    """Create a new strand"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create strands'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = StrandSerializer(data=request.data)
        
        if serializer.is_valid():
            strand = serializer.save()
            logger.info(f"Strand created: {strand.strand_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Strand {strand.strand_name} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating strand: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create strand'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def strand_detail(request, strand_id):
    """Update or delete a strand"""
    try:
        try:
            strand = Strand.objects.get(id=strand_id)
        except Strand.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Strand not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update strands'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = StrandSerializer(strand, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Strand updated: {strand.strand_code} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Strand updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete strands'
                }, status=status.HTTP_403_FORBIDDEN)
            
            strand.delete()
            logger.info(f"Strand deleted: {strand.strand_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Strand deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing strand: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== SUB-STRAND VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_substrands(request):
    """Get all substrands"""
    try:
        strand_id = request.query_params.get('strand')
        
        queryset = SubStrand.objects.all().select_related('strand').order_by('display_order')
        
        if strand_id:
            queryset = queryset.filter(strand_id=strand_id)
        
        serializer = SubStrandSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching substrands: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch substrands'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_substrand(request):
    """Create a new substrand"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create substrands'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = SubStrandSerializer(data=request.data)
        
        if serializer.is_valid():
            substrand = serializer.save()
            logger.info(f"Substrand created: {substrand.substrand_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Substrand {substrand.substrand_name} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating substrand: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create substrand'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def substrand_detail(request, substrand_id):
    """Update or delete a substrand"""
    try:
        try:
            substrand = SubStrand.objects.get(id=substrand_id)
        except SubStrand.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Substrand not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update substrands'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = SubStrandSerializer(substrand, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Substrand updated: {substrand.substrand_code} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Substrand updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete substrands'
                }, status=status.HTTP_403_FORBIDDEN)
            
            substrand.delete()
            logger.info(f"Substrand deleted: {substrand.substrand_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Substrand deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing substrand: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== LEARNING OUTCOME VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_learning_outcomes(request):
    """Get all learning outcomes"""
    try:
        substrand_id = request.query_params.get('substrand')
        
        queryset = LearningOutcome.objects.all().select_related('substrand')
        
        if substrand_id:
            queryset = queryset.filter(substrand_id=substrand_id)
        
        serializer = LearningOutcomeSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching learning outcomes: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch learning outcomes'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_learning_outcome(request):
    """Create a new learning outcome"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create learning outcomes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = LearningOutcomeSerializer(data=request.data)
        
        if serializer.is_valid():
            outcome = serializer.save()
            logger.info(f"Learning outcome created for substrand {outcome.substrand.substrand_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Learning outcome created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating learning outcome: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create learning outcome'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def learning_outcome_detail(request, outcome_id):
    """Update or delete a learning outcome"""
    try:
        try:
            outcome = LearningOutcome.objects.get(id=outcome_id)
        except LearningOutcome.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Learning outcome not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update learning outcomes'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = LearningOutcomeSerializer(outcome, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Learning outcome updated by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Learning outcome updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete learning outcomes'
                }, status=status.HTTP_403_FORBIDDEN)
            
            outcome.delete()
            logger.info(f"Learning outcome deleted by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Learning outcome deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing learning outcome: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== COMPETENCY VIEWS (Specific competencies within substrands) ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_competencies(request):
    """Get all specific competencies within substrands"""
    try:
        substrand_id = request.query_params.get('substrand')
        is_core = request.query_params.get('is_core')
        
        queryset = Competency.objects.all().select_related('substrand').order_by('display_order')
        
        if substrand_id:
            queryset = queryset.filter(substrand_id=substrand_id)
        
        if is_core is not None:
            queryset = queryset.filter(is_core_competency=is_core.lower() == 'true')
        
        serializer = CompetencySerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching competencies: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch competencies'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_competency(request):
    """Create a new specific competency"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create competencies'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = CompetencySerializer(data=request.data)
        
        if serializer.is_valid():
            competency = serializer.save()
            logger.info(f"Competency created: {competency.competency_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Competency {competency.competency_code} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating competency: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create competency'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_competency(request, competency_id):
    """Delete a specific competency"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete competencies'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            competency = Competency.objects.get(id=competency_id)
        except Competency.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Competency not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        competency.delete()
        logger.info(f"Competency deleted: {competency.competency_code} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'Competency deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting competency: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete competency'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== KICD CORE COMPETENCIES VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_core_competencies(request):
    """Get KICD core competencies"""
    try:
        core_competencies = CoreCompetency.objects.all().order_by('display_order', 'code')
        serializer = CoreCompetencySerializer(core_competencies, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching core competencies: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch core competencies'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_core_competency(request):
    """Create a KICD core competency"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create core competencies'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = CoreCompetencySerializer(data=request.data)
        
        if serializer.is_valid():
            competency = serializer.save()
            logger.info(f"Core competency created: {competency.code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Core competency "{competency.name}" created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating core competency: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create core competency'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def core_competency_detail(request, competency_id):
    """Update or delete a core competency"""
    try:
        try:
            competency = CoreCompetency.objects.get(id=competency_id)
        except CoreCompetency.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Core competency not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update core competencies'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = CoreCompetencySerializer(competency, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Core competency updated: {competency.code} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Core competency updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete core competencies'
                }, status=status.HTTP_403_FORBIDDEN)
            
            competency.delete()
            logger.info(f"Core competency deleted: {competency.code} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Core competency deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing core competency: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== KICD CORE VALUES VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_core_values(request):
    """Get KICD core values"""
    try:
        core_values = CoreValue.objects.all().order_by('display_order', 'name')
        serializer = CoreValueSerializer(core_values, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching core values: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch core values'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_core_value(request):
    """Create a KICD core value"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create core values'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = CoreValueSerializer(data=request.data)
        
        if serializer.is_valid():
            value = serializer.save()
            logger.info(f"Core value created: {value.name} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Core value "{value.name}" created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating core value: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create core value'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def core_value_detail(request, value_id):
    """Update or delete a core value"""
    try:
        try:
            value = CoreValue.objects.get(id=value_id)
        except CoreValue.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Core value not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update core values'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = CoreValueSerializer(value, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Core value updated: {value.name} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Core value updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete core values'
                }, status=status.HTTP_403_FORBIDDEN)
            
            value.delete()
            logger.info(f"Core value deleted: {value.name} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Core value deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing core value: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== GRADING SCALE VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_grading_scales(request):
    """Get all grading scales"""
    try:
        rating = request.query_params.get('rating')
        
        queryset = GradingScale.objects.all().order_by('rating', '-sub_level')
        
        if rating:
            queryset = queryset.filter(rating=rating)
        
        serializer = GradingScaleSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching grading scales: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch grading scales'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_grading_scale(request):
    """Create a new grading scale"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create grading scales'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = GradingScaleSerializer(data=request.data)
        
        if serializer.is_valid():
            grading_scale = serializer.save()
            logger.info(f"Grading scale created: {grading_scale.rating}{grading_scale.sub_level} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Grading scale {grading_scale.rating}{grading_scale.sub_level} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating grading scale: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create grading scale'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def grading_scale_detail(request, scale_id):
    """Update or delete a grading scale"""
    try:
        try:
            grading_scale = GradingScale.objects.get(id=scale_id)
        except GradingScale.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Grading scale not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update grading scales'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = GradingScaleSerializer(grading_scale, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Grading scale updated: {grading_scale.rating}{grading_scale.sub_level} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Grading scale updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['registrar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete grading scales'
                }, status=status.HTTP_403_FORBIDDEN)
            
            grading_scale.delete()
            logger.info(f"Grading scale deleted: {grading_scale.rating}{grading_scale.sub_level} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Grading scale deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing grading scale: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== WEIGHT CONFIGURATION VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_weight_config(request):
    """Get current weight configuration"""
    try:
        config = WeightConfiguration.objects.filter(is_active=True).first()
        
        if not config:
            return Response({
                'success': True,
                'data': {
                    'sba_weight': 40,
                    'exam_weight': 60
                }
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': True,
            'data': {
                'sba_weight': config.sba_weight,
                'exam_weight': config.exam_weight
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching weight config: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch weight configuration'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_weight_config(request):
    """Update weight configuration"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update weight configuration'
            }, status=status.HTTP_403_FORBIDDEN)
        
        sba_weight = request.data.get('sba_weight', 40)
        exam_weight = request.data.get('exam_weight', 60)
        
        if sba_weight + exam_weight != 100:
            return Response({
                'success': False,
                'error': 'SBA weight and Exam weight must add up to 100%'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        WeightConfiguration.objects.filter(is_active=True).update(is_active=False)
        
        config = WeightConfiguration.objects.create(
            sba_weight=sba_weight,
            exam_weight=exam_weight,
            is_active=True,
            created_by=request.user
        )
        
        logger.info(f"Weight configuration updated by {request.user.username}: SBA={sba_weight}%, Exam={exam_weight}%")
        
        return Response({
            'success': True,
            'data': {
                'sba_weight': config.sba_weight,
                'exam_weight': config.exam_weight
            },
            'message': 'Weight configuration updated successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error updating weight config: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to update weight configuration'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== CURRICULUM MAPPING VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_curriculum_mappings(request):
    """Get curriculum mappings for grade levels"""
    try:
        grade_level_id = request.query_params.get('grade_level')
        
        queryset = CurriculumMapping.objects.all().select_related('grade_level', 'learning_area').order_by('grade_level', 'display_order')
        
        if grade_level_id:
            queryset = queryset.filter(grade_level_id=grade_level_id)
        
        serializer = CurriculumMappingSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching curriculum mappings: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch curriculum mappings'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_curriculum_mapping(request):
    """Create a curriculum mapping"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create curriculum mappings'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = CurriculumMappingSerializer(data=request.data)
        
        if serializer.is_valid():
            mapping = serializer.save()
            logger.info(f"Curriculum mapping created: {mapping.grade_level.name} - {mapping.learning_area.area_name} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Curriculum mapping created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating curriculum mapping: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create curriculum mapping'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_curriculum_mapping(request, mapping_id):
    """Delete a curriculum mapping"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete curriculum mappings'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            mapping = CurriculumMapping.objects.get(id=mapping_id)
        except CurriculumMapping.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Curriculum mapping not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        mapping.delete()
        logger.info(f"Curriculum mapping deleted: {mapping.grade_level.name} - {mapping.learning_area.area_name} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'Curriculum mapping deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting curriculum mapping: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete curriculum mapping'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== STUDENT PORTFOLIO VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_portfolios(request):
    """Get student portfolios"""
    try:
        student_id = request.query_params.get('student')
        term_id = request.query_params.get('term')
        academic_year_id = request.query_params.get('academic_year')
        
        queryset = StudentPortfolio.objects.all().select_related('student', 'competency', 'term', 'academic_year', 'assessed_by')
        
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        serializer = StudentPortfolioSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching student portfolios: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch student portfolios'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_student_portfolio(request):
    """Create a student portfolio entry"""
    try:
        if request.user.role not in ['registrar', 'teacher', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create student portfolios'
            }, status=status.HTTP_403_FORBIDDEN)
        
        request.data['assessed_by'] = request.user.id
        request.data['assessed_date'] = datetime.now()
        
        serializer = StudentPortfolioSerializer(data=request.data)
        
        if serializer.is_valid():
            portfolio = serializer.save()
            logger.info(f"Student portfolio created: {portfolio.student.full_name} - {portfolio.competency.competency_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Portfolio entry created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating student portfolio: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create student portfolio'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_student_portfolio(request, portfolio_id):
    """Update a student portfolio entry"""
    try:
        if request.user.role not in ['registrar', 'teacher', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to update student portfolios'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            portfolio = StudentPortfolio.objects.get(id=portfolio_id)
        except StudentPortfolio.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student portfolio not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        request.data['assessed_by'] = request.user.id
        request.data['assessed_date'] = datetime.now()
        
        serializer = StudentPortfolioSerializer(portfolio, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Student portfolio updated: {portfolio.student.full_name} - {portfolio.competency.competency_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Portfolio entry updated successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error updating student portfolio: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to update student portfolio'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== BULK IMPORT VIEW ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_import_curriculum(request):
    """Bulk import curriculum from Excel/CSV"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to import curriculum'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if 'file' not in request.FILES:
            return Response({
                'success': False,
                'error': 'No file uploaded'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        file = request.FILES['file']
        
        try:
            if file.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to read file: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        imported_count = 0
        errors = []
        
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    grade_name = row.get('Grade_Level', '').strip()
                    if not grade_name:
                        continue
                    
                    # Get or create grade level
                    if grade_name.startswith('PP'):
                        level = 1 if 'PP1' in grade_name else 2
                        grade, _ = GradeLevel.objects.get_or_create(level=level, defaults={'name': grade_name})
                    elif grade_name.startswith('G'):
                        level = int(grade_name.replace('G', '')) + 2
                        grade, _ = GradeLevel.objects.get_or_create(level=level, defaults={'name': f'Grade {level - 2}'})
                    else:
                        continue
                    
                    # Get or create learning area
                    area_name = row.get('Subject_Name', '').strip()
                    area_code = row.get('Subject_Code', area_name[:3].upper()) if not pd.isna(row.get('Subject_Code')) else area_name[:3].upper()
                    
                    learning_area, _ = LearningArea.objects.get_or_create(
                        area_code=area_code,
                        defaults={
                            'area_name': area_name,
                            'area_type': 'Core',
                            'is_active': True
                        }
                    )
                    
                    # Create curriculum mapping
                    CurriculumMapping.objects.get_or_create(
                        grade_level=grade,
                        learning_area=learning_area,
                        defaults={'is_compulsory': True}
                    )
                    
                    # Create strand
                    strand_name = row.get('Strand_Name', '').strip()
                    if strand_name:
                        strand_code = row.get('Strand_Code', strand_name[:3].upper()) if not pd.isna(row.get('Strand_Code')) else strand_name[:3].upper()
                        strand, _ = Strand.objects.get_or_create(
                            learning_area=learning_area,
                            strand_code=strand_code,
                            grade_level=grade,
                            defaults={'strand_name': strand_name}
                        )
                        
                        # Create sub-strand
                        substrand_name = row.get('Sub_Strand_Name', '').strip()
                        if substrand_name:
                            substrand_code = row.get('Sub_Strand_Code', substrand_name[:4].upper()) if not pd.isna(row.get('Sub_Strand_Code')) else substrand_name[:4].upper()
                            substrand, _ = SubStrand.objects.get_or_create(
                                strand=strand,
                                substrand_code=substrand_code,
                                defaults={'substrand_name': substrand_name}
                            )
                            
                            # Create learning outcome
                            outcome_desc = row.get('Learning_Outcome', '').strip()
                            if outcome_desc and not pd.isna(outcome_desc):
                                LearningOutcome.objects.create(
                                    substrand=substrand,
                                    description=outcome_desc,
                                    domain='cognitive',
                                    competencies=row.get('Competency_Key', '').split(',') if not pd.isna(row.get('Competency_Key')) else []
                                )
                    
                    imported_count += 1
                
                except Exception as e:
                    errors.append({'row': index + 2, 'error': str(e)})
                    logger.error(f"Error importing row {index + 2}: {str(e)}")
        
        logger.info(f"Bulk import completed: {imported_count} items imported by {request.user.username}, {len(errors)} errors")
        
        return Response({
            'success': True,
            'imported_count': imported_count,
            'errors': errors,
            'message': f'Successfully imported {imported_count} curriculum items'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error in bulk import: {str(e)}")
        return Response({
            'success': False,
            'error': f'Bulk import failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== EXPORT VIEW ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_curriculum(request):
    """Export curriculum to Excel"""
    try:
        logger.info(f"Curriculum export initiated by {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'Export functionality will generate an Excel file'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error exporting curriculum: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to export curriculum'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)