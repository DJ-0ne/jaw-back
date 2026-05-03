from rest_framework import serializers
from cbe_app.models import FeeCategory, FeeStructure, FeeTransaction, StudentFeeInvoice, Class
from datetime import datetime

class FeeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeCategory
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_category_code(self, value):
        if FeeCategory.objects.filter(category_code=value).exists():
            raise serializers.ValidationError("Category code already exists")
        return value


class FeeStructureSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    category_code = serializers.CharField(source='category.category_code', read_only=True)
    class_name = serializers.CharField(source='class_id.class_name', read_only=True)
    class_code = serializers.CharField(source='class_id.class_code', read_only=True)
    numeric_level = serializers.IntegerField(source='class_id.numeric_level', read_only=True)
    frequency = serializers.CharField(source='category.frequency', read_only=True)
    is_mandatory = serializers.BooleanField(source='category.is_mandatory', read_only=True)

    class Meta:
        model = FeeStructure
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        instance = self.instance  # None on create, existing object on update

        # Only check duplicate on CREATE, not on UPDATE
        if instance is None:
            academic_year = data.get('academic_year')
            term = data.get('term')
            class_id = data.get('class_id')
            category = data.get('category')

            if all([academic_year, term, class_id, category]):
                if FeeStructure.objects.filter(
                    academic_year=academic_year,
                    term=term,
                    class_id=class_id,
                    category=category
                ).exists():
                    raise serializers.ValidationError(
                        "Fee structure already exists for this combination"
                    )

        return data
    
class FeeTransactionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    admission_no = serializers.CharField(source='student.admission_no', read_only=True)
    collected_by_name = serializers.CharField(source='collected_by.get_full_name', read_only=True)
    
    class Meta:
        model = FeeTransaction
        fields = '__all__'
        read_only_fields = ['id', 'transaction_no', 'created_at', 'updated_at']


class StudentFeeInvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    class_name = serializers.CharField(source='student.current_class.class_name', read_only=True)
    
    class Meta:
        model = StudentFeeInvoice
        fields = '__all__'
        read_only_fields = ['id', 'invoice_no', 'created_at', 'updated_at']