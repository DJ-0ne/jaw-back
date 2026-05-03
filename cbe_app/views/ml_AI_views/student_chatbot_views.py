"""
GET  /api/student/chatbot/analytics/  → CBC analytics for the dashboard
POST /api/student/chatbot/message/    → AI chat response
"""

import json
import logging
from django.db.models import Sum
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from cbe_app.models import (
    Student, StudentFeeInvoice, StudentAttendance,
    ExamResult, DisciplineIncident,
    # FIX: added the two models that were missing from imports
    StudentDisciplinePoints, Suspension,
)
from cbe_app.utils.ai_provider import call_ai

logger = logging.getLogger(__name__)

# ─── Scale definitions ───────────────────────────────────────────────────────
FOUR_POINT_GRADE_TO_POINTS = {'EE': 4, 'ME': 3, 'AE': 2, 'BE': 1}
FOUR_POINT_PTS_TO_CODE     = {4: 'EE', 3: 'ME', 2: 'AE', 1: 'BE'}
EIGHT_POINT_GRADE_TO_POINTS = {
    'EE1': 8, 'EE2': 7, 'ME1': 6, 'ME2': 5,
    'AE1': 4, 'AE2': 3, 'BE1': 2, 'BE2': 1,
}
EIGHT_POINT_PTS_TO_CODE = {
    8: 'EE1', 7: 'EE2', 6: 'ME1', 5: 'ME2',
    4: 'AE1', 3: 'AE2', 2: 'BE1', 1: 'BE2',
}
FOUR_POINT_LEVELS = {'pp1', 'pp2', '1', '2', '3', '4', '5', '6'}

# ─── Statuses that mean a discipline case is still OPEN ──────────────────────
# FIX: mirrors the logic in get_discipline_stats which uses
#      .exclude(status__in=['Resolved', 'Closed']) so that any future
#      status values are still captured correctly.
CLOSED_DISCIPLINE_STATUSES = {'Resolved', 'Closed'}

# ─── Pathway keyword map ─────────────────────────────────────────────────────
PATHWAY_KEYWORDS = {
    'STEM': [
        'math', 'maths', 'mathematics', 'science', 'physics', 'chemistry',
        'biology', 'computer', 'ict', 'technology', 'engineering',
    ],
    'Humanities & Social Sciences': [
        'history', 'geography', 'geo', 'cre', 'christian', 'ire', 'islamic',
        'social', 'civic', 'government', 'politics',
    ],
    'Business & Commerce': [
        'business', 'commerce', 'economics', 'accounting', 'finance',
        'entrepreneurship',
    ],
    'Languages & Literature': [
        'english', 'kiswahili', 'swahili', 'french', 'german', 'arabic',
        'literature', 'language', 'writing', 'reading',
    ],
    'Creative Arts & Design': [
        'art', 'music', 'home science', 'drama', 'craft', 'design',
        'textile', 'drawing', 'creative',
    ],
    'Health Sciences': [
        'biology', 'health', 'nutrition', 'physical education', 'pe',
        'anatomy', 'chemistry',
    ],
}


def _four_point_code(pct):
    if pct >= 90: return 'EE'
    if pct >= 75: return 'ME'
    if pct >= 58: return 'AE'
    return 'BE'


def _eight_point_code(pct):
    if pct >= 90: return 'EE1'
    if pct >= 75: return 'EE2'
    if pct >= 58: return 'ME1'
    if pct >= 41: return 'ME2'
    if pct >= 31: return 'AE1'
    if pct >= 21: return 'AE2'
    if pct >= 11: return 'BE1'
    return 'BE2'


def get_cbc_grade_level(student):
    if not student.current_class:
        return ''
    nl = student.current_class.numeric_level
    mapping = {1: 'pp1', 2: 'pp2'}
    return mapping.get(nl, str(nl - 2))


def grade_code_from_pct(pct, grade_level):
    gl = str(grade_level).lower().strip()
    return _four_point_code(pct) if gl in FOUR_POINT_LEVELS else _eight_point_code(pct)


def grade_to_points(code, grade_level=''):
    if not code:
        return 0
    gl = str(grade_level).lower().strip()
    if gl in FOUR_POINT_LEVELS:
        return FOUR_POINT_GRADE_TO_POINTS.get(code.upper(), 0)
    if len(code) == 2 and code.upper() in FOUR_POINT_GRADE_TO_POINTS:
        return FOUR_POINT_GRADE_TO_POINTS[code.upper()]
    return EIGHT_POINT_GRADE_TO_POINTS.get(code.upper(), 0)


def points_to_code(points, grade_level=''):
    if not points or points <= 0:
        return None
    gl = str(grade_level).lower().strip()
    if gl in FOUR_POINT_LEVELS:
        return FOUR_POINT_PTS_TO_CODE.get(points)
    return EIGHT_POINT_PTS_TO_CODE.get(points)


def get_risk_level(value, low_max, medium_max):
    if value <= low_max:    return "low"
    if value <= medium_max: return "medium"
    return "high"


def _is_teacher_result(result):
    """True when the exam was created by a teacher (has staff_profile)."""
    try:
        return bool(result.exam.created_by and hasattr(result.exam.created_by, 'staff_profile'))
    except Exception:
        return False


# ─── Career pathway calculator ───────────────────────────────────────────────

def compute_pathways(competencies):
    pathway_buckets = {name: [] for name in PATHWAY_KEYWORDS}

    for comp in competencies:
        name_lower = comp['name'].lower()
        for pathway, keywords in PATHWAY_KEYWORDS.items():
            if any(kw in name_lower for kw in keywords):
                pathway_buckets[pathway].append(comp)

    pathways = []
    for pathway_name, matched in pathway_buckets.items():
        if not matched:
            continue
        avg_mastery = round(sum(c['mastery'] for c in matched) / len(matched), 1)
        subject_names = [c['name'] for c in matched][:3]
        pathways.append({
            'name':         pathway_name,
            'match':        avg_mastery,
            'competencies': subject_names,
        })

    pathways.sort(key=lambda x: x['match'], reverse=True)
    return pathways[:4]


# ─── Discipline helper ────────────────────────────────────────────────────────

def build_discipline_summary(student):
    """
    Return a rich discipline summary so that both the dashboard and Jawabu
    have accurate, complete information.

    Data collected:
      - open_discipline_cases   : incidents NOT in Resolved / Closed
      - discipline_points       : total points accumulated this academic year
      - discipline_status       : Good / Warning / Probation / Suspension
                                  (from StudentDisciplinePoints)
      - active_suspensions      : count of Pending + Active suspensions
      - suspension_detail       : list of active/pending suspension records
    """
    current_year = str(timezone.now().year)

    # ── 1. Open incidents (mirrors get_discipline_stats logic) ───────────────
    # FIX: was previously a hard-coded whitelist ["Reported", "Under Investigation"]
    # which would miss any other active status.  Now we exclude closed statuses
    # so new statuses added in the future are captured automatically.
    open_cases_qs = DisciplineIncident.objects.filter(
        student=student
    ).exclude(status__in=CLOSED_DISCIPLINE_STATUSES)
    open_cases = open_cases_qs.count()

    # ── 2. Discipline points — sum directly from DisciplineIncident ─────────────
    # Root cause of the 420-vs-60 bug: StudentDisciplinePoints.total_points is a
    # denormalised running counter incremented on every case save.  If an incident
    # is re-saved or the signal fires more than once the counter overshoots
    # (e.g. 7 x 60 = 420 for a single 60-point incident).
    #
    # student_serializers.get_discipline_records avoids this by aggregating directly:
    #   incidents.aggregate(total=Sum('points_awarded'))['total']
    # We do the same, scoped to the current academic year.
    all_incidents_qs = DisciplineIncident.objects.filter(
        student=student,
        incident_date__year=int(current_year),
    )
    total_points_this_year = (
        all_incidents_qs.aggregate(total=Sum('points_awarded'))['total'] or 0
    )

    # Derive standing label from computed points using the same thresholds as
    # create_discipline_case in deputy_views — avoids stale StudentDisciplinePoints.
    if total_points_this_year >= 50:
        discipline_status = 'Suspension'
    elif total_points_this_year >= 40:
        discipline_status = 'Probation'
    elif total_points_this_year > 30:
        discipline_status = 'Warning'
    else:
        discipline_status = 'Good'

    # ── 3. Active / pending suspensions ──────────────────────────────────────
    # FIX: was never queried — chatbot could not tell a student they were suspended.
    active_suspension_qs = Suspension.objects.filter(
        student=student,
        status__in=['Pending', 'Active'],
    ).order_by('-start_date')

    active_suspensions = active_suspension_qs.count()

    suspension_detail = []
    for s in active_suspension_qs:
        suspension_detail.append({
            'type':             s.suspension_type,
            'status':           s.status,
            'start_date':       str(s.start_date),
            'end_date':         str(s.end_date),
            'reason':           s.reason,
            'parent_notified':  s.parent_notified,
        })

    return {
        'open_discipline_cases': open_cases,
        'discipline_points':     total_points_this_year,
        'discipline_status':     discipline_status,   # Good / Warning / Probation / Suspension
        'active_suspensions':    active_suspensions,
        'suspension_detail':     suspension_detail,
    }


# ─── System prompt ────────────────────────────────────────────────────────────

CBC_SYSTEM_PROMPT = """
You are Jawabu, an expert CBC (Competency-Based Curriculum) Academic Assistant for a Kenyan school.

IMPORTANT — HOW MARKS ARE STRUCTURED
======================================
A student's performance comes from TWO separate sources. Always explain this clearly when discussing results:

1. FORMAL EXAMS (set by the school registrar/administration)
   - These are official school exams: Mid-Term, End-Term, JESMA, Mathematics exams, etc.
   - They are set and approved at the school level.
   - They carry significant weight in a student's term performance.

2. CLASS ASSESSMENTS (set by individual subject teachers)
   - These are smaller, ongoing tests: CATs (Continuous Assessment Tests), assignments, projects.
   - They are set by each teacher for their subject.
   - Examples: "English Cat", "Maths Cat", "Science Assignment".
   - They test day-to-day understanding and practical skills.

Both are graded using the CBC competency scale below, but they are SEPARATE and shown separately on the dashboard.

CBC GRADING SCALE
==================
Grades PP1 – Grade 6 (4-point scale):
  EE = Exceeding Expectations   (90–100%) — 4 points
  ME = Meeting Expectations     (75–89%)  — 3 points
  AE = Approaching Expectations (58–74%)  — 2 points
  BE = Below Expectations       (0–57%)   — 1 point

Grades 7 – 9 (8-point scale):
  EE1 = Exceptional       (90–100%) — 8 points
  EE2 = Very Good         (75–89%)  — 7 points
  ME1 = Good              (58–74%)  — 6 points
  ME2 = Fair              (41–57%)  — 5 points
  AE1 = Needs Improvement (31–40%)  — 4 points
  AE2 = Below Average     (21–30%)  — 3 points
  BE1 = Well Below        (11–20%)  — 2 points
  BE2 = Minimal           (0–10%)   — 1 point

HOW TO INTERPRET RESULTS
=========================
- The "Overall Competency" shown is an average across all subjects for the latest term.
- The "Performance Trend" card is split into two sections:
    Formal Exam Trend — shows official school exam performance each term.
    Class Assessment Trend — shows teacher-set assessment performance each term.
  A student may score differently in each — this is NORMAL.
- Each subject shows its grade code (e.g. ME1), the percentage, and the points earned.

HANDLING TERM HISTORY
======================
When a student asks about their past performance per term, use the "exam_trend" and "assessment_trend"
arrays in the analytics. Each entry contains the term and the average score. Explain what the numbers
mean and encourage them to look at the trend chart for a visual overview.

STUDENT DISCIPLINE — FULL PICTURE
===================================
The analytics now provides four discipline fields. Always use ALL of them together for an accurate picture:

  open_discipline_cases  — number of incidents not yet resolved or closed.
  discipline_points      — cumulative discipline points earned this academic year (higher = more serious).
  discipline_status      — the school's official standing: Good, Warning, Probation, or Suspension.
  active_suspensions     — number of suspensions currently Pending or Active.
  suspension_detail      — list of active suspension records with type, dates, and reason.

Rules for mentioning discipline:
  - If discipline_status is "Good" AND open_discipline_cases is 0 AND active_suspensions is 0,
    do NOT mention discipline at all.
  - If discipline_status is "Warning" or open_discipline_cases > 0, gently inform the student and
    advise them to speak to their class teacher to resolve the matter before points escalate further.
  - If discipline_status is "Probation", treat this as serious. Clearly tell the student they are on
    probation due to accumulated discipline points and advise them to urgently speak with the
    Deputy Headteacher.
  - If discipline_status is "Suspension" OR active_suspensions > 0, clearly inform the student that
    there is an active or pending suspension on their record. Provide the suspension type, dates, and
    reason from suspension_detail. Advise them that their parent/guardian must be involved and that
    they must report to the Deputy Headteacher immediately.
  - Always mention the discipline_points total when the status is anything other than "Good", so the
    student understands the cumulative weight of their record.

DISCIPLINE POINTS SCALE (for reference when explaining to a student):
  0 – 30 points  : Good standing
  31 – 39 points : Warning issued
  40 – 49 points : Probation
  50+ points     : Suspension threshold

RECOMMENDED STUDY PATHWAYS
===========================
When a student asks about their future study pathway, use the provided analytics data to analyse
their strengths and weaknesses. The dashboard already shows computed pathway matches based on their
subject scores. Reference those pathways in your response and explain why each fits.

Pathway examples: STEM, Humanities & Social Sciences, Business & Commerce,
Creative Arts & Design, Languages & Literature, Health Sciences.

Give a concise, personalised recommendation and encourage the student to discuss their interests
with their teachers and parents.

COMMON COMPLAINTS AND HOW TO RESPOND
======================================
- "My marks are wrong": Ask which specific subject/assessment they are querying and advise them to speak to the relevant teacher or registrar.
- "Why are my assessment marks not showing?": Teacher assessments only appear once published.
- "My average seems low": The average covers only subjects assessed so far in the term.

Always be encouraging, reference the student by name when provided, give specific actionable advice,
and respond in plain text without markdown symbols.
""".strip()

# ─── Analytics builder ───────────────────────────────────────────────────────

def build_analytics(student):
    student_name    = f"{student.user.first_name} {student.user.last_name}".strip()
    student_class   = student.current_class.class_name if student.current_class else ""
    admission_no    = getattr(student, "admission_no", "") or ""
    grade_level_str = get_cbc_grade_level(student)

    all_results = ExamResult.objects.filter(
        student=student,
        exam__status__in=['published', 'completed'],
    ).select_related('exam', 'exam__created_by').order_by(
        '-exam__academic_year', '-exam__term', '-marked_at'
    )

    if not all_results.exists():
        discipline = build_discipline_summary(student)
        return _empty_analytics(student_name, student_class, admission_no, discipline)

    # ── Latest term competencies ──────────────────────────────────────────
    latest_term_key = (all_results[0].exam.academic_year, all_results[0].exam.term)
    latest_results  = [r for r in all_results if (r.exam.academic_year, r.exam.term) == latest_term_key]

    subject_buckets = {}
    for r in latest_results:
        key = (str(r.exam_id), r.subject or 'General')
        subject_buckets.setdefault(key, []).append(r)

    competencies  = []
    total_pct     = 0
    total_points  = 0

    for (_, subj_name), res_list in subject_buckets.items():
        latest = res_list[0]
        pct    = float(latest.percentage) if latest.percentage else 0
        stored = latest.grade
        valid  = {'EE', 'ME', 'AE', 'BE', 'EE1', 'EE2', 'ME1', 'ME2', 'AE1', 'AE2', 'BE1', 'BE2'}
        code   = stored.upper() if stored and stored.upper() in valid else grade_code_from_pct(pct, grade_level_str)
        pts    = grade_to_points(code, grade_level_str)
        is_ta  = _is_teacher_result(latest)

        competencies.append({
            "name":                  subj_name,
            "mastery":               round(pct, 1),
            "grade":                 code,
            "points":                pts,
            "exam_title":            latest.exam.title if latest.exam else "",
            "is_teacher_assessment": is_ta,
        })
        total_pct    += pct
        total_points += pts

    counts         = len(competencies)
    overall        = round(total_pct / counts, 1) if counts else 0
    overall_points = round(total_points / counts, 1) if counts else 0
    overall_code   = points_to_code(round(overall_points), grade_level_str) if counts else 'BE2'

    # ── Performance trend — SPLIT into exam vs assessment ─────────────────
    all_chrono = list(all_results.order_by('exam__academic_year', 'exam__term', 'exam__created_at'))

    term_exam_data   = {}
    term_assess_data = {}

    for r in all_chrono:
        key = (r.exam.academic_year, r.exam.term)
        if _is_teacher_result(r):
            term_assess_data.setdefault(key, []).append(r)
        else:
            term_exam_data.setdefault(key, []).append(r)

    def _make_trend(term_dict):
        trend = []
        for (year, term_no), results in sorted(term_dict.items()):
            pcts = [float(r.percentage) for r in results if r.percentage]
            if pcts:
                avg = round(sum(pcts) / len(pcts), 1)
                trend.append({"term": f"Term {term_no} ({year})", "value": avg})
        return trend

    exam_trend       = _make_trend(term_exam_data)
    assessment_trend = _make_trend(term_assess_data)

    # ── Fee / Attendance ──────────────────────────────────────────────────
    invoices     = StudentFeeInvoice.objects.filter(student=student)
    total_fees   = invoices.aggregate(t=Sum("total_amount"))["t"] or 0
    total_paid   = invoices.aggregate(t=Sum("amount_paid"))["t"] or 0
    fee_balance  = round(float(total_fees - total_paid), 2)
    today        = timezone.now().date()
    overdue_amount = float(
        invoices.filter(due_date__lt=today, balance_amount__gt=0)
        .aggregate(t=Sum("balance_amount"))["t"] or 0
    )

    att_qs          = StudentAttendance.objects.filter(student=student)
    total_sessions  = att_qs.count()
    present         = att_qs.filter(attendance_status="Present").count()
    attendance_rate = round(present / total_sessions * 100, 1) if total_sessions > 0 else 0

    # ── Discipline — full summary ─────────────────────────────────────────
    # FIX: replaced the old single-line count with the new helper that
    # also captures discipline points, status, and active suspensions.
    discipline = build_discipline_summary(student)

    # ── Risks ─────────────────────────────────────────────────────────────
    weak_areas  = [c for c in competencies if c["mastery"] < 41]
    failure_pct = round(len(weak_areas) / max(counts, 1) * 100, 1)
    dropout_pct = max(0.0, round(100 - attendance_rate - 10, 1))

    risks = {
        "failure_risk": {
            "level":       get_risk_level(failure_pct, 20, 40),
            "value":       f"{failure_pct}%",
            "description": "Probability of not meeting competency standards",
        },
        "dropout_risk": {
            "level":       get_risk_level(dropout_pct, 15, 35),
            "value":       f"{dropout_pct}%",
            "description": "Likelihood of discontinuing studies",
        },
        "intervention_needed": {
            "level":       get_risk_level(len(weak_areas), 2, 4),
            "value":       str(len(weak_areas)),
            "description": "Competency areas requiring attention",
        },
    }

    # ── Career pathways ───────────────────────────────────────────────────
    career_pathways = compute_pathways(competencies)

    return {
        "student_name":          student_name,
        "student_class":         student_class,
        "admission_no":          admission_no,
        "overall_competency":    overall,
        "competency_level":      overall_code,
        "exam_trend":            exam_trend,
        "assessment_trend":      assessment_trend,
        "performance_trend":     exam_trend + assessment_trend,
        "competencies":          competencies,
        "risks":                 risks,
        "career_pathways":       career_pathways,
        "fee_balance":           fee_balance,
        "overdue_amount":        overdue_amount,
        "attendance_rate":       attendance_rate,
        # ── Discipline fields (expanded) ──────────────────────────────────
        "open_discipline_cases": discipline["open_discipline_cases"],
        "discipline_points":     discipline["discipline_points"],
        "discipline_status":     discipline["discipline_status"],
        "active_suspensions":    discipline["active_suspensions"],
        "suspension_detail":     discipline["suspension_detail"],
    }


def _empty_analytics(name, cls, adm_no, discipline=None):
    if discipline is None:
        discipline = {
            "open_discipline_cases": 0,
            "discipline_points":     0,
            "discipline_status":     "Good",
            "active_suspensions":    0,
            "suspension_detail":     [],
        }
    return {
        "student_name":          name,
        "student_class":         cls,
        "admission_no":          adm_no,
        "overall_competency":    0,
        "competency_level":      'BE2',
        "exam_trend":            [],
        "assessment_trend":      [],
        "performance_trend":     [],
        "competencies":          [],
        "risks": {
            "failure_risk":        {"level": "low", "value": "0%", "description": "No data yet"},
            "dropout_risk":        {"level": "low", "value": "0%", "description": "No data yet"},
            "intervention_needed": {"level": "low", "value": "0",  "description": "No data yet"},
        },
        "career_pathways":       [],
        "fee_balance":           0,
        "overdue_amount":        0,
        "attendance_rate":       0,
        # Discipline
        "open_discipline_cases": discipline["open_discipline_cases"],
        "discipline_points":     discipline["discipline_points"],
        "discipline_status":     discipline["discipline_status"],
        "active_suspensions":    discipline["active_suspensions"],
        "suspension_detail":     discipline["suspension_detail"],
    }


# ─── Prompt builder ──────────────────────────────────────────────────────────

def build_prompt(message, context, history, analytics):
    parts = []
    if context:
        lines = ["[Student Context]"]
        for key, label in [("student_name", "Name"), ("student_class", "Class"), ("admission_no", "Admission No")]:
            if context.get(key):
                lines.append(f"{label}: {context[key]}")
        parts.append("\n".join(lines))
    if analytics:
        parts.append(f"[Live Student Analytics]\n{json.dumps(analytics, indent=2)}")
    if history:
        parts.append("[Conversation History]")
        for turn in history:
            role = "Student" if turn.get("role") == "user" else "Assistant"
            parts.append(f"{role}: {turn.get('content', '')}")
    parts.append(f"[Current Message]\nStudent: {message}\nAssistant:")
    return "\n\n".join(parts)


# ─── Views ────────────────────────────────────────────────────────────────────

class ChatbotAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            student = Student.objects.select_related("user", "current_class").get(
                user=request.user, archived=False
            )
        except Student.DoesNotExist:
            return Response({"success": False, "error": "Student profile not found."}, status=404)
        except Exception as e:
            logger.error(f"Student lookup error: {e}")
            return Response({"success": False, "error": str(e)}, status=500)

        try:
            data = build_analytics(student)
        except Exception as e:
            logger.error(f"Analytics build error: {e}")
            return Response({"success": False, "error": "Failed to build analytics."}, status=500)

        return Response({"success": True, "data": data})


class ChatbotMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response({"error": "message field is required."}, status=400)

        context = request.data.get("context") or {}
        history = [
            h for h in (request.data.get("conversation_history") or [])
            if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")
        ]

        try:
            student  = Student.objects.select_related("user", "current_class").get(
                user=request.user, archived=False
            )
            analytics = build_analytics(student)
        except Student.DoesNotExist:
            analytics = {}
        except Exception as e:
            logger.warning(f"Could not load analytics for AI context: {e}")
            analytics = {}

        prompt = build_prompt(message, context, history, analytics)

        try:
            ai_response = call_ai(prompt=prompt, system=CBC_SYSTEM_PROMPT, max_tokens=1000)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=503)
        except Exception as e:
            logger.error(f"AI call failed: {e}")
            return Response({"error": "AI service temporarily unavailable."}, status=503)

        return Response({"response": ai_response.strip()})