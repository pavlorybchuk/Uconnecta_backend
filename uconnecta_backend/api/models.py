import os
import uuid
from django.conf import settings
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
    Group,
    Permission,
)
from django.utils import timezone
from django.db.models import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator


def default_settings():
    return {
        "auto_delete_chats": False,
        "show_nickname": True,
        "allow_calls": True,
    }


def profile_photo_path(instance, filename):
    ext = filename.split(".")[-1]
    return os.path.join("profile_photos", f"{uuid.uuid4()}.{ext}")


class UserManager(BaseUserManager):
    def create_user(self, email, phone, username, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not phone:
            raise ValueError("Phone is required")
        if not username:
            raise ValueError("Username is required")
        if not password:
            raise ValueError("Password is required")

        email = self.normalize_email(email)

        if self.model.objects.filter(email=email).exists():
            raise ValueError("Email already exists")
        if self.model.objects.filter(phone=phone).exists():
            raise ValueError("Phone already exists")
        if self.model.objects.filter(username=username).exists():
            raise ValueError("Username already exists")

        user = self.model(email=email, phone=phone, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, phone, username, password=None, **extra_fields):
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self.create_user(email, phone, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=16, unique=True)
    country_code = models.CharField(max_length=2, blank=True, default="UA")
    created_at = models.DateTimeField(default=timezone.now)

    username = models.CharField(max_length=8, unique=True)
    local_password = models.CharField(max_length=255, blank=True, null=True)

    is_staff = models.BooleanField(default=False)

    groups = models.ManyToManyField(Group, related_name="custom_user_set", blank=True)
    user_permissions = models.ManyToManyField(
        Permission, related_name="custom_user_set", blank=True
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone", "username"]

    def __str__(self):
        return self.email


class Profile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="profile"
    )
    name = models.CharField(max_length=50, blank=True, null=True)
    surname = models.CharField(max_length=50, blank=True, null=True)
    patronymic = models.CharField(max_length=50, blank=True, null=True)

    how_to_address = models.CharField(max_length=30, blank=True, null=True)
    photo = models.ImageField(upload_to=profile_photo_path, blank=True, null=True)
    about = models.TextField(blank=True, null=True)

    settings = JSONField(default=default_settings)


class Car(models.Model):
    car_number = models.CharField(max_length=8, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cars")

    def __str__(self):
        return f"{self.user.username} - {self.car_number}"


class Chat(models.Model):
    CHAT_TYPES = (("direct", "Direct"),)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=10, choices=CHAT_TYPES, default="direct")

    created_at = models.DateTimeField(default=timezone.now)
    last_message_at = models.DateTimeField(blank=True, null=True)

    direct_key = models.CharField(max_length=80, unique=True, blank=True, null=True)


class ChatParticipant(models.Model):
    chat = models.ForeignKey(
        Chat, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="chat_participations"
    )

    deleted_at = models.DateTimeField(blank=True, null=True)
    auto_delete = models.BooleanField(default=False)
    auto_delete_enabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("chat", "user")


def chat_image_path(instance, filename):
    ext = filename.split(".")[-1]
    return os.path.join("chat_images", f"{uuid.uuid4()}.{ext}")


class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="messages_sent"
    )
    body = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    image = models.ImageField(upload_to=chat_image_path, blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["chat", "-created_at"])]


class Rate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    addressee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="rates_received"
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rates_given",
    )
    rate = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(5.0),
        ],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate__gte=0.0) & models.Q(rate__lte=5.0),
                name="rate_between_0_and_5",
            )
        ]


class BlockedUser(models.Model):
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocking")
    blocked = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="blocked_by"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("blocker", "blocked")


class PasswordReset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)


class Call(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="calls_made"
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="calls_received"
    )

    started_at = models.DateTimeField(default=timezone.now)
    answered_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)

    call_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Status(models.TextChoices):
        INITIATED = "initiated"
        ACCEPTED = "accepted"
        DECLINED = "declined"
        ENDED = "ended"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED,
    )


class DeletedMessage(models.Model):
    message = models.ForeignKey(
        "Message", on_delete=models.CASCADE, related_name="deleted_for"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [
            models.Index(fields=["user", "message"]),
        ]
