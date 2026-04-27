# cbe_app/views/school_deputyadmin_views/teacher_assignment_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Q

from cbe_app.models import (
    Staff, Class, LearningArea, ClassSubjectAllocation, 
    TeacherCategory, JSSDepartment, Department, AcademicYear, User,
    GradeLevel
)
from cbe_app.serializers.school_deputyadmin_seriliazers.teacher_assignment_serializers import (
    TeacherProfileSerializer, ClassWithStreamSerializer, SubjectSerializer,
    TeacherAssignmentSerializer, CreateAssignmentSerializer
)


class QualifiedTeachersView(APIView):
    """Get qualified teachers with specialization and department info"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            grade_level = request.query_params.get('grade_level')
            
            # Get only staff who are actual teachers (have teacher_category)
            teachers = Staff.objects.filter(
                status='Active',
                teacher_category__isnull=False
            ).exclude(
                teacher_category__code__in=['ADMIN', 'HR', 'SUPPORT', 'FINANCE']
            ).select_related(
                'user', 'teacher_category', 'jss_department', 'admin_department'
            ).order_by('first_name', 'last_name')
            
            # Filter by grade level qualification
            if grade_level:
                if grade_level == 'early':
                    teachers = teachers.filter(teacher_category__code='PP')
                elif grade_level == 'primary':
                    teachers = teachers.filter(teacher_category__code__in=['EP', 'PP'])
                elif grade_level == 'junior':
                    teachers = teachers.filter(teacher_category__code='JSS')
            
            serializer = TeacherProfileSerializer(teachers, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Teachers retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve teachers'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AvailableClassesView(APIView):
    """Get classes with stream information"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            grade_level_filter = request.query_params.get('grade_level')
            academic_year = request.query_params.get('academic_year')
            
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            # Get all active classes with their stream info
            classes = Class.objects.filter(is_active=True).order_by('numeric_level', 'stream')
            
            # Filter by grade level range
            if grade_level_filter:
                if grade_level_filter == 'early':
                    classes = classes.filter(numeric_level__in=[1, 2])
                elif grade_level_filter == 'primary':
                    classes = classes.filter(numeric_level__in=[3, 4, 5, 6, 7, 8])
                elif grade_level_filter == 'junior':
                    classes = classes.filter(numeric_level__in=[9, 10, 11])
            
            # Get already assigned subjects for these classes
            assignments = ClassSubjectAllocation.objects.filter(
                academic_year=academic_year if academic_year else ''
            ).values_list('class_id', 'subject_id')
            
            assigned_pairs = set((str(a[0]), str(a[1])) for a in assignments)
            
            serializer = ClassWithStreamSerializer(classes, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'assigned_pairs': list(assigned_pairs),
                'message': 'Classes retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve classes'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubjectsByGradeView(APIView):
    """Get subjects that can be taught"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subjects = LearningArea.objects.filter(is_active=True).order_by('area_name')
            serializer = SubjectSerializer(subjects, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Subjects retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve subjects'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherDepartmentsView(APIView):
    """Get departments for filtering teachers"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            departments = Department.objects.filter(is_active=True)
            jss_depts = JSSDepartment.objects.filter(is_active=True)
            
            data = []
            for dept in departments:
                data.append({
                    'id': str(dept.id),
                    'name': dept.department_name,
                    'code': dept.department_code,
                    'type': dept.department_type or 'ACADEMIC'
                })
            
            for dept in jss_depts:
                data.append({
                    'id': str(dept.id),
                    'name': dept.name,
                    'code': dept.code,
                    'type': 'JSS_DEPARTMENT'
                })
            
            return Response({
                'success': True,
                'data': data,
                'message': 'Departments retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve departments'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateTeacherAssignmentView(APIView):
    """Create a new teacher-class-subject assignment"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Validate input using serializer
        serializer = CreateAssignmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors,
                'message': 'Invalid assignment data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            data = serializer.validated_data
            
            # Get the staff member (teacher)
            staff = Staff.objects.get(id=data['teacher_id'])
            
            # Create assignment using the teacher's user account
            assignment = ClassSubjectAllocation.objects.create(
                class_id_id=data['class_id'],
                subject_id=data['subject_id'],
                teacher=staff.user,
                academic_year=data['academic_year'],
                periods_per_week=data['periods_per_week'],
                is_compulsory=data['is_compulsory']
            )
            
            # Return the created assignment with full details
            response_serializer = TeacherAssignmentSerializer(assignment)
            
            return Response({
                'success': True,
                'data': response_serializer.data,
                'message': 'Teacher assigned successfully'
            })
            
        except Staff.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Teacher not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to create assignment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherAssignmentsListView(APIView):
    """Get all teacher assignments with filters"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            academic_year = request.query_params.get('academic_year')
            grade_level = request.query_params.get('grade_level')
            department_id = request.query_params.get('department')
            
            if not academic_year:
                current_academic_year = AcademicYear.objects.filter(is_current=True).first()
                academic_year = current_academic_year.year_code if current_academic_year else None
            
            assignments = ClassSubjectAllocation.objects.filter(
                academic_year=academic_year if academic_year else ''
            ).select_related('class_id', 'subject', 'teacher__staff_profile')
            
            # Filter by grade level
            if grade_level:
                if grade_level == 'early':
                    assignments = assignments.filter(class_id__numeric_level__in=[1, 2])
                elif grade_level == 'primary':
                    assignments = assignments.filter(class_id__numeric_level__in=[3, 4, 5, 6, 7, 8])
                elif grade_level == 'junior':
                    assignments = assignments.filter(class_id__numeric_level__in=[9, 10, 11])
            
            # Filter by department
            if department_id:
                assignments = assignments.filter(
                    Q(teacher__staff_profile__admin_department_id=department_id) |
                    Q(teacher__staff_profile__jss_department_id=department_id)
                )
            
            serializer = TeacherAssignmentSerializer(assignments, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Assignments retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve assignments'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateTeacherAssignmentView(APIView):
    """Update an existing teacher assignment"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, assignment_id):
        try:
            assignment = ClassSubjectAllocation.objects.filter(id=assignment_id).first()
            if not assignment:
                return Response({
                    'success': False,
                    'message': 'Assignment not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            data = request.data
            
            # Update teacher if provided
            if 'teacher_id' in data:
                staff = Staff.objects.filter(id=data['teacher_id'], teacher_category__isnull=False).first()
                if staff and staff.user:
                    assignment.teacher = staff.user
            
            # Update other fields
            if 'periods_per_week' in data:
                assignment.periods_per_week = data['periods_per_week']
            
            if 'is_compulsory' in data:
                assignment.is_compulsory = data['is_compulsory']
            
            if 'academic_year' in data:
                assignment.academic_year = data['academic_year']
            
            assignment.save()
            
            serializer = TeacherAssignmentSerializer(assignment)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Assignment updated successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to update assignment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteTeacherAssignmentView(APIView):
    """Delete a teacher assignment"""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, assignment_id):
        try:
            assignment = ClassSubjectAllocation.objects.filter(id=assignment_id).first()
            if not assignment:
                return Response({
                    'success': False,
                    'message': 'Assignment not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            assignment.delete()
            
            return Response({
                'success': True,
                'message': 'Assignment removed successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Failed to delete assignment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherCategoriesView(APIView):
    """Get teacher categories (PP, EP, JSS)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            categories = TeacherCategory.objects.filter(is_active=True)
            serializer = TeacherCategorySerializer(categories, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'Teacher categories retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': [],
                'error': str(e),
                'message': 'Failed to retrieve categories'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GradeLevelsInfoView(APIView):
    """Get grade level information from the GradeLevel model"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            grade_levels = GradeLevel.objects.all().order_by('level')
            
            early_years_grades = []
            primary_grades = []
            junior_grades = []
            
            for gl in grade_levels:
                grade_info = {
                    'level': gl.level,
                    'name': gl.name,
                    'description': gl.description
                }
                
                if gl.level <= 2:
                    early_years_grades.append(grade_info)
                elif gl.level <= 8:
                    primary_grades.append(grade_info)
                else:
                    junior_grades.append(grade_info)
            
            data = {
                'early_years': {
                    'name': 'Early Years Education',
                    'grades': early_years_grades,
                    'teacher_category': 'PP',
                    'numeric_levels': [1, 2]
                },
                'primary': {
                    'name': 'Primary School',
                    'grades': primary_grades,
                    'teacher_category': 'EP',
                    'numeric_levels': [3, 4, 5, 6, 7, 8]
                },
                'junior_secondary': {
                    'name': 'Junior Secondary School',
                    'grades': junior_grades,
                    'teacher_category': 'JSS',
                    'numeric_levels': [9, 10, 11]
                }
            }
            
            return Response({
                'success': True,
                'data': data,
                'message': 'Grade levels retrieved successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'data': None,
                'error': str(e),
                'message': 'Failed to retrieve grade levels'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)