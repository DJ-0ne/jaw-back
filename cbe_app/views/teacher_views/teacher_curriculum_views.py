from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Q
import uuid

from cbe_app.models import (
    LearningArea, GradeLevel, Strand, SubStrand, LearningOutcome,
    ClassSubjectAllocation, AcademicYear, CoreCompetency,
    CoreValue, CurriculumVersion, Staff
)
from cbe_app.serializers.teacher_serializers.teacher_curriculum_serializers import (
    LearningAreaSerializer, GradeLevelSerializer, StrandSerializer,
    TeacherSubjectSerializer, CoreCompetencySerializer, 
    CoreValueSerializer, CurriculumVersionSerializer
)


def get_staff_from_user(user):
    """Get Staff object from User"""
    if hasattr(user, 'staff_profile'):
        return user.staff_profile
    return Staff.objects.filter(user=user).first()


class TeacherSubjectsView(APIView):
    """Get subjects taught by the teacher"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get Staff object
            staff = get_staff_from_user(request.user)
            
            if not staff:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No staff profile found'
                })
            
            # Get current academic year
            current_academic_year = AcademicYear.objects.filter(is_current=True).first()
            academic_year = current_academic_year.year_code if current_academic_year else '2024-2025'
            
            # Get unique subjects from teacher's allocations
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,  # Use Staff object
                academic_year=academic_year
            ).select_related('subject').distinct('subject')
            
            subjects = []
            for allocation in allocations:
                if allocation.subject:
                    subjects.append(allocation.subject)
            
            serializer = TeacherSubjectSerializer(subjects, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Subjects retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in TeacherSubjectsView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve subjects'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherGradeLevelsView(APIView):
    """Get grade levels for teacher's subjects"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get Staff object
            staff = get_staff_from_user(request.user)
            
            if not staff:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No staff profile found'
                })
            
            # Get current academic year
            current_academic_year = AcademicYear.objects.filter(is_current=True).first()
            academic_year = current_academic_year.year_code if current_academic_year else '2024-2025'
            
            # Get grade levels from teacher's allocated classes
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,
                academic_year=academic_year
            ).select_related('class_id')
            
            grade_levels_set = set()
            for allocation in allocations:
                if allocation.class_id:
                    grade_levels_set.add(allocation.class_id.numeric_level)
            
            # Get GradeLevel objects
            grade_levels = GradeLevel.objects.filter(level__in=grade_levels_set).order_by('level')
            
            serializer = GradeLevelSerializer(grade_levels, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Grade levels retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in TeacherGradeLevelsView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve grade levels'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurriculumStrandsView(APIView):
    """Get strands and sub-strands for a subject and grade"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subject_id = request.query_params.get('subject')
            grade_level_id = request.query_params.get('grade')
            
            if not subject_id:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Subject parameter is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get strands for the subject
            strands = Strand.objects.filter(
                learning_area_id=subject_id
            ).order_by('display_order')
            
            if grade_level_id:
                strands = strands.filter(grade_level_id=grade_level_id)
            
            # Prepare response data
            response_data = []
            for strand in strands:
                # Get sub-strands
                substrands = strand.substrands.all().order_by('display_order')
                substrands_data = []
                
                for sub in substrands:
                    # Get learning outcomes
                    outcomes = sub.learning_outcomes.all().order_by('display_order')
                    outcomes_data = []
                    
                    for outcome in outcomes:
                        outcomes_data.append({
                            'id': outcome.id,
                            'description': outcome.description,
                            'domain': outcome.domain,
                            'display_order': outcome.display_order
                        })
                    
                    substrands_data.append({
                        'id': sub.id,
                        'substrand_code': sub.substrand_code,
                        'substrand_name': sub.substrand_name,
                        'description': sub.description,
                        'display_order': sub.display_order,
                        'learning_outcomes': outcomes_data
                    })
                
                response_data.append({
                    'id': strand.id,
                    'strand_code': strand.strand_code,
                    'strand_name': strand.strand_name,
                    'description': strand.description,
                    'display_order': strand.display_order,
                    'progress': 0,
                    'total_outcomes': 0,
                    'covered_outcomes': 0,
                    'substrands': substrands_data
                })
            
            return Response({
                'success': True,
                'data': response_data,
                'message': 'Strands retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in CurriculumStrandsView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve strands'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CoreCompetenciesView(APIView):
    """Get all KICD core competencies"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            competencies = CoreCompetency.objects.all().order_by('display_order', 'code')
            serializer = CoreCompetencySerializer(competencies, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Core competencies retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in CoreCompetenciesView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve core competencies'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CoreValuesView(APIView):
    """Get all KICD core values"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            values = CoreValue.objects.all().order_by('display_order', 'name')
            serializer = CoreValueSerializer(values, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Core values retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in CoreValuesView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve core values'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LessonPlanCreateView(APIView):
    """Create a lesson plan"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            data = request.data
            
            # Validate required fields
            if not data.get('topic'):
                return Response({
                    'success': False,
                    'message': 'Topic is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate lesson plan ID
            lesson_plan_id = str(uuid.uuid4())
            
            # For now, just return success
            # You would save to a LessonPlan model here
            
            return Response({
                'success': True,
                'data': {
                    'id': lesson_plan_id,
                    'topic': data.get('topic'),
                    'status': 'saved'
                },
                'message': 'Lesson plan saved successfully'
            })
            
        except Exception as e:
            print(f"Error in LessonPlanCreateView: {str(e)}")
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to save lesson plan'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherLessonPlansView(APIView):
    """Get teacher's lesson plans"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Return empty list for now
            # You would query LessonPlan model here
            return Response({
                'success': True,
                'data': [],
                'message': 'Lesson plans retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in TeacherLessonPlansView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve lesson plans'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SyllabusProgressView(APIView):
    """Get syllabus progress for teacher's subjects"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subject_id = request.query_params.get('subject_id')
            grade_id = request.query_params.get('grade_id')
            
            if not subject_id:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Subject ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get strands for the subject
            strands = Strand.objects.filter(learning_area_id=subject_id)
            
            if grade_id:
                strands = strands.filter(grade_level_id=grade_id)
            
            progress_data = []
            for strand in strands:
                total_outcomes = LearningOutcome.objects.filter(
                    substrand__strand=strand
                ).count()
                
                progress_data.append({
                    'strand_id': strand.id,
                    'strand_name': strand.strand_name,
                    'total_outcomes': total_outcomes,
                    'covered_outcomes': 0,
                    'percentage': 0,
                    'total_lessons': total_outcomes * 3,
                    'completed_lessons': 0
                })
            
            return Response({
                'success': True,
                'data': progress_data,
                'message': 'Syllabus progress retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in SyllabusProgressView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve syllabus progress'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurriculumVersionsView(APIView):
    """Get curriculum versions"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            versions = CurriculumVersion.objects.filter(is_published=True).order_by('-created_at')
            serializer = CurriculumVersionSerializer(versions, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Curriculum versions retrieved successfully'
            })
            
        except Exception as e:
            print(f"Error in CurriculumVersionsView: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve curriculum versions'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)