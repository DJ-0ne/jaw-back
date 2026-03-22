# cbe_app/serializers/bursar_serializers/bursar_payment_serializers.py

from rest_framework import serializers
from cbe_app.models import (
    Student, Class, FeeTransaction, StudentFeeInvoice, 
    InvoiceItem, StudentCredit, AuditLog
)
from decimal import Decimal
from django.utils import timezone


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    class_name = serializers.CharField(source='current_class.class_name', read_only=True)
    class_code = serializers.CharField(source='current_class.class_code', read_only=True)
    
    class Meta:
        model = Student
        fields = [
            'id', 'admission_no', 'first_name', 'middle_name', 'last_name', 
            'full_name', 'class_name', 'class_code', 'current_class',
            'guardian_name', 'guardian_phone', 'phone', 'email', 'status'
        ]
    
    def get_full_name(self, obj):
        return obj.full_name


class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ['id', 'class_code', 'class_name', 'numeric_level', 'stream', 'is_active']


class InvoiceItemSerializer(serializers.ModelSerializer):
    fee_structure_name = serializers.CharField(source='fee_structure.category.category_name', read_only=True)
    fee_structure_code = serializers.CharField(source='fee_structure.category.category_code', read_only=True)
    
    class Meta:
        model = InvoiceItem
        fields = '__all__'


class StudentFeeInvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    admission_no = serializers.CharField(source='student.admission_no', read_only=True)
    class_name = serializers.CharField(source='student.current_class.class_name', read_only=True)
    items = InvoiceItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = StudentFeeInvoice
        fields = '__all__'
        read_only_fields = ['id', 'invoice_no', 'created_at', 'updated_at']


class FeeTransactionSerializer(serializers.ModelSerializer):
    # Student details
    student_name = serializers.SerializerMethodField()
    admission_no = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    guardian_name = serializers.SerializerMethodField()
    guardian_phone = serializers.SerializerMethodField()
    
    # Staff details
    collected_by_name = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()
    
    # Invoice details
    invoice_no = serializers.SerializerMethodField()
    invoice_academic_year = serializers.SerializerMethodField()
    invoice_term = serializers.SerializerMethodField()
    invoice_total = serializers.SerializerMethodField()
    invoice_paid = serializers.SerializerMethodField()
    invoice_balance = serializers.SerializerMethodField()
    
    # Formatted fields
    formatted_amount = serializers.SerializerMethodField()
    formatted_date = serializers.SerializerMethodField()
    formatted_time = serializers.SerializerMethodField()
    
    class Meta:
        model = FeeTransaction
        fields = [
            'id', 'transaction_no', 'amount', 'amount_kes', 'currency', 'exchange_rate',
            'payment_mode', 'payment_reference', 'payment_date', 'status',
            'bank_name', 'cheque_no', 'mobile_money_no',
            'student_name', 'admission_no', 'first_name', 'last_name', 'class_name',
            'guardian_name', 'guardian_phone',
            'collected_by_name', 'verified_by_name', 'verified_at',
            'invoice_no', 'invoice_academic_year', 'invoice_term',
            'invoice_total', 'invoice_paid', 'invoice_balance',
            'formatted_amount', 'formatted_date', 'formatted_time',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'transaction_no', 'created_at', 'updated_at']
    
    def get_student_name(self, obj):
        return obj.student.full_name
    
    def get_admission_no(self, obj):
        return obj.student.admission_no
    
    def get_first_name(self, obj):
        return obj.student.first_name
    
    def get_last_name(self, obj):
        return obj.student.last_name
    
    def get_class_name(self, obj):
        return obj.student.current_class.class_name if obj.student.current_class else None
    
    def get_guardian_name(self, obj):
        return obj.student.guardian_name
    
    def get_guardian_phone(self, obj):
        return obj.student.guardian_phone
    
    def get_collected_by_name(self, obj):
        if obj.collected_by:
            return f"{obj.collected_by.first_name} {obj.collected_by.last_name}".strip()
        return None
    
    def get_verified_by_name(self, obj):
        if obj.verified_by:
            return f"{obj.verified_by.first_name} {obj.verified_by.last_name}".strip()
        return None
    
    def get_invoice_no(self, obj):
        return obj.invoice.invoice_no if obj.invoice else None
    
    def get_invoice_academic_year(self, obj):
        return obj.invoice.academic_year if obj.invoice else None
    
    def get_invoice_term(self, obj):
        return obj.invoice.term if obj.invoice else None
    
    def get_invoice_total(self, obj):
        return obj.invoice.total_amount if obj.invoice else None
    
    def get_invoice_paid(self, obj):
        return obj.invoice.amount_paid if obj.invoice else None
    
    def get_invoice_balance(self, obj):
        return obj.invoice.balance_amount if obj.invoice else None
    
    def get_formatted_amount(self, obj):
        return f"KSh {obj.amount_kes:,.2f}" if obj.amount_kes else "KSh 0.00"
    
    def get_formatted_date(self, obj):
        return obj.payment_date.strftime('%d %b %Y') if obj.payment_date else None
    
    def get_formatted_time(self, obj):
        return obj.payment_date.strftime('%H:%M') if obj.payment_date else None


class TransactionListSerializer(serializers.ModelSerializer):
    """Simplified serializer for transaction list view"""
    student_name = serializers.SerializerMethodField()
    admission_no = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    collected_by_name = serializers.SerializerMethodField()
    formatted_amount = serializers.SerializerMethodField()
    formatted_date = serializers.SerializerMethodField()
    
    class Meta:
        model = FeeTransaction
        fields = [
            'id', 'transaction_no', 'amount_kes', 'payment_mode', 
            'payment_reference', 'payment_date', 'status',
            'student_name', 'admission_no', 'first_name', 'last_name', 'class_name',
            'collected_by_name', 'formatted_amount', 'formatted_date'
        ]
    
    def get_student_name(self, obj):
        return obj.student.full_name
    
    def get_admission_no(self, obj):
        return obj.student.admission_no
    
    def get_first_name(self, obj):
        return obj.student.first_name
    
    def get_last_name(self, obj):
        return obj.student.last_name
    
    def get_class_name(self, obj):
        return obj.student.current_class.class_name if obj.student.current_class else None
    
    def get_collected_by_name(self, obj):
        if obj.collected_by:
            return f"{obj.collected_by.first_name} {obj.collected_by.last_name}".strip()
        return None
    
    def get_formatted_amount(self, obj):
        return f"KSh {obj.amount_kes:,.2f}" if obj.amount_kes else "KSh 0.00"
    
    def get_formatted_date(self, obj):
        return obj.payment_date.strftime('%d %b %Y') if obj.payment_date else None


class TransactionDetailSerializer(FeeTransactionSerializer):
    """Extended serializer for transaction details with credits and audit"""
    credits = serializers.SerializerMethodField()
    audit_logs = serializers.SerializerMethodField()
    
    class Meta(FeeTransactionSerializer.Meta):
        fields = FeeTransactionSerializer.Meta.fields + ['credits', 'audit_logs']
    
    def get_credits(self, obj):
        from cbe_app.models import StudentCredit
        credits = StudentCredit.objects.filter(original_transaction=obj)
        return [{
            'id': str(c.id),
            'amount': float(c.credit_amount),
            'type': c.credit_type,
            'is_utilized': c.is_utilized,
            'expiry': c.credit_expiry
        } for c in credits]
    
    def get_audit_logs(self, obj):
        audit_logs = AuditLog.objects.filter(
            record_id=obj.id,
            table_name='FeeTransaction'
        ).order_by('-event_time')[:5]
        
        return [{
            'event_type': log.event_type,
            'event_time': log.event_time,
            'user': log.username,
            'changes': log.new_values
        } for log in audit_logs]


class TransactionStatsSerializer(serializers.Serializer):
    """Serializer for transaction statistics"""
    total_collected = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_transactions = serializers.IntegerField()
    unique_students = serializers.IntegerField()
    average_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    completed_count = serializers.IntegerField()
    by_payment_mode = serializers.ListField(child=serializers.DictField())


class ExportTransactionSerializer(serializers.Serializer):
    """Serializer for transaction export"""
    transaction_no = serializers.CharField()
    student_name = serializers.CharField()
    admission_no = serializers.CharField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    payment_date = serializers.CharField()
    payment_mode = serializers.CharField()
    reference = serializers.CharField()
    status = serializers.CharField()