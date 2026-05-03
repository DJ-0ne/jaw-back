from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
import uuid
import logging
from datetime import datetime

from cbe_app.models import (
    Exam, ExamSchedule, ExamMarker, ExamModeration, ExamPermission,
    Class, Staff, LearningArea, Student, GradeLevel
)
from cbe_app.serializers.registrar_serializers.exam_serializers import (
    ExamSerializer, ExamScheduleSerializer, ExamMarkerSerializer,
    ExamModerationSerializer, ExamPermissionSerializer
)
logger = logging.getLogger(__name__)


class RegistrarExamListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        exams = Exam.objects.all().order_by('-created_at')
        serializer = ExamSerializer(exams, many=True)
        data = serializer.data

        for exam_data in data:
            markers = ExamMarker.objects.filter(exam_id=exam_data['id'])
            exam_data['markers'] = [
                {
                    'id': str(m.teacher.id),
                    'subject': m.subject,
                    'teacher_name': f"{m.teacher.first_name} {m.teacher.last_name}",
                    'is_finalized': m.is_finalized,
                }
                for m in markers
            ]

        return Response({'success': True, 'data': data, 'count': len(data)})


class RegistrarExamCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data

        if not data.get('exam_code'):
            data['exam_code'] = f"EX-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        serializer = ExamSerializer(data=data)
        if serializer.is_valid():
            exam = serializer.save(created_by=request.user)
            return Response({
                'success': True,
                'data': ExamSerializer(exam).data,
                'message': 'Exam created successfully'
            })

        return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class RegistrarExamUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExamSerializer(exam, data=request.data, partial=True)
        if serializer.is_valid():
            exam = serializer.save(updated_by=request.user)
            return Response({
                'success': True,
                'data': ExamSerializer(exam).data,
                'message': 'Exam updated successfully'
            })

        return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class RegistrarExamMarkersGetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({'success': False, 'data': [], 'message': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        markers = ExamMarker.objects.filter(exam=exam).select_related('teacher')
        data = [
            {
                'id': str(m.teacher.id),
                'subject': m.subject,
                'teacher_name': f"{m.teacher.first_name} {m.teacher.last_name}",
                'is_finalized': m.is_finalized,
            }
            for m in markers
        ]

        return Response({'success': True, 'data': data})


class RegistrarExamDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
            exam.delete()
            return Response({'success': True, 'message': 'Exam deleted successfully'})
        except Exam.DoesNotExist:
            return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)


class RegistrarExamScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        schedules_data = request.data.get('schedules', [])

        ExamSchedule.objects.filter(exam=exam).delete()

        for schedule_data in schedules_data:
            schedule_data.pop('exam_id', None)
            schedule_data.pop('id', None)

            invigilator_id = schedule_data.pop('invigilator', None)
            if invigilator_id:
                try:
                    staff = Staff.objects.get(id=invigilator_id)
                    schedule_data['invigilator'] = staff.user
                except Staff.DoesNotExist:
                    schedule_data['invigilator'] = None
            else:
                schedule_data['invigilator'] = None

            ExamSchedule.objects.create(
                exam=exam,
                subject=schedule_data.get('subject', ''),
                date=schedule_data.get('date'),
                start_time=schedule_data.get('start_time'),
                end_time=schedule_data.get('end_time'),
                room=schedule_data.get('room', ''),
                invigilator=schedule_data.get('invigilator'),
                class_id=schedule_data.get('class_id', '')
            )

        if exam.status == 'draft':
            exam.status = 'scheduled'
            exam.save()

        return Response({'success': True, 'message': f'{len(schedules_data)} schedule(s) saved successfully'})


class RegistrarExamMarkersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        marking_data = request.data

        ExamMarker.objects.filter(exam=exam).delete()

        for subject, teacher_ids in marking_data.items():
            if subject and teacher_ids:
                for teacher_id in teacher_ids:
                    try:
                        teacher = Staff.objects.get(id=teacher_id)
                        ExamMarker.objects.create(
                            exam=exam,
                            subject=subject,
                            teacher=teacher.user
                        )
                    except (Staff.DoesNotExist, ValueError):
                        continue

        return Response({'success': True, 'message': 'Markers assigned successfully'})


class RegistrarExamModerationView(APIView):
    """
    Registrar submits moderation outcome.

    On APPROVAL  → exam moves to 'published'.
    On REJECTION → exam moves back to 'marking' AND all ExamMarker rows are
                   un-finalized so teachers can correct and re-submit their marks.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        # Resolve moderator: accept a Staff ID or a User ID
        moderator_user = None
        moderator_id   = data.get('moderator')
        if moderator_id:
            # Try Staff first (registrar UI sends Staff.id)
            try:
                staff          = Staff.objects.get(id=moderator_id)
                moderator_user = staff.user
            except Staff.DoesNotExist:
                pass

            # Fallback: try treating it as a raw User PK
            if moderator_user is None:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    moderator_user = User.objects.get(pk=moderator_id)
                except User.DoesNotExist:
                    pass

        approved = bool(data.get('approved', False))

        moderation, _ = ExamModeration.objects.update_or_create(
            exam=exam,
            defaults={
                'moderator': moderator_user,
                'notes':     data.get('notes', ''),
                'approved':  approved,
            }
        )

        if approved:
            exam.status = 'published'
            exam.save()
            message = 'Results approved and published successfully.'
        else:
            # Rejected — unlock all markers so teachers can correct their scores
            exam.status = 'marking'
            exam.save()
            ExamMarker.objects.filter(exam=exam).update(
                is_finalized=False,
                finalized_at=None,
            )
            message = (
                'Moderation rejected. Exam returned to marking. '
                'All teachers have been unlocked to correct their scores.'
            )

        return Response({'success': True, 'message': message, 'approved': approved})


class RegistrarExamPermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, scope='global', exam_id=None):
        if scope == 'global':
            permission, _ = ExamPermission.objects.get_or_create(
                permission_type='global',
                defaults={'created_by': request.user}
            )
            serializer = ExamPermissionSerializer(permission)
            return Response({'success': True, 'data': serializer.data})
        else:
            try:
                exam = Exam.objects.get(id=exam_id)
                permission, _ = ExamPermission.objects.get_or_create(
                    permission_type='exam',
                    exam=exam,
                    defaults={'created_by': request.user}
                )
                serializer = ExamPermissionSerializer(permission)
                return Response({'success': True, 'data': serializer.data})
            except Exam.DoesNotExist:
                return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, scope='global', exam_id=None):
        if scope == 'global':
            permission, _ = ExamPermission.objects.get_or_create(
                permission_type='global',
                defaults={'created_by': request.user}
            )
        else:
            try:
                exam = Exam.objects.get(id=exam_id)
                permission, _ = ExamPermission.objects.get_or_create(
                    permission_type='exam',
                    exam=exam,
                    defaults={'created_by': request.user}
                )
            except Exam.DoesNotExist:
                return Response({'success': False, 'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        permissions_data = request.data.get('permissions', {})
        lock_data        = request.data.get('scheduledLock', {})

        permission.school_wide_mark_uploading  = permissions_data.get('schoolWide', False)
        permission.require_moderation          = permissions_data.get('requireModeration', True)
        permission.auto_publish                = permissions_data.get('autoPublish', False)
        permission.grade_level_permissions     = permissions_data.get('gradeLevels', {})
        permission.subject_teacher_permissions = permissions_data.get('subjectTeachers', {})
        permission.lock_enabled                = lock_data.get('enabled', False)

        if lock_data.get('lockUntil'):
            permission.lock_until = datetime.fromisoformat(lock_data['lockUntil'].replace('Z', '+00:00'))

        permission.save()

        return Response({'success': True, 'message': 'Permissions updated successfully'})


class RegistrarGradeLevelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        grade_levels = GradeLevel.objects.all().order_by('level')

        if not grade_levels.exists():
            return Response({
                'success': False,
                'error': 'No grade levels found in database. Please add grade levels to the GradeLevel model.'
            }, status=status.HTTP_404_NOT_FOUND)

        data = [
            {
                'id':           str(gl.id),
                'level':        gl.level,
                'name':         gl.name,
                'display_name': gl.name,
            }
            for gl in grade_levels
        ]

        return Response({'success': True, 'data': data})


class RegistrarAllSchedulesView(APIView):
    """Get all exam schedules across all exams."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            schedules = (
                ExamSchedule.objects
                .select_related('exam', 'invigilator')
                .all()
                .order_by('date', 'start_time')
            )

            data = []
            for schedule in schedules:
                data.append({
                    'id':              str(schedule.id),
                    'exam_id':         str(schedule.exam.id),
                    'exam_code':       schedule.exam.exam_code,
                    'exam_title':      schedule.exam.title,
                    'exam_status':     schedule.exam.status,
                    'subject':         schedule.subject,
                    'date':            schedule.date,
                    'start_time':      schedule.start_time,
                    'end_time':        schedule.end_time,
                    'room':            schedule.room,
                    'invigilator':     str(schedule.invigilator_id) if schedule.invigilator else None,
                    'invigilator_name': (
                        f"{schedule.invigilator.first_name} {schedule.invigilator.last_name}"
                        if schedule.invigilator else None
                    ),
                })

            return Response({'success': True, 'data': data, 'count': len(data)})
        except Exception as e:
            logger.error(f"Error fetching all schedules: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarAllStaffView(APIView):
    """
    Returns ALL staff members so the registrar can assign any teacher
    (including non-markers) as a moderator.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff_qs = Staff.objects.select_related('user').filter(is_active=True).order_by('last_name', 'first_name')
            data = [
                {
                    'id':             str(s.id),
                    'user_id':        str(s.user.id),
                    'first_name':     s.first_name or s.user.first_name,
                    'last_name':      s.last_name  or s.user.last_name,
                    'specialization': getattr(s, 'specialization', ''),
                }
                for s in staff_qs
            ]
            return Response({'success': True, 'data': data})
        except Exception as e:
            logger.error(f"RegistrarAllStaffView error: {str(e)}", exc_info=True)
            return Response({'success': False, 'error': str(e)}, status=500)