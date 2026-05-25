"""Custom DRF permission classes for endpoint authorization."""

from rest_framework.permissions import BasePermission
from .models import ChatParticipant


class IsChatParticipant(BasePermission):
    """
    Permission class to verify user is a participant of a chat.

    Usage: Add to a view's permission_classes

    Access rules:
    - GET requests: User must be an active (non-deleted) participant
    - POST/PUT/DELETE requests: User must be a participant (even if deleted)
      This allows users to perform actions like deleting a chat even after
      they've already deleted it

    Example view:
        class GetChatDetailsView(APIView):
            permission_classes = [IsChatParticipant]

    The chat_id is extracted from view kwargs (either 'chat_id' or 'pk').
    """

    def has_permission(self, request, view):
        """
        Check if user has permission to access this chat.

        Args:
            request: HTTP request with user and method
            view: APIView with kwargs containing chat_id or pk

        Returns:
            bool: True if user has access, False otherwise
        """
        # Extract chat ID from URL kwargs
        chat_id = view.kwargs.get("chat_id") or view.kwargs.get("pk")
        if not chat_id or not request.user.is_authenticated:
            return False

        qs = ChatParticipant.objects.filter(chat_id=chat_id, user=request.user)

        # For read operations: require active participation (not deleted)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return qs.filter(deleted_at__isnull=True).exists()

        # For write operations: allow even if chat is deleted
        # This lets users delete a chat, restore deleted messages, etc.
        return qs.exists()
