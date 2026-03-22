from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta
import logging
import uuid
from decimal import Decimal

from cbe_app.models import (
    Student, Class, FeeStructure, FeeCategory, StudentFeeInvoice,
    FeeTransaction, InvoiceItem, AcademicYear, Term, AuditLog, StudentCredit
)
from cbe_app.serializers.bursar_serializers.bursar_payment_serializers import (
    StudentSerializer, ClassSerializer, FeeTransactionSerializer,
    StudentFeeInvoiceSerializer
)

logger = logging.getLogger(__name__)

# ==================== TRANSACTION RECORDS VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transactions_list(request):
    """Get all transactions with filtering"""
    try:
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_filter = request.query_params.get('status')
        payment_mode = request.query_params.get('payment_mode')
        search = request.query_params.get('search')
        limit = request.query_params.get('limit', 100)
        
        queryset = FeeTransaction.objects.filter(
            status='Completed'
        ).select_related('student', 'collected_by', 'verified_by')
        
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)
        
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
        
        if payment_mode and payment_mode != 'all':
            queryset = queryset.filter(payment_mode=payment_mode)
        
        if search:
            queryset = queryset.filter(
                Q(transaction_no__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(student__admission_no__icontains=search)
            )
        
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            pass
        
        # Prepare data with additional fields
        transactions_data = []
        for t in queryset:
            transactions_data.append({
                'id': t.id,
                'transaction_no': t.transaction_no,
                'amount_kes': t.amount_kes,
                'payment_mode': t.payment_mode,
                'payment_reference': t.payment_reference,
                'payment_date': t.payment_date,
                'status': t.status,
                'first_name': t.student.first_name,
                'last_name': t.student.last_name,
                'admission_no': t.student.admission_no,
                'class_name': t.student.current_class.class_name if t.student.current_class else None,
                'collected_by_name': f"{t.collected_by.first_name} {t.collected_by.last_name}".strip() if t.collected_by else None,
                'verified_by_name': f"{t.verified_by.first_name} {t.verified_by.last_name}".strip() if t.verified_by else None,
                'verified_at': t.verified_at,
                'created_at': t.created_at
            })
        
        return Response({
            'success': True,
            'data': transactions_data,
            'count': len(transactions_data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching transactions list: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transaction_stats(request):
    """Get transaction statistics"""
    try:
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        queryset = FeeTransaction.objects.filter(status='Completed')
        
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)
        
        total_collected = queryset.aggregate(total=Sum('amount_kes'))['total'] or 0
        total_transactions = queryset.count()
        unique_students = queryset.values('student_id').distinct().count()
        
        # Average amount
        average_amount = total_collected / total_transactions if total_transactions > 0 else 0
        
        # Completed count
        completed_count = queryset.filter(status='Completed').count()
        
        # Group by payment mode
        by_payment_mode = queryset.values('payment_mode').annotate(
            count=Count('id'),
            total=Sum('amount_kes')
        )
        
        return Response({
            'success': True,
            'data': {
                'total_collected': total_collected,
                'total_transactions': total_transactions,
                'unique_students': unique_students,
                'average_amount': average_amount,
                'completed_count': completed_count,
                'by_payment_mode': list(by_payment_mode)
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching transaction stats: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transaction_detail(request, transaction_id):
    """Get detailed transaction information"""
    try:
        transaction = FeeTransaction.objects.select_related(
            'student', 'collected_by', 'verified_by', 'invoice'
        ).get(id=transaction_id)
        
        # Get invoice details if available
        invoice_data = None
        if transaction.invoice:
            invoice_data = {
                'invoice_no': transaction.invoice.invoice_no,
                'academic_year': transaction.invoice.academic_year,
                'term': transaction.invoice.term,
                'total_amount': transaction.invoice.total_amount,
                'amount_paid': transaction.invoice.amount_paid,
                'balance': transaction.invoice.balance_amount,
                'status': transaction.invoice.status,
                'payment_status': transaction.invoice.payment_status
            }
        
        # Get credit details if any
        credits = StudentCredit.objects.filter(
            original_transaction=transaction
        ).values('id', 'credit_amount', 'credit_type', 'is_utilized')
        
        transaction_data = {
            'id': transaction.id,
            'transaction_no': transaction.transaction_no,
            'amount': transaction.amount,
            'amount_kes': transaction.amount_kes,
            'currency': transaction.currency,
            'exchange_rate': transaction.exchange_rate,
            'payment_mode': transaction.payment_mode,
            'payment_reference': transaction.payment_reference,
            'payment_date': transaction.payment_date,
            'status': transaction.status,
            'bank_name': transaction.bank_name,
            'cheque_no': transaction.cheque_no,
            'mobile_money_no': transaction.mobile_money_no,
            'first_name': transaction.student.first_name,
            'last_name': transaction.student.last_name,
            'admission_no': transaction.student.admission_no,
            'class_name': transaction.student.current_class.class_name if transaction.student.current_class else None,
            'guardian_name': transaction.student.guardian_name,
            'guardian_phone': transaction.student.guardian_phone,
            'collected_by_name': f"{transaction.collected_by.first_name} {transaction.collected_by.last_name}".strip() if transaction.collected_by else None,
            'verified_by_name': f"{transaction.verified_by.first_name} {transaction.verified_by.last_name}".strip() if transaction.verified_by else None,
            'verified_at': transaction.verified_at,
            'created_at': transaction.created_at,
            'invoice': invoice_data,
            'credits': list(credits)
        }
        
        return Response({
            'success': True,
            'data': transaction_data
        }, status=status.HTTP_200_OK)
    
    except FeeTransaction.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Transaction not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching transaction detail: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_transactions(request):
    """Export transactions to CSV"""
    try:
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_filter = request.query_params.get('status')
        payment_mode = request.query_params.get('payment_mode')
        format_type = request.query_params.get('format', 'csv')
        
        queryset = FeeTransaction.objects.filter(
            status='Completed'
        ).select_related('student')
        
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
        if payment_mode and payment_mode != 'all':
            queryset = queryset.filter(payment_mode=payment_mode)
        
        export_data = []
        for t in queryset:
            export_data.append({
                'transaction_no': t.transaction_no,
                'student_name': f"{t.student.first_name} {t.student.last_name}",
                'admission_no': t.student.admission_no,
                'amount': t.amount_kes,
                'payment_date': t.payment_date.strftime('%Y-%m-%d %H:%M:%S'),
                'payment_mode': t.payment_mode,
                'reference': t.payment_reference or '',
                'status': t.status
            })
        
        if format_type == 'csv':
            import csv
            from django.http import HttpResponse
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="transactions_{datetime.now().strftime("%Y%m%d")}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Transaction No', 'Student Name', 'Admission No', 'Amount (KES)', 'Date', 'Payment Method', 'Reference', 'Status'])
            
            for item in export_data:
                writer.writerow([
                    item['transaction_no'],
                    item['student_name'],
                    item['admission_no'],
                    item['amount'],
                    item['payment_date'],
                    item['payment_mode'],
                    item['reference'],
                    item['status']
                ])
            
            return response
        
        return Response({
            'success': True,
            'data': export_data,
            'count': len(export_data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error exporting transactions: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_payment_methods_stats(request):
    """Get payment methods statistics"""
    try:
        stats = FeeTransaction.objects.filter(
            status='Completed'
        ).values('payment_mode').annotate(
            total_amount=Sum('amount_kes'),
            count=Count('id')
        ).order_by('-total_amount')
        
        return Response({
            'success': True,
            'data': list(stats)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching payment methods stats: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)