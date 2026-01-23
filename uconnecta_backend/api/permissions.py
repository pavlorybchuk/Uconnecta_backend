from rest_framework.permissions import BasePermission
from .models import ChatParticipant

class IsChatParticipant(BasePermission):
    def has_permission(self, request, view):
        chat_id = view.kwargs.get("chat_id") or request.query_params.get("chat_id")
        if not chat_id:
            return False
        return ChatParticipant.objects.filter(
            chat_id=chat_id, user=request.user, deleted_at__isnull=True
        ).exists()
