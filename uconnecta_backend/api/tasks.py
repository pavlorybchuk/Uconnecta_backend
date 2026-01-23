from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import ChatParticipant

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
