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
        
        # Add markers to each exam
        for exam_data in data:
            markers = ExamMarker.objects.filter(exam_id=exam_data['id'])
            exam_data['markers'] = [
                {
                    'id': str(m.teacher.id),
                    'subject': m.subject,
                    'teacher_name': f"{m.teacher.first_name} {m.teacher.last_name}"
                }
                for m in markers
            ]
        
        return Response({
            'success': True,
            'data': data,
            'count': len(data)
        })


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
        
        return Response({
            'success': False,
            'error': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class RegistrarExamUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def put(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Exam not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = ExamSerializer(exam, data=request.data, partial=True)
        if serializer.is_valid():
            exam = serializer.save(updated_by=request.user)
            return Response({
                'success': True,
                'data': ExamSerializer(exam).data,
                'message': 'Exam updated successfully'
            })
        
        return Response({
            'success': False,
            'error': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class RegistrarExamMarkersGetView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({
                'success': False,
                'data': [],
                'message': 'Exam not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        markers = ExamMarker.objects.filter(exam=exam).select_related('teacher')
        data = []
        for marker in markers:
            data.append({
                'id': str(marker.teacher.id),
                'subject': marker.subject,
                'teacher_name': f"{marker.teacher.first_name} {marker.teacher.last_name}"
            })
        
        return Response({
            'success': True,
            'data': data
        })

class RegistrarExamDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
            exam.delete()
            return Response({
                'success': True,
                'message': 'Exam deleted successfully'
            })
        except Exam.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Exam not found'
            }, status=status.HTTP_404_NOT_FOUND)

class RegistrarExamScheduleView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Exam not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        schedules_data = request.data.get('schedules', [])
        
        # Delete existing schedules
        ExamSchedule.objects.filter(exam=exam).delete()
        
        # Create new schedules
        for schedule_data in schedules_data:
            # Remove exam_id if present and use the exam object
            schedule_data.pop('exam_id', None)
            schedule_data.pop('id', None)  # Remove id if present
            
            # Handle invigilator - convert staff ID to user
            invigilator_id = schedule_data.pop('invigilator', None)
            if invigilator_id:
                try:
                    staff = Staff.objects.get(id=invigilator_id)
                    schedule_data['invigilator'] = staff.user
                except Staff.DoesNotExist:
                    schedule_data['invigilator'] = None
            else:
                schedule_data['invigilator'] = None
            
            # Create schedule directly without serializer
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
        
        return Response({
            'success': True,
            'message': f'{len(schedules_data)} schedule(s) saved successfully'
        })

class RegistrarExamMarkersView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Exam not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
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
        
        return Response({
            'success': True,
            'message': 'Markers assigned successfully'
        })


class RegistrarExamModerationView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, exam_id):
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Exam not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data
        
        moderation, created = ExamModeration.objects.update_or_create(
            exam=exam,
            defaults={
                'moderator_id': data.get('moderator'),
                'notes': data.get('notes', ''),
                'approved': data.get('approved', False)
            }
        )
        
        if data.get('approved'):
            exam.status = 'published'
        else:
            exam.status = 'marking'
        exam.save()
        
        return Response({
            'success': True,
            'message': 'Moderation submitted successfully'
        })


class RegistrarExamPermissionsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, scope='global', exam_id=None):
        if scope == 'global':
            permission, _ = ExamPermission.objects.get_or_create(
                permission_type='global',
                defaults={'created_by': request.user}
            )
            serializer = ExamPermissionSerializer(permission)
            return Response({
                'success': True,
                'data': serializer.data
            })
        else:
            try:
                exam = Exam.objects.get(id=exam_id)
                permission, _ = ExamPermission.objects.get_or_create(
                    permission_type='exam',
                    exam=exam,
                    defaults={'created_by': request.user}
                )
                serializer = ExamPermissionSerializer(permission)
                return Response({
                    'success': True,
                    'data': serializer.data
                })
            except Exam.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Exam not found'
                }, status=status.HTTP_404_NOT_FOUND)
    
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
                return Response({
                    'success': False,
                    'error': 'Exam not found'
                }, status=status.HTTP_404_NOT_FOUND)
        
        permissions_data = request.data.get('permissions', {})
        lock_data = request.data.get('scheduledLock', {})
        
        permission.school_wide_mark_uploading = permissions_data.get('schoolWide', False)
        permission.require_moderation = permissions_data.get('requireModeration', True)
        permission.auto_publish = permissions_data.get('autoPublish', False)
        permission.grade_level_permissions = permissions_data.get('gradeLevels', {})
        permission.subject_teacher_permissions = permissions_data.get('subjectTeachers', {})
        permission.lock_enabled = lock_data.get('enabled', False)
        
        if lock_data.get('lockUntil'):
            permission.lock_until = datetime.fromisoformat(lock_data['lockUntil'].replace('Z', '+00:00'))
        
        permission.save()
        
        return Response({
            'success': True,
            'message': 'Permissions updated successfully'
        })


class RegistrarGradeLevelsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get from GradeLevel model only - NO dummy data
        grade_levels = GradeLevel.objects.all().order_by('level')
        
        if not grade_levels.exists():
            return Response({
                'success': False,
                'error': 'No grade levels found in database. Please add grade levels to the GradeLevel model.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        data = []
        for gl in grade_levels:
            data.append({
                'id': str(gl.id),
                'level': gl.level,
                'name': gl.name,
                'display_name': gl.name
            })
        
        return Response({
            'success': True,
            'data': data
        })
        
class RegistrarAllSchedulesView(APIView):
    """Get all exam schedules across all exams"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get all schedules with exam info
            schedules = ExamSchedule.objects.select_related('exam', 'invigilator').all().order_by('date', 'start_time')
            
            data = []
            for schedule in schedules:
                data.append({
                    'id': str(schedule.id),
                    'exam_id': str(schedule.exam.id),
                    'exam_code': schedule.exam.exam_code,
                    'exam_title': schedule.exam.title,
                    'exam_status': schedule.exam.status,
                    'subject': schedule.subject,
                    'date': schedule.date,
                    'start_time': schedule.start_time,
                    'end_time': schedule.end_time,
                    'room': schedule.room,
                    'invigilator': str(schedule.invigilator_id) if schedule.invigilator else None,
                    'invigilator_name': f"{schedule.invigilator.first_name} {schedule.invigilator.last_name}" if schedule.invigilator else None,
                })
            
            return Response({
                'success': True,
                'data': data,
                'count': len(data)
            })
        except Exception as e:
            logger.error(f"Error fetching all schedules: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)