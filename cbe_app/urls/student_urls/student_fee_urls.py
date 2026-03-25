from django.urls import path
from cbe_app.views.student_views.student_fee_views import (
    get_fee_summary,
    get_invoices,
    get_invoice_detail,
    get_transactions,
    get_fee_structure
)

urlpatterns = [
    path('summary/', get_fee_summary, name='student-fee-summary'),
    path('invoices/', get_invoices, name='student-invoices'),
    path('invoices/<uuid:invoice_id>/', get_invoice_detail, name='student-invoice-detail'),
    path('transactions/', get_transactions, name='student-transactions'),
    path('structure/', get_fee_structure, name='student-fee-structure'),
]