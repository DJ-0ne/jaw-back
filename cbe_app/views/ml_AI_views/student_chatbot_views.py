# cbe_app/views/student_views/chatbot_view.py
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
    TermlySummary, DisciplineIncident,
)
from cbe_app.utils.ai_provider import call_ai

logger = logging.getLogger(__name__)


# ─── Competency level helper ──────────────────────────────────────────────────

def get_competency_code(pct: float) -> str:
    if pct >= 90: return "EE1"
    if pct >= 75: return "EE2"
    if pct >= 58: return "ME1"
    if pct >= 41: return "ME2"
    if pct >= 31: return "AE1"
    if pct >= 21: return "AE2"
    if pct >= 11: return "BE1"
    return "BE2"


def get_risk_level(value: float, low_max: float, medium_max: float) -> str:
    if value <= low_max:    return "low"
    if value <= medium_max: return "medium"
    return "high"


# ─── System prompt ────────────────────────────────────────────────────────────

CBC_SYSTEM_PROMPT = """
You are an expert CBC (Competency-Based Curriculum) Academic Assistant for a Kenyan school management system.

Your role is to help students understand:
- Their competency mastery levels (EE1–BE2 scale)
- Career pathway recommendations based on their competency profile
- Academic risk analysis (failure risk, dropout risk, intervention needs)
- Fee balances and payment information
- Assessment and exam schedules
- Attendance records and improvement strategies
- Personalised learning recommendations

CBC Competency Level Scale:
  EE1 Exceptional        90–100%
  EE2 Very Good          75–89%
  ME1 Good               58–74%
  ME2 Fair               41–57%
  AE1 Needs Improvement  31–40%
  AE2 Below Average      21–30%
  BE1 Well Below         11–20%
  BE2 Minimal             0–10%

Always be encouraging, reference the student by name when provided, give specific
actionable advice, and respond in clear plain text without markdown symbols.
""".strip()


# ─── Analytics builder ────────────────────────────────────────────────────────

def build_analytics(student: Student) -> dict:
    """Build the full analytics payload from real DB data."""

    # ── 1. Student info ───────────────────────────────────────────────────────
    student_name  = f"{student.user.first_name} {student.user.last_name}".strip()
    student_class = student.current_class.class_name if student.current_class else ""
    admission_no  = getattr(student, "admission_no", "") or ""

    # ── 2. Competency scores from TermlySummary ────────────────────────────────
    all_summaries = TermlySummary.objects.filter(
        student=student
    ).select_related("learning_area", "term", "term__academic_year")

    # Use the most recent term
    latest_term_id = (
        all_summaries
        .order_by("-term__academic_year__year_code", "-term__term")
        .values_list("term_id", flat=True)
        .first()
    )
    latest_summaries = all_summaries.filter(term_id=latest_term_id) if latest_term_id else all_summaries.none()

    competencies = []
    for s in latest_summaries:
        pct = round(float(s.final_internal_value or 0) * 25, 1)
        competencies.append({"name": s.learning_area.area_name, "mastery": pct})

    overall = (
        round(sum(c["mastery"] for c in competencies) / len(competencies), 1)
        if competencies else 0
    )

    # ── 3. Performance trend (per term average) ───────────────────────────────
    performance_trend = []
    seen_terms = (
        all_summaries
        .values("term_id", "term__term", "term__academic_year__year_name")
        .distinct()
        .order_by("term__academic_year__year_code", "term__term")
    )
    for row in seen_terms:
        term_summaries = all_summaries.filter(term_id=row["term_id"])
        count = term_summaries.count()
        total_val = term_summaries.aggregate(t=Sum("final_internal_value"))["t"] or 0
        avg_pct = round(float(total_val) / max(count, 1) * 25, 1)
        label = f"Term {row['term__term']} {row['term__academic_year__year_name']}"
        performance_trend.append({"term": label, "value": avg_pct})

    # ── 4. Fee balance ─────────────────────────────────────────────────────────
    invoices       = StudentFeeInvoice.objects.filter(student=student)
    total_fees     = invoices.aggregate(t=Sum("total_amount"))["t"] or 0
    total_paid     = invoices.aggregate(t=Sum("amount_paid"))["t"] or 0
    fee_balance    = round(float(total_fees - total_paid), 2)
    today          = timezone.now().date()
    overdue_amount = float(
        invoices.filter(due_date__lt=today, balance_amount__gt=0)
        .aggregate(t=Sum("balance_amount"))["t"] or 0
    )

    # ── 5. Attendance ──────────────────────────────────────────────────────────
    att_qs         = StudentAttendance.objects.filter(student=student)
    total_sessions = att_qs.count()
    present_count  = att_qs.filter(attendance_status="Present").count()
    attendance_rate = round(present_count / total_sessions * 100, 1) if total_sessions > 0 else 0

    # ── 6. Open discipline cases ───────────────────────────────────────────────
    open_cases = DisciplineIncident.objects.filter(
        student=student, status__in=["Reported", "Under Investigation"]
    ).count()

    # ── 7. Risk calculations ───────────────────────────────────────────────────
    weak_areas  = [c for c in competencies if c["mastery"] < 41]
    failure_pct = round(len(weak_areas) / max(len(competencies), 1) * 100, 1)
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

    # ── 8. Career pathways ─────────────────────────────────────────────────────
    PATHWAY_WEIGHTS = {
        "STEM & Engineering":     ["Mathematics", "Science", "Critical Thinking"],
        "ICT & Computer Science": ["Digital Literacy", "Mathematics", "Creative Arts"],
        "Business & Finance":     ["Mathematics", "English", "Social Studies"],
        "Arts & Creative":        ["Creative Arts", "English", "Social Studies"],
        "Health Sciences":        ["Science", "Mathematics", "Social Studies"],
    }
    comp_map = {c["name"]: c["mastery"] for c in competencies}
    pathways = []
    for name, keys in PATHWAY_WEIGHTS.items():
        relevant = [comp_map[k] for k in keys if k in comp_map]
        if not relevant:
            continue
        match = round(sum(relevant) / len(relevant), 1)
        pathways.append({"name": name, "match": match, "competencies": keys})
    pathways = sorted(pathways, key=lambda p: p["match"], reverse=True)[:3]

    return {
        "student_name":          student_name,
        "student_class":         student_class,
        "admission_no":          admission_no,
        "overall_competency":    overall,
        "competency_level":      get_competency_code(overall),
        "performance_trend":     performance_trend,
        "competencies":          competencies,
        "risks":                 risks,
        "career_pathways":       pathways,
        "fee_balance":           fee_balance,
        "overdue_amount":        overdue_amount,
        "attendance_rate":       attendance_rate,
        "open_discipline_cases": open_cases,
    }


# ─── Prompt builder ───────────────────────────────────────────────────────────

def build_prompt(message: str, context: dict, history: list, analytics: dict) -> str:
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
    """GET /api/student/chatbot/analytics/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            student = Student.objects.select_related(
                "user", "current_class"
            ).get(user=request.user, archived=False)
        except Student.DoesNotExist:
            return Response(
                {"success": False, "error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Student lookup error: {e}")
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            data = build_analytics(student)
        except Exception as e:
            logger.error(f"Analytics build error: {e}")
            return Response(
                {"success": False, "error": "Failed to build analytics."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class ChatbotMessageView(APIView):
    """POST /api/student/chatbot/message/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"error": "message field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        context = request.data.get("context") or {}
        history = [
            h for h in (request.data.get("conversation_history") or [])
            if isinstance(h, dict)
            and h.get("role") in ("user", "assistant")
            and h.get("content")
        ]

        # Fetch live analytics to ground the AI in real student data
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
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error(f"AI call failed: {e}")
            return Response(
                {"error": "AI service temporarily unavailable. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"response": ai_response.strip()}, status=status.HTTP_200_OK)