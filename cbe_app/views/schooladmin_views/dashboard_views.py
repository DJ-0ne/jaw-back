from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import logging

from cbe_app.models import (
    Student, Class, FeeTransaction, AcademicYear, Term
)

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_principal_dashboard_stats(request):
    """
    Returns key stats for the principal dashboard:
    total students, total staff, monthly revenue, attendance rate.
    """
    try:
        total_students = Student.objects.filter(archived=False, status='Active').count()

        # Staff count using the correct 'status' field
        staff_count = 0
        try:
            from cbe_app.models import Staff
            staff_count = Staff.objects.filter(status='Active').count()
        except ImportError:
            # Fallback if Staff model doesn't exist
            from cbe_app.models import User
            staff_count = User.objects.filter(
                role__in=['teacher', 'staff'], is_active=True
            ).count()

        # Monthly revenue
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_revenue = FeeTransaction.objects.filter(
            status='Completed',
            payment_date__gte=month_start
        ).aggregate(total=Sum('amount_kes'))['total'] or 0

        # Attendance rate (if the Attendance model exists)
        attendance_rate = 0.0
        try:
            from cbe_app.models import Attendance
            thirty_days_ago = now - timedelta(days=30)
            att = Attendance.objects.filter(date__gte=thirty_days_ago).aggregate(
                present=Count('id', filter=Q(status='Present')),
                total=Count('id')
            )
            attendance_rate = round(
                (att['present'] / att['total'] * 100) if att['total'] else 0, 1
            )
        except ImportError:
            attendance_rate = 0.0

        return Response({
            'success': True,
            'data': {
                'total_students': total_students,
                'total_staff': staff_count,
                'monthly_revenue': float(monthly_revenue),
                'attendance_rate': attendance_rate,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_principal_dashboard_performance(request):
    """
    Returns monthly revenue trend for the last 6 months
    to power the Performance Trends line chart.
    """
    try:
        now = timezone.now()
        months_data = []

        for i in range(5, -1, -1):
            year = now.year
            month = now.month - i
            while month <= 0:
                month += 12
                year -= 1

            month_start = now.replace(year=year, month=month, day=1,
                                      hour=0, minute=0, second=0, microsecond=0)
            if month == 12:
                month_end = month_start.replace(year=year + 1, month=1)
            else:
                month_end = month_start.replace(month=month + 1)

            revenue = FeeTransaction.objects.filter(
                status='Completed',
                payment_date__gte=month_start,
                payment_date__lt=month_end
            ).aggregate(total=Sum('amount_kes'))['total'] or 0

            students_active = Student.objects.filter(
                archived=False, status='Active'
            ).count()

            months_data.append({
                'month': month_start.strftime('%b'),
                'revenue': float(revenue),
                'students': students_active,
            })

        return Response({'success': True, 'data': months_data}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Dashboard performance error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_principal_dashboard_activities(request):
    """
    Returns the 10 most recent completed fee transactions as activity feed.
    """
    try:
        transactions = FeeTransaction.objects.filter(
            status='Completed'
        ).select_related('student').order_by('-payment_date')[:10]

        activities = []
        for t in transactions:
            activities.append({
                'id': str(t.id),
                'action': f"Fee payment of KES {t.amount_kes:,.0f} received from "
                          f"{t.student.first_name} {t.student.last_name}",
                'time': t.payment_date.strftime('%d %b %Y %H:%M'),
                'type': 'finance',
            })

        return Response({'success': True, 'data': activities}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Dashboard activities error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)