# cbe_app/serializers/bursar_serializers/bursar_payment_serializers.py

from rest_framework import serializers
from cbe_app.models import Student, Class, FeeTransaction, StudentFeeInvoice, InvoiceItem

class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    class_name = serializers.CharField(source='current_class.class_name', read_only=True)
    
    class Meta:
        model = Student
        fields = ['id', 'admission_no', 'first_name', 'last_name', 'full_name', 'class_name', 'current_class']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ['id', 'class_code', 'class_name', 'numeric_level', 'stream']


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = '__all__'


class StudentFeeInvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = StudentFeeInvoice
        fields = '__all__'


class FeeTransactionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_no = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    
    class Meta:
        model = FeeTransaction
        fields = '__all__'
    
    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}".strip()
    
    def get_admission_no(self, obj):
        return obj.student.admission_no
    
    def get_first_name(self, obj):
        return obj.student.first_name
    
    def get_last_name(self, obj):
        return obj.student.last_name