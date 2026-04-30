"""
messaging_urls.py
Add to your main urls.py:
    path("api/", include("cbe_app.urls.messaging_urls.messaging_urls")),
"""

from django.urls import path
from cbe_app.views.notification.staff_notifications import (
    staff_list,
    inbox,
    unread_count,
    conversation,
    send_notification,
    mark_read,
    mark_all_read,
    archive_notification,
    conversation_list,
    role_notifications,
    # New endpoints
    edit_message,
    delete_message,
    list_attachments,
    create_poll,
    vote_poll,
    poll_detail,
)

urlpatterns = [
    # Staff directory
    path("staff/list/", staff_list, name="staff_list"),

    # Inbox & counts
    path("inbox/", inbox, name="notifications_inbox"),
    path("unread-count/", unread_count, name="notifications_unread_count"),
    path("mark-all-read/", mark_all_read, name="notifications_mark_all_read"),

    # Single notification actions
    path("<uuid:notification_id>/read/",        mark_read,         name="notification_mark_read"),
    path("<uuid:notification_id>/archive/",     archive_notification, name="notification_archive"),
    path("<uuid:notification_id>/edit/",        edit_message,      name="notification_edit"),
    path("<uuid:notification_id>/delete/",      delete_message,    name="notification_delete"),
    path("<uuid:notification_id>/attachments/", list_attachments,  name="notification_attachments"),

    # Messaging / conversations
    path("send/", send_notification, name="notification_send"),
    path("conversations/", conversation_list, name="conversation_list"),
    path("conversation/<uuid:user_id>/", conversation, name="conversation"),

    # Role-wide broadcasts
    path("role/", role_notifications, name="role_notifications"),

    # Polls
    path("polls/create/",        create_poll,  name="poll_create"),
    path("polls/<int:poll_id>/", poll_detail,  name="poll_detail"),
    path("polls/<int:poll_id>/vote/", vote_poll, name="poll_vote"),
]