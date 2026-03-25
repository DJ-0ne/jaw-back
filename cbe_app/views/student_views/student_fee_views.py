import logging
from datetime import datetime
from django.utils import timezone
from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from cbe_app.models import Student, StudentFeeInvoice, FeeTransaction, FeeStructure, AcademicYear, Term
from cbe_app.serializers.student_serializers.student_fee_serializers import (
    StudentInvoiceSerializer, FeeTransactionSerializer, FeeStructureItemSerializer,
    FeeSummarySerializer
)

logger = logging.getLogger(__name__)


def get_student(user):
    """Get student profile from user"""
    try:
        return Student.objects.get(user=user, archived=False)
    except Student.DoesNotExist:
        if user.email:
            try:
                return Student.objects.get(email=user.email, archived=False)
            except Student.DoesNotExist:
                pass
    return None


# ==================== FEE SUMMARY ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_summary(request):
    """Get fee summary for logged-in student"""
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found. Please contact the registrar.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get current academic year and term
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
        
        # Determine payment status
        if balance <= 0:
            payment_status = 'Fully Paid'
        elif total_paid > 0:
            payment_status = 'Partially Paid'
        else:
            payment_status = 'Unpaid'
        
        summary_data = {
            'total_fees': total_fees,
            'total_paid': total_paid,
            'balance': balance,
            'overdue_amount': overdue_amount,
            'overdue_days': overdue_days,
            'academic_year': current_academic_year.year_name if current_academic_year else 'N/A',
            'term': current_term.term if current_term else 'N/A',
            'payment_status': payment_status
        }
        
        serializer = FeeSummarySerializer(summary_data)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee summary: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== INVOICES ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_invoices(request):
    """Get all invoices for logged-in student"""
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        invoices = StudentFeeInvoice.objects.filter(student=student).order_by('-invoice_date')
        
        serializer = StudentInvoiceSerializer(invoices, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching invoices: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_invoice_detail(request, invoice_id):
    """Get specific invoice details"""
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        invoice = StudentFeeInvoice.objects.get(id=invoice_id, student=student)
        
        serializer = StudentInvoiceSerializer(invoice)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except StudentFeeInvoice.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Invoice not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching invoice detail: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== TRANSACTIONS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transactions(request):
    """Get all transactions for logged-in student"""
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        transactions = FeeTransaction.objects.filter(
            student=student,
            status='Completed'
        ).order_by('-payment_date')
        
        serializer = FeeTransactionSerializer(transactions, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching transactions: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== FEE STRUCTURE ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_structure(request):
    """Get fee structure for student's class"""
    try:
        student = get_student(request.user)
        
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not student.current_class:
            return Response({
                'success': False,
                'error': 'Student not assigned to any class'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get current academic year and term
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(is_current=True, academic_year=current_academic_year).first() if current_academic_year else None
        
        if not current_term:
            return Response({
                'success': True,
                'data': [],
                'message': 'No active term found'
            }, status=status.HTTP_200_OK)
        
        # Get fee structures for student's class
        fee_structures = FeeStructure.objects.filter(
            academic_year=current_academic_year.year_code,
            term=current_term.term,
            class_id=student.current_class,
            is_active=True
        ).select_related('category')
        
        structure_data = []
        for fs in fee_structures:
            structure_data.append({
                'category_name': fs.category.category_name,
                'category_code': fs.category.category_code,
                'description': fs.category.description or fs.category.category_name,
                'amount': fs.amount,
                'frequency': fs.category.frequency,
                'due_date': fs.due_date,
                'late_fee_percentage': fs.late_fee_percentage,
                'is_mandatory': fs.category.is_mandatory
            })
        
        serializer = FeeStructureItemSerializer(structure_data, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee structure: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)