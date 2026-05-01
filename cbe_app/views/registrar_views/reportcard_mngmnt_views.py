from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Avg, Q, Sum, Count
from django.utils import timezone
import logging
import pandas as pd
import uuid

from cbe_app.models import ExamResult, Exam, Student, Class, LearningArea, Term, AcademicYear

logger = logging.getLogger(__name__)


class RegistrarResultsListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            queryset = ExamResult.objects.select_related('exam', 'student').all().order_by('-marked_at')
            
            exam_id = request.query_params.get('exam_id')
            class_id = request.query_params.get('class_id')
            subject = request.query_params.get('subject')
            
            if exam_id:
                queryset = queryset.filter(exam_id=exam_id)
            if class_id:
                queryset = queryset.filter(student__current_class_id=class_id)
            if subject:
                queryset = queryset.filter(subject=subject)
            
            data = []
            for result in queryset:
                data.append({
                    'id': str(result.id),
                    'exam_id': str(result.exam.id),
                    'exam_title': result.exam.title,
                    'exam_type': result.exam.exam_type,
                    'exam_status': result.exam.status,
                    'total_marks': result.exam.total_marks,
                    'student_id': str(result.student.id),
                    'student_name': result.student.full_name,
                    'student_admission': result.student.admission_no,
                    'subject': result.subject or '',
                    'marks_obtained': float(result.marks_obtained) if result.marks_obtained else 0,
                    'percentage': float(result.percentage) if result.percentage else 0,
                    'grade': result.grade,
                    'remarks': result.remarks or '',
                    'marked_at': result.marked_at.isoformat() if result.marked_at else None,
                })
            
            return Response({
                'success': True,
                'data': data,
                'count': len(data)
            })
        except Exception as e:
            logger.error(f"Results list error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarExamsForReportView(APIView):
    """Get only published exams that can be used for report generation"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Only get published or archived exams (not draft)
            exams = Exam.objects.filter(
                Q(status='published') | Q(status='archived')
            ).order_by('-created_at')
            
            data = []
            for exam in exams:
                # Determine if this is SBA or Summative - FIXED (removed trailing comma)
                is_sba = exam.exam_type in ['Classroom-Based Assessment (CBA)', 'School-Based Assessment (SBA)', 'Continuous Assessment Test (CAT)']
                is_summative = exam.exam_type in ['end_term', 'mock', 'kpsea', 'kjsea']
               
                data.append({
                    'id': str(exam.id),
                    'title': exam.title,
                    'exam_type': exam.exam_type,
                    'exam_code': exam.exam_code,
                    'status': exam.status,
                    'academic_year': exam.academic_year,
                    'term': exam.term,
                    'grade_level': exam.grade_level,
                    'total_marks': exam.total_marks,
                    'is_sba': is_sba,
                    'is_summative': is_summative
                })
            
            return Response({
                'success': True,
                'data': data,
                'count': len(data)
            })
        except Exception as e:
            logger.error(f"Exams for report error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarResultsAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            queryset = ExamResult.objects.select_related('exam', 'student').all()
            
            exam_id = request.query_params.get('exam_id')
            class_id = request.query_params.get('class_id')
            subject = request.query_params.get('subject')  # FIXED: Added subject filter
            
            if exam_id:
                queryset = queryset.filter(exam_id=exam_id)
            if class_id:
                queryset = queryset.filter(student__current_class_id=class_id)
            if subject:  # FIXED: Added subject filter
                queryset = queryset.filter(subject=subject)
            
            # If no results, return zeros
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
            
            total_results = queryset.count()
            total_students = queryset.values('student').distinct().count()
            average_score = queryset.aggregate(avg=Avg('percentage'))['avg'] or 0
            passed = queryset.filter(percentage__gte=50).count()
            pass_rate = (passed / total_results) * 100 if total_results > 0 else 0
            
            # FIXED: Grade distribution with correct ranges
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
            
            # Top performers - only include summative results (with subjects)
            student_scores = {}
            for result in queryset:
                # Only include summative exam results (end_term, mock, kpsea, kjsea) that have subjects
                if result.exam.exam_type in ['end_term', 'mock', 'kpsea', 'kjsea'] and result.subject:
                    sid = str(result.student.id)
                    if sid not in student_scores:
                        student_scores[sid] = {'total': 0, 'count': 0, 'name': result.student.full_name, 'admission': result.student.admission_no}
                    if result.percentage:
                        student_scores[sid]['total'] += result.percentage
                        student_scores[sid]['count'] += 1
            
            top_performers = []
            for sid, data in student_scores.items():
                if data['count'] > 0:
                    top_performers.append({
                        'student_id': sid,
                        'name': data['name'],
                        'admission_no': data['admission'],
                        'average_score': round(data['total'] / data['count'], 2)
                    })
            top_performers = sorted(top_performers, key=lambda x: x['average_score'], reverse=True)[:10]
            
            # Subject performance - only for summative results
            subjects_data = {}
            for result in queryset:
                if result.exam.exam_type in ['end_term', 'mock', 'kpsea', 'kjsea'] and result.subject:
                    subj = result.subject
                    if subj not in subjects_data:
                        subjects_data[subj] = {'scores': [], 'highest': 0, 'lowest': 100}
                    if result.percentage:
                        subjects_data[subj]['scores'].append(result.percentage)
                        if result.percentage > subjects_data[subj]['highest']:
                            subjects_data[subj]['highest'] = result.percentage
                        if result.percentage < subjects_data[subj]['lowest']:
                            subjects_data[subj]['lowest'] = result.percentage
            
            subject_performance = []
            for subj, data in subjects_data.items():
                if data['scores']:
                    subject_performance.append({
                        'subject': subj,
                        'average': round(sum(data['scores']) / len(data['scores']), 2),
                        'highest': round(data['highest'], 2),
                        'lowest': round(data['lowest'], 2),
                        'count': len(data['scores'])
                    })
            subject_performance = sorted(subject_performance, key=lambda x: x['average'], reverse=True)
            
            # Class performance
            class_data = {}
            for result in queryset:
                if result.exam.exam_type in ['end_term', 'mock', 'kpsea', 'kjsea'] and result.student.current_class:
                    cls_id = str(result.student.current_class.id)
                    cls_name = result.student.current_class.class_name
                    if cls_id not in class_data:
                        class_data[cls_id] = {'name': cls_name, 'scores': [], 'passed': 0}
                    if result.percentage:
                        class_data[cls_id]['scores'].append(result.percentage)
                        if result.percentage >= 50:
                            class_data[cls_id]['passed'] += 1
            
            class_performance = []
            for cls_id, data in class_data.items():
                if data['scores']:
                    class_performance.append({
                        'class_id': cls_id,
                        'class_name': data['name'],
                        'average': round(sum(data['scores']) / len(data['scores']), 2),
                        'pass_rate': round((data['passed'] / len(data['scores'])) * 100, 2),
                        'count': len(data['scores'])
                    })
            class_performance = sorted(class_performance, key=lambda x: x['average'], reverse=True)
            
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
            logger.error(f"Analytics error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarStudentReportView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        try:
            student = Student.objects.get(id=student_id)
            exam_id = request.query_params.get('exam_id')
            
            if not exam_id:
                return Response({'success': False, 'error': 'Exam ID is required'}, status=400)
            
            # Get the selected exam (should be published or archived)
            try:
                selected_exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'success': False, 'error': 'Exam not found'}, status=404)
            
            # FIXED: Only allow published or archived exams for report generation (lowercase)
            if selected_exam.status not in ['published', 'archived']:
                return Response({'success': False, 'error': 'Exam must be published to generate report'}, status=400)
            
            # Get all SBA/CAT results for this student (cba, sba, cat)
            sba_results = ExamResult.objects.filter(
                student=student,
                exam__exam_type__in=['Classroom-Based Assessment (CBA)', 'School-Based Assessment (SBA)', 'Continuous Assessment Test (CAT)'],
                exam__status__in=['published', 'archived']
            ).select_related('exam')
            
            # Get summative results for the selected exam (end_term, mock, kpsea, kjsea)
            summative_results = ExamResult.objects.filter(
                exam=selected_exam,
                student=student
            ).select_related('exam')
            
            # Calculate average SBA score across all CATs
            sba_scores_list = []
            sba_details = []
            for result in sba_results:
                if result.percentage:
                    sba_scores_list.append(result.percentage)
                    sba_details.append({
                        'exam_id': str(result.exam.id),
                        'exam_title': result.exam.title,
                        'exam_type': result.exam.exam_type,
                        'subject': result.subject or 'General',
                        'percentage': float(result.percentage),
                        'marks_obtained': float(result.marks_obtained) if result.marks_obtained else 0,
                        'total_marks': result.exam.total_marks
                    })
            
            avg_sba_score = round(sum(sba_scores_list) / len(sba_scores_list), 2) if sba_scores_list else None
            
            # Group summative results by subject for weighted calculation
            subject_scores = {}
            for result in summative_results:
                if result.subject and result.percentage:
                    subject = result.subject
                    if subject not in subject_scores:
                        subject_scores[subject] = {
                            'summative_score': float(result.percentage),
                            'exam_id': str(result.exam.id),
                            'exam_title': result.exam.title,
                            'marks_obtained': float(result.marks_obtained) if result.marks_obtained else 0,
                            'total_marks': result.exam.total_marks
                        }
            
            # Calculate weighted total (40% SBA + 60% Summative) for each subject
            for subject, scores in subject_scores.items():
                if avg_sba_score:
                    scores['sba_score'] = avg_sba_score
                    scores['total'] = round((avg_sba_score * 0.4) + (scores['summative_score'] * 0.6), 2)
                else:
                    scores['sba_score'] = None
                    scores['total'] = scores['summative_score']
                
                # Determine achievement level based on total
                total = scores['total']
                if total >= 90:
                    scores['grade_code'] = 'EE1'
                    scores['grade_label'] = 'Exceptional'
                elif total >= 75:
                    scores['grade_code'] = 'EE2'
                    scores['grade_label'] = 'Very Good'
                elif total >= 58:
                    scores['grade_code'] = 'ME1'
                    scores['grade_label'] = 'Good'
                elif total >= 41:
                    scores['grade_code'] = 'ME2'
                    scores['grade_label'] = 'Fair'
                elif total >= 31:
                    scores['grade_code'] = 'AE1'
                    scores['grade_label'] = 'Needs Improvement'
                elif total >= 21:
                    scores['grade_code'] = 'AE2'
                    scores['grade_label'] = 'Below Average'
                elif total >= 11:
                    scores['grade_code'] = 'BE1'
                    scores['grade_label'] = 'Well Below Average'
                else:
                    scores['grade_code'] = 'BE2'
                    scores['grade_label'] = 'Minimal'
            
            # Calculate overall average
            all_totals = [s['total'] for s in subject_scores.values() if s['total']]
            overall_avg = round(sum(all_totals) / len(all_totals), 2) if all_totals else 0
            
            # Determine overall grade
            if overall_avg >= 90:
                overall_grade = 'EE1'
                overall_label = 'Exceptional'
            elif overall_avg >= 75:
                overall_grade = 'EE2'
                overall_label = 'Very Good'
            elif overall_avg >= 58:
                overall_grade = 'ME1'
                overall_label = 'Good'
            elif overall_avg >= 41:
                overall_grade = 'ME2'
                overall_label = 'Fair'
            elif overall_avg >= 31:
                overall_grade = 'AE1'
                overall_label = 'Needs Improvement'
            elif overall_avg >= 21:
                overall_grade = 'AE2'
                overall_label = 'Below Average'
            elif overall_avg >= 11:
                overall_grade = 'BE1'
                overall_label = 'Well Below Average'
            else:
                overall_grade = 'BE2'
                overall_label = 'Minimal'
            
            # Build subjects list for response
            subjects_list = []
            for subject, scores in subject_scores.items():
                subjects_list.append({
                    'subject': subject,
                    'sba_score': scores.get('sba_score'),
                    'summative_score': scores['summative_score'],
                    'total': scores['total'],
                    'grade_code': scores['grade_code'],
                    'grade_label': scores['grade_label'],
                    'exam_id': scores['exam_id'],
                    'exam_title': scores['exam_title']
                })
            
            return Response({
                'success': True,
                'data': {
                    'student': {
                        'id': str(student.id),
                        'name': student.full_name,
                        'admission_no': student.admission_no,
                        'upi_number': student.upi_number or 'N/A',
                        'gender': student.gender or 'N/A',
                        'class_name': student.current_class.class_name if student.current_class else 'Not Assigned'
                    },
                    'exam': {
                        'id': str(selected_exam.id),
                        'title': selected_exam.title,
                        'exam_type': selected_exam.exam_type,
                        'academic_year': selected_exam.academic_year,
                        'term': selected_exam.term,
                        'grade_level': selected_exam.grade_level,
                        'total_marks': selected_exam.total_marks
                    },
                    'sba_results': sba_details,
                    'avg_sba_score': avg_sba_score,
                    'subjects': subjects_list,
                    'summary': {
                        'total_subjects': len(subjects_list),
                        'average_score': overall_avg,
                        'grade_code': overall_grade,
                        'grade_label': overall_label
                    }
                }
            })
        except Student.DoesNotExist:
            return Response({'success': False, 'error': 'Student not found'}, status=404)
        except Exception as e:
            logger.error(f"Student report error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarBulkReportGenerationView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            exam_id = request.data.get('exam_id')
            class_ids = request.data.get('class_ids', [])
            
            if not exam_id or not class_ids:
                return Response({
                    'success': False,
                    'error': 'Exam ID and Class IDs are required'
                }, status=400)
            
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'success': False, 'error': 'Exam not found'}, status=404)
            
            # Only allow published or archived exams (lowercase)
            if exam.status not in ['published', 'archived']:
                return Response({'success': False, 'error': 'Exam must be published to generate reports'}, status=400)
            
            # Get all SBA/CAT results for all students for this specific term
            # FIXED: Only get SBA results from same academic year/term as the exam
            all_sba_results = ExamResult.objects.filter(
                exam__exam_type__in=['Classroom-Based Assessment (CBA)', 'School-Based Assessment (SBA)', 'Continuous Assessment Test (CAT)'],
                exam__status__in=['published', 'archived'],
                exam__academic_year=exam.academic_year,  # FIXED: Same academic year
                exam__term=exam.term  # FIXED: Same term
            ).select_related('student', 'exam')
            
            reports = []
            for class_id in class_ids:
                try:
                    class_obj = Class.objects.get(id=class_id)
                    students = Student.objects.filter(current_class=class_obj, status='Active')
                    
                    for student in students:
                        # Get SBA results for this student (already filtered by term/year)
                        student_sba = [r for r in all_sba_results if r.student.id == student.id]
                        sba_scores = [r.percentage for r in student_sba if r.percentage]
                        avg_sba = round(sum(sba_scores) / len(sba_scores), 2) if sba_scores else None
                        
                        # Get summative results for this exam
                        summative_results = ExamResult.objects.filter(exam=exam, student=student)
                        
                        if summative_results.exists():
                            subjects_list = []
                            for result in summative_results:
                                if result.subject and result.percentage:
                                    # Calculate weighted total
                                    if avg_sba:
                                        weighted_total = round((avg_sba * 0.4) + (result.percentage * 0.6), 2)
                                    else:
                                        weighted_total = result.percentage
                                    
                                    # Determine grade
                                    if weighted_total >= 90:
                                        grade = 'EE1'
                                    elif weighted_total >= 75:
                                        grade = 'EE2'
                                    elif weighted_total >= 58:
                                        grade = 'ME1'
                                    elif weighted_total >= 41:
                                        grade = 'ME2'
                                    elif weighted_total >= 31:
                                        grade = 'AE1'
                                    elif weighted_total >= 21:
                                        grade = 'AE2'
                                    elif weighted_total >= 11:
                                        grade = 'BE1'
                                    else:
                                        grade = 'BE2'
                                    
                                    subjects_list.append({
                                        'subject': result.subject,
                                        'sba_score': avg_sba,
                                        'summative_score': result.percentage,
                                        'total': weighted_total,
                                        'grade': grade
                                    })
                            
                            if subjects_list:
                                reports.append({
                                    'student_name': student.full_name,
                                    'admission_no': student.admission_no,
                                    'class_name': class_obj.class_name,
                                    'exam_title': exam.title,
                                    'subjects': subjects_list
                                })
                except Class.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'data': {
                    'reports': reports,
                    'total_students': len(reports),
                    'exam_title': exam.title
                }
            })
        except Exception as e:
            logger.error(f"Bulk report error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarResultSubjectsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subjects = LearningArea.objects.filter(is_active=True).values_list('area_name', flat=True)
            # Return just the names as strings, not objects
            data = list(subjects)  # This returns ["Mathematics", "English", "Kiswahili", ...]
            return Response({'success': True, 'data': data})
        except Exception as e:
            # FIXED: Return error response instead of success
            logger.error(f"Subjects error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarBulkResultsUploadView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            file = request.FILES.get('file')
            exam_id = request.data.get('exam_id')
            
            if not file or not exam_id:
                return Response({'success': False, 'error': 'File and exam_id required'}, status=400)
            
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'success': False, 'error': 'Exam not found'}, status=404)
            
            # Check if exam is in draft status - allow upload
            if exam.status not in ['draft', 'scheduled', 'published']:
                return Response({'success': False, 'error': 'Cannot upload results to exam in current status'}, status=400)
            
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            saved_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Try multiple column name variations
                    student_id_col = None
                    for col in ['student_id', 'admission_no', 'admission', 'student_admission']:
                        if col in row:
                            student_id_col = col
                            break
                    
                    subject_col = None
                    for col in ['subject', 'learning_area', 'area']:
                        if col in row:
                            subject_col = col
                            break
                    
                    score_col = None
                    for col in ['score', 'marks', 'marks_obtained', 'percentage']:
                        if col in row:
                            score_col = col
                            break
                    
                    if not student_id_col or not subject_col or not score_col:
                        errors.append(f"Row {index + 2}: Missing required columns")
                        continue
                    
                    student = Student.objects.filter(
                        Q(admission_no=str(row[student_id_col])) | 
                        Q(admission_no__iexact=str(row[student_id_col]))
                    ).first()
                    
                    if not student:
                        errors.append(f"Row {index + 2}: Student not found - {row[student_id_col]}")
                        continue
                    
                    subject = str(row[subject_col]).strip()
                    if not subject:
                        errors.append(f"Row {index + 2}: Subject is empty")
                        continue
                    
                    try:
                        score = float(row[score_col])
                    except (ValueError, TypeError):
                        errors.append(f"Row {index + 2}: Invalid score value - {row[score_col]}")
                        continue
                    
                    # Validate score range
                    if score < 0 or score > exam.total_marks:
                        errors.append(f"Row {index + 2}: Score {score} out of range (0-{exam.total_marks})")
                        continue
                    
                    percentage = (score / exam.total_marks) * 100 if exam.total_marks > 0 else 0
                    
                    # Determine grade using JSS 8-point scale
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
                    
                    ExamResult.objects.update_or_create(
                        exam=exam,
                        student=student,
                        subject=subject,
                        defaults={
                            'marks_obtained': score,
                            'percentage': round(percentage, 2),
                            'grade': grade,
                            'marked_by': request.user,
                            'marked_at': timezone.now()
                        }
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Row {index + 2} error: {str(e)}")
                    errors.append(f"Row {index + 2}: {str(e)}")
            
            return Response({
                'success': True,
                'saved_count': saved_count,
                'errors': errors[:20],  # Limit errors to first 20
                'message': f'Uploaded {saved_count} results successfully. {len(errors)} errors.' if errors else f'Successfully uploaded {saved_count} results'
            })
        except Exception as e:
            logger.error(f"Bulk upload error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)