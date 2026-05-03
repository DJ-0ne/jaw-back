import logging
from datetime import datetime
from django.utils import timezone
from django.db.models import Sum, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal

from cbe_app.models import (
    Student, StudentFeeInvoice, FeeTransaction, FeeStructure,
    AcademicYear, Term, InvoiceItem
)
from cbe_app.serializers.student_serializers.student_fee_serializers import (
    StudentInvoiceSerializer, FeeTransactionSerializer,
    FeeStructureItemSerializer, FeeSummarySerializer
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


def get_current_academic_year_and_term():
    """Get current academic year and term"""
    today = timezone.now().date()
    current_academic_year = AcademicYear.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).first()
    
    if not current_academic_year:
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
    
    current_term = None
    if current_academic_year:
        current_term = Term.objects.filter(
            academic_year=current_academic_year,
            start_date__lte=today, end_date__gte=today
        ).first()
        if not current_term:
            current_term = Term.objects.filter(
                academic_year=current_academic_year, is_current=True
            ).first()
    return current_academic_year, current_term


def get_or_create_current_invoice(student, request=None):
    """Auto-create invoice based on latest fee structures if it doesn't exist"""
    academic_year, term = get_current_academic_year_and_term()
    if not academic_year or not term or not student.current_class:
        return None

    term_value = term.term
    term_number = term_value.replace("Term ", "").strip()

    # Check existing invoice
    existing_invoice = StudentFeeInvoice.objects.filter(
        student=student,
        academic_year=academic_year.year_code,
    ).filter(
        Q(term=term_value) | Q(term=term_number)
    ).first()

    if existing_invoice:
        return existing_invoice

    # Get latest fee structures
    fee_structures = FeeStructure.objects.filter(
        class_id=student.current_class,
        is_active=True,
    ).filter(
        Q(academic_year=academic_year.year_code) |
        Q(academic_year=academic_year.year_code.replace("-", "/")) |
        Q(academic_year=academic_year.year_code.split("-")[0])
    ).filter(
        Q(term=term_value) |
        Q(term=term_number) |
        Q(term=f"Term {term_number}")
    ).select_related('category')

    if not fee_structures.exists():
        logger.warning(f"No fee structure found for {student.admission_no}")
        return None

    total_amount = sum(fs.amount for fs in fee_structures)

    invoice = StudentFeeInvoice.objects.create(
        student=student,
        academic_year=academic_year.year_code,
        term=term.term,
        invoice_date=timezone.now().date(),
        due_date=timezone.now().date() + timezone.timedelta(days=30),
        subtotal=total_amount,
        discount_amount=Decimal('0'),
        late_fee_amount=Decimal('0'),
        total_amount=total_amount,
        amount_paid=Decimal('0'),
        balance_amount=total_amount,
        status='Pending',
        payment_status='Unpaid',
        created_by=request.user if request else None,
    )

    for fs in fee_structures:
        InvoiceItem.objects.create(
            invoice=invoice,
            fee_structure=fs,
            description=fs.category.category_name,
            quantity=1,
            unit_price=fs.amount,
            amount=fs.amount,
            discount_percentage=Decimal('0'),
            discount_amount=Decimal('0'),
            net_amount=fs.amount,
        )

    logger.info(f"Auto-generated invoice for student {student.admission_no} - Amount: {total_amount}")
    return invoice


# ==================== FEE SUMMARY ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_summary(request):
    """Get fee summary for logged-in student - NOW DYNAMIC"""
    try:
        student = get_student(request.user)
        if not student:
            return Response({
                'success': False,
                'error': 'Student profile not found. Please contact the registrar.'
            }, status=status.HTTP_404_NOT_FOUND)

        academic_year, term = get_current_academic_year_and_term()
        invoice = get_or_create_current_invoice(student, request)

        # Always calculate from latest fee structures
        fee_structures = FeeStructure.objects.filter(
            class_id=student.current_class,
            is_active=True,
        ).filter(
            Q(academic_year=academic_year.year_code) |
            Q(academic_year=academic_year.year_code.replace("-", "/")) |
            Q(academic_year=academic_year.year_code.split("-")[0])
        ).filter(
            Q(term=term.term) | Q(term=term.term.replace("Term ", "")) if term else Q()
        ) if academic_year and term else FeeStructure.objects.none()

        total_fees = sum(fs.amount for fs in fee_structures) if fee_structures.exists() else 0
        total_paid = invoice.amount_paid if invoice else Decimal('0')
        balance = Decimal(total_fees) - total_paid

        # Overdue calculation
        today = timezone.now().date()
        overdue_amount = Decimal('0')
        overdue_days = 0

        if invoice and invoice.due_date and invoice.balance_amount > 0 and invoice.due_date < today:
            overdue_amount = invoice.balance_amount
            overdue_days = (today - invoice.due_date).days

        # Payment status
        if balance <= 0:
            payment_status = 'Fully Paid'
        elif total_paid > 0:
            payment_status = 'Partially Paid'
        else:
            payment_status = 'Unpaid'

        summary_data = {
            'total_fees': float(total_fees),
            'total_paid': float(total_paid),
            'balance': float(balance),
            'overdue_amount': float(overdue_amount),
            'overdue_days': overdue_days,
            'academic_year': academic_year.year_name if academic_year else 'N/A',
            'term': term.term if term else 'N/A',
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

        # Ensure current term invoice exists
        get_or_create_current_invoice(student, request)

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
    """Get fee structure for student's class - always reflects latest"""
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

        academic_year, term = get_current_academic_year_and_term()
        if not term:
            return Response({
                'success': True,
                'data': [],
                'message': 'No active term found'
            }, status=status.HTTP_200_OK)

        fee_structures = FeeStructure.objects.filter(
            class_id=student.current_class,
            is_active=True,
        ).filter(
            Q(academic_year=academic_year.year_code) |
            Q(academic_year=academic_year.year_code.replace("-", "/")) |
            Q(academic_year=academic_year.year_code.split("-")[0])
        ).filter(
            Q(term=term.term) |
            Q(term=term.term.replace("Term ", ""))
        ).select_related('category')

        structure_data = []
        for fs in fee_structures:
            structure_data.append({
                'category_name': fs.category.category_name,
                'category_code': fs.category.category_code,
                'description': fs.category.description or fs.category.category_name,
                'amount': float(fs.amount),
                'frequency': fs.category.frequency,
                'due_date': fs.due_date,
                'late_fee_percentage': float(fs.late_fee_percentage) if fs.late_fee_percentage else 0,
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