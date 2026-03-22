from django.urls import path
from cbe_app.views.accountant_views import fee_management_views as views

urlpatterns = [
    # Fee Categories
    path('categories/', views.get_fee_categories, name='get-fee-categories'),
    path('categories/create/', views.create_fee_category, name='create-fee-category'),
    path('categories/<uuid:category_id>/', views.fee_category_detail, name='fee-category-detail'),
    path('categories/stats/', views.get_fee_category_stats, name='fee-category-stats'),
    
    # Fee Structures
    path('structures/', views.get_fee_structures, name='get-fee-structures'),
    path('structures/create/', views.create_fee_structure, name='create-fee-structure'),
    path('structures/<uuid:structure_id>/', views.fee_structure_detail, name='fee-structure-detail'),
    path('structures/stats/', views.get_fee_structure_stats, name='fee-structure-stats'),
    path('structures/export/', views.export_fee_structures, name='export-fee-structures'),
    
    # Fee Transactions
    path('transactions/', views.get_fee_transactions, name='get-fee-transactions'),
    
    path('transactions/stats/', views.get_transaction_stats, name='transaction-stats'),
    path('transactions/daily-collection/', views.get_daily_collection, name='daily-collection'),
    path('transactions/payment-methods-stats/', views.get_payment_methods_stats, name='payment-methods-stats'),
    path('transactions/top-students/', views.get_top_students, name='top-students'),
]