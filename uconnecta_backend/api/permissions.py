from rest_framework.permissions import BasePermission
from .models import ChatParticipant

class IsChatParticipant(BasePermission):
    def has_permission(self, request, view):
        chat_id = view.kwargs.get("chat_id") or view.kwargs.get("pk")
        if not chat_id or not request.user.is_authenticated:
            return False

        qs = ChatParticipant.objects.filter(chat_id=chat_id, user=request.user)

        # Для GET: тільки активний учасник (не deleted)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return qs.filter(deleted_at__isnull=True).exists()

        # Для POST/PUT/DELETE: дозволяємо навіть якщо deleted_at != null
        return qs.exists()
