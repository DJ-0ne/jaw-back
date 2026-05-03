import re
import logging
from datetime import datetime, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q
from django.utils import timezone

from cbe_app.models import (
    Student, StudentFeeInvoice, FeeTransaction,
    StudentAttendance, DisciplineIncident, TermlySummary, Timetable,
    AcademicYear, Term, ExamResult
)
from cbe_app.serializers.student_serializers.student_serializers import (
    StudentProfileSerializer, FeeSummarySerializer, FeeTransactionSerializer,
    AttendanceRecordSerializer, DisciplineRecordSerializer,
    AcademicPerformanceSerializer, TimetableSlotSerializer
)

logger = logging.getLogger(__name__)

# ──────────────────────────── CBC HELPERS ────────────────────────────

GRADE_TO_POINTS = {
    'EE1': 8, 'EE2': 7, 'ME1': 6, 'ME2': 5,
    'AE1': 4, 'AE2': 3, 'BE1': 2, 'BE2': 1,
    'EE': 8, 'ME': 6, 'AE': 4, 'BE': 2,
}

PTS_TO_CODE = {
    8: 'EE1', 7: 'EE2', 6: 'ME1', 5: 'ME2',
    4: 'AE1', 3: 'AE2', 2: 'BE1', 1: 'BE2',
}

FOUR_POINT_LEVELS = {'pp1', 'pp2', '1', '2', '3', '4', '5', '6'}


def get_cbc_grade_level(student):
    """Convert class numeric_level to CBC grade string ('pp1','1','7', etc.)."""
    if not student.current_class:
        return ''
    nl = student.current_class.numeric_level
    mapping = {1: 'pp1', 2: 'pp2'}
    return mapping.get(nl, str(nl - 2))


def grade_to_points_cbc(code, grade_level):
    """Return points for a grade code using the correct scale for the grade level."""
    gl = str(grade_level).lower().strip()
    if gl in FOUR_POINT_LEVELS:
        return {'EE': 4, 'ME': 3, 'AE': 2, 'BE': 1}.get(code.upper(), 0)
    else:
        return GRADE_TO_POINTS.get(code.upper(), 0)


def points_to_grade_cbc(points, grade_level):
    """Convert points back to a grade code using the correct scale."""
    gl = str(grade_level).lower().strip()
    if gl in FOUR_POINT_LEVELS:
        return {4: 'EE', 3: 'ME', 2: 'AE', 1: 'BE'}.get(points, '')
    else:
        return PTS_TO_CODE.get(points, '')


# ==================== STUDENT PROFILE ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_profile(request):
    """Get logged-in student's profile"""
    try:
        student = Student.objects.select_related('user', 'current_class').get(
            user=request.user, archived=False)
        serializer = StudentProfileSerializer(student)
        return Response({'success': True, 'data': serializer.data})
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching student profile: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


# ==================== FEE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_summary(request):
    """Get fee summary for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(
            is_current=True, academic_year=current_academic_year).first() if current_academic_year else None

        invoices = StudentFeeInvoice.objects.filter(student=student)
        total_fees = invoices.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = invoices.aggregate(total=Sum('amount_paid'))['total'] or 0
        balance = total_fees - total_paid

        today = timezone.now().date()
        overdue_invoices = invoices.filter(due_date__lt=today, balance_amount__gt=0)
        overdue_amount = overdue_invoices.aggregate(total=Sum('balance_amount'))['total'] or 0

        overdue_days = 0
        if overdue_invoices.exists():
            oldest_due = overdue_invoices.order_by('due_date').first()
            if oldest_due:
                overdue_days = (today - oldest_due.due_date).days

        recent_transactions = FeeTransaction.objects.filter(
            student=student, status='Completed').order_by('-payment_date')[:5]
        recent_data = FeeTransactionSerializer(recent_transactions, many=True).data

        summary_data = {
            'total_fees': total_fees,
            'total_paid': total_paid,
            'balance': balance,
            'overdue_amount': overdue_amount,
            'overdue_days': overdue_days,
            'academic_year': current_academic_year.year_name if current_academic_year else 'N/A',
            'term': current_term.term if current_term else 'N/A',
            'recent_transactions': recent_data
        }
        serializer = FeeSummarySerializer(summary_data)
        return Response({'success': True, 'data': serializer.data})
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching fee summary: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_transactions(request):
    """Get all fee transactions for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        transactions = FeeTransaction.objects.filter(
            student=student, status='Completed').order_by('-payment_date')
        serializer = FeeTransactionSerializer(transactions, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching fee transactions: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


# ==================== ATTENDANCE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_attendance(request):
    """Get all attendance records for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = request.query_params.get('limit')

        records = StudentAttendance.objects.filter(student=student).select_related(
            'session', 'session__subject').order_by('-session__session_date')
        if start_date:
            records = records.filter(session__session_date__gte=start_date)
        if end_date:
            records = records.filter(session__session_date__lte=end_date)
        if limit:
            records = records[:int(limit)]

        serializer = AttendanceRecordSerializer(records, many=True)
        total = records.count()
        present = records.filter(attendance_status='Present').count()
        absent = records.filter(attendance_status='Absent').count()
        late = records.filter(attendance_status='Late').count()

        return Response({
            'success': True,
            'data': serializer.data,
            'summary': {
                'total': total,
                'present': present,
                'absent': absent,
                'late': late,
                'attendance_rate': round((present / total * 100), 2) if total else 0
            }
        })
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching attendance: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_attendance(request):
    """Get recent attendance records for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        limit = int(request.query_params.get('limit', 10))
        records = StudentAttendance.objects.filter(
            student=student).select_related('session', 'session__subject'
        ).order_by('-session__session_date')[:limit]
        serializer = AttendanceRecordSerializer(records, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching recent attendance: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


# ==================== DISCIPLINE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_records(request):
    """Get discipline records for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        incidents = DisciplineIncident.objects.filter(
            student=student).select_related('category').order_by('-incident_date')
        serializer = DisciplineRecordSerializer(incidents, many=True)

        total_points = incidents.aggregate(total=Sum('points_awarded'))['total'] or 0
        open_cases = incidents.filter(status__in=['Reported', 'Under Investigation']).count()
        resolved_cases = incidents.filter(status='Resolved').count()

        return Response({
            'success': True,
            'data': serializer.data,
            'summary': {
                'total_points': total_points,
                'open_cases': open_cases,
                'resolved_cases': resolved_cases,
                'total_incidents': incidents.count()
            }
        })
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching discipline records: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


# ==================== ACADEMIC PERFORMANCE (CBC‑aware, using ExamResult) ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_academic_performance(request):
    """Get aggregated academic performance from published ExamResults (all terms)."""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        grade_level = get_cbc_grade_level(student)

        results_qs = ExamResult.objects.filter(
            student=student,
            exam__status='published'
        ).select_related('exam').order_by('-exam__academic_year', '-exam__term', '-marked_at')

        # Optional filters
        term = request.query_params.get('term')
        academic_year = request.query_params.get('academic_year')
        if term:
            results_qs = results_qs.filter(exam__term=term)
        if academic_year:
            results_qs = results_qs.filter(exam__academic_year=academic_year)

        # Group by term and learning area
        summary_data = {}
        for r in results_qs:
            key = (r.exam.academic_year, r.exam.term, r.subject)
            if key not in summary_data:
                summary_data[key] = []
            summary_data[key].append(r)

        performance_data = []
        for (year, term, subject), res_list in summary_data.items():
            latest = res_list[0]
            pct = float(latest.percentage) if latest.percentage else 0
            code = latest.grade
            if not code or code.upper() not in (
                'EE', 'ME', 'AE', 'BE', 'EE1', 'EE2', 'ME1', 'ME2', 'AE1', 'AE2', 'BE1', 'BE2'
            ):
                if str(grade_level) in FOUR_POINT_LEVELS:
                    code = 'EE' if pct >= 90 else 'ME' if pct >= 75 else 'AE' if pct >= 58 else 'BE'
                else:
                    code = ('EE1' if pct >= 90 else 'EE2' if pct >= 75 else 'ME1' if pct >= 58 else
                            'ME2' if pct >= 41 else 'AE1' if pct >= 31 else 'AE2' if pct >= 21 else
                            'BE1' if pct >= 11 else 'BE2')
            points = grade_to_points_cbc(code, grade_level)

            performance_data.append({
                'learning_area': subject,
                'score': round(pct, 2),
                'grade': code,
                'points': points,
                'term': f"Term {term}",
                'academic_year': str(year)
            })

        return Response({'success': True, 'data': performance_data})
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.exception("get_academic_performance error")
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_performance(request):
    """Current term academic performance from published ExamResults (CBC scaled)."""
    try:
        student = Student.objects.get(user=request.user, archived=False)

        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(
            is_current=True, academic_year=current_academic_year).first()
        if not current_term:
            return Response({
                'success': True,
                'data': [],
                'message': 'No active term found'
            })

        # Extract year and term number
        year_int = None
        if current_academic_year and current_academic_year.start_date:
            year_int = current_academic_year.start_date.year
        elif current_academic_year and hasattr(current_academic_year, 'year_code'):
            match = re.search(r'\b(20\d{2})\b', str(current_academic_year.year_code))
            if match:
                year_int = int(match.group(1))

        match = re.search(r'(\d+)', str(current_term.term)) if current_term.term else None
        term_number = int(match.group(1)) if match else None

        if not year_int or not term_number:
            return Response({
                'success': False,
                'error': 'Could not determine year/term'
            }, status=500)

        grade_level = get_cbc_grade_level(student)

        results_qs = ExamResult.objects.filter(
            student=student,
            exam__status='published',
            exam__academic_year=year_int,
            exam__term=term_number
        ).select_related('exam').order_by('subject', '-marked_at')

        if not results_qs.exists():
            return Response({
                'success': True,
                'data': [],
                'message': 'No published results for the current term'
            })

        # Aggregate by subject
        subject_map = {}
        for result in results_qs:
            subj = result.subject or 'General'
            subject_map.setdefault(subj, []).append(result)

        performance_data = []
        total_points = 0
        total_percentage = 0

        for subj_name, res_list in subject_map.items():
            latest = res_list[0]
            pct = float(latest.percentage) if latest.percentage else 0
            code = latest.grade
            if code and code.upper() in (
                'EE', 'ME', 'AE', 'BE', 'EE1', 'EE2', 'ME1', 'ME2', 'AE1', 'AE2', 'BE1', 'BE2'
            ):
                pass
            else:
                if str(grade_level) in FOUR_POINT_LEVELS:
                    code = 'EE' if pct >= 90 else 'ME' if pct >= 75 else 'AE' if pct >= 58 else 'BE'
                else:
                    code = ('EE1' if pct >= 90 else 'EE2' if pct >= 75 else 'ME1' if pct >= 58 else
                            'ME2' if pct >= 41 else 'AE1' if pct >= 31 else 'AE2' if pct >= 21 else
                            'BE1' if pct >= 11 else 'BE2')

            points = grade_to_points_cbc(code, grade_level)

            if len(res_list) > 1:
                pts = [grade_to_points_cbc(r.grade, grade_level) for r in res_list if r.grade]
                pts = [p for p in pts if p > 0]
                if pts:
                    points = round(sum(pts) / len(pts))
                    code = points_to_grade_cbc(points, grade_level)

            performance_data.append({
                'learning_area': subj_name,
                'score': round(pct, 2),
                'grade': code,
                'points': points,
                'teacher_comment': latest.remarks or '',
            })
            total_points += points
            total_percentage += pct

        count = len(performance_data)
        overall_percentage = round(total_percentage / count, 2) if count else 0
        overall_points = round(total_points / count, 1) if count else 0
        overall_grade = points_to_grade_cbc(round(overall_points), grade_level)

        return Response({
            'success': True,
            'data': performance_data,
            'summary': {
                'term': current_term.term,
                'academic_year': str(year_int),
                'overall_score': overall_percentage,
                'overall_grade': overall_grade,
                'overall_points': overall_points,
                'subjects_count': count
            }
        })

    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.exception("get_current_performance error")
        return Response({'success': False, 'error': str(e)}, status=500)


# ==================== EXAM RESULTS (now uses ExamResult) ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exam_results(request):
    """Get detailed exam results for logged-in student (published only)."""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        grade_level = get_cbc_grade_level(student)

        term = request.query_params.get('term')
        academic_year = request.query_params.get('academic_year')

        results_qs = ExamResult.objects.filter(
            student=student,
            exam__status='published'
        ).select_related('exam').order_by('-exam__academic_year', '-exam__term', '-marked_at')

        if term:
            results_qs = results_qs.filter(exam__term=term)
        if academic_year:
            results_qs = results_qs.filter(exam__academic_year=academic_year)

        data = []
        for r in results_qs:
            pct = float(r.percentage) if r.percentage else 0
            code = r.grade
            if not code or code.upper() not in (
                'EE', 'ME', 'AE', 'BE', 'EE1', 'EE2', 'ME1', 'ME2', 'AE1', 'AE2', 'BE1', 'BE2'
            ):
                if str(grade_level) in FOUR_POINT_LEVELS:
                    code = 'EE' if pct >= 90 else 'ME' if pct >= 75 else 'AE' if pct >= 58 else 'BE'
                else:
                    code = ('EE1' if pct >= 90 else 'EE2' if pct >= 75 else 'ME1' if pct >= 58 else
                            'ME2' if pct >= 41 else 'AE1' if pct >= 31 else 'AE2' if pct >= 21 else
                            'BE1' if pct >= 11 else 'BE2')
            points = grade_to_points_cbc(code, grade_level)

            data.append({
                'exam_title': r.exam.title,
                'subject': r.subject,
                'percentage': pct,
                'grade': code,
                'points': points,
                'remarks': r.remarks or '',
                'marked_at': r.marked_at.isoformat() if r.marked_at else None
            })

        return Response({'success': True, 'data': data})
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching exam results: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)


# ==================== TIMETABLE ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_timetable(request):
    """Get timetable for logged-in student's class"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        if not student.current_class:
            return Response({
                'success': False,
                'error': 'Student not assigned to any class'
            }, status=400)

        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(
            is_current=True, academic_year=current_academic_year).first()
        if not current_term:
            return Response({'success': True, 'data': [], 'message': 'No active term found'})

        slots = Timetable.objects.filter(
            class_id=student.current_class,
            academic_year=current_academic_year.year_code,
            term=current_term.term,
            is_active=True
        ).select_related('subject', 'teacher').order_by('day_of_week', 'period')

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        timetable_data = []
        for slot in slots:
            timetable_data.append({
                'day': slot.day_of_week,
                'day_name': days[slot.day_of_week - 1] if 1 <= slot.day_of_week <= 5 else 'Saturday',
                'period': slot.period,
                'subject': slot.subject.area_name if slot.subject else 'N/A',
                'teacher': f"{slot.teacher.first_name} {slot.teacher.last_name}" if slot.teacher else 'N/A',
                'room': slot.room or 'N/A',
                'start_time': slot.start_time if hasattr(slot, 'start_time') else None,
                'end_time': slot.end_time if hasattr(slot, 'end_time') else None
            })

        return Response({
            'success': True,
            'data': timetable_data,
            'class': student.current_class.class_name
        })
    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching timetable: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=500)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_published_exams(request):
    """
    Get recent published exams with this student's results.
    Returns each exam as a card so the dashboard can show all published exams,
    not just a per-subject aggregate of the current term.
    """
    try:
        student = Student.objects.get(user=request.user, archived=False)
        grade_level = get_cbc_grade_level(student)

        limit = int(request.query_params.get('limit', 10))

        # Get all published exams that have results for this student
        results_qs = (
            ExamResult.objects
            .filter(student=student, exam__status='published')
            .select_related('exam')
            .order_by('-exam__academic_year', '-exam__term', '-marked_at')
        )

        # Group by exam
        exam_map = {}
        for r in results_qs:
            eid = str(r.exam.id)
            if eid not in exam_map:
                exam_map[eid] = {
                    'exam': r.exam,
                    'subjects': []
                }
            pct = float(r.percentage) if r.percentage else 0
            code = r.grade
            valid_codes = {
                'EE', 'ME', 'AE', 'BE',
                'EE1', 'EE2', 'ME1', 'ME2',
                'AE1', 'AE2', 'BE1', 'BE2'
            }
            if not code or code.upper() not in valid_codes:
                if str(grade_level) in FOUR_POINT_LEVELS:
                    code = ('EE' if pct >= 90 else 'ME' if pct >= 75
                            else 'AE' if pct >= 58 else 'BE')
                else:
                    code = ('EE1' if pct >= 90 else 'EE2' if pct >= 75
                            else 'ME1' if pct >= 58 else 'ME2' if pct >= 41
                            else 'AE1' if pct >= 31 else 'AE2' if pct >= 21
                            else 'BE1' if pct >= 11 else 'BE2')
            points = grade_to_points_cbc(code, grade_level)
            exam_map[eid]['subjects'].append({
                'subject': r.subject,
                'percentage': round(pct, 2),
                'grade': code,
                'points': points,
                'remarks': r.remarks or '',
            })

        # Build response list, one entry per exam
        data = []
        for eid, entry in list(exam_map.items())[:limit]:
            exam = entry['exam']
            subjects = entry['subjects']
            total_pct = sum(s['percentage'] for s in subjects)
            total_pts = sum(s['points'] for s in subjects)
            count = len(subjects)
            avg_pct = round(total_pct / count, 2) if count else 0
            avg_pts = round(total_pts / count, 1) if count else 0
            overall_grade = points_to_grade_cbc(round(avg_pts), grade_level)

            data.append({
                'exam_id': eid,
                'exam_code': exam.exam_code,
                'exam_title': exam.title,
                'exam_type': exam.exam_type,
                'academic_year': exam.academic_year,
                'term': exam.term,
                'start_date': str(exam.start_date) if exam.start_date else None,
                'total_marks': exam.total_marks,
                'subjects': subjects,
                'subjects_count': count,
                'average_percentage': avg_pct,
                'overall_grade': overall_grade,
                'overall_points': avg_pts,
            })

        return Response({
            'success': True,
            'data': data,
            'count': len(data),
        })

    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student profile not found'}, status=404)
    except Exception as e:
        logger.exception("get_recent_published_exams error")
        return Response({'success': False, 'error': str(e)}, status=500)