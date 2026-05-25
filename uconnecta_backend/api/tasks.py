"""
Background tasks for async operations (sending notifications, auto-deleting chats).
Uses Celery with Redis as broker.
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import ChatParticipant
from .fcm import send_push_to_token
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_push_task(token: str, title: str, body: str, data: dict):
    """
    Send Firebase Cloud Messaging push notification asynchronously.
    
    This task runs in the background via Celery worker.
    Called by views that need to notify users about events
    (new messages, incoming calls, etc.).
    
    Args:
        token (str): FCM device token
        title (str): Notification title
        body (str): Notification body text
        data (dict): Additional data payload
        
    Logs success/failure for monitoring.
    Never raises exceptions - silently catches and logs them.
    """
    try:
        ok = send_push_to_token(token=token, title=title, body=body, data=data)
        logger.info(
            "FCM send result=%s token_present=%s data=%s", ok, bool(token), data
        )
    except Exception as e:
        logger.exception("FCM send failed: %s", e)


@shared_task
def auto_delete_chats_for_users():
    """
    Automatically delete old chats for users who enabled auto-delete.
    
    This task is scheduled to run periodically (e.g., daily via Celery Beat).
    
    Behavior:
    - Finds ChatParticipants with auto_delete=True
    - Checks if chat was created more than 24 hours ago
    - Sets deleted_at timestamp to "soft delete" the chat
    
    The chat record itself is NOT deleted from database,
    only the ChatParticipant's deleted_at field is updated.
    This preserves message history and allows chat restoration.
    
    Configuration (in settings):
        CELERY_BEAT_SCHEDULE = {
            'auto-delete-chats': {
                'task': 'api.tasks.auto_delete_chats_for_users',
                'schedule': crontab(hour=0, minute=0),  # Daily at midnight
            },
        }
    """
    # Define threshold: chats older than 24 hours
    threshold = timezone.now() - timedelta(hours=24)

    # Find chats to auto-delete
    qs = ChatParticipant.objects.select_related("chat").filter(
        auto_delete=True,
        deleted_at__isnull=True,  # Not already deleted
        chat__created_at__lte=threshold,  # Older than 24 hours
    )

    # Mark as deleted for this user
    now = timezone.now()
    qs.update(deleted_at=now)
