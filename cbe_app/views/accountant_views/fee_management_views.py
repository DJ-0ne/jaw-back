# cbe_app/views/accountant_views/fee_views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count, Q
import logging
from datetime import datetime, date, timedelta
import uuid

from cbe_app.models import (
    FeeCategory, FeeStructure, FeeTransaction, StudentFeeInvoice,
    Class, Student, AcademicYear, Term, FinancialSetting
)
from cbe_app.serializers.accountant_serializers.fee_management_serializers import (
    FeeCategorySerializer, FeeStructureSerializer, FeeTransactionSerializer,
    StudentFeeInvoiceSerializer
)

logger = logging.getLogger(__name__)


# ==================== FEE CATEGORY VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_categories(request):
    """Get all fee categories"""
    try:
        is_active = request.query_params.get('is_active')
        frequency = request.query_params.get('frequency')
        
        queryset = FeeCategory.objects.all().order_by('category_code')
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        if frequency:
            queryset = queryset.filter(frequency=frequency)
        
        serializer = FeeCategorySerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee categories: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch fee categories'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_fee_category(request):
    """Create a new fee category"""
    try:
        if request.user.role not in ['accountant', 'bursar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create fee categories'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = FeeCategorySerializer(data=request.data)
        
        if serializer.is_valid():
            category = serializer.save(created_by=request.user)
            logger.info(f"Fee category created: {category.category_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': f'Fee category {category.category_name} created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating fee category: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create fee category'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def fee_category_detail(request, category_id):
    """Update or delete a fee category"""
    try:
        try:
            category = FeeCategory.objects.get(id=category_id)
        except FeeCategory.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Fee category not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['accountant', 'bursar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update fee categories'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = FeeCategorySerializer(category, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Fee category updated: {category.category_code} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Fee category updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['accountant', 'bursar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete fee categories'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Check if category is used in any structure
            if FeeStructure.objects.filter(category=category).exists():
                return Response({
                    'success': False,
                    'error': 'Cannot delete category as it is used in fee structures'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            category.delete()
            logger.info(f"Fee category deleted: {category.category_code} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Fee category deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing fee category: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_category_stats(request):
    """Get fee category statistics"""
    try:
        total = FeeCategory.objects.count()
        active = FeeCategory.objects.filter(is_active=True).count()
        by_frequency = FeeCategory.objects.values('frequency').annotate(count=Count('id'))
        
        return Response({
            'success': True,
            'data': {
                'count': total,
                'active_count': active,
                'by_frequency': list(by_frequency)
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee category stats: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== FEE STRUCTURE VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_structures(request):
    """Get all fee structures"""
    try:
        academic_year = request.query_params.get('academic_year')
        term = request.query_params.get('term')
        class_id = request.query_params.get('class_id')
        is_active = request.query_params.get('is_active')
        
        queryset = FeeStructure.objects.select_related(
            'class_id', 'category'
        ).all().order_by('academic_year', 'term', 'class_id')
        
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        
        if term:
            queryset = queryset.filter(term=term)
        
        if class_id:
            queryset = queryset.filter(class_id_id=class_id)
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        serializer = FeeStructureSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee structures: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch fee structures'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_fee_structure(request):
    """Create a new fee structure"""
    try:
        if request.user.role not in ['accountant', 'bursar', 'system_admin']:
            return Response({
                'success': False,
                'error': 'You do not have permission to create fee structures'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Create a mutable copy of the data
        data = request.data.copy()
        
        # Map frontend field names to backend field names
        if 'category_id' in data and 'category' not in data:
            data['category'] = data.pop('category_id')
        
        if 'class_id' in data and 'class_id' not in data:
            # Keep class_id as is - it's correct
            pass
        
        serializer = FeeStructureSerializer(data=data)
        
        if serializer.is_valid():
            structure = serializer.save(created_by=request.user)
            logger.info(f"Fee structure created: {structure.id} by {request.user.username}")
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Fee structure created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating fee structure: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to create fee structure'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def fee_structure_detail(request, structure_id):
    """Update or delete a fee structure"""
    try:
        try:
            structure = FeeStructure.objects.get(id=structure_id)
        except FeeStructure.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Fee structure not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PUT':
            if request.user.role not in ['accountant', 'bursar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update fee structures'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = FeeStructureSerializer(structure, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Fee structure updated: {structure.id} by {request.user.username}")
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'message': 'Fee structure updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if request.user.role not in ['accountant', 'bursar', 'system_admin']:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete fee structures'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Check if structure has any invoices
            if StudentFeeInvoice.objects.filter(items__fee_structure=structure).exists():
                return Response({
                    'success': False,
                    'error': 'Cannot delete structure as it is used in invoices'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            structure.delete()
            logger.info(f"Fee structure deleted: {structure.id} by {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Fee structure deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing fee structure: {str(e)}")
        return Response({
            'success': False,
            'error': 'Operation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_structure_stats(request):
    """Get fee structure statistics"""
    try:
        total = FeeStructure.objects.count()
        active = FeeStructure.objects.filter(is_active=True).count()
        total_amount = FeeStructure.objects.aggregate(Sum('amount'))['amount__sum'] or 0
        
        by_term = FeeStructure.objects.values('term').annotate(
            count=Count('id'),
            amount=Sum('amount')
        )
        
        return Response({
            'success': True,
            'data': {
                'total': total,
                'active_count': active,
                'total_amount': total_amount,
                'by_term': list(by_term)
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee structure stats: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== FEE TRANSACTION VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_transactions(request):
    """Get all fee transactions"""
    try:
        limit = request.query_params.get('limit', 100)
        status_filter = request.query_params.get('status')
        search = request.query_params.get('search')
        
        queryset = FeeTransaction.objects.select_related(
            'student', 'collected_by'
        ).all().order_by('-payment_date')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if search:
            queryset = queryset.filter(
                Q(transaction_no__icontains=search) |
                Q(student__admission_no__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search)
            )
        
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            pass
        
        serializer = FeeTransactionSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee transactions: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch fee transactions'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fee_transaction_stats(request):
    """Get fee transaction statistics"""
    try:
        total_transactions = FeeTransaction.objects.count()
        completed = FeeTransaction.objects.filter(status='Completed').count()
        pending = FeeTransaction.objects.filter(status='Pending').count()
        total_collected = FeeTransaction.objects.filter(
            status='Completed'
        ).aggregate(Sum('amount_kes'))['amount_kes__sum'] or 0
        
        collection_rate = (completed / total_transactions * 100) if total_transactions > 0 else 0
        
        return Response({
            'success': True,
            'data': {
                'total_transactions': total_transactions,
                'completed_transactions': completed,
                'pending_transactions': pending,
                'total_collected': total_collected,
                'collection_rate': round(collection_rate, 2)
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching fee transaction stats: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PRINT FUNCTIONS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_fee_structures(request):
    """Export all fee structures for printing"""
    try:
        academic_year = request.query_params.get('academic_year')
        
        queryset = FeeStructure.objects.select_related(
            'class_id', 'category'
        ).all().order_by('academic_year', 'term', 'class_id')
        
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        
        # Group by class for better organization
        structures_by_class = {}
        for structure in queryset:
            class_name = structure.class_id.class_name
            if class_name not in structures_by_class:
                structures_by_class[class_name] = []
            structures_by_class[class_name].append({
                'id': structure.id,
                'category_code': structure.category.category_code,
                'category_name': structure.category.category_name,
                'term': structure.term,
                'amount': structure.amount,
                'due_date': structure.due_date,
                'frequency': structure.category.frequency,
                'is_mandatory': structure.category.is_mandatory
            })
        
        # Calculate totals
        total_by_class = {}
        total_overall = 0
        
        for class_name, structures in structures_by_class.items():
            class_total = sum(s['amount'] for s in structures)
            total_by_class[class_name] = class_total
            total_overall += class_total
        
        return Response({
            'success': True,
            'data': {
                'structures_by_class': structures_by_class,
                'total_by_class': total_by_class,
                'total_overall': total_overall,
                'generated_date': datetime.now().isoformat(),
                'academic_year': academic_year or 'All Years'
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error exporting fee structures: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to export fee structures'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        

##########################################################################################################################################


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transaction_stats(request):
    """Get transaction statistics for dashboard"""
    try:
        # Get date range from query params
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        queryset = FeeTransaction.objects.filter(status='Completed')
        
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)
        
        # Today's date
        today = date.today()
        
        # Today's collections
        today_collection = queryset.filter(
            payment_date__date=today
        ).aggregate(total=Sum('amount_kes'))['total'] or 0
        
        # Total collected
        total_collected = queryset.aggregate(total=Sum('amount_kes'))['total'] or 0
        
        # Total transactions
        total_transactions = queryset.count()
        
        # Pending collections (invoices with balance > 0)
        pending_collections = StudentFeeInvoice.objects.filter(
            balance_amount__gt=0
        ).aggregate(total=Sum('balance_amount'))['total'] or 0
        
        # Overdue payments
        overdue_payments = StudentFeeInvoice.objects.filter(
            due_date__lt=today,
            balance_amount__gt=0
        ).aggregate(total=Sum('balance_amount'))['total'] or 0
        
        # Average transaction
        avg_transaction = total_collected / total_transactions if total_transactions > 0 else 0
        
        # Collection rate
        total_invoiced = StudentFeeInvoice.objects.aggregate(total=Sum('total_amount'))['total'] or 0
        collection_rate = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0
        
        # Active invoices
        active_invoices = StudentFeeInvoice.objects.filter(
            balance_amount__gt=0
        ).count()
        monthly_target_setting = FinancialSetting.objects.filter(
            setting_key='MONTHLY_TARGET'
        ).first()
        
        if monthly_target_setting:
            monthly_target = float(monthly_target_setting.setting_value)
        else:
            # Create default if not exists
            monthly_target = 10000005
            FinancialSetting.objects.create(
                setting_key='MONTHLY_TARGET',
                setting_value=monthly_target,
                description='Monthly collection target for the school'
            )
        
        return Response({
            'success': True,
            'data': {
                'total_collected': float(total_collected),
                'today_collection': float(today_collection),
                'pending_collections': float(pending_collections),
                'overdue_payments': float(overdue_payments),
                'collection_rate': round(collection_rate, 2),
                'avg_transaction': float(avg_transaction),
                'active_invoices': active_invoices,
                'total_transactions': total_transactions,
                'monthly_target': float(monthly_target)
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
def get_daily_collection(request):
    """Get daily collection for the last 30 days"""
    try:
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            end_date = date.today()
            start_date = end_date - timedelta(days=30)
        
        transactions = FeeTransaction.objects.filter(
            status='Completed',
            payment_date__date__gte=start_date,
            payment_date__date__lte=end_date
        )
        
        daily_data = {}
        for t in transactions:
            date_key = t.payment_date.date().isoformat()
            if date_key not in daily_data:
                daily_data[date_key] = {'date': date_key, 'total_amount': 0, 'count': 0}
            daily_data[date_key]['total_amount'] += float(t.amount_kes)
            daily_data[date_key]['count'] += 1
        
        result = sorted(daily_data.values(), key=lambda x: x['date'])
        
        return Response({
            'success': True,
            'data': result,
            'count': len(result)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching daily collection: {str(e)}")
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
        
        result = []
        for s in stats:
            result.append({
                'payment_mode': s['payment_mode'],
                'total_amount': float(s['total_amount']),
                'count': s['count']
            })
        
        return Response({
            'success': True,
            'data': result
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching payment methods stats: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_top_students(request):
    """Get top paying students"""
    try:
        limit = int(request.query_params.get('limit', 5))
        
        stats = FeeTransaction.objects.filter(
            status='Completed'
        ).values(
            'student_id', 'student__first_name', 'student__last_name', 'student__admission_no'
        ).annotate(
            total_paid=Sum('amount_kes'),
            transaction_count=Count('id')
        ).order_by('-total_paid')[:limit]
        
        result = []
        for s in stats:
            result.append({
                'student_id': s['student_id'],
                'first_name': s['student__first_name'],
                'last_name': s['student__last_name'],
                'admission_no': s['student__admission_no'],
                'total_paid': float(s['total_paid']),
                'transaction_count': s['transaction_count']
            })
        
        return Response({
            'success': True,
            'data': result
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error fetching top students: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)