from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import ChatParticipant
from .fcm import send_push_to_token
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_push_task(token: str, title: str, body: str, data: dict):
    try:
        ok = send_push_to_token(token=token, title=title, body=body, data=data)
        logger.info(
            "FCM send result=%s token_present=%s data=%s", ok, bool(token), data
        )
    except Exception as e:
        logger.exception("FCM send failed: %s", e)


@shared_task
def auto_delete_chats_for_users():
    threshold = timezone.now() - timedelta(hours=24)

    qs = ChatParticipant.objects.select_related("chat").filter(
        auto_delete=True,
        deleted_at__isnull=True,
        chat__created_at__lte=threshold,
    )

    now = timezone.now()
    qs.update(deleted_at=now)
