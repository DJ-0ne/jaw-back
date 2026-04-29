from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import uuid
import os
import logging

from cbe_app.models import (
    Class, Student, Staff, ClassSubjectAllocation, 
    Term, AcademicYear, AttendanceSession, StudentAttendance,
    Exam, ExamResult, StudentPortfolio, Competency
)
from cbe_app.serializers.teacher_serializers.teacher_class_serializers import (
    ClassListSerializer, SubjectClassSerializer, StudentListSerializer,
    AttendanceSubmitSerializer, AssessmentSubmitSerializer, 
    EvidenceUploadSerializer, StudentPortfolioSerializer
)


logger = logging.getLogger(__name__)


class TeacherMyClassesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Your user account is not linked to any staff profile.'
                }, status=200)
            
            staff = request.user.staff_profile
            
            classes = Class.objects.filter(
                class_teacher=staff,
                is_active=True
            ).order_by('numeric_level', 'stream')
            
            serializer = ClassListSerializer(classes, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} classes'
            })
            
        except Exception as e:
            logger.error(f"TeacherMyClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class TeacherSubjectClassesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Your user account is not linked to any staff profile.'
                }, status=200)
            
            staff = request.user.staff_profile
            
            # Get all allocations for this teacher - NO academic year filter
            allocations = ClassSubjectAllocation.objects.filter(
                teacher=staff
            ).select_related('class_id', 'subject')
            
            serializer = SubjectClassSerializer(allocations, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} subject classes'
            })
            
        except Exception as e:
            logger.error(f"TeacherSubjectClassesView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)


class ClassStudentsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Your user account is not linked to any staff profile.'
                }, status=200)
            
            staff = request.user.staff_profile
            
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'Class not found.'
                }, status=404)
            
            # Check access
            has_access = False
            if class_obj.class_teacher == staff:
                has_access = True
            if not has_access:
                has_access = ClassSubjectAllocation.objects.filter(
                    class_id=class_obj, teacher=staff
                ).exists()
            
            if not has_access:
                return Response({
                    'success': False,
                    'data': [],
                    'message': 'You do not have access to this class.'
                }, status=403)
            
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            ).order_by('first_name', 'last_name')
            
            # FIXED: Pass class_obj in context
            serializer = StudentListSerializer(students, many=True, context={'class_obj': class_obj})
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Found {len(serializer.data)} students'
            })
            
        except Exception as e:
            logger.error(f"ClassStudentsView error: {str(e)}")
            return Response({
                'success': False,
                'data': [],
                'error': str(e)
            }, status=500)

class ClassAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        try:
            try:
                class_obj = Class.objects.get(id=class_id, is_active=True)
            except Class.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Class not found.'
                }, status=404)
            
            students = Student.objects.filter(
                current_class=class_obj,
                status='Active',
                archived=False
            )
            
            if not students.exists():
                return Response({
                    'success': True,
                    'data': {
                        'mean_score': 0,
                        'class_rank': 1,
                        'total_streams': Class.objects.filter(
                            numeric_level=class_obj.numeric_level,
                            is_active=True
                        ).count(),
                        'performance_distribution': {'EE': 0, 'ME': 0, 'AE': 0, 'BE': 0},
                        'subject_mastery': [],
                        'top_performers': [],
                        'most_improved': []
                    }
                })
            
            current_term = Term.objects.filter(is_current=True).first()
            
            student_scores = []
            for student in students:
                score = 0
                if current_term:
                    summaries = student.termly_summaries.filter(term=current_term)
                    if summaries.exists():
                        avg_internal = summaries.aggregate(avg=Avg('final_internal_value'))['avg']
                        if avg_internal:
                            score = float(avg_internal) / 8 * 100
                student_scores.append(score)
            
            mean_score = sum(student_scores) / len(student_scores) if student_scores else 0
            
            distribution = {'EE': 0, 'ME': 0, 'AE': 0, 'BE': 0}
            for score in student_scores:
                if score >= 80:
                    distribution['EE'] += 1
                elif score >= 65:
                    distribution['ME'] += 1
                elif score >= 50:
                    distribution['AE'] += 1
                else:
                    distribution['BE'] += 1
            
            student_score_pairs = list(zip(students, student_scores))
            sorted_students = sorted(student_score_pairs, key=lambda x: x[1], reverse=True)
            
            top_performers = []
            for student, score in sorted_students[:5]:
                top_performers.append({
                    'id': str(student.id),
                    'name': student.full_name,
                    'score': round(score),
                    'improvement': '0'
                })
            
            total_streams = Class.objects.filter(
                numeric_level=class_obj.numeric_level,
                is_active=True
            ).count()
            
            return Response({
                'success': True,
                'data': {
                    'mean_score': round(mean_score, 1),
                    'class_rank': 1,
                    'total_streams': total_streams,
                    'performance_distribution': distribution,
                    'subject_mastery': [],
                    'top_performers': top_performers,
                    'most_improved': []
                }
            })
            
        except Exception as e:
            logger.error(f"ClassAnalyticsView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class TakeAttendanceView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AttendanceSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            if not hasattr(request.user, 'staff_profile'):
                return Response({
                    'success': False,
                    'message': 'No staff profile linked.'
                }, status=400)
            
            data = serializer.validated_data
            attendance_date = data['date']
            period = data['period']
            records = data['records']
            class_id = data.get('class_id')
            subject_id = data.get('subject_id')
            
            session_type_map = {'morning': 'Morning', 'afternoon': 'Afternoon', 'full': 'Full Day'}
            session_type = session_type_map.get(period, 'Morning')
            
            class_obj = None
            if class_id:
                try:
                    class_obj = Class.objects.get(id=class_id)
                except Class.DoesNotExist:
                    pass
            
            session, created = AttendanceSession.objects.get_or_create(
                session_date=attendance_date,
                session_type=session_type,
                class_id=class_obj,
                defaults={
                    'conducted_by': request.user,
                    'start_time': timezone.now().time(),
                    'is_active': True
                }
            )
            
            for record in records:
                try:
                    student = Student.objects.get(id=record['student_id'])
                except Student.DoesNotExist:
                    continue
                
                status_map = {'present': 'Present', 'absent': 'Absent', 
                             'late': 'Late', 'excused': 'Excused'}
                attendance_status = status_map.get(record['status'], 'Absent')
                
                StudentAttendance.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={
                        'attendance_status': attendance_status,
                        'remarks': record.get('remarks', ''),
                        'recorded_by': request.user
                    }
                )
            
            return Response({
                'success': True,
                'message': 'Attendance recorded successfully'
            })
            
        except Exception as e:
            logger.error(f"TakeAttendanceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class SaveAssessmentView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AssessmentSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            
            exam = Exam.objects.create(
                exam_code=f"ASS-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                title=data['title'],
                exam_type='cba',
                grade_level='7',
                academic_year=timezone.now().year,
                term=1,
                total_marks=data['max_score'],
                status='published',
                created_by=request.user
            )
            
            for score_data in data['scores']:
                try:
                    student = Student.objects.get(id=score_data['student_id'])
                    ExamResult.objects.create(
                        exam=exam,
                        student=student,
                        subject=data['subject'],
                        marks_obtained=score_data.get('score', 0),
                        remarks=score_data.get('feedback', ''),
                        marked_by=request.user
                    )
                except Student.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'message': 'Assessment saved successfully'
            })
            
        except Exception as e:
            logger.error(f"SaveAssessmentView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class UploadEvidenceView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = EvidenceUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=400)
        
        try:
            data = serializer.validated_data
            
            try:
                student = Student.objects.get(id=data['student_id'])
            except Student.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Student not found'
                }, status=404)
            
            file = data['file']
            
            file_extension = os.path.splitext(file.name)[1]
            file_name = f"evidence/{timezone.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex}{file_extension}"
            file_path = default_storage.save(file_name, ContentFile(file.read()))
            
            evidence_type = 'document'
            if file.content_type and file.content_type.startswith('image/'):
                evidence_type = 'image'
            elif file.content_type == 'application/pdf':
                evidence_type = 'pdf'
            
            current_term = Term.objects.filter(is_current=True).first()
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            default_competency = Competency.objects.first()
            
            if default_competency and current_term and academic_year:
                StudentPortfolio.objects.create(
                    student=student,
                    competency=default_competency,
                    term=current_term,
                    academic_year=academic_year,
                    evidence_url=file_path,
                    evidence_type=evidence_type,
                    teacher_comment=data.get('description', ''),
                    status='pending',
                    assessed_by=request.user,
                    assessed_date=timezone.now()
                )
            
            return Response({
                'success': True,
                'message': 'Evidence uploaded successfully'
            })
            
        except Exception as e:
            logger.error(f"UploadEvidenceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class GetEvidenceView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        try:
            portfolios = StudentPortfolio.objects.filter(
                student_id=student_id
            ).order_by('-assessed_date')
            
            data = []
            for p in portfolios:
                data.append({
                    'id': str(p.id),
                    'student_id': str(p.student_id),
                    'student_name': p.student.full_name,
                    'evidence_url': p.evidence_url,
                    'evidence_type': p.evidence_type,
                    'teacher_comment': p.teacher_comment,
                    'assessed_date': p.assessed_date.isoformat() if p.assessed_date else None
                })
            
            return Response({
                'success': True,
                'data': data
            })
            
        except Exception as e:
            logger.error(f"GetEvidenceView error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)