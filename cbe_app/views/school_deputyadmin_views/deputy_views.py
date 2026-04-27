# cbe_app/views/deputy_views/discipline_views.py

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cbe_app.models import (
    DisciplineIncident, ConductRecord, InterventionProgram,
    CounselingSession, Suspension, StudentDisciplinePoints
)
from cbe_app.serializers.school_deputyadmin_seriliazers.discipline_seriliazers import *


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_cases(request):
    """Get paginated list of discipline cases"""
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
    """Create a new discipline case"""
    try:
        serializer = DisciplineIncidentCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        case = serializer.save()
        
        student = case.student
        academic_year = str(timezone.now().year)
        term = 'Term 1'
        
        points_record, created = StudentDisciplinePoints.objects.get_or_create(
            student=student,
            academic_year=academic_year,
            term=term,
            defaults={'total_points': 0}
        )
        points_record.total_points += case.points_awarded
        points_record.last_incident_date = case.incident_date
        
        if points_record.total_points >= 50:
            points_record.current_status = 'Suspension'
        elif points_record.total_points >= 30:
            points_record.current_status = 'Probation'
        elif points_record.total_points >= 15:
            points_record.current_status = 'Warning'
        else:
            points_record.current_status = 'Good'
        
        points_record.save()
        
        return Response({
            'success': True,
            'data': DisciplineIncidentListSerializer(case).data,
            'message': 'Case created successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def resolve_discipline_case(request, case_id):
    """Mark a discipline case as resolved"""
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
    """Delete a discipline case"""
    try:
        case = DisciplineIncident.objects.get(id=case_id)
        case.delete()
        return Response({'success': True, 'message': 'Case deleted successfully'})
    except DisciplineIncident.DoesNotExist:
        return Response({'success': False, 'error': 'Case not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conduct_records(request):
    """Get all conduct records"""
    try:
        records = ConductRecord.objects.select_related('student').order_by('-last_updated')
        serializer = ConductRecordSerializer(records, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_interventions(request):
    """Get all intervention programs"""
    try:
        programs = InterventionProgram.objects.all().order_by('-created_at')
        serializer = InterventionProgramSerializer(programs, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_intervention(request):
    """Create a new intervention program"""
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
    """Get all counseling sessions"""
    try:
        sessions = CounselingSession.objects.select_related('student', 'counselor').order_by('-session_date')
        serializer = CounselingSessionSerializer(sessions, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_counseling_session(request):
    """Create a new counseling session"""
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
def get_suspensions(request):
    """Get all suspensions"""
    try:
        suspensions = Suspension.objects.select_related('student', 'assigned_by').order_by('-start_date')
        serializer = SuspensionSerializer(suspensions, many=True)
        return Response({'success': True, 'data': serializer.data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_discipline_stats(request):
    """Get discipline statistics"""
    try:
        total_cases = DisciplineIncident.objects.count()
        active_cases = DisciplineIncident.objects.exclude(status__in=['Resolved', 'Closed']).count()
        resolved_cases = DisciplineIncident.objects.filter(status='Resolved').count()
        total_interventions = InterventionProgram.objects.filter(status='Active').count()
        active_suspensions = Suspension.objects.filter(status='Active').count()
        total_counseling = CounselingSession.objects.exclude(status='Completed').count()
        
        stats = {
            'totalCases': total_cases,
            'activeCases': active_cases,
            'resolvedCases': resolved_cases,
            'totalInterventions': total_interventions,
            'activeSuspensions': active_suspensions,
            'totalCounseling': total_counseling
        }
        
        return Response({'success': True, 'data': stats})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)