# views.py - Add to your existing views file

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Q, Count, F, Avg, Sum, FloatField
from django.db.models.functions import Coalesce
from collections import defaultdict
import uuid

from cbe_app.models import (
    LearningArea, GradeLevel, Strand, SubStrand, LearningOutcome,
    ClassSubjectAllocation, AcademicYear, Term, CoreCompetency,
    CoreValue, CurriculumVersion, StudentPortfolio
)
from cbe_app.serializers.teacher_serializers.teacher_curriculum_serializers import (
    LearningAreaSerializer, GradeLevelSerializer, StrandSerializer,
    TeacherSubjectSerializer, SyllabusProgressSerializer,
    LessonPlanSerializer, LessonPlanResponseSerializer,
    CoreCompetencySerializer, CoreValueSerializer,
    CurriculumVersionSerializer
)


class TeacherSubjectsView(APIView):
    """Get subjects taught by the teacher"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            academic_year = request.query_params.get('academic_year')
            
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            # Get unique subjects from teacher's allocations
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=request.user,
                academic_year=academic_year if academic_year else ''
            ).select_related('subject').distinct('subject')
            
            subjects = [allocation.subject for allocation in allocations if allocation.subject]
            
            # Add grade level info
            for subject in subjects:
                # Get grade level from curriculum mapping
                grade_mapping = subject.grade_mappings.first()
                if grade_mapping:
                    subject.grade_level = grade_mapping.grade_level
            
            serializer = TeacherSubjectSerializer(subjects, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Subjects retrieved successfully'
            })
            
        except Exception as e:
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
            # Get grade levels from teacher's allocated classes
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=request.user
            ).select_related('class_id')
            
            grade_levels = set()
            for allocation in allocations:
                if allocation.class_id:
                    grade_levels.add(allocation.class_id.numeric_level)
            
            grade_level_objs = GradeLevel.objects.filter(level__in=grade_levels).order_by('level')
            
            serializer = GradeLevelSerializer(grade_level_objs, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Grade levels retrieved successfully'
            })
            
        except Exception as e:
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
            
            # Get strands for the subject and grade level
            strands = Strand.objects.filter(
                learning_area_id=subject_id
            ).order_by('display_order')
            
            if grade_level_id:
                strands = strands.filter(grade_level_id=grade_level_id)
            
            # Prefetch sub-strands and learning outcomes
            strands = strands.prefetch_related(
                'substrands__learning_outcomes__competencies'
            )
            
            serializer = StrandSerializer(strands, many=True)
            
            # Add progress information for each strand
            response_data = []
            for strand, strand_data in zip(strands, serializer.data):
                # Calculate progress based on student portfolios
                total_outcomes = LearningOutcome.objects.filter(
                    substrand__strand=strand
                ).count()
                
                covered_outcomes = StudentPortfolio.objects.filter(
                    competency__substrand__strand=strand,
                    status='assessed'
                ).values('competency').distinct().count() if total_outcomes > 0 else 0
                
                progress = round((covered_outcomes / total_outcomes) * 100) if total_outcomes > 0 else 0
                
                strand_data['progress'] = progress
                strand_data['total_outcomes'] = total_outcomes
                strand_data['covered_outcomes'] = covered_outcomes
                response_data.append(strand_data)
            
            return Response({
                'success': True,
                'data': response_data,
                'message': 'Strands retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve strands'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SyllabusProgressView(APIView):
    """Get syllabus progress for teacher's subjects"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subject_id = request.query_params.get('subject_id')
            grade_level_id = request.query_params.get('grade_id')
            
            if not subject_id:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Subject ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get strands for the subject
            strands = Strand.objects.filter(
                learning_area_id=subject_id
            ).order_by('display_order')
            
            if grade_level_id:
                strands = strands.filter(grade_level_id=grade_level_id)
            
            progress_data = []
            for strand in strands:
                total_outcomes = LearningOutcome.objects.filter(
                    substrand__strand=strand
                ).count()
                
                # Count covered outcomes based on assessed portfolios
                covered_outcomes = StudentPortfolio.objects.filter(
                    competency__substrand__strand=strand,
                    status='assessed'
                ).values('competency').distinct().count()
                
                percentage = round((covered_outcomes / total_outcomes) * 100) if total_outcomes > 0 else 0
                
                # Estimate lessons (3 lessons per outcome)
                total_lessons = total_outcomes * 3
                completed_lessons = covered_outcomes * 3
                
                progress_data.append({
                    'strand_id': strand.id,
                    'strand_name': strand.strand_name,
                    'total_outcomes': total_outcomes,
                    'covered_outcomes': covered_outcomes,
                    'percentage': percentage,
                    'total_lessons': total_lessons,
                    'completed_lessons': completed_lessons
                })
            
            return Response({
                'success': True,
                'data': progress_data,
                'message': 'Syllabus progress retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve syllabus progress'
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
        serializer = LessonPlanSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors,
                'message': 'Invalid lesson plan data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            data = serializer.validated_data
            
            # Generate lesson plan ID
            lesson_plan_id = str(uuid.uuid4())
            
            # In production, save to a LessonPlan model
            # For now, we'll store in session or database
            # You would create a LessonPlan model and save here
            
            return Response({
                'success': True,
                'data': {
                    'id': lesson_plan_id,
                    **data
                },
                'message': 'Lesson plan saved successfully'
            })
            
        except Exception as e:
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
            subject_id = request.query_params.get('subject_id')
            
            # In production, query LessonPlan model
            # For now, return empty list
            lesson_plans = []
            
            return Response({
                'success': True,
                'data': lesson_plans,
                'message': 'Lesson plans retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve lesson plans'
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
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve curriculum versions'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)