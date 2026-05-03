# cbe_app/views/student_views/student_report_views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from cbe_app.models import Student, ExamResult, StudentAttendance, StudentFeeInvoice
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Grade maps ────────────────────────────────────────────────────────────────
GRADE_TO_POINTS_8 = {
    'EE1': 8, 'EE2': 7, 'ME1': 6, 'ME2': 5,
    'AE1': 4, 'AE2': 3, 'BE1': 2, 'BE2': 1,
}
GRADE_TO_POINTS_4 = {'EE': 4, 'ME': 3, 'AE': 2, 'BE': 1}

# Exam types that are SBA (teacher-set continuous assessments)
SBA_EXAM_TYPES = {
    'classroom-based assessment (cba)',
    'school-based assessment (sba)',
    'continuous assessment test (cat)',
    'cat',
    'cba',
    'sba',
    'assignment',
    'project',
}

# Exam types that are formal/summative (school/admin-set)
SUMMATIVE_EXAM_TYPES = {
    'end_term',
    'mid_term',
    'opener',
    'mock',
    'kpsea',
    'kjsea',
    'jesma',
}


def _is_sba(exam_type: str) -> bool:
    return (exam_type or '').lower().strip() in SBA_EXAM_TYPES


def _is_summative(exam_type: str) -> bool:
    et = (exam_type or '').lower().strip()
    # If it explicitly matches summative types → True
    if et in SUMMATIVE_EXAM_TYPES:
        return True
    # If it's not SBA either, treat as summative (formal school exam)
    if et not in SBA_EXAM_TYPES:
        return True
    return False


def _grade_to_points(grade: str, is_lower_primary: bool) -> int:
    if not grade:
        return 0
    g = grade.upper()
    if is_lower_primary:
        return GRADE_TO_POINTS_4.get(g, 0)
    return GRADE_TO_POINTS_8.get(g, 0)


def _pct_to_grade(pct, is_lower_primary: bool) -> str:
    if pct is None:
        return 'BE2'
    if is_lower_primary:
        if pct >= 90: return 'EE'
        if pct >= 75: return 'ME'
        if pct >= 58: return 'AE'
        return 'BE'
    if pct >= 90: return 'EE1'
    if pct >= 75: return 'EE2'
    if pct >= 58: return 'ME1'
    if pct >= 41: return 'ME2'
    if pct >= 31: return 'AE1'
    if pct >= 21: return 'AE2'
    if pct >= 11: return 'BE1'
    return 'BE2'


def _grade_label(code: str) -> str:
    return {
        'EE1': 'Exceptional', 'EE2': 'Very Good',
        'ME1': 'Good',        'ME2': 'Fair',
        'AE1': 'Needs Improvement', 'AE2': 'Below Average',
        'BE1': 'Well Below Average', 'BE2': 'Minimal',
        'EE': 'Exceeding Expectations',
        'ME': 'Meeting Expectations',
        'AE': 'Approaching Expectations',
        'BE': 'Below Expectations',
    }.get(code, code)


def _build_class_name(student) -> str:
    if not student.current_class:
        return 'N/A'
    name = student.current_class.class_name
    if getattr(student.current_class, 'stream', None):
        name = f"{name} ({student.current_class.stream})"
    return name


def _aggregate_subjects(results_by_subject: dict, is_lower: bool) -> list:
    """Average multiple entries for the same subject and build row dict."""
    aggregated = []
    for subj, res_list in results_by_subject.items():
        latest = res_list[0]

        all_pcts = [float(r.percentage) for r in res_list if r.percentage is not None]
        pct = round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0

        grade = _pct_to_grade(pct, is_lower)
        points = _grade_to_points(grade, is_lower)

        aggregated.append({
            'subject':         subj,
            'grade':           grade,
            'grade_label':     _grade_label(grade),
            'points':          points,
            'percentage':      pct,
            'teacher_comment': latest.remarks or '',
            'exam_title':      latest.exam.title if latest.exam else '',
            'exam_type':       latest.exam.exam_type if latest.exam else '',
        })

    aggregated.sort(key=lambda x: x['subject'])
    return aggregated


class StudentReportCardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # ── 1. Identify the student ───────────────────────────────────────
            if hasattr(request.user, 'student_profile'):
                student = request.user.student_profile
            else:
                try:
                    student = Student.objects.select_related('current_class').get(
                        user=request.user, archived=False
                    )
                except Student.DoesNotExist:
                    return Response({'success': False, 'error': 'Student profile not found.'}, status=404)

            is_lower = bool(
                student.current_class and student.current_class.numeric_level <= 6
            )

            # ── 2. Find all terms that have published results ──────────────────
            all_published = ExamResult.objects.filter(
                student=student,
                exam__status__in=['published', 'completed'],
            ).select_related('exam').order_by(
                '-exam__academic_year', '-exam__term'
            )

            if not all_published.exists():
                return Response({'success': False, 'error': 'No published results found for this student.'}, status=404)

            # Build unique term list for the selector (most recent first)
            seen = set()
            available_terms = []
            for r in all_published:
                key = f"{r.exam.academic_year}||{r.exam.term}"
                if key not in seen:
                    seen.add(key)
                    available_terms.append({
                        'term_id':       key,
                        'label':         f"Term {r.exam.term} — {r.exam.academic_year}",
                        'academic_year': r.exam.academic_year,
                        'term_number':   r.exam.term,
                    })

            # ── 3. Resolve which term to show ─────────────────────────────────
            term_id = request.query_params.get('term_id', '').strip()
            if term_id:
                if '||' not in term_id:
                    return Response({'success': False, 'error': 'Invalid term_id format. Use year||term_number.'}, status=400)
                left, right = term_id.split('||', 1)
                try:
                    academic_year = int(left.strip())
                    term_number   = int(right.strip())
                except ValueError:
                    return Response({'success': False, 'error': 'term_id values must be integers.'}, status=400)
            else:
                # Default → most recent term
                academic_year = available_terms[0]['academic_year']
                term_number   = available_terms[0]['term_number']

            # ── 4. Fetch results for the selected term ─────────────────────────
            term_results = all_published.filter(
                exam__academic_year=academic_year,
                exam__term=term_number,
            )

            if not term_results.exists():
                return Response({'success': False, 'error': f'No results for Term {term_number} — {academic_year}.'}, status=404)

            # ── 5. Split into Summative vs SBA ────────────────────────────────
            summative_subjects = {}
            sba_subjects = {}

            for result in term_results:
                exam_type = result.exam.exam_type if result.exam else ''
                subject   = (result.subject or 'General').strip()

                if _is_sba(exam_type):
                    sba_subjects.setdefault(subject, []).append(result)
                else:
                    summative_subjects.setdefault(subject, []).append(result)

            summative_aggregated = _aggregate_subjects(summative_subjects, is_lower)
            sba_aggregated       = _aggregate_subjects(sba_subjects, is_lower)

            # ── 6. Overall summary (combined) ─────────────────────────────────
            all_rows = summative_aggregated + sba_aggregated
            if all_rows:
                avg_pct    = round(sum(r['percentage'] for r in all_rows) / len(all_rows), 1)
                avg_points = round(sum(r['points'] for r in all_rows) / len(all_rows), 1)
            else:
                avg_pct, avg_points = 0, 0

            overall_grade = _pct_to_grade(avg_pct, is_lower)

            # ── 7. Attendance for this term ───────────────────────────────────
            att_qs         = StudentAttendance.objects.filter(student=student)
            total_sessions = att_qs.count()
            present        = att_qs.filter(attendance_status='Present').count()
            absent         = total_sessions - present
            att_rate       = round(present / total_sessions * 100, 1) if total_sessions else 0

            # ── 8. Build response ─────────────────────────────────────────────
            photo_url = None
            if hasattr(student, 'photo') and student.photo:
                try:
                    photo_url = request.build_absolute_uri(student.photo.url)
                except Exception:
                    pass

            report = {
                'student': {
                    'name':         getattr(student, 'full_name', str(student)),
                    'admission_no': getattr(student, 'admission_no', ''),
                    'class':        _build_class_name(student),
                    'photo_url':    photo_url,
                },
                'term':            f"Term {term_number}",
                'term_number':     term_number,
                'academic_year':   str(academic_year),

                # Selector data
                'available_terms': available_terms,
                'current_term_id': f"{academic_year}||{term_number}",

                # Results split
                'summative_results': summative_aggregated,   # formal school exams
                'sba_results':       sba_aggregated,         # teacher SBA/CAT/CBA

                # Legacy keys (keep for backward compatibility)
                'formal_results':     summative_aggregated,
                'assessment_results': sba_aggregated,

                # Overall
                'overall_grade':      overall_grade,
                'overall_grade_label': _grade_label(overall_grade),
                'overall_points':     avg_points,
                'overall_percentage': avg_pct,

                # Attendance
                'attendance': {
                    'total_days': total_sessions,
                    'present':    present,
                    'absent':     absent,
                    'rate':       att_rate,
                },

                # Remarks (populated by staff — placeholders until model supports it)
                'class_teacher_remark': 'Shows consistent effort in most subjects.',
                'head_teacher_remark':  'Keep working hard.',
                'next_term_begins':     'To be announced',
            }

            return Response({'success': True, 'data': report})

        except Exception as e:
            logger.exception('StudentReportCardView error')
            return Response({'success': False, 'error': str(e)}, status=500)