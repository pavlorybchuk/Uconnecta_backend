from django.http import JsonResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    User,
    Profile,
    Chat,
    ChatParticipant,
    Message,
    Rate,
    BlockedUser,
    PasswordReset,
    Call,
    Car,
)
from .serializers import (
    UserSerializer,
    ProfileSerializer,
    ChatSerializer,
    ChatParticipantSerializer,
    MessageSerializer,
    RateSerializer,
    BlockedUserSerializer,
    PasswordResetSerializer,
    LocalPasswordSerializer,
    CallSerializer,
    CarSerializer,
)
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import uuid


def start_call(caller, receiver) -> Call:
    call = Call.objects.create(
        caller=caller, receiver=receiver, status="ringing", call_token=str(uuid.uuid4())
    )
    return call


def answer_call(call) -> Call:
    call.status = "in_progress"
    call.save()
    return call


def end_call(call) -> Call:
    call.status = "ended"
    call.ended_at = timezone.now()
    call.save()
    return call


class CallViewSet(viewsets.ModelViewSet):
    queryset = Call.objects.all()
    serializer_class = CallSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def start(self, request) -> Response:
        receiver_id = request.data.get("receiver_id")
        receiver = User.objects.get(pk=receiver_id)
        call = start_call(request.user, receiver)
        serializer = self.get_serializer(call)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None) -> Response:
        call = self.get_object()
        call = answer_call(call)
        serializer = self.get_serializer(call)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None) -> Response:
        call = self.get_object()
        call = end_call(call)
        serializer = self.get_serializer(call)
        return Response(serializer.data)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["email", "username", "phone"]
    ordering_fields = ["created_at", "username"]

    @action(detail=True, methods=["patch"], serializer_class=LocalPasswordSerializer)
    def set_local_password(self, request, pk=None) -> Response:
        user = self.get_object()
        serializer = LocalPasswordSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "local password updated"})


class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]


class ChatViewSet(viewsets.ModelViewSet):
    queryset = Chat.objects.all()
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "last_message"]


class ChatParticipantViewSet(viewsets.ModelViewSet):
    queryset = ChatParticipant.objects.all()
    serializer_class = ChatParticipantSerializer
    permission_classes = [IsAuthenticated]


class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]


class RateViewSet(viewsets.ModelViewSet):
    queryset = Rate.objects.all()
    serializer_class = RateSerializer
    permission_classes = [IsAuthenticated]


class BlockedUserViewSet(viewsets.ModelViewSet):
    queryset = BlockedUser.objects.all()
    serializer_class = BlockedUserSerializer
    permission_classes = [IsAuthenticated]


class PasswordResetViewSet(viewsets.ModelViewSet):
    queryset = PasswordReset.objects.all()
    serializer_class = PasswordResetSerializer
    permission_classes = [IsAuthenticated]


class CarViewSet(viewsets.ModelViewSet):
    queryset = Car.objects.all()
    serializer_class = CarSerializer
    permission_classes = [IsAuthenticated]


def search_user(request) -> JsonResponse:
    if request.method == "GET":
        username = request.GET.get("username")
        car_number = request.GET.get("number")

        if car_number:
            try:
                car = Car.objects.select_related("user").get(car_number=car_number)
                user = car.user
                return JsonResponse(
                    {
                        "id": user.user_id,
                        "username": user.username,
                        "email": user.email,
                        "car_number": car.car_number,
                        "full_name": (
                            (
                                user.profile.surname
                                + user.profile.name
                                + user.profile.patronymic
                            )
                            if user.profile.settings.get("show_nickname", False)
                            else (
                                user.profile.how_to_address
                                if user.profile.how_to_address
                                else None
                            )
                        ),
                        "photo": user.profile.photo if user.profile.photo else None,
                        "about": user.profile.about,
                    }
                )
            except Car.DoesNotExist:
                return JsonResponse({"error": "Car not found"}, status=404)

        elif username:
            try:
                user = User.objects.get(username=username)
                car = Car.objects.filter(user__username=user.username).first()
                return JsonResponse(
                    {
                        "id": user.user_id,
                        "username": user.username,
                        "email": user.email,
                        "car_number": car.car_number if car else None,
                        "full_name": (
                            (
                                user.profile.surname
                                + user.profile.name
                                + user.profile.patronymic
                            )
                            if user.profile.settings.get("show_nickname", False)
                            else (
                                user.profile.how_to_address
                                if user.profile.how_to_address
                                else None
                            )
                        ),
                        "photo": (
                            request.build_absolute_uri(user.profile.photo.url)
                            if user.profile.photo
                            else None
                        ),
                        "about": user.profile.about,
                    }
                )
            except User.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)

        else:
            return JsonResponse(
                {"error": "Provide username or car number as query parameter"},
                status=400,
            )
