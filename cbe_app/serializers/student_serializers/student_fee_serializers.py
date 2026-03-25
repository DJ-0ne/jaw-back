from rest_framework import serializers
from cbe_app.models import StudentFeeInvoice, FeeTransaction, FeeStructure, FeeCategory, Student
from decimal import Decimal

class FeeTransactionSerializer(serializers.ModelSerializer):
    """Serializer for fee transactions"""
    payment_mode_display = serializers.SerializerMethodField()
    
    class Meta:
        model = FeeTransaction
        fields = [
            'id', 'transaction_no', 'payment_date', 'payment_mode', 'payment_mode_display',
            'amount', 'amount_kes', 'status', 'payment_reference', 'receipt_printed',
            'bank_name', 'cheque_no', 'mobile_money_no'
        ]
    
    def get_payment_mode_display(self, obj):
        return obj.get_payment_mode_display()


class InvoiceItemSerializer(serializers.Serializer):
    """Serializer for invoice items"""
    description = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class StudentInvoiceSerializer(serializers.ModelSerializer):
    """Serializer for student invoices"""
    items = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentFeeInvoice
        fields = [
            'id', 'invoice_no', 'academic_year', 'term', 'invoice_date', 'due_date',
            'subtotal', 'discount_amount', 'late_fee_amount', 'total_amount',
            'amount_paid', 'balance_amount', 'status', 'status_display', 'items'
        ]
    
    def get_items(self, obj):
        items = []
        for item in obj.items.all():
            items.append({
                'description': item.description,
                'amount': item.amount,
                'discount': item.discount_amount,
                'net_amount': item.net_amount
            })
        return items
    
    def get_status_display(self, obj):
        return obj.get_status_display()


class FeeStructureItemSerializer(serializers.Serializer):
    """Serializer for fee structure items"""
    category_name = serializers.CharField()
    category_code = serializers.CharField()
    description = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    frequency = serializers.CharField()
    due_date = serializers.DateField()
    late_fee_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_mandatory = serializers.BooleanField()


class FeeSummarySerializer(serializers.Serializer):
    """Serializer for fee summary"""
    total_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_days = serializers.IntegerField()
    academic_year = serializers.CharField()
    term = serializers.CharField()
    payment_status = serializers.CharField()


class FeeStatementSerializer(serializers.Serializer):
    """Serializer for fee statement"""
    student_name = serializers.CharField()
    admission_no = serializers.CharField()
    class_name = serializers.CharField()
    academic_year = serializers.CharField()
    term = serializers.CharField()
    total_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    transactions = FeeTransactionSerializer(many=True)
    generated_date = serializers.DateTimeField()