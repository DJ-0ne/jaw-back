# cbe_app/urls/principal_urls.py
from django.urls import path
from cbe_app.views.schooladmin_views.dashboard_views import (
    get_principal_dashboard_stats,
    get_principal_dashboard_performance,
    get_principal_dashboard_activities
)
from cbe_app.views.schooladmin_views.prin_fin_views import (
    get_finance_overview,
    get_finance_revenue_trend,
    get_students_fee_summary,
    get_recent_transactions
)
from cbe_app.views.schooladmin_views.prin_stud_views import (
    get_principal_students,
    get_principal_student_detail
)

app_name = 'principal'   # good for namespacing (optional)

urlpatterns = [
    # ── Dashboard ──────────────────────────────────────────────────
    path('dashboard/stats/',
         get_principal_dashboard_stats,
         name='principal-dashboard-stats'),

    path('dashboard/performance/',
         get_principal_dashboard_performance,
         name='principal-dashboard-performance'),

    path('dashboard/activities/',
         get_principal_dashboard_activities,
         name='principal-dashboard-activities'),

    # ── Finance ────────────────────────────────────────────────────
    path('finance/overview/',
         get_finance_overview,
         name='principal-finance-overview'),

    path('finance/revenue-trend/',
         get_finance_revenue_trend,
         name='principal-finance-revenue-trend'),

    # supports ?search=&class_id=&term_id=&page=1&page_size=50
    path('finance/students-fees/',
         get_students_fee_summary,
         name='principal-finance-students-fees'),

    path('finance/recent-transactions/',
         get_recent_transactions,
         name='principal-finance-recent-transactions'),

    # ── Students ───────────────────────────────────────────────────
    # supports ?search=&class_id=&status=&page=1&page_size=50
    path('students/',
         get_principal_students,
         name='principal-students-list'),

    path('students/<uuid:student_id>/',
         get_principal_student_detail,
         name='principal-student-detail'),
]