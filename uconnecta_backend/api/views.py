import os
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.models import Avg
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers
from .models import (
    BlockedUser,
    Car,
    Chat,
    ChatParticipant,
    DeletedMessage,
    Message,
    Call,
)
from .serializers import (
    BlockUserSerializer,
    BlockedUserSerializer,
    CarCreateSerializer,
    RegisterSerializer,
    MeSerializer,
    MeUpdateSerializer,
    ChatListSerializer,
    MessageSerializer,
    CallSerializer,
    UserPublicSerializer,
    SendEmailSerializer,
    LogoutSerializer,
)
from .permissions import IsChatParticipant
import string
import random
import requests

User = get_user_model()


def generate_username():
    chars = list(string.ascii_letters + string.digits)
    res = ""
    for _ in range(8):
        res += random.choice(chars)
    return res


class LogoutView(APIView):
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Logged out"}, status=status.HTTP_200_OK)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data.copy()
        while True:
            data["username"] = generate_username()
            s = RegisterSerializer(data=data)
            if s.is_valid():
                user = s.save()
                return Response({"id": str(user.id)}, status=status.HTTP_201_CREATED)

            if "username" in s.errors:
                continue

            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


class SearchUserView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        car_number = request.query_params.get("car_number")
        username = request.query_params.get("username")

        if not car_number and not username:
            return Response({"detail": "Provide car_number or username"}, status=400)

        qs = User.objects.select_related("profile").annotate(
            rating=Avg("rates_received__rate")
        )

        if car_number:
            qs = qs.filter(cars__car_number=car_number)
        if username:
            qs = qs.filter(username__iexact=username)

        user = qs.first()
        if not user:
            return Response({"detail": "Not found"}, status=404)

        return Response(UserPublicSerializer(user, context={"request": request}).data)


class MeView(APIView):
    def get(self, request):
        user = (
            User.objects.select_related("profile")
            .prefetch_related("cars")
            .annotate(rating=Avg("rates_received__rate"))
            .get(pk=request.user.pk)
        )
        return Response(MeSerializer(user).data)

    def patch(self, request):
        s = MeUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        s.is_valid(raise_exception=True)
        s.save()

        user = (
            User.objects.select_related("profile")
            .prefetch_related("cars")
            .annotate(rating=Avg("rates_received__rate"))
            .get(pk=request.user.pk)
        )

        return Response(MeSerializer(user).data)


class ChatsListView(APIView):
    """
    /api/chats?sort=last_message|created_at
    Повертає тільки ті чати, де користувач не видалив чат (deleted_at is null)
    + додає other_user та auto_delete для UI
    """

    def get(self, request):
        sort = request.query_params.get("sort", "last_message")
        ordering = "-last_message_at" if sort == "last_message" else "-created_at"

        my_cps = list(
            ChatParticipant.objects.filter(
                user=request.user, deleted_at__isnull=True
            ).select_related("chat")
        )
        chat_ids = [cp.chat_id for cp in my_cps]

        if not chat_ids:
            return Response([])

        auto_delete_by_chat = {cp.chat_id: cp.auto_delete for cp in my_cps}
        auto_delete_enabled_at_by_chat = {
            cp.chat_id: cp.auto_delete_enabled_at for cp in my_cps
        }

        chats = Chat.objects.filter(
            participants__user=request.user,
            participants__deleted_at__isnull=True,
        ).distinct()

        other_cps = list(
            ChatParticipant.objects.filter(chat_id__in=chat_ids)
            .exclude(user=request.user)
            .select_related("user", "user__profile")
        )

        other_user_ids = [cp.user_id for cp in other_cps]

        others = (
            User.objects.filter(id__in=other_user_ids)
            .select_related("profile")
            .annotate(rating=Avg("rates_received__rate"))
        )
        other_by_id = {u.id: u for u in others}

        other_user_by_chat = {}
        for cp in other_cps:
            u = other_by_id.get(cp.user_id)
            if u:
                other_user_by_chat[cp.chat_id] = u

        serializer = ChatListSerializer(
            chats,
            many=True,
            context={
                "request": request,
                "auto_delete_by_chat": auto_delete_by_chat,
                "other_user_by_chat": other_user_by_chat,
                "auto_delete_enabled_at_by_chat": auto_delete_enabled_at_by_chat,
            },
        )
        return Response(serializer.data)


def is_blocked(a, b):
    return (
        BlockedUser.objects.filter(blocker=a, blocked=b).exists()
        or BlockedUser.objects.filter(blocker=b, blocked=a).exists()
    )


class CreateDirectChatView(APIView):
    """
    POST /api/chats/direct { "other_user_id": "uuid" }
    Створює direct чат між двома людьми (без дублювань).
    """

    @transaction.atomic
    def post(self, request):
        other_id = request.data.get("other_user_id")
        if not other_id:
            return Response({"detail": "other_user_id required"}, status=400)
        if str(request.user.id) == str(other_id):
            return Response({"detail": "Cannot create chat with yourself"}, status=400)

        other = User.objects.filter(id=other_id).first()
        if not other:
            return Response({"detail": "User not found"}, status=404)

        if is_blocked(request.user, other):
            return Response({"detail": "User is blocked"}, status=403)

        a, b = sorted([str(request.user.id), str(other.id)])
        direct_key = f"{a}:{b}"

        chat = Chat.objects.filter(type="direct", direct_key=direct_key).first()
        if not chat:
            chat = Chat.objects.create(type="direct", direct_key=direct_key)

            ChatParticipant.objects.create(
                chat=chat,
                user=request.user,
                auto_delete=bool(
                    request.user.profile.settings.get("auto_delete_chats", False)
                ),
            )
            ChatParticipant.objects.create(
                chat=chat,
                user=other,
                auto_delete=bool(
                    other.profile.settings.get("auto_delete_chats", False)
                ),
            )

        return Response({"chat_id": str(chat.id)}, status=201)


class DeleteChatForMeView(APIView):
    """
    POST /api/chats/<chat_id>/delete-for-me
    """

    def post(self, request, chat_id):
        cp = ChatParticipant.objects.filter(chat_id=chat_id, user=request.user).first()
        if not cp:
            return Response({"detail": "Not found"}, status=404)
        cp.deleted_at = timezone.now()
        cp.save(update_fields=["deleted_at"])
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "chat.event",
                "payload": {
                    "type": "chat.deleted_for_me",
                    "payload": {
                        "chat_id": str(chat_id),
                        "user_id": str(request.user.id),
                    },
                },
            },
        )
        return Response({"detail": "deleted_for_me"})


class DeleteChatForAllView(APIView):
    def post(self, request, chat_id):
        is_participant = ChatParticipant.objects.filter(
            chat_id=chat_id, user=request.user
        ).exists()
        if not is_participant:
            return Response({"detail": "Forbidden"}, status=403)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "chat.event",
                "payload": {
                    "type": "chat.deleted_for_all",
                    "payload": {"chat_id": str(chat_id)},
                },
            },
        )

        Chat.objects.filter(id=chat_id).delete()
        return Response({"detail": "deleted_for_all"})


class ChatMessagesView(APIView):
    """
    GET /api/chats/<chat_id>/messages
    Повертає всі повідомлення чату (тільки для учасника, який не delete-for-me).
    """

    permission_classes = [IsChatParticipant]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, chat_id):
        msgs = (
            Message.objects.filter(chat_id=chat_id)
            .exclude(deleted_for__user=request.user)
            .select_related("sender")
            .order_by("created_at")
        )
        return Response(
            MessageSerializer(msgs, many=True, context={"request": request}).data
        )

    def post(self, request, chat_id):
        participant = ChatParticipant.objects.filter(
            chat=chat_id, user=request.user
        ).first()

        if not participant:
            return Response({"detail": "Forbidden"}, status=403)

        if participant.deleted_at is not None:
            participant.deleted_at = None
            participant.save(update_fields=["deleted_at"])

        other = (
            ChatParticipant.objects.filter(chat_id=chat_id)
            .exclude(user=request.user)
            .select_related("user")
            .first()
        )
        if not other:
            return Response({"detail": "Chat participant not found"}, status=400)

        if is_blocked(request.user, other.user):
            return Response(
                {"detail": "You cannot send messages to this user"}, status=403
            )

        body = (request.data.get("body") or "").strip()
        image = request.FILES.get("image")

        if not body and not image:
            return Response({"detail": "body or image required"}, status=400)

        msg = Message.objects.create(
            chat_id=chat_id,
            sender=request.user,
            body=body if body else None,
            image=image,
        )

        Message.objects.filter(id=msg.id).update()
        msg.chat.last_message_at = timezone.now()
        msg.chat.save(update_fields=["last_message_at"])

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "chat.message",
                "message": MessageSerializer(msg).data,
            },
        )

        return Response(
            MessageSerializer(msg, context={"request": request}).data, status=201
        )


class CallsHistoryView(APIView):
    """
    GET /api/calls/history
    """

    def get(self, request):
        qs = Call.objects.filter(
            Q(caller=request.user) | Q(receiver=request.user)
        ).order_by("-started_at")
        return Response(CallSerializer(qs, many=True).data)


class BlockedUsersListView(APIView):
    def get(self, request):
        qs = (
            BlockedUser.objects.filter(blocker=request.user)
            .select_related("blocked", "blocked__profile")
            .annotate(rating=Avg("blocked__rates_received__rate"))
            .order_by("-created_at")
        )

        items = list(qs)
        for obj in items:
            setattr(obj.blocked, "rating", obj.rating)

        return Response(BlockedUserSerializer(items, many=True).data)


class AddCarView(APIView):
    def post(self, request):
        serializer = CarCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        car = serializer.save()
        return Response({"car_number": car.car_number}, status=status.HTTP_201_CREATED)


class DeleteCarView(APIView):
    def delete(self, request, car_number: str):
        car_number = car_number.upper().strip()

        car = Car.objects.filter(car_number=car_number, user=request.user).first()

        if not car:
            return Response(
                {"detail": "Car not found or does not belong to you"},
                status=status.HTTP_404_NOT_FOUND,
            )

        car.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnblockUserView(APIView):
    def delete(self, request, user_id):
        deleted, _ = BlockedUser.objects.filter(
            blocker=request.user, blocked_id=user_id
        ).delete()

        if deleted == 0:
            return Response(
                {"detail": "User is not blocked"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class BlockUserView(APIView):
    def post(self, request):
        s = BlockUserSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(
            {
                "detail": "blocked",
                "blocked_user_id": str(obj.blocked_id),
                "created_at": obj.created_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class MessageDeleteForMeView(APIView):
    permission_classes = [IsChatParticipant]

    def post(self, request, chat_id, msg_id):
        msg = Message.objects.filter(id=msg_id, chat_id=chat_id).first()
        if not msg:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        DeletedMessage.objects.get_or_create(message=msg, user=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)


class MessageDeleteForAllView(APIView):
    permission_classes = [IsChatParticipant]

    def post(self, request, chat_id, msg_id):
        msg = Message.objects.filter(id=msg_id, chat_id=chat_id).first()
        if not msg:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # тільки відправник може видалити "для всіх"
        if msg.sender_id != request.user.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        msg.delete()  # реальне видалення з БД
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {"type": "chat.message_deleted", "message_id": msg_id},
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)


class CreateCallView(APIView):
    def post(self, request):
        receiver_id = request.data.get("receiver_id")
        if not receiver_id:
            return Response({"detail": "receiver_id required"}, status=400)

        receiver = User.objects.select_related("profile").filter(id=receiver_id).first()
        if not receiver:
            return Response({"detail": "Receiver not found"}, status=404)

        if receiver == request.user:
            return Response({"detail": "Cannot call yourself"}, status=400)

        if not receiver.profile.settings.get("allow_calls", True):
            return Response({"detail": "User does not allow calls"}, status=403)

        if is_blocked(request.user, receiver):
            return Response({"detail": "Blocked"}, status=403)

        call = Call.objects.create(
            caller=request.user, receiver=receiver, status="ringing"
        )
        return Response({"call_id": str(call.id), "status": call.status}, status=201)


class AcceptCallView(APIView):
    def post(self, request, call_id):
        call = (
            Call.objects.select_related("caller", "receiver").filter(id=call_id).first()
        )
        if not call:
            return Response({"detail": "Not found"}, status=404)
        if call.receiver != request.user:
            return Response({"detail": "Forbidden"}, status=403)
        if call.status != "ringing":
            return Response({"detail": "Invalid state"}, status=400)

        call.status = "in_progress"
        call.answered_at = timezone.now() if hasattr(call, "answered_at") else None
        call.save()
        return Response({"status": call.status})


class RejectCallView(APIView):
    def post(self, request, call_id):
        call = (
            Call.objects.select_related("caller", "receiver").filter(id=call_id).first()
        )
        if not call:
            return Response({"detail": "Not found"}, status=404)
        if call.receiver != request.user:
            return Response({"detail": "Forbidden"}, status=403)
        if call.status != "ringing":
            return Response({"detail": "Invalid state"}, status=400)

        call.status = "rejected"
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])
        return Response({"status": call.status})


class EndCallView(APIView):
    def post(self, request, call_id):
        call = (
            Call.objects.select_related("caller", "receiver").filter(id=call_id).first()
        )
        if not call:
            return Response({"detail": "Not found"}, status=404)
        if request.user not in (call.caller, call.receiver):
            return Response({"detail": "Forbidden"}, status=403)

        call.status = "ended"
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])
        return Response({"status": call.status})


class CallHistoryView(APIView):
    def get(self, request):
        qs = Call.objects.filter(
            Q(caller=request.user) | Q(receiver=request.user)
        ).order_by("-started_at")
        data = [
            {
                "id": str(c.id),
                "caller_id": str(c.caller_id),
                "receiver_id": str(c.receiver_id),
                "status": c.status,
                "started_at": c.started_at,
                "ended_at": c.ended_at,
            }
            for c in qs[:100]
        ]
        return Response(data)


class IceServersView(APIView):
    def get(self, request):
        return Response(
            {
                "iceServers": [
                    {"urls": ["stun:stun.l.google.com:19302"]},
                ]
            }
        )


class SendEmailView(APIView):
    """
    POST /api/email/send/
    Body: { "to": "...", "subject": "...", "body": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        s = SendEmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        to = s.validated_data["to"]
        subject = s.validated_data["subject"]
        body = s.validated_data["body"]
        user_to = User.objects.filter(id=to).first()
        if not user_to:
            return Response(
                {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        response = requests.post(
            "https://api.mailgun.net/v3/sandbox66b11c0a8eef4eeeace8879fec71adcd.mailgun.org/messages",
            auth=("api", os.getenv("MAILGUN_API_KEY")),
            data={
                "from": "Mailgun Sandbox <postmaster@sandbox66b11c0a8eef4eeeace8879fec71adcd.mailgun.org>",
                "to": user_to.email,
                "subject": subject,
                "text": body,
            },
        )

        if response.status_code != 200:
            return Response(
                {"detail": response.text},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"sent": response.status_code == 200}, status=status.HTTP_200_OK
        )


class ToggleAutoDeleteView(APIView):

    def post(self, request, chat_id):
        cp = ChatParticipant.objects.filter(chat_id=chat_id, user=request.user).first()
        if not cp:
            return Response({"detail": "Forbidden"}, status=403)

        if cp.auto_delete:
            cp.auto_delete = False
            cp.auto_delete_enabled_at = None
        else:
            cp.auto_delete = True
            cp.auto_delete_enabled_at = timezone.now()

        cp.save(update_fields=["auto_delete", "auto_delete_enabled_at"])
        return Response(
            {
                "auto_delete": cp.auto_delete,
                "auto_delete_enabled_at": cp.auto_delete_enabled_at,
            }
        )


class MessageEditView(APIView):
    permission_classes = [IsChatParticipant]

    def patch(self, request, chat_id, msg_id):
        msg = Message.objects.filter(id=msg_id, chat_id=chat_id).first()
        if not msg:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # лише автор
        if msg.sender_id != request.user.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        body = (request.data.get("body") or "").strip()

        # якщо у повідомленні немає картинки — не дозволяємо зробити його повністю пустим
        if not body and not msg.image:
            return Response(
                {"detail": "body required"}, status=status.HTTP_400_BAD_REQUEST
            )

        msg.body = body if body else None
        msg.save(update_fields=["body"])
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "chat.message_edited",
                "message": MessageSerializer(msg, context={"request": request}).data,
            },
        )

        # якщо хочеш синхронізацію через WS — можна додати group_send тут
        return Response(
            MessageSerializer(msg, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
