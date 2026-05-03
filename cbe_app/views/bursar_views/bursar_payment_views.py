# cbe_app/views/bursar_views/bursar_views.py

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


def get_current_academic_year_and_term():
    """Get current academic year and term based on date"""
    today = timezone.now().date()
    
    current_academic_year = AcademicYear.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).first()
    
    if not current_academic_year:
        current_academic_year = AcademicYear.objects.filter(is_current=True).first()
    
    current_term = None
    if current_academic_year:
        current_term = Term.objects.filter(
            academic_year=current_academic_year,
            start_date__lte=today,
            end_date__gte=today
        ).first()
        
        if not current_term:
            current_term = Term.objects.filter(
                academic_year=current_academic_year,
                is_current=True
            ).first()
    
    return current_academic_year, current_term


def create_audit_log(request, action, model_name, record_id, old_values=None, new_values=None):
    """Create audit log entry"""
    try:
        AuditLog.objects.create(
            event_type=action,
            user=request.user,
            username=request.user.username,
            user_role=request.user.role,
            table_name=model_name,
            record_id=record_id,
            operation='UPDATE' if old_values else 'INSERT',
            old_values=old_values,
            new_values=new_values,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            endpoint=request.path,
            http_method=request.method
        )
    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")


from django.db.models import Q

def generate_invoice_for_student(student, academic_year, term, request=None, fallback_amount=None):
    try:
        term_value = term.term
        term_number = term_value.replace("Term ", "").strip()
        term_padded = f"Term {term_number}"

        year_code = academic_year.year_code
        year_slash = year_code.replace("-", "/")
        year_short = year_code.split("-")[0]

        existing_invoice = StudentFeeInvoice.objects.filter(
            student=student,
            academic_year=year_code,
        ).filter(
            Q(term=term_value) | Q(term=term_number)
        ).first()

        if existing_invoice:
            return existing_invoice

        fee_structures = FeeStructure.objects.filter(
            class_id=student.current_class,
            is_active=True,
        ).filter(
            Q(academic_year=year_code) |
            Q(academic_year=year_slash) |
            Q(academic_year=year_short)
        ).filter(
            Q(term=term_value) |
            Q(term=term_number) |
            Q(term=term_padded)
        ).select_related('category')

        logger.info(
            f"[invoice] student={student.admission_no} "
            f"class={student.current_class} "
            f"year_variants=[{year_code},{year_slash},{year_short}] "
            f"term_variants=[{term_value},{term_number}] "
            f"fee_structures_count={fee_structures.count()}"
        )
        sample = FeeStructure.objects.filter(
            class_id=student.current_class
        ).values('academic_year', 'term', 'is_active', 'amount')[:10]
        logger.info(f"[invoice] DB sample for class {student.current_class}: {list(sample)}")

        if not fee_structures.exists():
            if fallback_amount is not None:
                fallback_decimal = Decimal(str(fallback_amount))
                invoice = StudentFeeInvoice.objects.create(
                    student=student,
                    academic_year=year_code,
                    term=term.term,
                    invoice_date=timezone.now().date(),
                    due_date=timezone.now().date() + timedelta(days=30),
                    subtotal=fallback_decimal,
                    discount_amount=Decimal('0'),
                    late_fee_amount=Decimal('0'),
                    total_amount=fallback_decimal,
                    amount_paid=Decimal('0'),
                    balance_amount=fallback_decimal,
                    status='Pending',
                    payment_status='Unpaid',
                    created_by=request.user if request else None,
                )
                return invoice

            logger.warning(
                f"No fee structure found for class={student.current_class}, "
                f"academic_year={year_code}, term={term_value}"
            )
            return None

        total_amount = sum(fs.amount for fs in fee_structures)

        invoice = StudentFeeInvoice.objects.create(
            student=student,
            academic_year=year_code,
            term=term.term,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
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

        return invoice

    except Exception as e:
        logger.error(f"Error generating invoice: {str(e)}")
        return None

 # Add to bursar_views.py

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recalculate_invoice(request, student_id):
    try:
        student = Student.objects.get(id=student_id)
        academic_year, term = get_current_academic_year_and_term()

        if not academic_year or not term:
            return Response({'success': False, 'error': 'No active academic year or term'}, status=status.HTTP_400_BAD_REQUEST)

        term_value = term.term
        term_number = term_value.replace("Term ", "").strip()
        year_code = academic_year.year_code
        year_slash = year_code.replace("-", "/")
        year_short = year_code.split("-")[0]

        invoice = StudentFeeInvoice.objects.filter(
            student=student,
            academic_year=year_code,
        ).filter(
            Q(term=term_value) | Q(term=term_number)
        ).first()

        if not invoice:
            return Response({'success': False, 'error': 'No invoice found for current term'}, status=status.HTTP_404_NOT_FOUND)

        fee_structures = FeeStructure.objects.filter(
            class_id=student.current_class,
            is_active=True,
        ).filter(
            Q(academic_year=year_code) | Q(academic_year=year_slash) | Q(academic_year=year_short)
        ).filter(
            Q(term=term_value) | Q(term=term_number) | Q(term=f"Term {term_number}")
        ).select_related('category')

        if not fee_structures.exists():
            return Response({'success': False, 'error': 'No fee structures found'}, status=status.HTTP_400_BAD_REQUEST)

        new_total = sum(fs.amount for fs in fee_structures)
        old_total = invoice.total_amount
        amount_changed = new_total != old_total

        # Only write to DB if something actually changed
        if amount_changed:
            with transaction.atomic():
                invoice.items.all().delete()
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

                invoice.subtotal = new_total
                invoice.total_amount = new_total
                invoice.balance_amount = new_total - invoice.amount_paid

                if invoice.balance_amount <= Decimal('0'):
                    invoice.status = 'Paid'
                    invoice.payment_status = 'Fully Paid'
                    invoice.balance_amount = Decimal('0')
                elif invoice.amount_paid > Decimal('0'):
                    invoice.status = 'Partial'
                    invoice.payment_status = 'Partially Paid'
                else:
                    invoice.status = 'Pending'
                    invoice.payment_status = 'Unpaid'

                invoice.save()
                logger.info(f"Invoice recalculated for {student.admission_no}: {old_total} -> {new_total}")

        return Response({
            'success': True,
            'amount_changed': amount_changed,
            'data': StudentFeeInvoiceSerializer(invoice).data,
        }, status=status.HTTP_200_OK)

    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error recalculating invoice: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
def get_student_credit_balance(student):
    """Get student's credit balance from previous excess payments"""
    try:
        credit_total = StudentCredit.objects.filter(
            student=student,
            is_utilized=False,
            credit_expiry__gte=timezone.now().date()
        ).aggregate(total=Sum('credit_amount'))['total'] or 0
        return credit_total
    except:
        return 0


# ==================== STUDENT SEARCH VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_students(request):
    """Search students by admission number"""
    try:
        admission_no = request.query_params.get('admission_no')
        
        if not admission_no:
            return Response({
                'success': False,
                'error': 'Admission number required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        students = Student.objects.filter(
            admission_no__icontains=admission_no,
            archived=False,
            status='Active'
        ).select_related('current_class')
        
        serializer = StudentSerializer(students, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error searching students: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_students_by_class(request):
    """Get all students in a class"""
    try:
        class_id = request.query_params.get('class_id')
        
        if not class_id:
            return Response({
                'success': False,
                'error': 'Class ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        students = Student.objects.filter(
            current_class_id=class_id,
            archived=False,
            status='Active'
        ).select_related('current_class')
        
        serializer = StudentSerializer(students, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching students by class: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== INVOICE MANAGEMENT VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_invoice_status(request, student_id):
    """Check if student has an invoice for current term"""
    try:
        student = Student.objects.get(id=student_id)
        academic_year, term = get_current_academic_year_and_term()
        
        if not academic_year or not term:
            return Response({
                'success': True,
                'data': {
                    'has_invoice': False,
                    'invoice_id': None,
                    'invoice_no': None,
                    'balance': 0,
                    'total_amount': 0
                }
            }, status=status.HTTP_200_OK)
        
        # Wherever you query StudentFeeInvoice by term, use the same pattern:
        term_value = term.term
        term_number = term_value.replace("Term ", "").strip()

        invoice = StudentFeeInvoice.objects.filter(
            student=student,
            academic_year=academic_year.year_code,
        ).filter(
            Q(term=term_value) | Q(term=term_number)
        ).first()
        
        return Response({
            'success': True,
            'data': {
                'has_invoice': invoice is not None,
                'invoice_id': str(invoice.id) if invoice else None,
                'invoice_no': invoice.invoice_no if invoice else None,
                'balance': invoice.balance_amount if invoice else 0,
                'total_amount': invoice.total_amount if invoice else 0
            }
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error checking invoice status: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_invoice(request, student_id):
    """Generate invoice for student for current term"""
    try:
        student = Student.objects.get(id=student_id)
        academic_year, term = get_current_academic_year_and_term()

        if not academic_year or not term:
            return Response({
                'success': False,
                'error': 'No active academic year or term found'
            }, status=status.HTTP_400_BAD_REQUEST)

        term_value = term.term
        term_number = term_value.replace("Term ", "").strip()

        # Use the same broad filter as the helper — avoids "already exists" being missed
        existing_invoice = StudentFeeInvoice.objects.filter(
            student=student,
            academic_year=academic_year.year_code,
        ).filter(
            Q(term=term_value) | Q(term=term_number)
        ).first()

        if existing_invoice:
            return Response({
                'success': True,
                'data': StudentFeeInvoiceSerializer(existing_invoice).data,
                'message': 'Invoice already exists'
            }, status=status.HTTP_200_OK)

        invoice = generate_invoice_for_student(student, academic_year, term, request)

        if invoice:
            create_audit_log(
                request, 'INVOICE_GENERATED', 'StudentFeeInvoice', invoice.id,
                None, {'invoice_no': invoice.invoice_no, 'amount': float(invoice.total_amount)}
            )
            return Response({
                'success': True,
                'data': StudentFeeInvoiceSerializer(invoice).data,
                'message': 'Invoice generated successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'error': f'No fee structure found for class {student.current_class.class_name}. '
                         f'Please set up fee structures for this class first.'
            }, status=status.HTTP_400_BAD_REQUEST)

    except Student.DoesNotExist:
        return Response({'success': False, 'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error generating invoice: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_balance(request, student_id):
    """Get student balance with invoices"""
    try:
        student = Student.objects.get(id=student_id)
        
        invoices = StudentFeeInvoice.objects.filter(
            student=student
        ).exclude(
            payment_status='Fully Paid'
        ).order_by('-invoice_date')
        
        total_balance = invoices.aggregate(total=Sum('balance_amount'))['total'] or 0
        
        credit_balance = get_student_credit_balance(student)
        
        net_balance = total_balance - credit_balance
        
        return Response({
            'success': True,
            'data': {
                'current_balance': net_balance,
                'total_balance': total_balance,
                'credit_balance': credit_balance,
                'invoices': StudentFeeInvoiceSerializer(invoices, many=True).data
            }
        }, status=status.HTTP_200_OK)
    
    except Student.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error fetching student balance: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PAYMENT PROCESSING VIEWS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_payment(request):
    """Process a fee payment"""
    try:
        if request.user.role not in ['bursar', 'accountant', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to process payments'
            }, status=status.HTTP_403_FORBIDDEN)
        
        student_id = request.data.get('student_id')
        amount = Decimal(str(request.data.get('amount_kes', 0)))
        
        if amount < Decimal('5'):
            return Response({
                'success': False,
                'error': 'Minimum payment amount is KSh 5.00'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        payment_mode = request.data.get('payment_mode')
        
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Student not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        academic_year, term = get_current_academic_year_and_term()
        
        if not academic_year or not term:
            return Response({
                'success': False,
                'error': 'No active academic year or term found'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        invoice = StudentFeeInvoice.objects.filter(
            student=student,
            academic_year=academic_year.year_code,
            term=term.term
        ).first()
        
        if not invoice:
            invoice = generate_invoice_for_student(
                student, academic_year, term, request,
                fallback_amount=amount  # creates invoice with payment amount as total
            )
            if not invoice:
                return Response({
                    'success': False,
                    'error': f'Failed to create invoice for {student.current_class.class_name}. Please contact admin.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            transaction_no = f"TXN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            
            fee_transaction = FeeTransaction.objects.create(
                transaction_no=transaction_no,
                invoice=invoice,
                student=student,
                payment_date=timezone.now(),
                payment_mode=payment_mode,
                payment_reference=request.data.get('payment_reference', ''),
                bank_name=request.data.get('bank_name'),
                cheque_no=request.data.get('cheque_no'),
                mobile_money_no=request.data.get('mobile_money_no'),
                amount=amount,
                currency='KES',
                exchange_rate=Decimal('1'),
                amount_kes=amount,
                status='Completed',
                collected_by=request.user,
                receipt_printed=False
            )
            
            previous_balance = invoice.balance_amount
            
            invoice.amount_paid = invoice.amount_paid + amount
            invoice.balance_amount = invoice.total_amount - invoice.amount_paid
            
            if invoice.balance_amount <= Decimal('0'):
                invoice.status = 'Paid'
                invoice.payment_status = 'Fully Paid'
                invoice.balance_amount = Decimal('0')
            elif invoice.amount_paid > Decimal('0'):
                invoice.status = 'Partial'
                invoice.payment_status = 'Partially Paid'
            
            invoice.save()
            
            excess_payment = Decimal('0')
            if invoice.balance_amount < Decimal('0'):
                excess_payment = abs(invoice.balance_amount)
                StudentCredit.objects.create(
                    student=student,
                    credit_amount=excess_payment,
                    credit_type='EXCESS_PAYMENT',
                    original_transaction=fee_transaction,
                    credit_date=timezone.now().date(),
                    credit_expiry=timezone.now().date() + timedelta(days=365),
                    is_utilized=False,
                    notes=f"Excess payment from transaction {transaction_no}"
                )
                invoice.balance_amount = Decimal('0')
                invoice.save()
            
            create_audit_log(
                request,
                'PAYMENT_RECEIVED',
                'FeeTransaction',
                fee_transaction.id,
                None,
                {
                    'student': student.admission_no,
                    'amount': float(amount),
                    'payment_mode': payment_mode,
                    'invoice_no': invoice.invoice_no
                }
            )
            
            return Response({
                'success': True,
                'data': {
                    'transaction': {
                        'transaction_no': fee_transaction.transaction_no,
                        'amount_kes': float(amount),
                        'payment_mode': payment_mode,
                        'payment_reference': fee_transaction.payment_reference,
                        'payment_date': fee_transaction.payment_date.isoformat(),
                        'previous_balance': float(previous_balance),
                        'new_balance': float(invoice.balance_amount),
                        'excess_credit': float(excess_payment)
                    },
                    'receipt': {
                        'receipt_no': fee_transaction.transaction_no,
                        'student_name': f"{student.first_name} {student.last_name}",
                        'admission_no': student.admission_no,
                        'class_name': student.current_class.class_name if student.current_class else 'Not Assigned',
                        'amount_paid': float(amount),
                        'payment_mode': payment_mode,
                        'payment_date': fee_transaction.payment_date,
                        'balance_after': float(invoice.balance_amount)
                    }
                },
                'message': 'Payment processed successfully'
            }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== DASHBOARD VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_transactions(request):
    """Get recent transactions"""
    try:
        limit = int(request.query_params.get('limit', 10))
        
        transactions = FeeTransaction.objects.filter(
            status='Completed'
        ).select_related('student').order_by('-payment_date')[:limit]
        
        serializer = FeeTransactionSerializer(transactions, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching recent transactions: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)