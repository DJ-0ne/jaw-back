# cbe_app/views/registrar_views/academic_views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError
import logging
from datetime import datetime
import uuid

from cbe_app.models import (
    LearningArea, Strand, SubStrand, Competency,
    AcademicYear, Term, GradeLevel, GradingScale, CurriculumMapping, StudentPortfolio, Class
)
from cbe_app.serializers.registrar_serializers.academic_mngmnt_serializers import (
    LearningAreaSerializer, StrandSerializer, SubStrandSerializer,
    CompetencySerializer, AcademicYearSerializer, TermSerializer, StudentPortfolioSerializer, GradeLevelSerializer, CurriculumMappingSerializer,
    GradingScaleSerializer
)

logger = logging.getLogger(__name__)


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
        
        # If this is set as current, unset other current years
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
            
            # If setting as current, unset others
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
        
        # If this is set as current, unset other current terms for same academic year
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
                'id': academic_year.id,
                'year_code': academic_year.year_code,
                'year_name': academic_year.year_name
            } if academic_year else None,
            'term': {
                'id': term.id,
                'term': term.term,
                'start_date': term.start_date,
                'end_date': term.end_date
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
            
            # If setting as current, unset other current terms for same academic year
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


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_learning_area(request, area_id):
    """Delete a learning area"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete learning areas'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            learning_area = LearningArea.objects.get(id=area_id)
        except LearningArea.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Learning area not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        learning_area.delete()
        logger.info(f"Learning area deleted: {learning_area.area_code} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'Learning area deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting learning area: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete learning area'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== STRAND VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_strands(request):
    """Get all strands"""
    try:
        learning_area_id = request.query_params.get('learning_area')
        
        queryset = Strand.objects.all().select_related('learning_area').order_by('display_order')
        
        if learning_area_id:
            queryset = queryset.filter(learning_area_id=learning_area_id)
        
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


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_strand(request, strand_id):
    """Delete a strand"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete strands'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            strand = Strand.objects.get(id=strand_id)
        except Strand.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Strand not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        strand.delete()
        logger.info(f"Strand deleted: {strand.strand_code} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'Strand deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting strand: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete strand'
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


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_substrand(request, substrand_id):
    """Delete a substrand"""
    try:
        if request.user.role not in ['registrar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete substrands'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            substrand = SubStrand.objects.get(id=substrand_id)
        except SubStrand.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Substrand not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        substrand.delete()
        logger.info(f"Substrand deleted: {substrand.substrand_code} by {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'Substrand deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error deleting substrand: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to delete substrand'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== COMPETENCY VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_competencies(request):
    """Get all competencies"""
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
    """Create a new competency"""
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
    """Delete a competency"""
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
        

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_grade_levels(request):
    """Get all grade levels"""
    try:
        grade_levels = GradeLevel.objects.all().order_by('level')
        serializer = GradeLevelSerializer(grade_levels, many=True)
        return Response({'success': True, 'data': serializer.data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_class_competencies(request):
    """Get all competencies for a specific class/grade level"""
    try:
        class_id = request.query_params.get('class_id')
        if not class_id:
            return Response({'success': False, 'error': 'class_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the class and its numeric level
        class_obj = Class.objects.get(id=class_id)
        grade_level = class_obj.numeric_level
        
        # Get curriculum mappings for this grade level
        mappings = CurriculumMapping.objects.filter(grade_level__level=grade_level).select_related('learning_area')
        learning_areas = [m.learning_area for m in mappings]
        
        # Get all competencies for these learning areas
        competencies_data = []
        for area in learning_areas:
            strands = Strand.objects.filter(learning_area=area).order_by('display_order')
            for strand in strands:
                substrands = SubStrand.objects.filter(strand=strand).order_by('display_order')
                for substrand in substrands:
                    comps = Competency.objects.filter(substrand=substrand).order_by('display_order')
                    for comp in comps:
                        competencies_data.append({
                            'learning_area': area.area_name,
                            'strand': strand.strand_name,
                            'substrand': substrand.substrand_name,
                            'competency_code': comp.competency_code,
                            'competency_statement': comp.competency_statement,
                            'is_core': comp.is_core_competency,
                        })
        
        return Response({'success': True, 'data': competencies_data}, status=status.HTTP_200_OK)
    except Class.DoesNotExist:
        return Response({'success': False, 'error': 'Class not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        class_id = request.query_params.get('class')
        term_id = request.query_params.get('term')
        academic_year_id = request.query_params.get('academic_year')
        
        queryset = StudentPortfolio.objects.all().select_related('student', 'competency', 'term', 'academic_year', 'assessed_by')
        
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        
        if class_id:
            queryset = queryset.filter(student__current_class_id=class_id)
        
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
        
        # Set assessed_by to current user
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
    """Update a student portfolio entry (add rating, comment)"""
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
        
        # Update with assessed_by
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

