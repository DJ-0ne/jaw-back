# cbe_app/urls/student_urls/student_chatbot_urls.py
from django.urls import path
from cbe_app.views.ml_AI_views.student_chatbot_views import (
    ChatbotMessageView,
    ChatbotAnalyticsView,
)

urlpatterns = [
    # POST  /api/student/chatbot/message/
    path("message/", ChatbotMessageView.as_view(), name="chatbot-message"),
    # GET   /api/student/chatbot/analytics/
    path("analytics/", ChatbotAnalyticsView.as_view(), name="chatbot-analytics"),
]