from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
import logging

from cbe_app.models import Student, Class
from cbe_app.serializers.registrar_serializers.student_admission_serializers import StudentSerializer

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_principal_students(request):
    """
    Returns paginated student list for the Principal portal.

    Query params:
      - search:      name, admission_no, or guardian phone
      - class_id:    filter by class UUID
      - status:      Active | Probation | At Risk
      - page:        default 1
      - page_size:   default 50
    """
    try:
        search = request.query_params.get('search', '').strip()
        class_id = request.query_params.get('class_id')
        status_filter = request.query_params.get('status')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 200)

        qs = Student.objects.filter(archived=False).select_related(
            'current_class'
        ).order_by('current_class__class_name', 'last_name')

        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(middle_name__icontains=search) |
                Q(admission_no__icontains=search) |
                Q(guardian_phone__icontains=search) |
                Q(guardian_name__icontains=search)
            )

        if class_id:
            qs = qs.filter(current_class_id=class_id)

        if status_filter:
            qs = qs.filter(status__iexact=status_filter)

        total = qs.count()
        start = (page - 1) * page_size
        students_page = qs[start:start + page_size]

        # Summary counts (unfiltered by pagination but respecting search/class/status)
        active_count = Student.objects.filter(archived=False, status='Active').count()
        at_risk_count = Student.objects.filter(archived=False, status='At Risk').count()
        probation_count = Student.objects.filter(archived=False, status='Probation').count()
        total_count = Student.objects.filter(archived=False).count()

        data = []
        for s in students_page:
            data.append({
                'id': str(s.id),
                'admission_no': s.admission_no,
                'name': f"{s.first_name} {s.middle_name or ''} {s.last_name}".strip(),
                'first_name': s.first_name,
                'last_name': s.last_name,
                'gender': s.gender,
                'date_of_birth': str(s.date_of_birth) if s.date_of_birth else None,
                'grade': s.current_class.class_name if s.current_class else '—',
                'class_code': s.current_class.class_code if s.current_class else '—',
                'guardian_name': s.guardian_name or '—',
                'guardian_phone': s.guardian_phone or '—',
                'guardian_email': s.guardian_email or '—',
                'address': s.address or '—',
                'status': s.status,
                'admission_date': str(s.admission_date) if s.admission_date else None,
                'upi_number': s.upi_number or '',
            })

        # Classes for filter dropdown
        classes = list(
            Class.objects.filter(is_active=True).values('id', 'class_name', 'class_code').order_by('class_name')
        )
        classes = [
            {'id': str(c['id']), 'class_name': c['class_name'], 'class_code': c['class_code']}
            for c in classes
        ]

        return Response({
            'success': True,
            'data': data,
            'summary': {
                'total': total_count,
                'active': active_count,
                'at_risk': at_risk_count,
                'probation': probation_count,
            },
            'meta': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size,
            },
            'filters': {
                'classes': classes,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Principal students list error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_principal_student_detail(request, student_id):
    """
    Returns full detail for a single student for the modal view.
    """
    try:
        try:
            student = Student.objects.select_related('current_class', 'created_by').get(
                id=student_id, archived=False
            )
        except Student.DoesNotExist:
            return Response({'success': False, 'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StudentSerializer(student)
        return Response({'success': True, 'data': serializer.data}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Principal student detail error: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)