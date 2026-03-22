# cbe_app/urls/bursar_urls/bursar_urls.py

from django.urls import path
from cbe_app.views.bursar_views import payment_records_views as views

urlpatterns = [
    
    # Transaction Records (NEW)
    path('transactions/', views.get_transactions_list, name='transactions-list'),
    path('transactions/stats/', views.get_transaction_stats, name='transaction-stats'),
    path('transactions/<uuid:transaction_id>/', views.get_transaction_detail, name='transaction-detail'),
    path('transactions/export/', views.export_transactions, name='export-transactions'),
    path('transactions/payment-methods-stats/', views.get_payment_methods_stats, name='payment-methods-stats'),
]