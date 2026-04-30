from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Count, Q
from django.utils import timezone
import logging

from cbe_app.models import (
    Student, Class, FeeTransaction, StudentFeeInvoice,
    AcademicYear, Term
)

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_finance_overview(request):
    """Top-level financial KPIs."""
    try:
        total_revenue = FeeTransaction.objects.filter(
            status='Completed'
        ).aggregate(total=Sum('amount_kes'))['total'] or 0

        by_mode = FeeTransaction.objects.filter(
            status='Completed'
        ).values('payment_mode').annotate(total=Sum('amount_kes'))

        return Response({
            'success': True,
            'data': {
                'total_revenue': float(total_revenue),
                'revenue_by_mode': list(by_mode),
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Finance overview error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_finance_revenue_trend(request):
    """Monthly revenue breakdown for the last 6 months."""
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
            next_month = month + 1
            next_year = year
            if next_month > 12:
                next_month = 1
                next_year += 1
            month_end = month_start.replace(year=next_year, month=next_month)

            revenue = FeeTransaction.objects.filter(
                status='Completed',
                payment_date__gte=month_start,
                payment_date__lt=month_end
            ).aggregate(total=Sum('amount_kes'))['total'] or 0

            months_data.append({
                'month': month_start.strftime('%b'),
                'tuition': float(revenue),
            })

        return Response({'success': True, 'data': months_data}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Finance revenue trend error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_students_fee_summary(request):
    """
    Lists active students with fee summary and per‑term breakdown.
    NOTE: StudentFeeInvoice.term is a CharField, not a FK – grouping uses the string directly.
    """
    try:
        search = request.query_params.get('search', '').strip()
        class_id = request.query_params.get('class_id')
        term_id = request.query_params.get('term_id')      # will be ignored if term field is not FK
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))

        students_qs = Student.objects.filter(
            archived=False, status='Active'
        ).select_related('current_class').order_by('current_class__class_name', 'last_name')

        if search:
            students_qs = students_qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(admission_no__icontains=search)
            )

        if class_id:
            students_qs = students_qs.filter(current_class_id=class_id)

        # term filtering is not possible via FK → we skip it (or you could filter by term name after lookup)
        # but that would be fragile; so we ignore term_id entirely.
        if term_id:
            logger.warning(f"Term filter ignored – StudentFeeInvoice.term is not a FK. term_id={term_id}")

        total_count = students_qs.count()
        start = (page - 1) * page_size
        students_page = students_qs[start:start + page_size]

        results = []
        for student in students_page:
            invoices = StudentFeeInvoice.objects.filter(student=student)
            total_billed = invoices.aggregate(b=Sum('total_amount'))['b'] or 0
            total_paid = invoices.aggregate(p=Sum('amount_paid'))['p'] or 0
            balance = float(total_billed) - float(total_paid)

            # Per‑term breakdown – group by the CharField `term`
            term_breakdown = []
            try:
                breakdown_qs = invoices.values('term').annotate(
                    billed=Sum('total_amount'),
                    paid=Sum('amount_paid')
                ).order_by('term')

                term_breakdown = [
                    {
                        'term_id': None,                         # no FK available
                        'term_name': item['term'] or 'N/A',
                        'billed': float(item['billed'] or 0),
                        'paid': float(item['paid'] or 0),
                    }
                    for item in breakdown_qs
                ]
            except Exception as e:
                logger.warning(f"Term breakdown failed for student {student.id}: {e}")

            results.append({
                'id': str(student.id),
                'admission_no': student.admission_no,
                'name': f"{student.first_name} {student.last_name}",
                'grade': student.current_class.class_name if student.current_class else '—',
                'class_code': student.current_class.class_code if student.current_class else '—',
                'total_billed': float(total_billed),
                'total_paid': float(total_paid),
                'balance': balance,
                'payment_status': (
                    'Paid' if balance <= 0
                    else 'Partial' if total_paid > 0
                    else 'Unpaid'
                ),
                'term_breakdown': term_breakdown,
            })

        # Terms list for filter dropdown – still uses the Term model
        terms = list(
            Term.objects.values('id', 'term').order_by('term')
        )
        terms = [{'id': str(t['id']), 'term_name': t['term']} for t in terms]

        # Classes list for filter dropdown
        classes = list(
            Class.objects.filter(is_active=True).values('id', 'class_name', 'class_code')
        )
        classes = [
            {'id': str(c['id']), 'class_name': c['class_name'], 'class_code': c['class_code']}
            for c in classes
        ]

        return Response({
            'success': True,
            'data': results,
            'meta': {
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size,
            },
            'filters': {
                'terms': terms,
                'classes': classes,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Students fee summary error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_transactions(request):
    """20 most recent completed fee transactions."""
    try:
        transactions = FeeTransaction.objects.filter(
            status='Completed'
        ).select_related('student', 'collected_by').order_by('-payment_date')[:20]

        data = []
        for t in transactions:
            data.append({
                'id': str(t.id),
                'transaction_no': t.transaction_no,
                'description': f"Fee payment – {t.student.first_name} {t.student.last_name}",
                'amount': float(t.amount_kes),
                'type': 'income',
                'date': t.payment_date.strftime('%Y-%m-%d'),
                'status': t.status,
                'payment_mode': t.payment_mode,
            })

        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Recent transactions error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)