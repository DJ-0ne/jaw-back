from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta
import logging

from cbe_app.models import Student, StudentFeeInvoice, FeeTransaction, StudentAttendance, DisciplineIncident, TermlySummary, Timetable
from cbe_app.serializers.student_serializers.student_serializers import (
    StudentProfileSerializer, FeeSummarySerializer, FeeTransactionSerializer,
    AttendanceRecordSerializer, DisciplineRecordSerializer,
    AcademicPerformanceSerializer, TimetableSlotSerializer
)

logger = logging.getLogger(__name__)

# ==================== STUDENT PROFILE ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_profile(request):
    """Get logged-in student's profile"""
    try:
        # Get student profile linked to the logged-in user
        student = Student.objects.select_related('user', 'current_class').get(user=request.user, archived=False)
        serializer = StudentProfileSerializer(student)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching student profile: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== FEE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_summary(request):
    """Get fee summary for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        
        # Get current academic year and term
        from cbe_app.models import AcademicYear, Term
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(is_current=True, academic_year=current_academic_year).first() if current_academic_year else None
        
        # Get all invoices for the student
        invoices = StudentFeeInvoice.objects.filter(student=student)
        
        total_fees = invoices.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = invoices.aggregate(total=Sum('amount_paid'))['total'] or 0
        balance = total_fees - total_paid
        
        # Calculate overdue amount
        today = timezone.now().date()
        overdue_invoices = invoices.filter(due_date__lt=today, balance_amount__gt=0)
        overdue_amount = overdue_invoices.aggregate(total=Sum('balance_amount'))['total'] or 0
        
        # Calculate overdue days
        overdue_days = 0
        if overdue_invoices.exists():
            oldest_due = overdue_invoices.order_by('due_date').first()
            if oldest_due:
                overdue_days = (today - oldest_due.due_date).days
        
        # Get recent transactions
        recent_transactions = FeeTransaction.objects.filter(
            student=student,
            status='Completed'
        ).order_by('-payment_date')[:5]
        
        recent_transactions_data = FeeTransactionSerializer(recent_transactions, many=True).data
        
        summary_data = {
            'total_fees': total_fees,
            'total_paid': total_paid,
            'balance': balance,
            'overdue_amount': overdue_amount,
            'overdue_days': overdue_days,
            'academic_year': current_academic_year.year_name if current_academic_year else 'N/A',
            'term': current_term.term if current_term else 'N/A',
            'recent_transactions': recent_transactions_data
        }
        
        serializer = FeeSummarySerializer(summary_data)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching fee summary: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_transactions(request):
    """Get all fee transactions for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        
        transactions = FeeTransaction.objects.filter(
            student=student,
            status='Completed'
        ).order_by('-payment_date')
        
        serializer = FeeTransactionSerializer(transactions, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching fee transactions: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== ATTENDANCE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_attendance(request):
    """Get all attendance records for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        
        # Get parameters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = request.query_params.get('limit')
        
        attendance_records = StudentAttendance.objects.filter(
            student=student
        ).select_related('session', 'session__subject').order_by('-session__session_date')
        
        if start_date:
            attendance_records = attendance_records.filter(session__session_date__gte=start_date)
        if end_date:
            attendance_records = attendance_records.filter(session__session_date__lte=end_date)
        if limit:
            attendance_records = attendance_records[:int(limit)]
        
        serializer = AttendanceRecordSerializer(attendance_records, many=True)
        
        # Calculate summary
        total = attendance_records.count()
        present = attendance_records.filter(attendance_status='Present').count()
        absent = attendance_records.filter(attendance_status='Absent').count()
        late = attendance_records.filter(attendance_status='Late').count()
        
        return Response({
            'success': True,
            'data': serializer.data,
            'summary': {
                'total': total,
                'present': present,
                'absent': absent,
                'late': late,
                'attendance_rate': round((present / total * 100), 2) if total > 0 else 0
            }
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching attendance: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_attendance(request):
    """Get recent attendance records for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        limit = request.query_params.get('limit', 10)
        
        attendance_records = StudentAttendance.objects.filter(
            student=student
        ).select_related('session', 'session__subject').order_by('-session__session_date')[:int(limit)]
        
        serializer = AttendanceRecordSerializer(attendance_records, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching recent attendance: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== DISCIPLINE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_records(request):
    """Get discipline records for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        
        incidents = DisciplineIncident.objects.filter(
            student=student
        ).select_related('category').order_by('-incident_date')
        
        serializer = DisciplineRecordSerializer(incidents, many=True)
        
        # Calculate summary
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
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching discipline records: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== ACADEMIC PERFORMANCE ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_academic_performance(request):
    """Get academic performance for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        
        term = request.query_params.get('term')
        academic_year = request.query_params.get('academic_year')
        
        # Get termly summaries
        summaries = TermlySummary.objects.filter(student=student)
        
        if term:
            summaries = summaries.filter(term__term=term)
        if academic_year:
            summaries = summaries.filter(term__academic_year__year_code=academic_year)
        
        # Group by term and learning area
        performance_data = []
        
        for summary in summaries.select_related('term', 'term__academic_year', 'learning_area'):
            performance_data.append({
                'learning_area': summary.learning_area.area_name,
                'score': float(summary.final_internal_value) * 25,  # Convert to percentage
                'rating': summary.final_rating,
                'term': summary.term.term,
                'academic_year': summary.term.academic_year.year_name
            })
        
        return Response({
            'success': True,
            'data': performance_data
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching academic performance: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_performance(request):
    """Get current term academic performance for logged-in student"""
    try:
        from cbe_app.models import Term, AcademicYear
        
        student = Student.objects.get(user=request.user, archived=False)
        
        # Get current academic year and term
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(is_current=True, academic_year=current_academic_year).first()
        
        if not current_term:
            return Response({
                'success': True,
                'data': [],
                'message': 'No active term found'
            }, status=status.HTTP_200_OK)
        
        # Get termly summaries for current term
        summaries = TermlySummary.objects.filter(
            student=student,
            term=current_term
        ).select_related('learning_area').order_by('learning_area__area_name')
        
        performance_data = []
        total_score = 0
        
        for summary in summaries:
            score = float(summary.final_internal_value) * 25
            total_score += score
            performance_data.append({
                'learning_area': summary.learning_area.area_name,
                'score': round(score, 2),
                'grade': summary.final_rating,
                'rating': summary.final_rating,
                'teacher_comment': summary.teacher_comment
            })
        
        # Calculate overall performance
        overall_score = round(total_score / len(performance_data), 2) if performance_data else 0
        overall_grade = get_grade_from_score(overall_score)
        
        return Response({
            'success': True,
            'data': performance_data,
            'summary': {
                'term': current_term.term,
                'academic_year': current_academic_year.year_name if current_academic_year else 'N/A',
                'overall_score': overall_score,
                'overall_grade': overall_grade,
                'subjects_count': len(performance_data)
            }
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching current performance: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_grade_from_score(score):
    """Helper function to get grade from percentage score"""
    if score >= 80:
        return 'Exceeding'
    elif score >= 60:
        return 'Meeting'
    elif score >= 40:
        return 'Approaching'
    else:
        return 'Below'


# ==================== EXAM RESULTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exam_results(request):
    """Get exam results for logged-in student"""
    try:
        student = Student.objects.get(user=request.user, archived=False)
        
        # Get summative ratings
        from cbe_app.models import SummativeRating, SummativeAssessment
        
        term = request.query_params.get('term')
        assessment_type = request.query_params.get('assessment_type')
        
        ratings = SummativeRating.objects.filter(student=student).select_related(
            'assessment', 'assessment__learning_area', 'assessment__assessment_window',
            'competency', 'competency__substrand__strand__learning_area'
        )
        
        if term:
            ratings = ratings.filter(assessment__assessment_window__term__term=term)
        if assessment_type:
            ratings = ratings.filter(assessment__assessment_window__assessment_type=assessment_type)
        
        # Group by learning area and assessment
        results = []
        for rating in ratings:
            results.append({
                'learning_area': rating.assessment.learning_area.area_name,
                'assessment_type': rating.assessment.assessment_window.assessment_type,
                'competency': rating.competency.competency_code,
                'rating': rating.rating,
                'score': rating.internal_value * 25,
                'teacher_comment': rating.teacher_comment,
                'date': rating.rated_at.date()
            })
        
        return Response({
            'success': True,
            'data': results
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching exam results: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get current academic year and term
        from cbe_app.models import AcademicYear, Term
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(is_current=True, academic_year=current_academic_year).first()
        
        if not current_term:
            return Response({
                'success': True,
                'data': [],
                'message': 'No active term found'
            }, status=status.HTTP_200_OK)
        
        # Get timetable for the student's class
        timetable_slots = Timetable.objects.filter(
            class_id=student.current_class,
            academic_year=current_academic_year.year_code,
            term=current_term.term,
            is_active=True
        ).select_related('subject', 'teacher').order_by('day_of_week', 'period')
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        timetable_data = []
        
        for slot in timetable_slots:
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
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching timetable: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)