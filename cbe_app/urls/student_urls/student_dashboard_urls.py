from django.urls import path
from cbe_app.views.student_views.student_views import (
    get_student_profile,
    get_fee_summary,
    get_fee_transactions,
    get_attendance,
    get_recent_attendance,
    get_discipline_records,
    get_academic_performance,
    get_current_performance,
    get_exam_results,
    get_timetable
)

urlpatterns = [
    # Profile
    path('profile/', get_student_profile, name='student-profile'),
    
    # Fees
    path('dashboard/fees/summary/', get_fee_summary, name='student-fee-summary'),
    path('dashboard/fees/transactions/', get_fee_transactions, name='student-fee-transactions'),
    
    # Attendance
    path('attendance/', get_attendance, name='student-attendance'),
    path('attendance/recent/', get_recent_attendance, name='student-attendance-recent'),
    
    # Discipline
    path('discipline/', get_discipline_records, name='student-discipline'),
    
    # Academic
    path('performance/', get_academic_performance, name='student-performance'),
    path('performance/current/', get_current_performance, name='student-current-performance'),
    path('results/', get_exam_results, name='student-results'),
    
    # Timetable
    path('timetable/', get_timetable, name='student-timetable'),
]