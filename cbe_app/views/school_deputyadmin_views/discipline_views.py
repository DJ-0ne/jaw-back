from django.utils import timezone
from django.db.models import Count, Q
from collections import defaultdict
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from cbe_app.models import (
    DisciplineIncident, DisciplineCategory, CounselingSession,
    Suspension, Student
)
from cbe_app.serializers.school_deputyadmin_seriliazers.discipline_seriliazers import DisciplineIncidentListSerializer

# Helper: colour palette for pie chart
COLOR_PALETTE = ['#3B82F6', '#EF4444', '#F59E0B', '#10B981', '#8B5CF6', '#EC4899', '#6366F1']

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_data(request):
    """Aggregated data for the deputy principal dashboard."""
    today = timezone.now().date()

    # ---- 1. Statistics ----
    active_cases = DisciplineIncident.objects.exclude(status__in=['Resolved', 'Closed']).count()
    resolved_today = DisciplineIncident.objects.filter(
        status='Resolved', resolution_date=today
    ).count()
    pending_review = DisciplineIncident.objects.filter(status='Pending').count()
    active_suspensions = Suspension.objects.filter(status='Active').count()
    
    # Counseling sessions scheduled for today
    today_counseling = CounselingSession.objects.filter(session_date=today).count()
    today_sessions = CounselingSession.objects.filter(session_date=today)
    
    # Repeat offenders: students with more than 1 active case
    repeat_offenders = (
        Student.objects.filter(
            discipline_incidents__status__in=['Investigation', 'Pending', 'Open']
        )
        .annotate(active_count=Count('discipline_incidents'))
        .filter(active_count__gt=1)
        .count()
    )

    stats = {
        'activeCases': active_cases,
        'resolvedToday': resolved_today,
        'pendingReview': pending_review,
        'suspensions': active_suspensions,
        'counselingSessions': today_counseling,          # today’s total
        'repeatOffenders': repeat_offenders,
    }

    # ---- 2. Weekly Cases (Mon–Fri) ----
    # Determine start of current week (Monday)
    monday = today - timedelta(days=today.weekday())
    week_days = [monday + timedelta(days=i) for i in range(5)]  # Mon–Fri

    weekly_cases = []
    for day in week_days:
        incidents_on_day = DisciplineIncident.objects.filter(incident_date=day)
        # Minor: severity Low/Medium, Major: High/Critical
        minor_count = incidents_on_day.filter(
            category__severity_level__in=['Low', 'Medium', 'Minor']
        ).count()
        major_count = incidents_on_day.filter(
            category__severity_level__in=['High', 'Major', 'Critical']
        ).count()
        resolved_count = incidents_on_day.filter(status='Resolved').count()

        weekly_cases.append({
            'day': day.strftime('%a'),  # Mon, Tue, ...
            'minor': minor_count,
            'major': major_count,
            'resolved': resolved_count,
        })

    # ---- 3. Offence Types Distribution ----
    categories = DisciplineCategory.objects.filter(is_active=True)
    total_incidents = DisciplineIncident.objects.count() or 1  # avoid division by zero

    offense_types = []
    for idx, cat in enumerate(categories):
        count = DisciplineIncident.objects.filter(category=cat).count()
        percentage = round((count / total_incidents) * 100, 1)
        offense_types.append({
            'name': cat.category_name,
            'value': percentage,
            'color': COLOR_PALETTE[idx % len(COLOR_PALETTE)],
        })

    # ---- 4. Recent Discipline Cases (last 5) ----
    recent = DisciplineIncident.objects.select_related(
        'student', 'category', 'reported_by'
    ).order_by('-incident_date', '-created_at')[:5]
    recent_serialized = DisciplineIncidentListSerializer(recent, many=True).data

    # ---- 5. Today’s Schedule (counseling sessions + placeholder for meetings) ----
    schedule = []
    for session in today_sessions.select_related('student', 'counselor'):
        schedule.append({
            'time': session.start_time.strftime('%I:%M %p') if session.start_time else '',
            'title': f"Counseling Session - {session.student.first_name} {session.student.last_name}",
            'location': session.location or '',
        })
    # Optionally add a static staff meeting if desired
    schedule.append({
        'time': '2:00 PM',
        'title': 'Staff Meeting - Discipline Review',
        'location': 'Conference Room',
    })

    return Response({
        'success': True,
        'data': {
            'stats': stats,
            'weeklyCases': weekly_cases,
            'offenseTypes': offense_types,
            'recentCases': recent_serialized,
            'todaySchedule': schedule,
        }
    }, status=200)