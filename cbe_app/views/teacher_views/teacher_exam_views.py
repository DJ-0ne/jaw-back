from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import logging

from cbe_app.models import (
    Exam, ExamMarker, ExamModeration, ExamResult, Student, Class,
    Staff, LearningArea, GradeLevel
)

logger = logging.getLogger(__name__)

HARD_LOCKED_STATUSES = {'published', 'archived', 'cancelled'}


def grade_level_to_numeric(grade_level):
    if not grade_level:
        return None
    gl = str(grade_level).strip().lower()
    if gl == 'pp1':
        return 1
    if gl == 'pp2':
        return 2
    try:
        return int(gl) + 2
    except (ValueError, TypeError):
        return None


def resolve_classes_for_exam(exam, classes_map=None):
    if exam.classes and len(exam.classes) > 0:
        uuids = [str(cid) for cid in exam.classes if cid]
        if uuids:
            classes = list(Class.objects.filter(id__in=uuids))
            if classes:
                names = []
                for c in classes:
                    n = c.class_name
                    if c.stream:
                        n = f"{n} ({c.stream})"
                    names.append(n)
                display = ", ".join(names)
                primary_id = str(classes[0].id)
                return classes, display, primary_id

    numeric = grade_level_to_numeric(exam.grade_level)
    if numeric is not None:
        qs = list(Class.objects.filter(
            numeric_level=numeric,
            is_active=True
        ).order_by('stream'))
        if qs:
            base_name = qs[0].class_name
            streams = [c.stream for c in qs if c.stream]
            display = f"{base_name} ({', '.join(streams)})" if streams else base_name
            return qs, display, str(qs[0].id)

    return [], None, None


def compute_grade(percentage, is_upper):
    if is_upper:
        if percentage >= 90: return 'EE1'
        elif percentage >= 75: return 'EE2'
        elif percentage >= 58: return 'ME1'
        elif percentage >= 41: return 'ME2'
        elif percentage >= 31: return 'AE1'
        elif percentage >= 21: return 'AE2'
        elif percentage >= 11: return 'BE1'
        else: return 'BE2'
    else:
        if percentage >= 90: return 'EE'
        elif percentage >= 75: return 'ME'
        elif percentage >= 58: return 'AE'
        else: return 'BE'


def is_upper_grade(grade_level):
    try:
        return int(str(grade_level).strip()) >= 7
    except (ValueError, TypeError):
        return False


def _is_moderator_for_exam(user, exam):
    return ExamModeration.objects.filter(exam=exam, moderator=user).exists()


def _get_moderated_subjects(exam, user):
    """Return the list of subjects already locked by this moderator."""
    moderation_obj = ExamModeration.objects.filter(exam=exam, moderator=user).first()
    if moderation_obj and moderation_obj.moderated_subjects:
        return list(moderation_obj.moderated_subjects)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# LIST VIEW
# ─────────────────────────────────────────────────────────────────────────────

class TeacherExamsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            marker_qs = ExamMarker.objects.filter(
                teacher=request.user
            ).select_related('exam').order_by('-exam__created_at')

            moderation_exam_ids = set(
                ExamModeration.objects.filter(moderator=request.user)
                .values_list('exam_id', flat=True)
            )

            seen_exams = {}

            for marker in marker_qs:
                exam = marker.exam
                if exam.id not in seen_exams:
                    seen_exams[exam.id] = {
                        'exam': exam,
                        'assigned_subjects': [],
                        'finalized_subjects': [],
                        'is_moderator': exam.id in moderation_exam_ids,
                    }
                seen_exams[exam.id]['assigned_subjects'].append(marker.subject)
                if marker.is_finalized:
                    seen_exams[exam.id]['finalized_subjects'].append(marker.subject)

            for mod_exam in Exam.objects.filter(id__in=moderation_exam_ids):
                if mod_exam.id not in seen_exams:
                    seen_exams[mod_exam.id] = {
                        'exam': mod_exam,
                        'assigned_subjects': [],
                        'finalized_subjects': [],
                        'is_moderator': True,
                    }
                else:
                    seen_exams[mod_exam.id]['is_moderator'] = True

            if not seen_exams:
                return Response({'success': True, 'data': [], 'message': 'No exams assigned to you'})

            all_class_ids = []
            for entry in seen_exams.values():
                exam = entry['exam']
                if exam.classes:
                    for cid in exam.classes:
                        try:
                            all_class_ids.append(int(cid))
                        except (ValueError, TypeError):
                            pass

            classes_map = {
                c.id: c for c in Class.objects.filter(id__in=all_class_ids)
            } if all_class_ids else {}

            grade_levels_map = {
                str(gl.level): gl.name
                for gl in GradeLevel.objects.all()
            }

            # Fetch all moderation objects for this user in one query
            moderation_map = {
                str(m.exam_id): m
                for m in ExamModeration.objects.filter(moderator=request.user)
            }

            data = []
            for exam_id, entry in seen_exams.items():
                exam               = entry['exam']
                assigned_subjects  = entry['assigned_subjects']
                finalized_subjects = entry['finalized_subjects']
                is_moderator       = entry['is_moderator']

                classes_list, class_name, class_id = resolve_classes_for_exam(exam, classes_map)

                grade_level_display = grade_levels_map.get(
                    str(exam.grade_level),
                    f"Grade {exam.grade_level}" if exam.grade_level else 'N/A'
                )

                student_count = 0
                if classes_list:
                    student_count = Student.objects.filter(
                        current_class__in=classes_list,
                        status='Active',
                        archived=False
                    ).count()

                teacher_all_finalized = (
                    len(assigned_subjects) > 0 and
                    set(assigned_subjects) == set(finalized_subjects)
                )

                display_subjects = assigned_subjects or list(
                    ExamMarker.objects.filter(exam=exam)
                    .values_list('subject', flat=True)
                    .distinct()
                )

                # Include moderated_subjects for moderators
                moderation_obj = moderation_map.get(str(exam.id))
                moderated_subjects = list(moderation_obj.moderated_subjects or []) if moderation_obj else []

                data.append({
                    'id':                    str(exam.id),
                    'exam_code':             exam.exam_code,
                    'title':                 exam.title,
                    'exam_type':             exam.exam_type,
                    'grade_level':           exam.grade_level,
                    'grade_level_display':   grade_level_display,
                    'academic_year':         exam.academic_year,
                    'term':                  exam.term,
                    'total_marks':           exam.total_marks,
                    'passing_marks':         exam.passing_marks,
                    'status':                exam.status,
                    'start_date':            exam.start_date,
                    'end_date':              exam.end_date,
                    'class_id':              class_id,
                    'className':             class_name or grade_level_display,
                    'subjects':              exam.subjects,
                    'assigned_subject':      display_subjects[0] if len(display_subjects) == 1 else None,
                    'assigned_subjects':     display_subjects,
                    'finalized_subjects':    finalized_subjects,
                    'moderated_subjects':    moderated_subjects,
                    'teacher_all_finalized': teacher_all_finalized,
                    'is_moderator':          is_moderator,
                    'students_count':        ExamResult.objects.filter(
                        exam=exam,
                        subject__in=(display_subjects or [])
                    ).values('student').distinct().count(),
                    'total_students':        student_count,
                })

            return Response({'success': True, 'data': data, 'message': f'Found {len(data)} exams'})

        except Exception as e:
            logger.error(f"TeacherExamsListView error: {str(e)}", exc_info=True)
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# SCORES VIEW
# ─────────────────────────────────────────────────────────────────────────────

class TeacherExamScoresView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        try:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'success': False, 'data': [], 'message': 'Exam not found'}, status=404)

            is_moderator = _is_moderator_for_exam(request.user, exam)
            marker_qs    = ExamMarker.objects.filter(exam=exam, teacher=request.user)
            is_marker    = marker_qs.exists()

            if not is_marker and not is_moderator:
                return Response({
                    'success': False, 'data': [],
                    'message': 'You are not assigned to mark or moderate this exam'
                }, status=403)

            requested_subject = request.query_params.get('subject', '').strip()

            if is_marker and not is_moderator:
                assigned_subjects  = list(marker_qs.values_list('subject', flat=True))
                finalized_subjects = list(marker_qs.filter(is_finalized=True).values_list('subject', flat=True))

                if requested_subject:
                    if requested_subject not in assigned_subjects:
                        return Response({
                            'success': False, 'data': [],
                            'message': f'You are not assigned to mark "{requested_subject}"'
                        }, status=403)
                    active_subject = requested_subject
                elif len(assigned_subjects) == 1:
                    active_subject = assigned_subjects[0]
                else:
                    return Response({
                        'success': False, 'data': [],
                        'message': 'Please specify which subject via ?subject=<name>',
                        'assigned_subjects': assigned_subjects,
                    }, status=400)

                active_marker             = marker_qs.filter(subject=active_subject).first()
                teacher_subject_finalized = bool(active_marker and active_marker.is_finalized)
                teacher_all_finalized     = (
                    set(assigned_subjects) == set(finalized_subjects)
                    and len(assigned_subjects) > 0
                )
                moderated_subjects = []

            else:
                # Moderator path
                all_subjects = list(
                    ExamMarker.objects.filter(exam=exam)
                    .values_list('subject', flat=True)
                    .distinct()
                )
                if not requested_subject:
                    if len(all_subjects) == 1:
                        requested_subject = all_subjects[0]
                    else:
                        return Response({
                            'success': False, 'data': [],
                            'message': 'Please specify which subject via ?subject=<name>',
                            'assigned_subjects': all_subjects,
                        }, status=400)

                active_subject     = requested_subject
                assigned_subjects  = all_subjects
                finalized_subjects = list(
                    ExamMarker.objects.filter(exam=exam, is_finalized=True)
                    .values_list('subject', flat=True).distinct()
                )
                # Moderators are never locked by finalization — only by their own moderated_subjects
                teacher_subject_finalized = False
                teacher_all_finalized     = False
                # Fetch this moderator's already-locked subjects
                moderated_subjects = _get_moderated_subjects(exam, request.user)

            # ── Fetch students and scores ─────────────────────────────────────
            classes_list, class_name, class_id = resolve_classes_for_exam(exam)

            if not classes_list:
                return Response({
                    'success': True, 'data': [], 'className': None,
                    'maxScore': exam.total_marks, 'subject': active_subject,
                    'teacher_subject_finalized': teacher_subject_finalized,
                    'teacher_all_finalized':     teacher_all_finalized,
                    'finalized_subjects':        finalized_subjects,
                    'assigned_subjects':         assigned_subjects,
                    'moderated_subjects':        moderated_subjects,
                    'is_moderator':              is_moderator,
                    'message': 'No classes found for this exam.',
                })

            students = Student.objects.filter(
                current_class__in=classes_list,
                status='Active',
                archived=False
            ).select_related('current_class').order_by(
                'current_class__stream', 'first_name', 'last_name'
            )

            results = {
                r.student_id: r
                for r in ExamResult.objects.filter(exam=exam, subject=active_subject)
            }

            upper = is_upper_grade(exam.grade_level)

            data = []
            for student in students:
                result     = results.get(student.id)
                percentage = float(result.percentage) if result and result.percentage else 0
                grade      = None
                if result and result.marks_obtained is not None:
                    grade = compute_grade(percentage, upper)

                data.append({
                    'student_id':   str(student.id),
                    'admission_no': student.admission_no,
                    'first_name':   student.first_name,
                    'last_name':    student.last_name,
                    'stream':       student.current_class.stream if student.current_class else None,
                    'score':        float(result.marks_obtained) if result and result.marks_obtained is not None else None,
                    'percentage':   percentage,
                    'grade':        grade,
                    'is_absent':    bool(result and result.marks_obtained is None and result.grade == 'AB'),
                })

            return Response({
                'success':                   True,
                'data':                      data,
                'className':                 class_name,
                'maxScore':                  exam.total_marks,
                'subject':                   active_subject,
                'assigned_subjects':         assigned_subjects,
                'finalized_subjects':        finalized_subjects,
                'moderated_subjects':        moderated_subjects,
                'teacher_subject_finalized': teacher_subject_finalized,
                'teacher_all_finalized':     teacher_all_finalized,
                'is_moderator':              is_moderator,
                'message':                   f'Found {len(data)} students',
            })

        except Exception as e:
            logger.error(f"TeacherExamScoresView error: {str(e)}", exc_info=True)
            return Response({'success': False, 'data': [], 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# BULK SAVE
# ─────────────────────────────────────────────────────────────────────────────

class TeacherExamScoresBulkSaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        try:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'success': False, 'message': 'Exam not found'}, status=404)

            if exam.status in HARD_LOCKED_STATUSES:
                return Response({
                    'success': False,
                    'message': f'This exam is {exam.status}. Marks can no longer be edited.'
                }, status=403)

            is_moderator = _is_moderator_for_exam(request.user, exam)
            marker_qs    = ExamMarker.objects.filter(exam=exam, teacher=request.user)
            is_marker    = marker_qs.exists()

            if not is_marker and not is_moderator:
                return Response({'success': False, 'message': 'You are not assigned to this exam'}, status=403)

            requested_subject = (request.data.get('subject') or '').strip()

            if is_moderator:
                all_subjects = list(
                    ExamMarker.objects.filter(exam=exam)
                    .values_list('subject', flat=True)
                    .distinct()
                )
                if requested_subject:
                    active_subject = requested_subject
                elif len(all_subjects) == 1:
                    active_subject = all_subjects[0]
                else:
                    return Response({
                        'success': False,
                        'message': 'Please include "subject" in the request body.',
                        'assigned_subjects': all_subjects,
                    }, status=400)

                # Check if moderator already locked this subject
                current_moderated = _get_moderated_subjects(exam, request.user)
                if active_subject in current_moderated:
                    return Response({
                        'success': False,
                        'message': f'"{active_subject}" has already been moderated and locked.'
                    }, status=403)

            else:
                # Pure marker path
                assigned_subjects = list(marker_qs.values_list('subject', flat=True))

                if requested_subject:
                    if requested_subject not in assigned_subjects:
                        return Response({
                            'success': False,
                            'message': f'You are not assigned to mark "{requested_subject}" for this exam'
                        }, status=403)
                    active_subject = requested_subject
                elif len(assigned_subjects) == 1:
                    active_subject = assigned_subjects[0]
                else:
                    return Response({
                        'success': False,
                        'message': 'Please include "subject" in the request body.',
                        'assigned_subjects': assigned_subjects,
                    }, status=400)

                active_marker = marker_qs.filter(subject=active_subject).first()
                if active_marker and active_marker.is_finalized:
                    return Response({
                        'success': False,
                        'message': f'You have already finalized "{active_subject}". Marks are locked.'
                    }, status=403)

            upper       = is_upper_grade(exam.grade_level)
            scores_data = request.data.get('scores', [])
            saved_count = 0

            for score_item in scores_data:
                student_id = score_item.get('student_id')
                score      = score_item.get('score')
                is_absent  = score_item.get('is_absent', False)

                try:
                    student = Student.objects.get(id=student_id)
                except Student.DoesNotExist:
                    continue

                if is_absent:
                    marks_obtained = None
                    percentage     = None
                    grade          = 'AB'
                else:
                    marks_obtained = float(score) if score is not None else None
                    if marks_obtained is not None and exam.total_marks > 0:
                        percentage = (marks_obtained / exam.total_marks) * 100
                        grade      = compute_grade(percentage, upper)
                    else:
                        percentage = None
                        grade      = None

                ExamResult.objects.update_or_create(
                    exam=exam,
                    student=student,
                    subject=active_subject,
                    defaults={
                        'marks_obtained': marks_obtained,
                        'percentage':     round(percentage, 2) if percentage is not None else None,
                        'grade':          grade,
                        'marked_by':      request.user,
                        'marked_at':      timezone.now(),
                    }
                )
                saved_count += 1

            # ── Moderator: lock this subject ──────────────────────────────────
            if is_moderator:
                moderation_obj, _ = ExamModeration.objects.get_or_create(
                    exam=exam,
                    moderator=request.user,
                    defaults={'notes': '', 'approved': False}
                )
                current_moderated = list(moderation_obj.moderated_subjects or [])
                if active_subject not in current_moderated:
                    current_moderated.append(active_subject)
                moderation_obj.moderated_subjects = current_moderated
                moderation_obj.save()

                # Determine all subjects on the exam
                all_exam_subjects = list(
                    ExamMarker.objects.filter(exam=exam)
                    .values_list('subject', flat=True)
                    .distinct()
                )
                all_moderated = (
                    len(all_exam_subjects) > 0 and
                    set(all_exam_subjects) == set(current_moderated)
                )

                if all_moderated:
                    exam.status = 'published'
                    exam.save()
                    message = 'All subjects moderated — exam published!'
                else:
                    remaining = len(all_exam_subjects) - len(current_moderated)
                    message = f'"{active_subject}" locked. {remaining} subject(s) remaining.'

                return Response({
                    'success':            True,
                    'message':            message,
                    'saved_count':        saved_count,
                    'subject':            active_subject,
                    'moderated_subjects': current_moderated,
                    'exam_status':        exam.status,
                    'all_moderated':      all_moderated,
                })

            # ── Marker: advance exam status if needed ─────────────────────────
            if exam.status in ('scheduled', 'live') and saved_count > 0:
                exam.status = 'marking'
                exam.save()

            return Response({
                'success':     True,
                'message':     f'Saved {saved_count} scores for {active_subject}',
                'saved_count': saved_count,
                'subject':     active_subject,
            })

        except Exception as e:
            logger.error(f"TeacherExamScoresBulkSaveView error: {str(e)}", exc_info=True)
            return Response({'success': False, 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# FINALIZE
# ─────────────────────────────────────────────────────────────────────────────

class TeacherExamFinalizeView(APIView):
    """
    Marks ALL of this teacher's ExamMarker rows for the exam as finalized.
    The exam moves to 'moderation' only when every ExamMarker across ALL
    teachers is finalized.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        try:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'success': False, 'message': 'Exam not found'}, status=404)

            my_markers = ExamMarker.objects.filter(exam=exam, teacher=request.user)
            if not my_markers.exists():
                return Response({'success': False, 'message': 'You are not assigned to this exam'}, status=403)

            if exam.status in HARD_LOCKED_STATUSES:
                return Response({
                    'success': False,
                    'message': f'This exam is {exam.status} and cannot be finalized.'
                }, status=403)

            already_done = my_markers.filter(is_finalized=False).count() == 0
            if already_done:
                return Response({
                    'success': False,
                    'message': 'You have already finalized all your subjects for this exam.'
                }, status=400)

            now = timezone.now()
            my_markers.update(is_finalized=True, finalized_at=now)

            finalized_subjects = list(my_markers.values_list('subject', flat=True))

            total_markers     = ExamMarker.objects.filter(exam=exam).count()
            finalized_markers = ExamMarker.objects.filter(exam=exam, is_finalized=True).count()
            all_done          = (total_markers > 0) and (finalized_markers >= total_markers)

            if all_done:
                exam.status = 'moderation'
                exam.save()
                return Response({
                    'success':            True,
                    'message':            'All teachers have finalized. Exam submitted for moderation.',
                    'finalized_subjects': finalized_subjects,
                    'exam_status':        'moderation',
                    'all_done':           True,
                })
            else:
                pending = total_markers - finalized_markers
                return Response({
                    'success':            True,
                    'message':            (
                        f'Your marks for {", ".join(finalized_subjects)} are locked. '
                        f'{pending} other subject(s) still need to be finalized before moderation begins.'
                    ),
                    'finalized_subjects': finalized_subjects,
                    'exam_status':        exam.status,
                    'all_done':           False,
                })

        except Exception as e:
            logger.error(f"TeacherExamFinalizeView error: {str(e)}", exc_info=True)
            return Response({'success': False, 'error': str(e)}, status=500)