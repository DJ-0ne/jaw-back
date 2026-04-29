from django.urls import path
from cbe_app.views.teacher_views.teacher_jssentry_views import (
    JSSClassesView,
    JSSStudentsView,
    JSSSubjectsView,
    JSSMarksBulkSaveView,
    JSSMarksRetrieveView,
    JSSTermsView
)

urlpatterns = [
    path('classes/', JSSClassesView.as_view(), name='teacher-jss-classes'),
    path('students/<uuid:class_id>/', JSSStudentsView.as_view(), name='teacher-jss-students'),
    path('subjects/', JSSSubjectsView.as_view(), name='teacher-jss-subjects'),
    path('marks/bulk-save/', JSSMarksBulkSaveView.as_view(), name='teacher-jss-marks-bulk-save'),
    path('marks/retrieve/', JSSMarksRetrieveView.as_view(), name='teacher-jss-marks-retrieve'),
    path('terms/', JSSTermsView.as_view(), name='teacher-jss-terms'),
]