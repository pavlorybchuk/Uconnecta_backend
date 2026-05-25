"""
Django ORM Models for UConecta Backend.

This module defines the core data models for the UConecta application, including:
- User authentication and profiles
- Chat system (direct messaging)
- Call history tracking
- User blocking functionality
- Password reset tokens
- Rating system
"""

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
    """
    Returns default user profile settings as a dictionary.
    
    Settings include:
    - auto_delete_chats: Whether to automatically delete old chats (default: False)
    - show_nickname: Whether to display user's nickname to others (default: True)
    - allow_calls: Whether to allow incoming calls (default: True)
    
    Returns:
        dict: Default settings dictionary
    """
    return {
        "auto_delete_chats": False,
        "show_nickname": True,
        "allow_calls": True,
    }


def profile_photo_path(instance, filename):
    """
    Generates a unique file path for profile photos.
    
    This function creates a UUID-based filename to avoid conflicts and
    stores all profile photos in the 'profile_photos' directory.
    
    Args:
        instance: The model instance (Profile)
        filename (str): Original uploaded filename
        
    Returns:
        str: Path to save the file (e.g., 'profile_photos/uuid.jpg')
    """
    ext = filename.split(".")[-1]
    return os.path.join("profile_photos", f"{uuid.uuid4()}.{ext}")


class UserManager(BaseUserManager):
    """
    Custom user manager for the User model.
    
    Handles creation of regular users and superusers with custom fields.
    Validates that email, phone, and username are unique and not empty.
    """
    
    def create_user(self, email, phone, username, password=None, **extra_fields):
        """
        Create and save a regular user.
        
        Args:
            email (str): User's email address (unique, required)
            phone (str): User's phone number (unique, required)
            username (str): User's username (unique, required, max 8 chars)
            password (str): User's password (required, will be hashed)
            **extra_fields: Additional fields to set on the user
            
        Returns:
            User: The created user instance
            
        Raises:
            ValueError: If any required field is missing or already exists
        """
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
        """
        Create and save a superuser (admin) with elevated permissions.
        
        Args:
            email (str): Superuser's email address
            phone (str): Superuser's phone number
            username (str): Superuser's username
            password (str): Superuser's password
            **extra_fields: Additional fields
            
        Returns:
            User: The created superuser instance
        """
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self.create_user(email, phone, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model extending Django's AbstractBaseUser.
    
    Uses email as the primary authentication field instead of username.
    Stores user information including contact details and Firebase Cloud Messaging token.
    
    Fields:
        id (UUID): Primary key, unique identifier
        email (str): Email address, used for authentication
        phone (str): Phone number with country code
        country_code (str): 2-letter country code (default: 'UA')
        created_at (DateTime): Account creation timestamp
        username (str): Short username (8 chars max, user-friendly identifier)
        local_password (str): Optional local password (may be blank if using OAuth)
        fcm_token (str): Firebase Cloud Messaging token for push notifications
        is_staff (bool): Whether user can access admin panel
    """
    
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
    fcm_token = models.CharField(max_length=255, null=True, blank=True)
    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone", "username"]

    def __str__(self):
        """Return string representation (email address)."""
        return self.email


class Profile(models.Model):
    """
    Extended user profile information.
    
    Related to User model via OneToOneField. Contains personal details,
    profile photo, about section, and user preferences/settings.
    
    Fields:
        user (User): Link to User model (primary key relationship)
        name (str): First name
        surname (str): Last name
        patronymic (str): Patronymic name (Eastern European naming convention)
        how_to_address (str): Preferred form of address (nickname, shortened name, etc.)
        photo (ImageField): Profile photo/avatar
        about (str): User bio/about section
        settings (JSONField): User preferences (auto_delete, show_nickname, allow_calls)
    """
    
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
    """
    Stores vehicle information for users.
    
    Allows users to register their vehicles' license plates for identification
    in ride-sharing or matching scenarios.
    
    Fields:
        car_number (str): Vehicle license plate (primary key, unique)
        user (User): Foreign key to User model
    """
    
    car_number = models.CharField(max_length=8, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cars")

    def __str__(self):
        """Return formatted string representation."""
        return f"{self.user.username} - {self.car_number}"


class Chat(models.Model):
    """
    Represents a chat conversation.
    
    Currently only supports direct (one-to-one) chats between two users.
    Stores metadata about the chat including creation time and last message timestamp.
    
    Fields:
        id (UUID): Primary key, unique identifier
        type (str): Chat type choice ('direct' is currently the only option)
        created_at (DateTime): When the chat was created
        last_message_at (DateTime): Timestamp of the most recent message
        direct_key (str): Unique key for direct chats (format: 'user_id:user_id' sorted)
    """
    
    CHAT_TYPES = (("direct", "Direct"),)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=10, choices=CHAT_TYPES, default="direct")

    created_at = models.DateTimeField(default=timezone.now)
    last_message_at = models.DateTimeField(blank=True, null=True)

    direct_key = models.CharField(max_length=80, unique=True, blank=True, null=True)


class ChatParticipant(models.Model):
    """
    Represents a user's participation in a chat.
    
    Links users to chats and tracks individual participant metadata like
    deletion status and auto-delete preferences.
    
    Fields:
        chat (Chat): Foreign key to Chat
        user (User): Foreign key to User
        deleted_at (DateTime): When user deleted the chat (null = not deleted)
        auto_delete (bool): Whether to auto-delete old messages in this chat
        auto_delete_enabled_at (DateTime): When auto-delete was enabled
    """
    
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
    """
    Generates a unique file path for chat message images.
    
    Creates UUID-based filenames and stores all images in the 'chat_images' directory.
    
    Args:
        instance: The model instance (Message)
        filename (str): Original uploaded filename
        
    Returns:
        str: Path to save the file (e.g., 'chat_images/uuid.jpg')
    """
    ext = filename.split(".")[-1]
    return os.path.join("chat_images", f"{uuid.uuid4()}.{ext}")


class Message(models.Model):
    """
    Represents a single message in a chat.
    
    Can contain either text content, an image, or both.
    Linked to a chat and a sender user.
    
    Fields:
        id (UUID): Primary key (auto-generated)
        chat (Chat): Foreign key to Chat
        sender (User): Foreign key to sender User
        body (str): Message text content (optional)
        created_at (DateTime): When the message was sent
        image (ImageField): Attached image (optional)
    """
    
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="messages_sent"
    )
    body = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    image = models.ImageField(upload_to=chat_image_path, blank=True, null=True)

    class Meta:
        # Index on (chat, created_at) for efficient sorting and filtering
        indexes = [models.Index(fields=["chat", "-created_at"])]


class Rate(models.Model):
    """
    Stores user ratings/reviews.
    
    Allows users to rate other users on a scale of 0-5.
    The sender can be null if the rater deletes their account.
    
    Fields:
        id (UUID): Primary key, unique identifier
        addressee (User): Foreign key to the user being rated
        sender (User): Foreign key to the user giving the rating
        rate (Decimal): Rating value between 0.0 and 5.0
    """
    
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
        # Database constraint to ensure rate is between 0 and 5
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate__gte=0.0) & models.Q(rate__lte=5.0),
                name="rate_between_0_and_5",
            )
        ]


class BlockedUser(models.Model):
    """
    Tracks user blocking relationships.
    
    When a user blocks another, they won't see their messages or be able
    to interact with them.
    
    Fields:
        blocker (User): Foreign key to user doing the blocking
        blocked (User): Foreign key to user being blocked
        created_at (DateTime): When the block was created
    """
    
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocking")
    blocked = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="blocked_by"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("blocker", "blocked")


class PasswordReset(models.Model):
    """
    Stores password reset tokens for account recovery.
    
    When a user requests a password reset, a token is generated that expires
    after a certain time. The token can only be used once.
    
    Fields:
        id (UUID): Primary key, unique identifier
        user (User): Foreign key to User requesting reset
        token (str): Reset token (should be secure/random)
        expires_at (DateTime): When the token expires
        used (bool): Whether this token has been used
        created_at (DateTime): When the reset request was created
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)


class Call(models.Model):
    """
    Stores call history and call state information.
    
    Records details about calls between users including timing,
    status (initiated, accepted, declined, ended), and call token for WebRTC.
    
    Fields:
        id (UUID): Primary key, unique identifier
        caller (User): Foreign key to user initiating the call
        receiver (User): Foreign key to user receiving the call
        started_at (DateTime): When the call was initiated
        answered_at (DateTime): When the receiver accepted (null if rejected)
        ended_at (DateTime): When the call ended (null if still active)
        call_token (UUID): Unique token for WebRTC signaling
        status (str): Current call status (initiated, accepted, declined, ended)
    """
    
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
        """Call status choices."""
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
    """
    Tracks messages deleted by users (for-me deletion).
    
    When a user deletes a message for themselves, this record is created.
    The message itself isn't deleted from database, only hidden from that user.
    
    Fields:
        message (Message): Foreign key to the deleted Message
        user (User): Foreign key to user who deleted the message
        deleted_at (DateTime): When the message was deleted
    """
    
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
