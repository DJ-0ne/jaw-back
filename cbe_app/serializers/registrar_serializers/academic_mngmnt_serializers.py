from rest_framework import serializers
from cbe_app.models import LearningArea, Strand, SubStrand, Competency, AcademicYear, Term,GradeLevel, GradingScale, CurriculumMapping, StudentPortfolio

class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        if data['start_date'] >= data['end_date']:
            raise serializers.ValidationError("Start date must be before end date")
        return data


class TermSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.year_name', read_only=True)
    
    class Meta:
        model = Term
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        if data['start_date'] >= data['end_date']:
            raise serializers.ValidationError("Start date must be before end date")
        return data


class LearningAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningArea
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class StrandSerializer(serializers.ModelSerializer):
    learning_area_name = serializers.CharField(source='learning_area.area_name', read_only=True)
    
    class Meta:
        model = Strand
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class SubStrandSerializer(serializers.ModelSerializer):
    strand_name = serializers.CharField(source='strand.strand_name', read_only=True)
    
    class Meta:
        model = SubStrand
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class CompetencySerializer(serializers.ModelSerializer):
    substrand_name = serializers.CharField(source='substrand.substrand_name', read_only=True)
    
    class Meta:
        model = Competency
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_competency_code(self, value):
        if Competency.objects.filter(competency_code=value).exists():
            raise serializers.ValidationError("Competency code already exists")
        return value
    

class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class GradingScaleSerializer(serializers.ModelSerializer):
    rating_display = serializers.CharField(source='get_rating_display', read_only=True)
    
    class Meta:
        model = GradingScale
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        if data['min_percentage'] >= data['max_percentage']:
            raise serializers.ValidationError("Min percentage must be less than max percentage")
        
        # Check for overlapping ranges
        overlapping = GradingScale.objects.filter(
            rating=data['rating'],
            sub_level=data['sub_level']
        ).exclude(id=self.instance.id if self.instance else None)
        
        if overlapping.exists():
            raise serializers.ValidationError(f"Grading scale for {data['rating']}{data['sub_level']} already exists")
        
        return data


class CurriculumMappingSerializer(serializers.ModelSerializer):
    grade_level_name = serializers.CharField(source='grade_level.name', read_only=True)
    learning_area_name = serializers.CharField(source='learning_area.area_name', read_only=True)
    learning_area_code = serializers.CharField(source='learning_area.area_code', read_only=True)
    
    class Meta:
        model = CurriculumMapping
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        # Check if this mapping already exists
        if CurriculumMapping.objects.filter(
            grade_level=data['grade_level'],
            learning_area=data['learning_area']
        ).exists():
            raise serializers.ValidationError("This learning area is already mapped to this grade level")
        return data


class StudentPortfolioSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission = serializers.CharField(source='student.admission_no', read_only=True)
    competency_code = serializers.CharField(source='competency.competency_code', read_only=True)
    competency_statement = serializers.CharField(source='competency.competency_statement', read_only=True)
    term_name = serializers.CharField(source='term.term', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.year_name', read_only=True)
    rating_display = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentPortfolio
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'assessed_by', 'assessed_date']
    
    def get_rating_display(self, obj):
        if obj.rating and obj.sub_level:
            return f"{obj.rating}{obj.sub_level}"
        return None
    
    def validate(self, data):
        # Check if portfolio already exists for this student, competency, term, year
        if StudentPortfolio.objects.filter(
            student=data['student'],
            competency=data['competency'],
            term=data['term'],
            academic_year=data['academic_year']
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("Portfolio already exists for this student, competency, term, and year")
        return data