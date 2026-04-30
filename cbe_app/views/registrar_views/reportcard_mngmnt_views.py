from openpyxl.descriptors import Max, Min
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Avg, Count, Q, F, Sum
from django.utils import timezone
import logging
import pandas as pd
from io import BytesIO

from cbe_app.models import ExamResult, Exam, Student, Class, LearningArea
from cbe_app.serializers.registrar_serializers.reportcard_serializers import (
    ExamResultSerializer, ResultAnalyticsSerializer
)

logger = logging.getLogger(__name__)


class RegistrarResultsListView(APIView):
    """Get all exam results with filters"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            queryset = ExamResult.objects.select_related('exam', 'student', 'marked_by').all().order_by('-marked_at')
            
            # Apply filters
            exam_id = request.query_params.get('exam_id')
            class_id = request.query_params.get('class_id')
            subject = request.query_params.get('subject')
            student_id = request.query_params.get('student_id')
            
            if exam_id:
                queryset = queryset.filter(exam_id=exam_id)
            if class_id:
                queryset = queryset.filter(student__current_class_id=class_id)
            if subject:
                queryset = queryset.filter(subject=subject)
            if student_id:
                queryset = queryset.filter(student_id=student_id)
            
            serializer = ExamResultSerializer(queryset, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'count': len(serializer.data)
            })
        except Exception as e:
            logger.error(f"Error fetching results: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RegistrarResultsAnalyticsView(APIView):
    """Get analytics for results reporting"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            queryset = ExamResult.objects.select_related('exam', 'student').all()
            
            # Apply filters
            exam_id = request.query_params.get('exam_id')
            class_id = request.query_params.get('class_id')
            subject = request.query_params.get('subject')
            
            if exam_id:
                queryset = queryset.filter(exam_id=exam_id)
            if class_id:
                queryset = queryset.filter(student__current_class_id=class_id)
            if subject:
                queryset = queryset.filter(subject=subject)
            
            if queryset.count() == 0:
                return Response({
                    'success': True,
                    'data': {
                        'total_results': 0,
                        'average_score': 0,
                        'pass_rate': 0,
                        'total_students': 0,
                        'grade_distribution': {},
                        'top_performers': [],
                        'subject_performance': [],
                        'class_performance': []
                    }
                })
            
            # Calculate analytics
            total_results = queryset.count()
            total_students = queryset.values('student').distinct().count()
            
            # Average score
            average_score = queryset.aggregate(avg=Avg('percentage'))['avg'] or 0
            
            # Pass rate (passing marks >= 50)
            passed = queryset.filter(percentage__gte=50).count()
            pass_rate = (passed / total_results) * 100 if total_results > 0 else 0
            
            # Grade distribution (8-point CBC scale)
            grade_distribution = {
                'EE1': queryset.filter(percentage__gte=90).count(),
                'EE2': queryset.filter(percentage__gte=75, percentage__lt=90).count(),
                'ME1': queryset.filter(percentage__gte=58, percentage__lt=75).count(),
                'ME2': queryset.filter(percentage__gte=41, percentage__lt=58).count(),
                'AE1': queryset.filter(percentage__gte=31, percentage__lt=41).count(),
                'AE2': queryset.filter(percentage__gte=21, percentage__lt=31).count(),
                'BE1': queryset.filter(percentage__gte=11, percentage__lt=21).count(),
                'BE2': queryset.filter(percentage__lt=11).count(),
            }
            
            # Top performers (students with highest average)
            top_performers = []
            student_avg = queryset.values('student_id', 'student__first_name', 'student__last_name', 'student__admission_no').annotate(
                avg_score=Avg('percentage')
            ).order_by('-avg_score')[:10]
            
            for s in student_avg:
                top_performers.append({
                    'student_id': str(s['student_id']),
                    'name': f"{s['student__first_name']} {s['student__last_name']}",
                    'admission_no': s['student__admission_no'],
                    'average_score': round(s['avg_score'], 2)
                })
            
            # Subject performance
            subject_performance = []
            subjects = queryset.values_list('subject', flat=True).distinct()
            for subj in subjects:
                subject_results = queryset.filter(subject=subj)
                subject_performance.append({
                    'subject': subj,
                    'average': round(subject_results.aggregate(avg=Avg('percentage'))['avg'] or 0, 2),
                    'highest': round(subject_results.aggregate(max=Max('percentage'))['max'] or 0, 2),
                    'lowest': round(subject_results.aggregate(min=Min('percentage'))['min'] or 0, 2),
                    'count': subject_results.count()
                })
            subject_performance.sort(key=lambda x: x['average'], reverse=True)
            
            # Class performance
            class_performance = []
            classes = Class.objects.filter(current_students__isnull=False).distinct()
            for cls in classes:
                class_results = queryset.filter(student__current_class=cls)
                if class_results.exists():
                    class_performance.append({
                        'class_id': str(cls.id),
                        'class_name': cls.class_name,
                        'average': round(class_results.aggregate(avg=Avg('percentage'))['avg'] or 0, 2),
                        'pass_rate': round((class_results.filter(percentage__gte=50).count() / class_results.count()) * 100, 2),
                        'count': class_results.count()
                    })
            class_performance.sort(key=lambda x: x['average'], reverse=True)
            
            return Response({
                'success': True,
                'data': {
                    'total_results': total_results,
                    'average_score': round(average_score, 2),
                    'pass_rate': round(pass_rate, 2),
                    'total_students': total_students,
                    'grade_distribution': grade_distribution,
                    'top_performers': top_performers,
                    'subject_performance': subject_performance,
                    'class_performance': class_performance
                }
            })
        except Exception as e:
            logger.error(f"Error fetching analytics: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RegistrarStudentReportView(APIView):
    """Get individual student report"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        try:
            student = Student.objects.get(id=student_id)
            exam_id = request.query_params.get('exam_id')
            
            queryset = ExamResult.objects.filter(student=student).select_related('exam')
            
            if exam_id:
                queryset = queryset.filter(exam_id=exam_id)
            
            results = ExamResultSerializer(queryset, many=True).data
            
            # Calculate subject grades
            subjects = {}
            for result in results:
                subject = result['subject']
                if subject not in subjects:
                    subjects[subject] = []
                subjects[subject].append(result['percentage'])
            
            subject_grades = []
            for subject, percentages in subjects.items():
                avg_score = sum(percentages) / len(percentages)
                subject_grades.append({
                    'subject': subject,
                    'score': round(avg_score, 2),
                    'count': len(percentages)
                })
            
            return Response({
                'success': True,
                'data': {
                    'student': {
                        'id': str(student.id),
                        'name': student.full_name,
                        'admission_no': student.admission_no,
                        'upi_number': student.upi_number,
                        'class_name': student.current_class.class_name if student.current_class else None
                    },
                    'results': results,
                    'subject_grades': subject_grades,
                    'summary': {
                        'total_subjects': len(subject_grades),
                        'average_score': round(sum([s['score'] for s in subject_grades]) / len(subject_grades), 2) if subject_grades else 0
                    }
                }
            })
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching student report: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RegistrarBulkResultsUploadView(APIView):
    """Bulk upload results from Excel/CSV"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            file = request.FILES.get('file')
            exam_id = request.data.get('exam_id')
            
            if not file or not exam_id:
                return Response({
                    'success': False,
                    'error': 'File and exam_id are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Exam not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Read Excel/CSV file
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            saved_count = 0
            errors = []
            
            for _, row in df.iterrows():
                try:
                    student_id = row.get('student_id') or row.get('admission_no')
                    subject = row.get('subject')
                    marks_obtained = float(row.get('score') or row.get('marks_obtained') or 0)
                    
                    if not student_id or not subject:
                        continue
                    
                    # Find student
                    student = Student.objects.filter(
                        Q(id=student_id) | Q(admission_no=student_id)
                    ).first()
                    
                    if not student:
                        errors.append(f"Student not found: {student_id}")
                        continue
                    
                    # Calculate percentage
                    percentage = (marks_obtained / exam.total_marks) * 100 if exam.total_marks > 0 else 0
                    
                    # Calculate grade
                    if exam.grade_level in ['pp1', 'pp2', '1', '2', '3', '4', '5']:
                        if percentage >= 90:
                            grade = 'EE'
                        elif percentage >= 75:
                            grade = 'ME'
                        elif percentage >= 58:
                            grade = 'AE'
                        else:
                            grade = 'BE'
                    else:
                        if percentage >= 90:
                            grade = 'EE1'
                        elif percentage >= 75:
                            grade = 'EE2'
                        elif percentage >= 58:
                            grade = 'ME1'
                        elif percentage >= 41:
                            grade = 'ME2'
                        elif percentage >= 31:
                            grade = 'AE1'
                        elif percentage >= 21:
                            grade = 'AE2'
                        elif percentage >= 11:
                            grade = 'BE1'
                        else:
                            grade = 'BE2'
                    
                    # Create or update result
                    ExamResult.objects.update_or_create(
                        exam=exam,
                        student=student,
                        subject=subject,
                        defaults={
                            'marks_obtained': marks_obtained,
                            'percentage': round(percentage, 2),
                            'grade': grade,
                            'marked_by': request.user,
                            'marked_at': timezone.now()
                        }
                    )
                    saved_count += 1
                except Exception as e:
                    errors.append(str(e))
            
            return Response({
                'success': True,
                'message': f'Successfully uploaded {saved_count} results',
                'saved_count': saved_count,
                'errors': errors if errors else None
            })
        except Exception as e:
            logger.error(f"Error bulk uploading results: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RegistrarResultSubjectsView(APIView):
    """Get all subjects from results"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subjects = ExamResult.objects.values_list('subject', flat=True).distinct()
            data = [{'id': s, 'name': s} for s in subjects if s]
            return Response({
                'success': True,
                'data': data
            })
        except Exception as e:
            return Response({
                'success': True,
                'data': []  # Return empty if no results yet
            })
            
class RegistrarBulkReportGenerationView(APIView):
    """Generate bulk reports for multiple students/classes"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            exam_id = request.data.get('exam_id')
            class_ids = request.data.get('class_ids', [])
            format_type = request.data.get('format', 'pdf')
            
            if not exam_id or not class_ids:
                return Response({
                    'success': False,
                    'error': 'Exam ID and Class IDs are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Exam not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            reports = []
            total_students = 0
            
            for class_id in class_ids:
                try:
                    class_obj = Class.objects.get(id=class_id)
                    students = Student.objects.filter(current_class=class_obj, status='Active')
                    
                    for student in students:
                        results = ExamResult.objects.filter(exam=exam, student=student)
                        
                        if results.exists():
                            report_data = {
                                'student_name': student.full_name,
                                'admission_no': student.admission_no,
                                'class_name': class_obj.class_name,
                                'exam_title': exam.title,
                                'subjects': []
                            }
                            
                            for result in results:
                                report_data['subjects'].append({
                                    'subject': result.subject,
                                    'score': result.percentage,
                                    'grade': result.grade
                                })
                            
                            reports.append(report_data)
                            total_students += 1
                            
                except Class.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'message': f'Generated {len(reports)} reports for {total_students} students',
                'data': {
                    'reports': reports,
                    'total_students': total_students,
                    'exam_title': exam.title,
                    'format': format_type
                }
            })
            
        except Exception as e:
            logger.error(f"Error generating bulk reports: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)