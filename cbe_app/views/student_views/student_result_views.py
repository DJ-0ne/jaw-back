from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cbe_app.models import ExamResult, Student, Exam

import logging
logger = logging.getLogger(__name__)

GRADE_TO_POINTS = {
    'EE1': 8, 'EE2': 7, 'ME1': 6, 'ME2': 5,
    'AE1': 4, 'AE2': 3, 'BE1': 2, 'BE2': 1,
    'EE':  8, 'ME':  6, 'AE':  4, 'BE':  2,
}

PTS_TO_CODE = {
    8: 'EE1', 7: 'EE2', 6: 'ME1', 5: 'ME2',
    4: 'AE1', 3: 'AE2', 2: 'BE1', 1: 'BE2',
}


def grade_to_points(grade_code):
    if not grade_code:
        return None
    return GRADE_TO_POINTS.get(grade_code.upper())


def _build_class_name(student):
    if not student.current_class:
        return 'N/A'
    name = student.current_class.class_name
    if student.current_class.stream:
        name = f"{name} ({student.current_class.stream})"
    return name


def _get_student(request):
    if hasattr(request.user, 'student_profile'):
        return request.user.student_profile, None
    try:
        return Student.objects.select_related('current_class').get(user=request.user), None
    except Student.DoesNotExist:
        logger.warning("No student linked to user %s", request.user.username)
        return None, Response({'success': True, 'data': []})


def _parse_term_id(term_id):
    if '||' not in term_id:
        raise ValueError(f"Invalid term_id: {term_id!r} — expected 'YEAR||TERM'")
    left, right = term_id.split('||', 1)
    return int(left.strip()), int(right.strip())


def _is_teacher_assessment(exam):
    return bool(exam.created_by and hasattr(exam.created_by, 'staff_profile'))


class StudentTermsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            student, err = _get_student(request)
            if err:
                return err

            published_qs = ExamResult.objects.filter(
                student=student,
                exam__status__in=['published', 'completed'],
            ).select_related('exam').order_by('-exam__academic_year', 'exam__term')

            all_statuses = list(
                ExamResult.objects.filter(student=student)
                .values_list('exam__status', flat=True).distinct()
            )
            logger.info(
                "StudentTermsView: student=%s published+completed=%d all_statuses=%s",
                student.admission_no, published_qs.count(), all_statuses,
            )

            if not published_qs.exists():
                return Response({'success': True, 'data': []})

            seen = set()
            data = []
            for result in published_qs:
                exam = result.exam
                key = (exam.academic_year, exam.term)
                if key not in seen:
                    seen.add(key)
                    data.append({
                        'id':            f"{exam.academic_year}||{exam.term}",
                        'term':          f"Term {exam.term}",
                        'academic_year': str(exam.academic_year),
                        'is_current':    False,
                        'start_date':    None,
                        'end_date':      None,
                    })

            data.sort(key=lambda x: (-int(x['academic_year']), int(x['id'].split('||')[1])))
            return Response({'success': True, 'data': data})

        except Exception as e:
            logger.exception("StudentTermsView error")
            return Response({'success': False, 'error': str(e)}, status=500)


class StudentAssessmentWindowsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            term_id = request.query_params.get('term_id', '').strip()
            if not term_id:
                return Response({'success': True, 'data': []})

            try:
                academic_year, term_number = _parse_term_id(term_id)
            except ValueError as e:
                return Response({'success': False, 'error': str(e)}, status=400)

            student, err = _get_student(request)
            if err:
                return err

            exam_ids = ExamResult.objects.filter(
                student=student,
                exam__status__in=['published', 'completed'],
                exam__academic_year=academic_year,
                exam__term=term_number,
            ).values_list('exam_id', flat=True).distinct()

            exams = Exam.objects.filter(
                id__in=exam_ids,
                status__in=['published', 'completed'],
            ).select_related('created_by').order_by('created_at')

            windows = [
                {
                    'id':                    str(exam.id),
                    'assessment_type':       exam.title,
                    'exam_type':             exam.exam_type,
                    'is_teacher_assessment': _is_teacher_assessment(exam),
                    'weight_percentage':     None,
                }
                for exam in exams
            ]

            logger.info("StudentAssessmentWindowsView: term=%s exams=%d", term_id, len(windows))
            return Response({'success': True, 'data': windows})

        except Exception as e:
            logger.exception("StudentAssessmentWindowsView error")
            return Response({'success': False, 'error': str(e)}, status=500)


class StudentResultsPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            student_id = request.query_params.get('student_id', '').strip()
            term_id    = request.query_params.get('term_id', '').strip()
            window_id  = request.query_params.get('window_id', '').strip()

            if not student_id:
                return Response({'success': False, 'error': 'student_id is required'}, status=400)
            if not term_id:
                return Response({'success': False, 'error': 'term_id is required'}, status=400)

            try:
                student = Student.objects.select_related('current_class').get(id=student_id)
            except Student.DoesNotExist:
                return Response({'success': False, 'error': 'Student not found'}, status=404)

            try:
                academic_year, term_number = _parse_term_id(term_id)
            except ValueError as e:
                return Response({'success': False, 'error': str(e)}, status=400)

            logger.info(
                "Preview: student=%s year=%s term=%s window=%r",
                student.admission_no, academic_year, term_number, window_id,
            )

            results_qs = ExamResult.objects.filter(
                student=student,
                exam__status__in=['published', 'completed'],
                exam__academic_year=academic_year,
                exam__term=term_number,
            ).select_related('exam', 'exam__created_by')

            if window_id:
                results_qs = results_qs.filter(exam_id=window_id)

            results_qs = results_qs.order_by('exam__created_at', 'subject', '-marked_at')

            published_count = results_qs.count()
            all_count = ExamResult.objects.filter(
                student=student,
                exam__academic_year=academic_year,
                exam__term=term_number,
            ).count()
            logger.info("Preview: published+completed=%d total_this_term=%d", published_count, all_count)

            empty_shell = {
                'studentName':   student.full_name,
                'admissionNo':   student.admission_no,
                'className':     _build_class_name(student),
                'term':          f"Term {term_number}",
                'academicYear':  str(academic_year),
                'learningAreas': [],
            }

            if not results_qs.exists():
                return Response({'success': True, 'data': empty_shell})

            # ── Key change: group by (exam_id, subject) so each exam's entry
            #   for a subject is kept separate — no cross-exam collapsing. ──
            subject_map = {}
            for result in results_qs:
                key = (str(result.exam_id), result.subject or 'General')
                subject_map.setdefault(key, []).append(result)

            learning_areas = []
            for (exam_id, subj_name), res_list in subject_map.items():
                latest     = res_list[0]
                grade_code = latest.grade
                points     = grade_to_points(grade_code)
                percentage = float(latest.percentage) if latest.percentage else 0

                # Average only within the same (exam, subject) bucket
                if len(res_list) > 1:
                    all_points = [p for r in res_list if (p := grade_to_points(r.grade)) is not None]
                    all_pcts   = [float(r.percentage) for r in res_list if r.percentage]
                    if all_points:
                        avg_pts    = round(sum(all_points) / len(all_points))
                        points     = avg_pts
                        grade_code = PTS_TO_CODE.get(avg_pts, grade_code)
                    if all_pcts:
                        percentage = round(sum(all_pcts) / len(all_pcts), 2)

                exam = latest.exam
                learning_areas.append({
                    'name':                subj_name,
                    'code':                subj_name[:4].upper(),
                    'score':               grade_code,
                    'points':              points,
                    'percentage':          percentage,
                    'teacherComment':      latest.remarks or '',
                    'examTitle':           exam.title if exam else '',
                    'examId':              str(exam.id) if exam else '',
                    'gradeLevel':          exam.grade_level if exam else '',
                    'isTeacherAssessment': _is_teacher_assessment(exam) if exam else False,
                    'markedAt':            latest.marked_at.isoformat() if latest.marked_at else None,
                })

            # Sort: exams first, then assessments; within each group sort by name
            learning_areas.sort(key=lambda x: (x['isTeacherAssessment'], x['examTitle'], x['name']))

            return Response({
                'success': True,
                'data': {**empty_shell, 'learningAreas': learning_areas},
            })

        except Exception as e:
            logger.exception("StudentResultsPreviewView error")
            return Response({'success': False, 'error': str(e)}, status=500)