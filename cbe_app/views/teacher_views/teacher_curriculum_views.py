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
    CoreValue, CurriculumVersion, Staff, LessonPlan, Class
)
from cbe_app.serializers.teacher_serializers.teacher_curriculum_serializers import (
    LearningAreaSerializer, GradeLevelSerializer, StrandSerializer,
    TeacherSubjectSerializer, CoreCompetencySerializer,
    CoreValueSerializer, CurriculumVersionSerializer, LessonPlanSerializer
)
import re
import logging
logger = logging.getLogger(__name__)


def get_staff_from_user(user):
    if hasattr(user, 'staff_profile'):
        return user.staff_profile
    return Staff.objects.filter(user=user).first()


def _resolve_grade_level(grade_id):
    if not grade_id:
        return None
    grade_id_str = str(grade_id).strip()

    # 1. Try as UUID
    try:
        uid = uuid.UUID(grade_id_str)
        gl = GradeLevel.objects.filter(id=uid).first()
        if gl:
            return gl
        # Try as Class UUID
        try:
            cls = Class.objects.get(id=uid)
            gl = GradeLevel.objects.filter(level=cls.numeric_level).first()
            if gl:
                return gl
            m = re.search(r'\d+', cls.class_name or '')
            if m:
                gl = GradeLevel.objects.filter(level=int(m.group())).first()
                if gl:
                    return gl
            if cls.class_name:
                gl = GradeLevel.objects.filter(name__icontains=cls.class_name).first()
                if gl:
                    return gl
        except Class.DoesNotExist:
            return None
    except ValueError:
        pass

    # 2. Try as plain integer level
    try:
        level = int(grade_id_str)
        gl = GradeLevel.objects.filter(level=level).first()
        if gl:
            return gl
        gl = GradeLevel.objects.filter(name__icontains=str(level)).first()
        if gl:
            return gl
    except (ValueError, TypeError):
        pass

    return None


def _extract_grade_number_from_class_name(class_name):
    if not class_name:
        return None
    match = re.search(r'\d+', class_name)
    if match:
        return int(match.group())
    return None


class TeacherSubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({'success': True, 'data': [], 'message': 'No staff profile found'})
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).select_related('subject').distinct('subject')
            subjects = [a.subject for a in allocations if a.subject]
            serializer = TeacherSubjectSerializer(subjects, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': 'Subjects retrieved successfully'})
        except Exception as e:
            logger.error(f"TeacherSubjectsView error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve subjects'}, status=500)


class TeacherGradeLevelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({'success': True, 'data': [], 'message': 'No staff profile found'})

            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff,
                class_id__is_active=True
            ).select_related('class_id')

            grade_data = []
            seen_levels = set()

            for alloc in allocations:
                if not alloc.class_id:
                    continue
                class_name = alloc.class_id.class_name
                grade_number = _extract_grade_number_from_class_name(class_name)
                if grade_number is None:
                    grade_number = alloc.class_id.numeric_level
                if grade_number in seen_levels:
                    continue
                seen_levels.add(grade_number)

                grade_level = GradeLevel.objects.filter(level=grade_number).first()
                if not grade_level:
                    default_name = class_name if class_name else f'Level {grade_number}'
                    grade_level, created = GradeLevel.objects.get_or_create(
                        level=grade_number,
                        defaults={'name': default_name}
                    )
                    if created:
                        logger.info(f"Auto-created GradeLevel id={grade_level.id} level={grade_number} from class '{class_name}'")

                grade_data.append({
                    'id':    str(grade_level.id),   # ← always the real GradeLevel UUID
                    'name':  class_name,
                    'level': grade_level.level,
                })

            grade_data.sort(key=lambda x: x['level'])
            return Response({'success': True, 'data': grade_data, 'message': f'Found {len(grade_data)} grade levels'})
        except Exception as e:
            logger.error(f"TeacherGradeLevelsView error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve grade levels'}, status=500)


class CurriculumStrandsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subject_id = request.query_params.get('subject')
            grade_id   = request.query_params.get('grade')

            if not subject_id:
                return Response({'success': True, 'data': [], 'message': 'No subject selected'})

            strands = Strand.objects.filter(
                learning_area_id=subject_id
            ).select_related('grade_level').order_by('display_order')

            if not strands.exists():
                return Response({'success': True, 'data': [], 'message': 'No strands found for this subject'})

            if grade_id:
                grade_level = _resolve_grade_level(grade_id)
                if grade_level:
                    grade_filtered = strands.filter(grade_level=grade_level)
                    if grade_filtered.exists():
                        strands = grade_filtered
                    else:
                        return Response({'success': True, 'data': [], 'message': 'No curriculum defined for this subject and grade level'})
                else:
                    return Response({'success': True, 'data': [], 'message': 'Invalid grade identifier'})

            response_data = []
            for strand in strands:
                substrands_data = []
                substrands = SubStrand.objects.filter(strand=strand).order_by('display_order')

                for sub in substrands:
                    outcomes_qs = LearningOutcome.objects.filter(substrand=sub)
                    try:
                        outcomes_qs = outcomes_qs.order_by('display_order')
                        list(outcomes_qs[:1])
                    except Exception:
                        outcomes_qs = LearningOutcome.objects.filter(substrand=sub)

                    outcomes_data = [
                        {
                            'id':            str(o.id),
                            'description':   o.description,
                            'domain':        o.domain,
                            'display_order': getattr(o, 'display_order', 0),
                        }
                        for o in outcomes_qs
                    ]
                    substrands_data.append({
                        'id':                str(sub.id),
                        'substrand_code':    sub.substrand_code,
                        'substrand_name':    sub.substrand_name,
                        'description':       sub.description or '',
                        'display_order':     getattr(sub, 'display_order', 0),
                        'learning_outcomes': outcomes_data,
                    })

                total_outcomes = sum(len(s['learning_outcomes']) for s in substrands_data)
                response_data.append({
                    'id':                str(strand.id),
                    'strand_code':       strand.strand_code,
                    'strand_name':       strand.strand_name,
                    'description':       strand.description or '',
                    'display_order':     getattr(strand, 'display_order', 0),
                    'progress':          0,
                    'total_outcomes':    total_outcomes,
                    'covered_outcomes':  0,
                    'total_lessons':     total_outcomes,
                    'completed_lessons': 0,
                    'substrands':        substrands_data,
                })

            return Response({'success': True, 'data': response_data, 'message': f'Found {len(response_data)} strands'})
        except Exception as e:
            logger.exception(f"CurriculumStrandsView error: {e}")
            return Response({'success': False, 'data': [], 'message': str(e)}, status=500)


class CoreCompetenciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            competencies = CoreCompetency.objects.all().order_by('display_order', 'code')
            serializer = CoreCompetencySerializer(competencies, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': 'Core competencies retrieved successfully'})
        except Exception as e:
            logger.error(f"CoreCompetenciesView error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve core competencies'}, status=500)


class CoreValuesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            values = CoreValue.objects.all().order_by('display_order', 'name')
            serializer = CoreValueSerializer(values, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': 'Core values retrieved successfully'})
        except Exception as e:
            logger.error(f"CoreValuesView error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve core values'}, status=500)


class LessonPlanCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data = request.data
            if not data.get('topic'):
                return Response({'success': False, 'message': 'Topic is required'}, status=400)

            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({'success': False, 'message': 'No staff profile found'}, status=400)

            grade_level = _resolve_grade_level(data.get('grade_id'))
            if not grade_level:
                return Response({'success': False, 'message': 'Invalid or missing grade'}, status=400)

            subject_id = data.get('subject_id')
            if not subject_id:
                return Response({'success': False, 'message': 'Subject is required'}, status=400)
            try:
                subject = LearningArea.objects.get(id=uuid.UUID(str(subject_id)))
            except (ValueError, LearningArea.DoesNotExist):
                subject = LearningArea.objects.filter(area_code=str(subject_id)).first()
                if not subject:
                    return Response({'success': False, 'message': 'Selected subject does not exist'}, status=400)

            lesson_plan_id = data.get('id')
            if lesson_plan_id:
                try:
                    lesson_plan = LessonPlan.objects.get(id=lesson_plan_id, teacher=staff)
                except LessonPlan.DoesNotExist:
                    return Response({'success': False, 'message': 'Lesson plan not found'}, status=404)
            else:
                lesson_plan = LessonPlan()
                lesson_plan.teacher = staff

            lesson_plan.subject_id     = subject.id
            lesson_plan.grade_level_id = grade_level.id

            for fk_field, model_cls in [('strand_id', Strand), ('substrand_id', SubStrand)]:
                fk_val = data.get(fk_field)
                if fk_val:
                    try:
                        model_cls.objects.get(id=uuid.UUID(str(fk_val)))
                        setattr(lesson_plan, fk_field, fk_val)
                    except (ValueError, model_cls.DoesNotExist):
                        pass

            # ── outcome_id: validate UUID and save ──────────────────────────────
            outcome_id = data.get('outcome_id')
            if outcome_id:
                try:
                    validated_uuid = uuid.UUID(str(outcome_id))
                    # Confirm the outcome actually exists
                    if LearningOutcome.objects.filter(id=validated_uuid).exists():
                        lesson_plan.outcome_id = validated_uuid
                    else:
                        logger.warning(f"outcome_id {outcome_id} not found in DB — not linking")
                except ValueError:
                    logger.warning(f"outcome_id {outcome_id!r} is not a valid UUID — skipping")

            lesson_plan.topic      = data.get('topic')
            lesson_plan.objectives = data.get('objectives', [])
            lesson_plan.activities = data.get('activities', [])
            lesson_plan.resources  = data.get('resources', [])
            lesson_plan.assessment = data.get('assessment', '')
            lesson_plan.duration   = data.get('duration', 40)

            date_str = data.get('date')
            try:
                lesson_plan.lesson_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()
            except (ValueError, TypeError):
                lesson_plan.lesson_date = datetime.now().date()

            lesson_plan.status = data.get('status', 'planned')
            lesson_plan.save()

            return Response({
                'success': True,
                'data': {
                    'id':         str(lesson_plan.id),
                    'outcome_id': str(lesson_plan.outcome_id) if lesson_plan.outcome_id else None,
                },
                'message': 'Lesson plan saved successfully'
            })
        except Exception as e:
            logger.error(f"LessonPlanCreateView error: {e}")
            return Response({'success': False, 'error': str(e), 'message': 'Failed to save lesson plan'}, status=500)


def _serialize_lesson_plan(lp):
    """Consistent serialization used by both GET list and PUT response."""
    return {
        'id':               str(lp.id),
        'topic':            lp.topic,
        'objectives':       lp.objectives,
        'activities':       lp.activities,
        'resources':        lp.resources,
        'assessment':       lp.assessment,
        'duration':         lp.duration,
        'lesson_date':      lp.lesson_date.isoformat(),
        'status':           lp.status,
        # ── Subject ──────────────────────────────────────────────────────────
        'subject_id':       str(lp.subject_id)          if lp.subject_id      else None,
        'subject_name':     lp.subject.area_name         if lp.subject         else 'N/A',
        # ── Grade — return BOTH UUID and numeric level so frontend can match ─
        'grade_level_id':   str(lp.grade_level_id)       if lp.grade_level_id  else None,
        'grade_level':      lp.grade_level.level         if lp.grade_level     else None,  # ← numeric
        'grade_name':       lp.grade_level.name          if lp.grade_level     else 'N/A',
        # ── Strand / SubStrand ───────────────────────────────────────────────
        'strand_id':        str(lp.strand_id)            if lp.strand_id       else None,
        'strand_name':      lp.strand.strand_name        if lp.strand          else None,
        'substrand_id':     str(lp.substrand_id)         if lp.substrand_id    else None,
        'substrand_name':   lp.substrand.substrand_name  if lp.substrand       else None,
        # ── Outcome — critical for coverage tracking ─────────────────────────
        'outcome_id':       str(lp.outcome_id)           if lp.outcome_id      else None,
        # ── Timestamps ───────────────────────────────────────────────────────
        'created_at':       lp.created_at.isoformat(),
        'updated_at':       lp.updated_at.isoformat(),
    }


class TeacherLessonPlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = get_staff_from_user(request.user)
            if not staff:
                return Response({'success': True, 'data': [], 'message': 'No staff profile found'})

            qs = LessonPlan.objects.filter(teacher=staff).select_related(
                'subject', 'grade_level', 'strand', 'substrand'
            ).order_by('-lesson_date')

            subject_id    = request.query_params.get('subject')
            grade_id      = request.query_params.get('grade')
            status_filter = request.query_params.get('status')

            if subject_id:
                qs = qs.filter(subject_id=subject_id)
            if grade_id:
                grade_level = _resolve_grade_level(grade_id)
                if grade_level:
                    qs = qs.filter(grade_level=grade_level)
            if status_filter:
                qs = qs.filter(status=status_filter)

            data = [_serialize_lesson_plan(lp) for lp in qs]
            return Response({'success': True, 'data': data, 'message': f'Found {len(data)} lesson plans'})
        except Exception as e:
            logger.error(f"TeacherLessonPlansView.get error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve lesson plans'}, status=500)

    def post(self, request):
        return LessonPlanCreateView().post(request)


class LessonPlanDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_plan(self, lesson_id, staff):
        try:
            return LessonPlan.objects.select_related(
                'subject', 'grade_level', 'strand', 'substrand'
            ).get(id=lesson_id, teacher=staff)
        except LessonPlan.DoesNotExist:
            return None

    def get(self, request, lesson_id):
        try:
            staff = get_staff_from_user(request.user)
            plan  = self._get_plan(lesson_id, staff)
            if not plan:
                return Response({'success': False, 'error': 'Lesson plan not found'}, status=404)
            return Response({'success': True, 'data': _serialize_lesson_plan(plan), 'message': 'Lesson plan retrieved successfully'})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)

    def put(self, request, lesson_id):
        try:
            staff = get_staff_from_user(request.user)
            plan  = self._get_plan(lesson_id, staff)
            if not plan:
                return Response({'success': False, 'error': 'Lesson plan not found'}, status=404)

            data = request.data
            fields = ['topic', 'objectives', 'activities', 'resources', 'assessment', 'duration', 'status']
            for f in fields:
                if f in data:
                    setattr(plan, f, data[f])
            if 'date' in data:
                try:
                    plan.lesson_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            plan.save()
            return Response({'success': True, 'data': _serialize_lesson_plan(plan), 'message': 'Lesson plan updated successfully'})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)

    def delete(self, request, lesson_id):
        try:
            staff = get_staff_from_user(request.user)
            plan  = self._get_plan(lesson_id, staff)
            if not plan:
                return Response({'success': False, 'error': 'Lesson plan not found'}, status=404)
            plan.delete()
            return Response({'success': True, 'message': 'Lesson plan deleted successfully'})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)


class SyllabusProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subject_id = request.query_params.get('subject_id')
            grade_id   = request.query_params.get('grade_id')
            if not subject_id:
                return Response({'success': False, 'data': [], 'message': 'Subject ID is required'}, status=400)

            strands = Strand.objects.filter(learning_area_id=subject_id)
            if grade_id:
                grade_level = _resolve_grade_level(grade_id)
                if grade_level:
                    strands = strands.filter(grade_level=grade_level)

            progress_data = []
            for strand in strands:
                total_outcomes = LearningOutcome.objects.filter(substrand__strand=strand).count()
                progress_data.append({
                    'strand_id':         str(strand.id),
                    'strand_name':       strand.strand_name,
                    'total_outcomes':    total_outcomes,
                    'covered_outcomes':  0,
                    'percentage':        0,
                    'total_lessons':     total_outcomes * 3,
                    'completed_lessons': 0,
                })
            return Response({'success': True, 'data': progress_data, 'message': 'Syllabus progress retrieved successfully'})
        except Exception as e:
            logger.error(f"SyllabusProgressView error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve syllabus progress'}, status=500)


class CurriculumVersionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            versions = CurriculumVersion.objects.filter(is_published=True).order_by('-created_at')
            serializer = CurriculumVersionSerializer(versions, many=True)
            return Response({'success': True, 'data': serializer.data, 'message': 'Curriculum versions retrieved successfully'})
        except Exception as e:
            logger.error(f"CurriculumVersionsView error: {e}")
            return Response({'success': False, 'data': [], 'error': str(e), 'message': 'Failed to retrieve curriculum versions'}, status=500)