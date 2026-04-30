

import logging

from rest_framework.decorators import (
    api_view, authentication_classes, parser_classes, permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from cbe_app.models import Notification

logger = logging.getLogger(__name__)

try:
    from cbe_app.models import MessageAttachment, MessagePoll
    HAS_ATTACH = True
except ImportError:
    MessageAttachment = None
    MessagePoll = None
    HAS_ATTACH = False
    logger.warning("MessageAttachment / MessagePoll models not found – attachment support disabled.")

User = get_user_model()

STAFF_ROLES = [
    "system_admin", "principal", "deputy_principal", "director_studies",
    "registrar", "bursar", "accountant", "teacher", "hr_manager",
]

# All MIME types accepted for upload
ALLOWED_CONTENT_TYPES = {
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/svg+xml", "image/bmp", "image/x-icon",
    # Videos
    "video/mp4", "video/webm", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/mpeg", "video/ogg", "video/3gpp", "video/3gpp2",
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/csv",
    "application/zip", "application/x-zip-compressed",
    "application/octet-stream",  # fallback – always accepted, coerced below
}

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB

# Extension → MIME coercion map used when browser sends "" or octet-stream
_EXT_MIME = {
    # Video
    ".mp4": "video/mp4",   ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime", ".qt": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska", ".mk3d": "video/x-matroska",
    ".mpeg": "video/mpeg",  ".mpg": "video/mpeg",
    ".ogv": "video/ogg",
    ".3gp": "video/3gpp",  ".3g2": "video/3gpp2",
    # Images
    ".jpg": "image/jpeg",  ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    # Documents
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
}

_JWT  = [JWTAuthentication]
_AUTH = [IsAuthenticated]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _coerce_mime(uploaded_file):
    """
    Return the best MIME type for an uploaded file.
    Browsers (especially mobile/Safari) often send 'application/octet-stream'
    or an empty string for video and document files.  We fall back to extension
    lookup in those cases so the stored content_type is always meaningful.
    """
    ct = (uploaded_file.content_type or "").strip().lower()
    if ct and ct != "application/octet-stream":
        return ct
    # Try extension lookup
    name = uploaded_file.name.lower()
    for ext, mime in _EXT_MIME.items():
        if name.endswith(ext):
            return mime
    return "application/octet-stream"


def _user_to_dict(user):
    role = "Unknown"
    if hasattr(user, "role") and user.role:
        role = user.role
    elif hasattr(user, "profile") and hasattr(user.profile, "role"):
        role = user.profile.role
    elif user.groups.exists():
        role = user.groups.first().name
    return {
        "id":        str(user.id),
        "username":  user.username,
        "full_name": user.get_full_name() or user.username,
        "email":     user.email,
        "role":      role,
        "is_online": False,
    }


def _attachment_to_dict(a, request=None):
    """
    Return a dict for a MessageAttachment with a fully-qualified URL.
    Uses request.build_absolute_uri so recipients on other machines
    always get an http(s)://host/media/… URL they can open.
    """
    try:
        raw_url = a.file.url
    except Exception:
        raw_url = ""

    url = request.build_absolute_uri(raw_url) if request and raw_url else raw_url

    return {
        "id":            a.id,
        "url":           url,
        "original_name": a.original_name,
        "content_type":  a.content_type,
        "size":          a.size,
    }


def _poll_to_dict(poll, requesting_user_id=None):
    user_vote = poll.votes.get(str(requesting_user_id)) if requesting_user_id else None
    tally = {}
    for opt_idx in poll.votes.values():
        tally[opt_idx] = tally.get(opt_idx, 0) + 1
    return {
        "id":          poll.id,
        "question":    poll.question,
        "options":     poll.options,
        "tally":       tally,
        "user_vote":   user_vote,
        "total_votes": len(poll.votes),
    }


def _notification_to_dict(n, requesting_user_id=None, request=None):
    # Attachments ─────────────────────────────────────────────────────────────
    attachments = []
    if HAS_ATTACH:
        try:
            # Using .all() on a prefetched reverse relation is safe and free.
            attachments = [_attachment_to_dict(a, request) for a in n.attachments.all()]
        except Exception as exc:
            logger.debug("Could not fetch attachments for notification %s: %s", n.id, exc)

    # Poll ────────────────────────────────────────────────────────────────────
    poll_data = None
    if HAS_ATTACH:
        try:
            poll_data = _poll_to_dict(n.poll, requesting_user_id)
        except Exception:
            poll_data = None

    return {
        "id":                str(n.id),
        "notification_type": n.notification_type,
        "title":             n.title,
        "message":           n.message,
        "recipient_type":    n.recipient_type,
        "recipient_id":      str(n.recipient_id) if n.recipient_id else None,
        "recipient_role":    n.recipient_role,
        "priority":          n.priority,
        "status":            n.status,
        "action_url":        n.action_url,
        "related_table":     n.related_table,
        "related_id":        str(n.related_id) if n.related_id else None,
        "sent_by":           _user_to_dict(n.sent_by) if n.sent_by else None,
        "sent_at":           n.sent_at.isoformat(),
        "read_at":           n.read_at.isoformat() if n.read_at else None,
        "expires_at":        n.expires_at.isoformat() if n.expires_at else None,
        "edited":            getattr(n, "edited", False),
        "attachments":       attachments,
        "poll":              poll_data,
    }


def _fetch_notification_for_response(notification_id, request=None):
    """
    Re-fetch a notification from the DB with all relations loaded so that
    _notification_to_dict always returns complete attachment/poll data.

    This is the KEY fix: after creating a notification and saving its
    attachments, the in-memory object's reverse-relation cache is empty.
    Calling n.attachments.all() on it returns [] even though the rows exist
    in the DB.  Re-fetching with prefetch_related populates the cache from a
    fresh SELECT, guaranteeing the response JSON includes every attachment.
    """
    qs = Notification.objects.filter(id=notification_id).select_related("sent_by")
    if HAS_ATTACH:
        qs = qs.prefetch_related("attachments", "poll")
    return qs.get()


# ─────────────────────────────────────────────────────────────────────────────
# Staff list
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def staff_list(request):
    staff_users = (
        User.objects.filter(role__in=STAFF_ROLES)
        .exclude(id=request.user.id)
        .distinct()
    )
    q = request.GET.get("q", "").strip()
    if q:
        staff_users = staff_users.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(username__icontains=q) | Q(email__icontains=q)
        )
    return Response({"staff": [_user_to_dict(u) for u in staff_users]})


# ─────────────────────────────────────────────────────────────────────────────
# Inbox
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def inbox(request):
    user_role = getattr(request.user, "role", None)
    scope     = request.GET.get("scope", "")

    base_q = (
        Q(recipient_type="User", recipient_id=request.user.id)
        | Q(recipient_type="Role", recipient_role=user_role)
        | Q(recipient_type="All")
    )

    if scope == "direct":
        base_q = Q(recipient_type="User", recipient_id=request.user.id)

    elif scope == "broadcast":
        base_q = (
            Q(recipient_type="Role", recipient_role=user_role)
            | Q(recipient_type="All")
            | Q(sent_by=request.user, recipient_type__in=["Role", "All"])
        )

    elif scope == "system":
        base_q = Q(
            recipient_type="User",
            recipient_id=request.user.id,
            notification_type__in=["alert", "announcement", "system"],
        )

    qs = (
        Notification.objects.filter(base_q)
        .select_related("sent_by")
        .order_by("-sent_at")
    )

    if HAS_ATTACH:
        qs = qs.prefetch_related("attachments", "poll")

    status_param = request.GET.get("status")
    if status_param:
        qs = qs.filter(status=status_param)

    page_num  = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 50))
    paginator = Paginator(qs, page_size)
    page      = paginator.get_page(page_num)

    uid = str(request.user.id)
    return Response({
        "notifications": [_notification_to_dict(n, uid, request) for n in page.object_list],
        "total":         paginator.count,
        "page":          page_num,
        "pages":         paginator.num_pages,
        "unread_count":  qs.filter(status="Unread").count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Unread count
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def unread_count(request):
    user_role = getattr(request.user, "role", None)

    dm_unread = Notification.objects.filter(
        recipient_type="User",
        recipient_id=request.user.id,
        notification_type="message",
        status="Unread",
    ).count()

    broadcast_unread = Notification.objects.filter(
        Q(recipient_type="Role", recipient_role=user_role)
        | Q(recipient_type="All"),
        status="Unread",
    ).count()

    inbox_unread = Notification.objects.filter(
        Q(
            recipient_type="User",
            recipient_id=request.user.id,
            notification_type__in=["alert", "announcement", "system"],
        )
        | Q(
            recipient_type="User",
            recipient_id=request.user.id,
            notification_type="message",
        ),
        status="Unread",
    ).count()

    return Response({
        "unread_count":     dm_unread + broadcast_unread + inbox_unread,
        "chat_unread":      dm_unread + broadcast_unread,
        "inbox_unread":     inbox_unread,
        "broadcast_unread": broadcast_unread,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Conversation (DM thread between two users)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def conversation(request, user_id):
    qs = (
        Notification.objects.filter(notification_type="message")
        .filter(
            Q(sent_by=request.user, recipient_type="User", recipient_id=user_id)
            | Q(sent_by_id=user_id, recipient_type="User", recipient_id=request.user.id)
        )
        .select_related("sent_by")
        .order_by("sent_at")
    )

    if HAS_ATTACH:
        qs = qs.prefetch_related("attachments")

    messages = list(qs)

    Notification.objects.filter(
        notification_type="message",
        recipient_type="User",
        recipient_id=request.user.id,
        sent_by_id=user_id,
        status="Unread",
    ).update(status="Read", read_at=timezone.now())

    uid = str(request.user.id)
    return Response({
        "messages": [_notification_to_dict(n, uid, request) for n in messages],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Send notification  (supports multipart/form-data for file attachments)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
@parser_classes([MultiPartParser, FormParser, JSONParser])
def send_notification(request):
    data = request.data

    # ── Required field validation ─────────────────────────────────────────
    for field in ["recipient_type", "notification_type", "title"]:
        if not data.get(field):
            return Response(
                {"error": f"'{field}' is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Collect uploaded files from BOTH the named field and the generic FILES dict.
    uploaded_files = request.FILES.getlist("attachments")
    if not uploaded_files:
        uploaded_files = list(request.FILES.values())

    has_files = bool(uploaded_files)

    logger.debug(
        "send_notification: user=%s recipient_type=%s files=%d",
        request.user.id, data.get("recipient_type"), len(uploaded_files),
    )

    if not data.get("message") and not has_files:
        return Response(
            {"error": "'message' is required (or attach at least one file)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    recipient_type = data["recipient_type"]
    recipient_id   = data.get("recipient_id")
    recipient_role = data.get("recipient_role")

    if recipient_type == "User" and not recipient_id:
        return Response(
            {"error": "'recipient_id' required for User type"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if recipient_type == "Role" and not recipient_role:
        return Response(
            {"error": "'recipient_role' required for Role type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    expires_at = None
    if data.get("expires_at"):
        from django.utils.dateparse import parse_datetime
        try:
            expires_at = parse_datetime(data["expires_at"])
        except Exception:
            pass

    # ── Create the notification record ────────────────────────────────────
    notification = Notification.objects.create(
        notification_type=data["notification_type"],
        title=data["title"],
        message=data.get("message") or "",
        recipient_type=recipient_type,
        recipient_id=recipient_id     if recipient_type == "User" else None,
        recipient_role=recipient_role  if recipient_type == "Role" else None,
        priority=data.get("priority", "Normal"),
        status="Unread",
        action_url=data.get("action_url"),
        related_table=data.get("related_table"),
        related_id=data.get("related_id"),
        sent_by=request.user,
        expires_at=expires_at,
    )

    # ── Save attachments ──────────────────────────────────────────────────
    attachment_errors = []

    if has_files:
        if not HAS_ATTACH:
            logger.error("Files uploaded but MessageAttachment model is not installed.")
            attachment_errors.append("Attachment model not installed; files were not saved.")
        else:
            for uploaded_file in uploaded_files:
                if uploaded_file.size > MAX_UPLOAD_SIZE:
                    attachment_errors.append(
                        f"{uploaded_file.name}: exceeds 100 MB limit — skipped"
                    )
                    continue

                mime = _coerce_mime(uploaded_file)

                logger.debug(
                    "Saving attachment: name=%s original_ct=%r resolved_ct=%s size=%d",
                    uploaded_file.name, uploaded_file.content_type, mime, uploaded_file.size,
                )

                try:
                    MessageAttachment.objects.create(
                        notification=notification,
                        file=uploaded_file,
                        original_name=uploaded_file.name,
                        content_type=mime,
                        size=uploaded_file.size,
                    )
                except Exception as exc:
                    logger.exception("Failed to save attachment %s", uploaded_file.name)
                    attachment_errors.append(f"{uploaded_file.name}: {exc}")

    # ── CRITICAL FIX: re-fetch with prefetch_related before serialising ───
    # The in-memory `notification` object has an empty reverse-relation cache
    # for `attachments` — Django does not automatically update it after calling
    # MessageAttachment.objects.create(...).  Without this re-fetch,
    # n.attachments.all() returns [] and the response JSON has attachments: []
    # even though the rows were just committed to the DB.  The frontend then
    # renders an empty bubble because there is no text and no attachments.
    uid = str(request.user.id)
    try:
        fresh_notification = _fetch_notification_for_response(notification.id, request)
    except Exception:
        # Fallback: use the in-memory object (attachments may be missing but
        # at least the message text / metadata will be correct).
        logger.warning(
            "Could not re-fetch notification %s after create; falling back to in-memory object.",
            notification.id,
        )
        fresh_notification = notification

    response_data = {
        "success":      True,
        "notification": _notification_to_dict(fresh_notification, uid, request),
    }
    if attachment_errors:
        response_data["warnings"] = attachment_errors

    return Response(response_data, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# Mark single notification as read
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["PATCH"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def mark_read(request, notification_id):
    try:
        n = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    user      = request.user
    user_role = getattr(user, "role", None)

    is_recipient = (
        (n.recipient_type == "User"  and str(n.recipient_id) == str(user.id))
        or (n.recipient_type == "Role" and n.recipient_role == user_role)
        or (n.recipient_type == "All")
    )

    if not is_recipient:
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    if n.status != "Read":
        n.status  = "Read"
        n.read_at = timezone.now()
        n.save(update_fields=["status", "read_at"])

    uid = str(user.id)
    return Response({"success": True, "notification": _notification_to_dict(n, uid, request)})


# ─────────────────────────────────────────────────────────────────────────────
# Mark all read
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def mark_all_read(request):
    user_role = getattr(request.user, "role", None)
    updated = Notification.objects.filter(
        Q(recipient_type="User", recipient_id=request.user.id)
        | Q(recipient_type="Role", recipient_role=user_role)
        | Q(recipient_type="All"),
        status="Unread",
    ).update(status="Read", read_at=timezone.now())
    return Response({"success": True, "updated": updated})


# ─────────────────────────────────────────────────────────────────────────────
# Archive
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["DELETE", "PATCH"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def archive_notification(request, notification_id):
    try:
        n = Notification.objects.get(id=notification_id, recipient_id=request.user.id)
    except Notification.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    n.status = "Archived"
    n.save(update_fields=["status"])
    return Response({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# Edit message  (sender only, within 24 h)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["PATCH"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def edit_message(request, notification_id):
    try:
        n = Notification.objects.get(id=notification_id, sent_by=request.user)
    except Notification.DoesNotExist:
        return Response(
            {"error": "Not found or not your message"},
            status=status.HTTP_404_NOT_FOUND,
        )

    age = timezone.now() - n.sent_at
    if age.total_seconds() > 86_400:
        return Response(
            {"error": "Cannot edit messages older than 24 hours"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    new_message = request.data.get("message", "").strip()
    if not new_message:
        return Response(
            {"error": "'message' is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    n.message = new_message
    update_fields = ["message"]
    if hasattr(n, "edited"):
        n.edited = True
        update_fields.append("edited")
    n.save(update_fields=update_fields)

    # Re-fetch with prefetch so attachments are included in the edit response too
    uid = str(request.user.id)
    try:
        fresh_n = _fetch_notification_for_response(n.id, request)
    except Exception:
        fresh_n = n

    return Response({"success": True, "notification": _notification_to_dict(fresh_n, uid, request)})


# ─────────────────────────────────────────────────────────────────────────────
# Delete message  (sender only)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["DELETE"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def delete_message(request, notification_id):
    try:
        n = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    
    if str(n.sent_by_id) != str(request.user.id):
        return Response({"error": "You can only delete your own messages"}, status=status.HTTP_403_FORBIDDEN)
    
    n.delete()
    return Response({"success": True, "deleted_id": str(notification_id)})


# ─────────────────────────────────────────────────────────────────────────────
# List attachments for a notification
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def list_attachments(request, notification_id):
    if not HAS_ATTACH:
        return Response({"attachments": []})

    try:
        n = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    user      = request.user
    user_role = getattr(user, "role", None)
    is_recipient = (
        (n.recipient_type == "User"  and str(n.recipient_id) == str(user.id))
        or (n.recipient_type == "Role" and n.recipient_role == user_role)
        or (n.recipient_type == "All")
        or (n.sent_by_id == user.id)
    )
    if not is_recipient:
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    attachments = MessageAttachment.objects.filter(notification=n)
    return Response({
        "attachments": [_attachment_to_dict(a, request) for a in attachments],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Conversation list  (sidebar: most recent DM per partner)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def conversation_list(request):
    user_id = request.user.id

    all_msgs = (
        Notification.objects.filter(
            notification_type="message",
            recipient_type="User",
            recipient_id__isnull=False,
        )
        .filter(Q(sent_by=request.user) | Q(recipient_id=user_id))
        .select_related("sent_by")
        .order_by("-sent_at")
    )

    if HAS_ATTACH:
        all_msgs = all_msgs.prefetch_related("attachments")

    seen          = set()
    conversations = []

    for msg in all_msgs:
        partner_id = msg.recipient_id if msg.sent_by_id == user_id else msg.sent_by_id
        if partner_id in seen:
            continue
        seen.add(partner_id)

        try:
            partner = User.objects.get(id=partner_id)
        except (User.DoesNotExist, ValueError):
            continue

        unread = Notification.objects.filter(
            notification_type="message",
            recipient_type="User",
            recipient_id=user_id,
            sent_by_id=partner_id,
            status="Unread",
        ).count()

        conversations.append({
            "partner":      _user_to_dict(partner),
            "last_message": _notification_to_dict(msg, str(user_id), request),
            "unread_count": unread,
        })

    return Response({"conversations": conversations})


# ─────────────────────────────────────────────────────────────────────────────
# Role notifications
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def role_notifications(request):
    user_role = getattr(request.user, "role", None)
    if not user_role:
        return Response({"notifications": [], "total": 0})

    qs = (
        Notification.objects.filter(recipient_type="Role", recipient_role=user_role)
        .select_related("sent_by")
        .order_by("-sent_at")
    )

    if HAS_ATTACH:
        qs = qs.prefetch_related("attachments", "poll")

    page_num  = int(request.GET.get("page", 1))
    paginator = Paginator(qs, 20)
    page      = paginator.get_page(page_num)
    uid       = str(request.user.id)

    return Response({
        "notifications": [_notification_to_dict(n, uid, request) for n in page.object_list],
        "total":         paginator.count,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Polls
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def create_poll(request):
    if not HAS_ATTACH:
        return Response(
            {"error": "Poll model not installed"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    notification_id = request.data.get("notification_id")
    question        = (request.data.get("question") or "").strip()
    options         = request.data.get("options", [])

    if not question:
        return Response({"error": "'question' is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(options, list) or len(options) < 2:
        return Response(
            {"error": "'options' must be a list with at least 2 items"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if notification_id:
        try:
            n = Notification.objects.get(id=notification_id, sent_by=request.user)
        except Notification.DoesNotExist:
            return Response(
                {"error": "Notification not found or not yours"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            _ = n.poll
            return Response(
                {"error": "Poll already exists for this notification"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            pass
    else:
        d              = request.data
        recipient_type = d.get("recipient_type", "All")
        recipient_role = d.get("recipient_role")
        n = Notification.objects.create(
            notification_type="message",
            title=question[:100],
            message=f"Poll: {question}",
            recipient_type=recipient_type,
            recipient_role=recipient_role if recipient_type == "Role" else None,
            priority=d.get("priority", "Normal"),
            status="Unread",
            sent_by=request.user,
        )

    poll = MessagePoll.objects.create(
        notification=n,
        question=question,
        options=[str(o).strip() for o in options],
        votes={},
    )

    uid = str(request.user.id)
    # Re-fetch so poll reverse relation is populated
    try:
        fresh_n = _fetch_notification_for_response(n.id, request)
    except Exception:
        fresh_n = n

    return Response(
        {
            "success":      True,
            "poll":         _poll_to_dict(poll, uid),
            "notification": _notification_to_dict(fresh_n, uid, request),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def vote_poll(request, poll_id):
    if not HAS_ATTACH:
        return Response(
            {"error": "Poll model not installed"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    try:
        poll = MessagePoll.objects.select_related("notification").get(id=poll_id)
    except MessagePoll.DoesNotExist:
        return Response({"error": "Poll not found"}, status=status.HTTP_404_NOT_FOUND)

    option_index = request.data.get("option_index")
    if option_index is None or not isinstance(option_index, int):
        return Response(
            {"error": "'option_index' (int) is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if option_index < 0 or option_index >= len(poll.options):
        return Response({"error": "Invalid option_index"}, status=status.HTTP_400_BAD_REQUEST)

    uid = str(request.user.id)
    poll.votes[uid] = option_index
    poll.save(update_fields=["votes"])

    return Response({"success": True, "poll": _poll_to_dict(poll, uid)})


@api_view(["GET"])
@authentication_classes(_JWT)
@permission_classes(_AUTH)
def poll_detail(request, poll_id):
    if not HAS_ATTACH:
        return Response(
            {"error": "Poll model not installed"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    try:
        poll = MessagePoll.objects.get(id=poll_id)
    except MessagePoll.DoesNotExist:
        return Response({"error": "Poll not found"}, status=status.HTTP_404_NOT_FOUND)

    uid = str(request.user.id)
    return Response({"poll": _poll_to_dict(poll, uid)})