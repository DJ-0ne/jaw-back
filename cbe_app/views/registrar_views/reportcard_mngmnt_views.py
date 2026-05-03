from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Q
from django.utils import timezone
import logging
import pandas as pd
import uuid

from cbe_app.models import ExamResult, Exam, Student, Class, LearningArea, Term, AcademicYear

logger = logging.getLogger(__name__)


# ── Shared constants ───────────────────────────────────────────────────────────
SBA_TYPES = [
    'cat', 'cba', 'sba',
    'Classroom-Based Assessment (CBA)',
    'School-Based Assessment (SBA)',
    'Continuous Assessment Test (CAT)',
]
SBA_STATUSES = ['published', 'archived', 'ongoing', 'completed']
SUMMATIVE_TYPES = ['end_term', 'mock', 'kpsea', 'kjsea']
SUMMATIVE_STATUSES = ['published', 'archived']


# ── Shared helpers ─────────────────────────────────────────────────────────────
def _grade_from_score(score):
    if score >= 90: return 'EE1', 'Exceptional'
    elif score >= 75: return 'EE2', 'Very Good'
    elif score >= 58: return 'ME1', 'Good'
    elif score >= 41: return 'ME2', 'Fair'
    elif score >= 31: return 'AE1', 'Needs Improvement'
    elif score >= 21: return 'AE2', 'Below Average'
    elif score >= 11: return 'BE1', 'Well Below Average'
    else: return 'BE2', 'Minimal'


def _grade_code_only(score):
    return _grade_from_score(score)[0]


def _resolve_subject_for_sba(result):
    """
    Return the effective subject name for an SBA ExamResult.

    Priority:
      1. result.subject (explicit tag on the result row) — ideal path
      2. exam.subjects list with exactly one entry — teacher set subject
         on the exam itself but not on individual result rows
      3. None — genuinely untaggable (multi-subject exam, no result tag)
    """
    raw = (result.subject or '').strip()
    if raw:
        return raw

    # Fallback: look at the exam's subjects field
    exam_subjects = result.exam.subjects  # JSONField / ArrayField list e.g. ["English"]
    if exam_subjects and isinstance(exam_subjects, list):
        # Remove blanks
        clean = [s.strip() for s in exam_subjects if s and s.strip()]
        if len(clean) == 1:
            return clean[0]
        # Multiple subjects on one SBA exam — cannot safely assign to one subject
    return None


def _build_per_subject_sba(sba_result_rows):
    """
    Process SBA result rows for a single student.

    Subject resolution uses _resolve_subject_for_sba() which checks
    result.subject first, then exam.subjects (single-subject exams only).

    Returns:
        per_subject_sba_avg  – { subject_name: avg_pct }
        sba_details          – list of badge dicts for the frontend
        avg_sba_score        – overall average across ALL sba scores (display)
    """
    subject_tagged = {}   # { subject: [pct, ...] }
    all_scores = []
    sba_details = []

    for result in sba_result_rows:
        if result.percentage is not None:
            pct = float(result.percentage)
        elif result.marks_obtained is not None and result.exam.total_marks:
            pct = round((float(result.marks_obtained) / float(result.exam.total_marks)) * 100, 2)
        else:
            pct = None

        marks = float(result.marks_obtained) if result.marks_obtained is not None else 0

        # Resolve effective subject (result tag → exam subjects → None)
        effective_subject = _resolve_subject_for_sba(result)
        display_subject = effective_subject if effective_subject else 'General'

        sba_details.append({
            'exam_id': str(result.exam.id),
            'exam_title': result.exam.title,
            'exam_type': result.exam.exam_type,
            'subject': display_subject,
            'percentage': pct,
            'marks_obtained': marks,
            'total_marks': result.exam.total_marks,
            'term': result.exam.term,
            'academic_year': result.exam.academic_year,
        })

        if pct is not None:
            all_scores.append(pct)
            if effective_subject:
                subject_tagged.setdefault(effective_subject, []).append(pct)
            # Truly unresolvable → display only, never spreads to summative

    per_subject_sba_avg = {
        subj: round(sum(scores) / len(scores), 2)
        for subj, scores in subject_tagged.items() if scores
    }
    avg_sba_score = round(sum(all_scores) / len(all_scores), 2) if all_scores else None

    return per_subject_sba_avg, sba_details, avg_sba_score


# ── AFTER (fixed) ──────────────────────────────────────────────────────────────
def _weighted_total(subject, summative_score, per_subject_sba_avg):
    """
    Return (sba_score_or_None, weighted_total).

    Weighting rule (KNEC CBE):
      • SBA present  → total = (sba × 0.40) + (summative × 0.60)
      • SBA absent   → SBA component is 0; student earns only the summative
                       portion:  total = (0 × 0.40) + (summative × 0.60)
                       This correctly penalises missing SBA rather than
                       silently inflating the score to the raw summative.

    Exact subject match only — no cross-subject bleed.
    """
    subject_sba = per_subject_sba_avg.get(subject)
    if subject_sba is not None:
        total = round((subject_sba * 0.40) + (summative_score * 0.60), 2)
    else:
        # No SBA recorded → SBA score = 0; only 60 % weight is earned
        total = round(summative_score * 0.60, 2)
    return subject_sba, total


# ── Views ──────────────────────────────────────────────────────────────────────

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

            return Response({'success': True, 'data': data, 'count': len(data)})
        except Exception as e:
            logger.error(f"Results list error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarExamsForReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            exams = Exam.objects.filter(
                Q(status='published') | Q(status='archived')
            ).order_by('-created_at')

            data = []
            for exam in exams:
                is_sba = exam.exam_type in [
                    'Classroom-Based Assessment (CBA)',
                    'School-Based Assessment (SBA)',
                    'Continuous Assessment Test (CAT)',
                ]
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
                    'is_summative': exam.exam_type in SUMMATIVE_TYPES,
                })

            return Response({'success': True, 'data': data, 'count': len(data)})
        except Exception as e:
            logger.error(f"Exams for report error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarResultsAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            queryset = ExamResult.objects.select_related('exam', 'student').all()

            class_id = request.query_params.get('class_id')
            if class_id:
                queryset = queryset.filter(student__current_class_id=class_id)

            queryset = queryset.filter(exam__status__in=['published', 'archived'])

            if queryset.count() == 0:
                return Response({
                    'success': True,
                    'data': {
                        'total_results': 0, 'average_score': 0, 'pass_rate': 0,
                        'total_students': 0, 'grade_distribution': {},
                        'top_performers': [], 'subject_performance': [], 'class_performance': [],
                    }
                })

            total_results = queryset.count()
            total_students = queryset.values('student').distinct().count()
            average_score = queryset.aggregate(avg=Avg('percentage'))['avg'] or 0
            passed = queryset.filter(percentage__gte=50).count()
            pass_rate = (passed / total_results) * 100 if total_results > 0 else 0

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

            student_scores = {}
            for result in queryset:
                if result.exam.exam_type in SUMMATIVE_TYPES and result.subject:
                    sid = str(result.student.id)
                    if sid not in student_scores:
                        student_scores[sid] = {
                            'total': 0, 'count': 0,
                            'name': result.student.full_name,
                            'admission': result.student.admission_no,
                        }
                    if result.percentage:
                        student_scores[sid]['total'] += result.percentage
                        student_scores[sid]['count'] += 1

            top_performers = []
            for sid, d in student_scores.items():
                if d['count'] > 0:
                    top_performers.append({
                        'student_id': sid,
                        'name': d['name'],
                        'admission_no': d['admission'],
                        'average_score': round(d['total'] / d['count'], 2),
                    })
            top_performers = sorted(top_performers, key=lambda x: x['average_score'], reverse=True)[:10]

            subjects_data = {}
            for result in queryset:
                if result.exam.exam_type in SUMMATIVE_TYPES and result.subject:
                    subj = result.subject
                    if subj not in subjects_data:
                        subjects_data[subj] = {'scores': [], 'highest': 0, 'lowest': 100}
                    if result.percentage:
                        subjects_data[subj]['scores'].append(result.percentage)
                        subjects_data[subj]['highest'] = max(subjects_data[subj]['highest'], result.percentage)
                        subjects_data[subj]['lowest'] = min(subjects_data[subj]['lowest'], result.percentage)

            subject_performance = []
            for subj, d in subjects_data.items():
                if d['scores']:
                    subject_performance.append({
                        'subject': subj,
                        'average': round(sum(d['scores']) / len(d['scores']), 2),
                        'highest': round(d['highest'], 2),
                        'lowest': round(d['lowest'], 2),
                        'count': len(d['scores']),
                    })
            subject_performance.sort(key=lambda x: x['average'], reverse=True)

            class_data = {}
            for result in queryset:
                if result.exam.exam_type in SUMMATIVE_TYPES and result.student.current_class:
                    cls_id = str(result.student.current_class.id)
                    if cls_id not in class_data:
                        class_data[cls_id] = {
                            'name': result.student.current_class.class_name,
                            'scores': [], 'passed': 0,
                        }
                    if result.percentage:
                        class_data[cls_id]['scores'].append(result.percentage)
                        if result.percentage >= 50:
                            class_data[cls_id]['passed'] += 1

            class_performance = []
            for cls_id, d in class_data.items():
                if d['scores']:
                    class_performance.append({
                        'class_id': cls_id,
                        'class_name': d['name'],
                        'average': round(sum(d['scores']) / len(d['scores']), 2),
                        'pass_rate': round((d['passed'] / len(d['scores'])) * 100, 2),
                        'count': len(d['scores']),
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
                    'class_performance': class_performance,
                }
            })
        except Exception as e:
            logger.error(f"Analytics error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarStudentReportView(APIView):
    """
    Full student report card.

    SBA subject resolution order (per result):
      1. result.subject  — explicit tag saved on the ExamResult row
      2. exam.subjects   — single-item list means the whole exam was for that subject
      3. Unresolvable    — shown in badges for transparency, never applied to summative

    This ensures teachers who tag the subject on the Exam (not on each result)
    still get correct per-subject SBA averages without any cross-subject bleed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        try:
            student = Student.objects.get(id=student_id)

            # ── SBA results ───────────────────────────────────────────────────
            sba_qs = ExamResult.objects.filter(
                student=student,
                exam__exam_type__in=SBA_TYPES,
                exam__status__in=SBA_STATUSES,
            ).select_related('exam').order_by('exam__term', 'exam__academic_year')

            per_subject_sba_avg, sba_details, avg_sba_score = _build_per_subject_sba(sba_qs)

            # ── Summative results ─────────────────────────────────────────────
            summative_qs = ExamResult.objects.filter(
                student=student,
                exam__exam_type__in=SUMMATIVE_TYPES,
                exam__status__in=SUMMATIVE_STATUSES,
            ).select_related('exam').order_by('exam__academic_year', 'exam__term', 'subject')

            exams_map = {}
            for result in summative_qs:
                eid = str(result.exam.id)
                if eid not in exams_map:
                    exams_map[eid] = {
                        'exam_id': eid,
                        'exam_title': result.exam.title,
                        'exam_type': result.exam.exam_type,
                        'academic_year': result.exam.academic_year,
                        'term': result.exam.term,
                        'grade_level': result.exam.grade_level,
                        'total_marks': result.exam.total_marks,
                        'subjects': {},
                    }
                if result.subject and result.percentage is not None:
                    exams_map[eid]['subjects'][result.subject] = {
                        'summative_score': float(result.percentage),
                        'marks_obtained': float(result.marks_obtained) if result.marks_obtained is not None else 0,
                    }

            exams_list = []
            for eid, exam_data in exams_map.items():
                subjects_list = []
                for subject, scores in exam_data['subjects'].items():
                    summative_score = scores['summative_score']
                    subject_sba, total = _weighted_total(subject, summative_score, per_subject_sba_avg)
                    grade_code, grade_label = _grade_from_score(total)

                    subjects_list.append({
                        'subject': subject,
                        'sba_score': subject_sba,
                        'summative_score': summative_score,
                        'marks_obtained': scores['marks_obtained'],
                        'total': total,
                        'grade_code': grade_code,
                        'grade_label': grade_label,
                    })

                totals = [s['total'] for s in subjects_list]
                overall_avg = round(sum(totals) / len(totals), 2) if totals else 0
                overall_grade, overall_label = _grade_from_score(overall_avg) if totals else ('BE2', 'Minimal')

                exams_list.append({
                    'exam_id': eid,
                    'exam_title': exam_data['exam_title'],
                    'exam_type': exam_data['exam_type'],
                    'academic_year': exam_data['academic_year'],
                    'term': exam_data['term'],
                    'grade_level': exam_data['grade_level'],
                    'total_marks': exam_data['total_marks'],
                    'subjects': subjects_list,
                    'summary': {
                        'total_subjects': len(subjects_list),
                        'average_score': overall_avg,
                        'grade_code': overall_grade,
                        'grade_label': overall_label,
                    },
                })

            exams_list.sort(key=lambda x: (x['academic_year'], x['term']))

            return Response({
                'success': True,
                'data': {
                    'student': {
                        'id': str(student.id),
                        'name': student.full_name,
                        'admission_no': student.admission_no,
                        'upi_number': student.upi_number or 'N/A',
                        'gender': student.gender or 'N/A',
                        'class_name': student.current_class.class_name if student.current_class else 'Not Assigned',
                    },
                    'sba_results': sba_details,
                    'avg_sba_score': avg_sba_score,
                    'per_subject_sba': per_subject_sba_avg,
                    'exams': exams_list,
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
            class_ids = request.data.get('class_ids', [])
            if not class_ids:
                return Response({'success': False, 'error': 'Class IDs are required'}, status=400)

            all_sba_results = list(
                ExamResult.objects.filter(
                    exam__exam_type__in=SBA_TYPES,
                    exam__status__in=SBA_STATUSES,
                ).select_related('student', 'exam')
            )

            reports = []
            for class_id in class_ids:
                try:
                    class_obj = Class.objects.get(id=class_id)
                    students = Student.objects.filter(current_class=class_obj, status='Active')

                    for student in students:
                        student_sba_rows = [r for r in all_sba_results if r.student.id == student.id]
                        per_subject_sba_avg, _, avg_sba = _build_per_subject_sba(student_sba_rows)

                        summative_results = ExamResult.objects.filter(
                            student=student,
                            exam__exam_type__in=SUMMATIVE_TYPES,
                            exam__status__in=SUMMATIVE_STATUSES,
                        ).select_related('exam')

                        if not summative_results.exists():
                            continue

                        exams_map = {}
                        for result in summative_results:
                            eid = str(result.exam.id)
                            if eid not in exams_map:
                                exams_map[eid] = {
                                    'exam_title': result.exam.title,
                                    'exam_type': result.exam.exam_type,
                                    'academic_year': result.exam.academic_year,
                                    'term': result.exam.term,
                                    'subjects': [],
                                }
                            if result.subject and result.percentage:
                                summative_score = float(result.percentage)
                                subject_sba, total = _weighted_total(
                                    result.subject, summative_score, per_subject_sba_avg
                                )
                                exams_map[eid]['subjects'].append({
                                    'subject': result.subject,
                                    'sba_score': subject_sba,
                                    'summative_score': summative_score,
                                    'total': total,
                                    'grade': _grade_code_only(total),
                                })

                        exams_list = list(exams_map.values())
                        if exams_list:
                            reports.append({
                                'student_name': student.full_name,
                                'admission_no': student.admission_no,
                                'upi_number': student.upi_number or 'N/A',
                                'gender': student.gender or 'N/A',
                                'class_name': class_obj.class_name,
                                'avg_sba_score': avg_sba,
                                'sba_count': len(student_sba_rows),
                                'exams': exams_list,
                            })
                except Class.DoesNotExist:
                    continue

            return Response({
                'success': True,
                'data': {'reports': reports, 'total_students': len(reports)}
            })
        except Exception as e:
            logger.error(f"Bulk report error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)


class RegistrarResultSubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subjects = LearningArea.objects.filter(is_active=True).values_list('area_name', flat=True)
            return Response({'success': True, 'data': list(subjects)})
        except Exception as e:
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

            if exam.status not in ['draft', 'scheduled', 'published']:
                return Response({'success': False, 'error': 'Cannot upload results to exam in current status'}, status=400)

            df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)

            saved_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    student_id_col = next(
                        (c for c in ['student_id', 'admission_no', 'admission', 'student_admission'] if c in row), None
                    )
                    subject_col = next(
                        (c for c in ['subject', 'learning_area', 'area'] if c in row), None
                    )
                    score_col = next(
                        (c for c in ['score', 'marks', 'marks_obtained', 'percentage'] if c in row), None
                    )

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

                    if score < 0 or score > exam.total_marks:
                        errors.append(f"Row {index + 2}: Score {score} out of range (0-{exam.total_marks})")
                        continue

                    percentage = (score / exam.total_marks) * 100 if exam.total_marks > 0 else 0

                    ExamResult.objects.update_or_create(
                        exam=exam,
                        student=student,
                        subject=subject,
                        defaults={
                            'marks_obtained': score,
                            'percentage': round(percentage, 2),
                            'grade': _grade_code_only(percentage),
                            'marked_by': request.user,
                            'marked_at': timezone.now(),
                        }
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Row {index + 2} error: {str(e)}")
                    errors.append(f"Row {index + 2}: {str(e)}")

            msg = (
                f'Uploaded {saved_count} results successfully. {len(errors)} errors.'
                if errors else f'Successfully uploaded {saved_count} results'
            )
            return Response({
                'success': True, 'saved_count': saved_count,
                'errors': errors[:20], 'message': msg,
            })
        except Exception as e:
            logger.error(f"Bulk upload error: {str(e)}")
            return Response({'success': False, 'error': str(e)}, status=500)