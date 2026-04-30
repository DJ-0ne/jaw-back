from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

STAFF_ROLES = [
    "system_admin", "principal", "deputy_principal", "director_studies",
    "registrar", "bursar", "accountant", "teacher", "hr_manager",
]


def _payload(instance):
    return {
        "notification_type": instance.notification_type,
        "id":             str(instance.id),
        "title":          instance.title,
        "message":        instance.message,
        "priority":       instance.priority,
        "status":         instance.status,
        "sent_at":        instance.sent_at.isoformat(),
        "recipient_type": instance.recipient_type,
        "recipient_id":   str(instance.recipient_id) if instance.recipient_id else None,
        "recipient_role": instance.recipient_role,
        "sent_by": {
            "id":        str(instance.sent_by.id),
            "full_name": instance.sent_by.get_full_name() or instance.sent_by.username,
            "role":      getattr(instance.sent_by, "role", ""),
        } if instance.sent_by else None,
    }


def _push(channel_layer, user_id, event):
    try:
        async_to_sync(channel_layer.group_send)(f"user_{user_id}", event)
    except Exception as e:
        print(f"[WS] Push failed for user_{user_id}: {e}")


@receiver(post_save, sender=Notification)
def push_notification(sender, instance, created, **kwargs):
    if not created:
        return
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    event = {"type": "notification_message", "data": _payload(instance)}

    if instance.recipient_type == "User" and instance.recipient_id:
        _push(channel_layer, instance.recipient_id, event)
        if instance.sent_by_id and str(instance.sent_by_id) != str(instance.recipient_id):
            _push(channel_layer, instance.sent_by_id, event)

    elif instance.recipient_type == "Role" and instance.recipient_role:
        uids = User.objects.filter(role=instance.recipient_role).values_list("id", flat=True)
        for uid in uids:
            _push(channel_layer, uid, event)
        # Also push to sender so they see their own broadcast in inbox
        if instance.sent_by_id:
            _push(channel_layer, instance.sent_by_id, event)

    elif instance.recipient_type == "All":
        uids = User.objects.filter(role__in=STAFF_ROLES).values_list("id", flat=True)
        for uid in uids:
            _push(channel_layer, uid, event)
        if instance.sent_by_id:
            _push(channel_layer, instance.sent_by_id, event)