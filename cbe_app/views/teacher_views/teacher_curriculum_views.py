from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Q
import uuid
from datetime import datetime

from cbe_app.models import (
    LearningArea, GradeLevel, Strand, SubStrand, LearningOutcome,
    ClassSubjectAllocation, AcademicYear, CoreCompetency,
    CoreValue, CurriculumVersion, Staff, LessonPlan
)
from cbe_app.serializers.teacher_serializers.teacher_curriculum_serializers import (
    LearningAreaSerializer, GradeLevelSerializer, StrandSerializer,
    TeacherSubjectSerializer, CoreCompetencySerializer, 
    CoreValueSerializer, CurriculumVersionSerializer, LessonPlanSerializer
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
            staff = get_staff_from_user(request.user)
            
            if not staff:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No staff profile found'
                })
            
            current_academic_year = AcademicYear.objects.filter(is_current=True).first()
            academic_year = current_academic_year.year_code if current_academic_year else '2024-2025'
            
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,
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
            staff = get_staff_from_user(request.user)
            
            if not staff:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No staff profile found'
                })
            
            current_academic_year = AcademicYear.objects.filter(is_current=True).first()
            academic_year = current_academic_year.year_code if current_academic_year else '2024-2025'
            
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,
                academic_year=academic_year
            ).select_related('class_id')
            
            grade_levels_set = set()
            for allocation in allocations:
                if allocation.class_id:
                    grade_levels_set.add(allocation.class_id.numeric_level)
            
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
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subject_id = request.query_params.get('subject')
            grade_level_id = request.query_params.get('grade')
            
            if not subject_id:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No subject selected'
                })
            
            strands = Strand.objects.filter(learning_area_id=subject_id)
            
            if grade_level_id:
                strands = strands.filter(grade_level_id=grade_level_id)
            
            if not strands.exists():
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No strands found for this subject and grade'
                })
            
            response_data = []
            for strand in strands:
                substrands_data = []
                substrands = SubStrand.objects.filter(strand=strand).order_by('display_order')
                
                for sub in substrands:
                    outcomes_data = []
                    outcomes = LearningOutcome.objects.filter(substrand=sub).order_by('display_order')
                    
                    for outcome in outcomes:
                        outcomes_data.append({
                            'id': str(outcome.id),
                            'description': outcome.description,
                            'domain': outcome.domain,
                            'display_order': outcome.display_order
                        })
                    
                    substrands_data.append({
                        'id': str(sub.id),
                        'substrand_code': sub.substrand_code,
                        'substrand_name': sub.substrand_name,
                        'description': sub.description or '',
                        'display_order': sub.display_order,
                        'learning_outcomes': outcomes_data
                    })
                
                response_data.append({
                    'id': str(strand.id),
                    'strand_code': strand.strand_code,
                    'strand_name': strand.strand_name,
                    'description': strand.description or '',
                    'display_order': strand.display_order,
                    'progress': 0,
                    'total_outcomes': sum(len(s['learning_outcomes']) for s in substrands_data),
                    'covered_outcomes': 0,
                    'total_lessons': sum(len(s['learning_outcomes']) for s in substrands_data),
                    'completed_lessons': 0,
                    'substrands': substrands_data
                })
            
            return Response({
                'success': True,
                'data': response_data,
                'message': f'Found {len(response_data)} strands'
            })
            
        except Exception as e:
            return Response({
                'success': True,
                'data': [],
                'message': str(e)
            })


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
    """Create or update a lesson plan"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            data = request.data
            
            if not data.get('topic'):
                return Response({
                    'success': False,
                    'message': 'Topic is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({
                    'success': False,
                    'message': 'No staff profile found'
                }, status=400)
            
            # Check if updating existing lesson plan
            lesson_plan_id = data.get('id')
            if lesson_plan_id:
                try:
                    lesson_plan = LessonPlan.objects.get(id=lesson_plan_id, teacher=staff)
                except LessonPlan.DoesNotExist:
                    return Response({
                        'success': False,
                        'message': 'Lesson plan not found'
                    }, status=404)
            else:
                lesson_plan = LessonPlan()
                lesson_plan.teacher = staff
            
            # Set fields
            lesson_plan.subject_id = data.get('subject_id')
            lesson_plan.grade_level_id = data.get('grade_id')
            lesson_plan.strand_id = data.get('strand_id')
            lesson_plan.substrand_id = data.get('substrand_id')
            lesson_plan.outcome_id = data.get('outcome_id')
            lesson_plan.topic = data.get('topic')
            lesson_plan.objectives = data.get('objectives', [])
            lesson_plan.activities = data.get('activities', [])
            lesson_plan.resources = data.get('resources', [])
            lesson_plan.assessment = data.get('assessment', '')
            lesson_plan.duration = data.get('duration', 40)
            
            # Parse date
            date_str = data.get('date')
            if date_str:
                lesson_plan.lesson_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                lesson_plan.lesson_date = datetime.now().date()
            
            lesson_plan.status = data.get('status', 'planned')
            
            lesson_plan.save()
            
            return Response({
                'success': True,
                'data': {'id': str(lesson_plan.id)},
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
    """Get and create lesson plans"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """GET method - retrieve lesson plans"""
        try:
            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({
                    'success': True,
                    'data': [],
                    'message': 'No staff profile found'
                })
            
            subject_id = request.query_params.get('subject')
            grade_id = request.query_params.get('grade')
            status_filter = request.query_params.get('status')
            
            lesson_plans = LessonPlan.objects.filter(teacher=staff).order_by('-lesson_date')
            
            if subject_id:
                lesson_plans = lesson_plans.filter(subject_id=subject_id)
            if grade_id:
                lesson_plans = lesson_plans.filter(grade_level_id=grade_id)
            if status_filter:
                lesson_plans = lesson_plans.filter(status=status_filter)
            
            data = []
            for lp in lesson_plans:
                data.append({
                    'id': str(lp.id),
                    'topic': lp.topic,
                    'objectives': lp.objectives,
                    'activities': lp.activities,
                    'resources': lp.resources,
                    'assessment': lp.assessment,
                    'duration': lp.duration,
                    'lesson_date': lp.lesson_date.isoformat(),
                    'status': lp.status,
                    'subject_id': str(lp.subject_id),
                    'subject_name': lp.subject.area_name,
                    'grade_level_id': str(lp.grade_level_id),
                    'grade_name': lp.grade_level.name,
                    'strand_id': str(lp.strand_id) if lp.strand_id else None,
                    'strand_name': lp.strand.strand_name if lp.strand else None,
                    'substrand_id': str(lp.substrand_id) if lp.substrand_id else None,
                    'substrand_name': lp.substrand.substrand_name if lp.substrand else None,
                    'outcome_id': str(lp.outcome_id) if lp.outcome_id else None,
                    'created_at': lp.created_at.isoformat(),
                    'updated_at': lp.updated_at.isoformat()
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': f'Found {len(data)} lesson plans'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve lesson plans'
            }, status=500)
    
    def post(self, request):
        """POST method - create or update lesson plan"""
        try:
            data = request.data
            
            if not data.get('topic'):
                return Response({
                    'success': False,
                    'message': 'Topic is required'
                }, status=400)
            
            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({
                    'success': False,
                    'message': 'No staff profile found'
                }, status=400)
            
            # Check if updating existing
            lesson_plan_id = data.get('id')
            if lesson_plan_id:
                try:
                    lesson_plan = LessonPlan.objects.get(id=lesson_plan_id, teacher=staff)
                except LessonPlan.DoesNotExist:
                    return Response({
                        'success': False,
                        'message': 'Lesson plan not found'
                    }, status=404)
            else:
                lesson_plan = LessonPlan()
                lesson_plan.teacher = staff
            
            lesson_plan.subject_id = data.get('subject_id')
            lesson_plan.grade_level_id = data.get('grade_id')
            lesson_plan.strand_id = data.get('strand_id')
            lesson_plan.substrand_id = data.get('substrand_id')
            lesson_plan.outcome_id = data.get('outcome_id')
            lesson_plan.topic = data.get('topic')
            lesson_plan.objectives = data.get('objectives', [])
            lesson_plan.activities = data.get('activities', [])
            lesson_plan.resources = data.get('resources', [])
            lesson_plan.assessment = data.get('assessment', '')
            lesson_plan.duration = data.get('duration', 40)
            
            from datetime import datetime
            date_str = data.get('date')
            if date_str:
                lesson_plan.lesson_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                lesson_plan.lesson_date = datetime.now().date()
            
            lesson_plan.status = data.get('status', 'planned')
            lesson_plan.save()
            
            return Response({
                'success': True,
                'data': {'id': str(lesson_plan.id)},
                'message': 'Lesson plan saved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to save lesson plan'
            }, status=500)
            

class LessonPlanDetailView(APIView):
    """Get, update, or delete a specific lesson plan"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, lesson_id):
        try:
            staff = get_staff_from_user(request.user)
            lesson_plan = LessonPlan.objects.get(id=lesson_id, teacher=staff)
            serializer = LessonPlanSerializer(lesson_plan)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Lesson plan retrieved successfully'
            })
            
        except LessonPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Lesson plan not found'
            }, status=404)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def put(self, request, lesson_id):
        try:
            staff = get_staff_from_user(request.user)
            lesson_plan = LessonPlan.objects.get(id=lesson_id, teacher=staff)
            
            data = request.data
            
            # Update fields
            if 'topic' in data:
                lesson_plan.topic = data['topic']
            if 'objectives' in data:
                lesson_plan.objectives = data['objectives']
            if 'activities' in data:
                lesson_plan.activities = data['activities']
            if 'resources' in data:
                lesson_plan.resources = data['resources']
            if 'assessment' in data:
                lesson_plan.assessment = data['assessment']
            if 'duration' in data:
                lesson_plan.duration = data['duration']
            if 'date' in data:
                lesson_plan.lesson_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            if 'status' in data:
                lesson_plan.status = data['status']
            
            lesson_plan.save()
            serializer = LessonPlanSerializer(lesson_plan)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Lesson plan updated successfully'
            })
            
        except LessonPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Lesson plan not found'
            }, status=404)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def delete(self, request, lesson_id):
        try:
            staff = get_staff_from_user(request.user)
            lesson_plan = LessonPlan.objects.get(id=lesson_id, teacher=staff)
            lesson_plan.delete()
            
            return Response({
                'success': True,
                'message': 'Lesson plan deleted successfully'
            })
            
        except LessonPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Lesson plan not found'
            }, status=404)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


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
            
            strands = Strand.objects.filter(learning_area_id=subject_id)
            
            if grade_id:
                strands = strands.filter(grade_level_id=grade_id)
            
            progress_data = []
            for strand in strands:
                total_outcomes = LearningOutcome.objects.filter(
                    substrand__strand=strand
                ).count()
                
                progress_data.append({
                    'strand_id': str(strand.id),
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