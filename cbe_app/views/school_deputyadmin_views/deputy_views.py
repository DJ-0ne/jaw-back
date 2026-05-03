# cbe_app/views/deputy_views/discipline_views.py

from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from cbe_app.models import (
    DisciplineIncident, ConductRecord, InterventionProgram,
    CounselingSession, Suspension, StudentDisciplinePoints,
    DisciplineCategory
)
from cbe_app.serializers.school_deputyadmin_seriliazers.discipline_seriliazers import (
    DisciplineIncidentListSerializer, DisciplineIncidentCreateSerializer,
    DisciplineCategorySerializer, DisciplineCategoryCreateSerializer,
    ConductRecordSerializer, InterventionProgramSerializer, InterventionProgramCreateSerializer,
    CounselingSessionSerializer, CounselingSessionCreateSerializer,
    SuspensionSerializer, SuspensionCreateSerializer
)


def _auto_create_suspension_if_needed(student, request, incident=None):
    """
    Check student's total points and create a Pending suspension if points > 30
    and no existing active/pending suspension for the same student in current year/term.
    Optionally link to the incident that caused the threshold breach.
    """
    academic_year = str(timezone.now().year)
    term = 'Term 1'
    points_record = StudentDisciplinePoints.objects.filter(
        student=student,
        academic_year=academic_year,
        term=term
    ).first()

    if not points_record or points_record.total_points <= 30:
        return

    existing = Suspension.objects.filter(
        student=student,
        status__in=['Pending', 'Active']
    ).exists()
    if existing:
        return

    # Placeholder dates to satisfy NOT NULL constraint – deputy will set real dates upon approval
    today = timezone.now().date()
    default_end = today + timedelta(days=1)

    Suspension.objects.create(
        student=student,
        incident=incident,               # now linked to the triggering case (if provided)
        suspension_type='In-School',
        start_date=today,
        end_date=default_end,
        reason="Automatic suspension: accumulation of discipline points exceeding threshold.",
        assigned_by=request.user,
        status='Pending',
        parent_notified=False
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_cases(request):
    try:
        queryset = DisciplineIncident.objects.select_related('student', 'category', 'reported_by')

        search = request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(incident_code__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(description__icontains=search)
            )

        status_filter = request.query_params.get('status', '')
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)

        severity = request.query_params.get('severity', '')
        if severity and severity != 'all':
            queryset = queryset.filter(category__severity_level=severity)

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size

        total = queryset.count()
        cases = queryset.order_by('-incident_date', '-created_at')[start:end]
        serializer = DisciplineIncidentListSerializer(cases, many=True)

        return Response({
            'success': True,
            'data': serializer.data,
            'pagination': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_discipline_case(request):
    try:
        serializer = DisciplineIncidentCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        case = serializer.save()
        student = case.student
        academic_year = str(timezone.now().year)
        term = 'Term 1'

        points_record, _ = StudentDisciplinePoints.objects.get_or_create(
            student=student,
            academic_year=academic_year,
            term=term,
            defaults={'total_points': 0}
        )

        points_record.total_points += case.points_awarded
        points_record.last_incident_date = case.incident_date

        if points_record.total_points >= 50:
            points_record.current_status = 'Suspension'
        elif points_record.total_points >= 40:
            points_record.current_status = 'Probation'
        elif points_record.total_points > 30:
            points_record.current_status = 'Warning'
        else:
            points_record.current_status = 'Good'

        points_record.save()

        # ---- AUTO SUSPENSION LOGIC (with incident link) ----
        _auto_create_suspension_if_needed(student, request, incident=case)

        return Response({
            'success': True,
            'data': DisciplineIncidentListSerializer(case).data,
            'message': 'Case created successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        import traceback
        print("FULL ERROR:", traceback.format_exc())
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Categories ----------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_categories(request):
    try:
        categories = DisciplineCategory.objects.filter(is_active=True).order_by('category_name')
        serializer = DisciplineCategorySerializer(categories, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_discipline_category(request):
    try:
        serializer = DisciplineCategoryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        category = serializer.save()
        return Response({
            'success': True,
            'data': DisciplineCategorySerializer(category).data,
            'message': 'Category created successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_discipline_category(request, category_id):
    try:
        category = get_object_or_404(DisciplineCategory, id=category_id)
        serializer = DisciplineCategorySerializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({'success': True, 'data': serializer.data, 'message': 'Category updated successfully'})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_discipline_category(request, category_id):
    category = get_object_or_404(DisciplineCategory, id=category_id)
    category_name = str(category)
    category.delete()
    return Response({'success': True, 'message': f'Category "{category_name}" deleted successfully'})


# ---------- Cases ----------
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def resolve_discipline_case(request, case_id):
    try:
        case = DisciplineIncident.objects.get(id=case_id)
        case.status = 'Resolved'
        case.resolution_date = timezone.now().date()
        case.save()
        return Response({'success': True, 'message': 'Case resolved successfully'})
    except DisciplineIncident.DoesNotExist:
        return Response({'success': False, 'error': 'Case not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_discipline_case(request, case_id):
    try:
        case = DisciplineIncident.objects.get(id=case_id)
        case.delete()
        return Response({'success': True, 'message': 'Case deleted successfully'})
    except DisciplineIncident.DoesNotExist:
        return Response({'success': False, 'error': 'Case not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Suspension Management ----------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_suspensions(request):
    try:
        suspensions = Suspension.objects.select_related('student', 'assigned_by').order_by('-start_date')
        serializer = SuspensionSerializer(suspensions, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_suspension(request):
    try:
        serializer = SuspensionCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        suspension = serializer.save()
        return Response({
            'success': True,
            'data': SuspensionSerializer(suspension).data,
            'message': 'Suspension created successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_suspension(request, suspension_id):
    try:
        suspension = get_object_or_404(Suspension, id=suspension_id)
        serializer = SuspensionSerializer(suspension, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({'success': True, 'data': serializer.data, 'message': 'Suspension updated successfully'})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_suspension(request, suspension_id):
    try:
        suspension = get_object_or_404(Suspension, id=suspension_id)
        suspension.delete()
        return Response({'success': True, 'message': 'Suspension deleted successfully'})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Other views (conduct, interventions, counseling, etc.) unchanged ----------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conduct_records(request):
    try:
        records = ConductRecord.objects.select_related('student').order_by('-last_updated')
        serializer = ConductRecordSerializer(records, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_interventions(request):
    try:
        programs = InterventionProgram.objects.all().order_by('-created_at')
        serializer = InterventionProgramSerializer(programs, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_intervention(request):
    try:
        serializer = InterventionProgramCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        program = serializer.save()
        return Response({
            'success': True,
            'data': InterventionProgramSerializer(program).data,
            'message': 'Intervention program created successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_counseling_sessions(request):
    try:
        sessions = CounselingSession.objects.select_related('student', 'counselor').order_by('-session_date')
        serializer = CounselingSessionSerializer(sessions, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_counseling_session(request):
    try:
        serializer = CounselingSessionCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        session = serializer.save()
        return Response({
            'success': True,
            'data': CounselingSessionSerializer(session).data,
            'message': 'Counseling session scheduled successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_students_list(request):
    try:
        from cbe_app.models import Student
        queryset = Student.objects.select_related('current_class').filter(status='Active', archived=False)
        search = request.query_params.get('search', '').strip()
        class_filter = request.query_params.get('class_id', '').strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(admission_no__icontains=search)
            )
        if class_filter:
            queryset = queryset.filter(current_class__id=class_filter)
        queryset = queryset.order_by('first_name', 'last_name')[:50]
        data = [{
            'id': str(s.id),
            'full_name': f"{s.first_name} {s.last_name}",
            'admission_number': s.admission_no,
            'class_name': str(s.current_class) if s.current_class else '',
            'class_id': str(s.current_class.id) if s.current_class else '',
        } for s in queryset]
        return Response({'success': True, 'data': data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_classes_list(request):
    try:
        from cbe_app.models import Class
        classes = Class.objects.filter(is_active=True).order_by('class_name')
        data = [{'id': str(c.id), 'name': c.class_name} for c in classes]
        return Response({'success': True, 'data': data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_stats(request):
    try:
        total_cases = DisciplineIncident.objects.count()
        active_cases = DisciplineIncident.objects.exclude(status__in=['Resolved', 'Closed']).count()
        resolved_cases = DisciplineIncident.objects.filter(status='Resolved').count()
        total_interventions = InterventionProgram.objects.filter(status='Active').count()
        active_suspensions = Suspension.objects.filter(status__in=['Pending', 'Active']).count()
        total_counseling = CounselingSession.objects.exclude(status='Completed').count()
        return Response({
            'success': True,
            'data': {
                'totalCases': total_cases,
                'activeCases': active_cases,
                'resolvedCases': resolved_cases,
                'totalInterventions': total_interventions,
                'activeSuspensions': active_suspensions,
                'totalCounseling': total_counseling
            }
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def suspension_detail(request, suspension_id):
    """
    Handle PUT (update) and DELETE for a single suspension.
    """
    suspension = get_object_or_404(Suspension, id=suspension_id)

    if request.method == 'PUT':
        serializer = SuspensionSerializer(suspension, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({'success': True, 'data': serializer.data, 'message': 'Suspension updated successfully'})

    elif request.method == 'DELETE':
        suspension.delete()
        return Response({'success': True, 'message': 'Suspension deleted successfully'})