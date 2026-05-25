"""
Django REST Framework Serializers for UConecta Backend.

Serializers handle conversion between Python objects and JSON for API requests/responses.
They also provide validation for incoming data.

Main serializers:
- User authentication: RegisterSerializer, LogoutSerializer
- User data: MeSerializer, MeUpdateSerializer, UserPublicSerializer
- Chat functionality: ChatListSerializer, MessageSerializer
- Blocking: BlockUserSerializer, BlockedUserSerializer
- Calls: CallSerializer
- Other: CarCreateSerializer, SendEmailSerializer
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, Car, Chat, Message, Call, BlockedUser
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

User = get_user_model()


class LogoutSerializer(serializers.Serializer):
    """
    Serializer for user logout.
    
    Accepts a refresh token and blacklists it to invalidate the session.
    Used by the LogoutView to securely log out users.
    
    Fields:
        refresh (str): The JWT refresh token to invalidate
    """
    refresh = serializers.CharField()

    def validate(self, attrs):
        """Store the refresh token for use in save()."""
        self.token = attrs["refresh"]
        return attrs

    def save(self, **kwargs):
        """
        Blacklist the refresh token to prevent further use.
        
        Raises:
            ValidationError: If the token is invalid or expired
        """
        try:
            RefreshToken(self.token).blacklist()
        except TokenError:
            raise serializers.ValidationError({"refresh": "Invalid or expired token"})


class RegisterSerializer(serializers.Serializer):
    """
    Serializer for user registration.
    
    Validates user input and creates a new User account with associated Profile.
    Generates a unique 8-character username if not provided.
    
    Fields:
        email (str): Email address (must be unique)
        phone (str): Phone number (must be unique)
        username (str): Optional username (max 8 chars, will be auto-generated if not provided)
        password (str): Password (min 6 chars, write-only)
        repeat_password (str): Password confirmation (must match password)
        how_to_address (str): Preferred nickname or form of address (optional)
    """
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=16)
    username = serializers.CharField(max_length=8, required=False)
    password = serializers.CharField(write_only=True, min_length=6)
    repeat_password = serializers.CharField(write_only=True, min_length=6)
    how_to_address = serializers.CharField(
        max_length=30, required=False, allow_blank=True
    )

    def validate_email(self, value):
        """Ensure email is not already registered."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists")
        return value

    def validate_phone(self, value):
        """Ensure phone number is not already registered."""
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("User with this phone already exists")
        return value

    def validate_username(self, value):
        """Ensure username is not already taken."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("User with this username already exists")
        return value

    def validate(self, attrs):
        """Validate that passwords match."""
        if attrs["password"] != attrs["repeat_password"]:
            raise serializers.ValidationError(
                {"repeat_password": "Passwords do not match"}
            )
        return attrs

    def create(self, validated_data):
        """
        Create new User and associated Profile.
        
        Args:
            validated_data (dict): Validated user data
            
        Returns:
            User: The newly created user instance
        """
        username = validated_data.get("username")
        if not username:
            raise serializers.ValidationError(
                {"username": "Username generation failed"}
            )
        how_to_address = validated_data.pop("how_to_address", "")
        validated_data.pop("repeat_password")

        user = User.objects.create_user(**validated_data)

        user.profile.how_to_address = how_to_address
        user.profile.save(update_fields=["how_to_address"])

        return user


class CarCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/registering a vehicle.
    
    Allows users to add their vehicle's license plate number.
    Normalizes and validates the car number format.
    
    Fields:
        car_number (str): Vehicle license plate (must be unique)
    """
    class Meta:
        model = Car
        fields = ["car_number"]

    def validate_car_number(self, value):
        """
        Normalize and validate car number.
        
        Converts to uppercase and strips whitespace.
        Ensures it's not already registered.
        """
        value = value.upper().strip()
        if Car.objects.filter(car_number=value).exists():
            raise serializers.ValidationError("Car with this number already exists")
        return value

    def create(self, validated_data):
        """Create car record linked to the current user."""
        user = self.context["request"].user
        return Car.objects.create(user=user, **validated_data)


class ProfilePublicSerializer(serializers.ModelSerializer):
    """
    Serializer for public profile information.
    
    Exposes limited profile details for viewing by other users.
    Does not include sensitive settings or internal data.
    
    Fields:
        name (str): First name
        surname (str): Last name
        patronymic (str): Patronymic name
        how_to_address (str): Preferred nickname
        photo (ImageField): Profile photo URL
        about (str): Bio/description
        settings (JSONField): User preferences
    """
    class Meta:
        model = Profile
        fields = [
            "name",
            "surname",
            "patronymic",
            "how_to_address",
            "photo",
            "about",
            "settings",
        ]


class MeSerializer(serializers.ModelSerializer):
    """
    Serializer for the current user's full profile (GET /api/me/).
    
    Returns comprehensive user information including cars, ratings, and profile.
    Uses read-only fields for security.
    
    Fields:
        id (UUID): User ID
        email (str): Email address
        phone (str): Phone number
        username (str): Username
        how_to_address (str): Preferred nickname
        profile (ProfilePublicSerializer): Nested profile data
        cars (list): List of registered car numbers
        rating (float): Average rating from other users
        has_password (bool): Whether user has a local password set
    """
    how_to_address = serializers.CharField(
        source="profile.how_to_address", read_only=True
    )
    profile = ProfilePublicSerializer(read_only=True)
    cars = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    def get_cars(self, obj):
        """Return list of car numbers owned by user."""
        return list(obj.cars.values_list("car_number", flat=True))

    def get_has_password(self, obj):
        """Return whether user has set a local password."""
        return bool(obj.local_password)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "username",
            "how_to_address",
            "profile",
            "cars",
            "rating",
            "has_password",
        ]

    def get_rating(self, obj):
        """
        Return user's average rating rounded to 2 decimal places.
        
        Returns None if no ratings exist.
        """
        r = getattr(obj, "rating", None)
        return None if r is None else round(float(r), 2)


class MeUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating user profile (PATCH /api/me/).
    
    Allows users to update their basic info, profile details, and preferences.
    All fields are optional for partial updates.
    Includes validation for uniqueness of email, phone, and username.
    
    Fields:
        email (str): Email address (must be unique if changed)
        phone (str): Phone number (must be unique if changed)
        username (str): Username (must be unique if changed)
        name (str): First name
        surname (str): Last name
        patronymic (str): Patronymic name
        how_to_address (str): Preferred form of address
        about (str): Bio/description
        settings (dict): User preference settings
    """
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(max_length=16, required=False)
    username = serializers.CharField(max_length=8, required=False)
    name = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )
    surname = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )
    patronymic = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )
    how_to_address = serializers.CharField(
        max_length=30, required=False, allow_null=True, allow_blank=True
    )
    about = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    settings = serializers.JSONField(required=False)

    def validate_email(self, v):
        """Ensure new email is not already in use by another user."""
        if (
            User.objects.filter(email=v)
            .exclude(pk=self.context["request"].user.pk)
            .exists()
        ):
            raise serializers.ValidationError("Email already exists")
        return v

    def validate_phone(self, v):
        """Ensure new phone is not already in use by another user."""
        if (
            User.objects.filter(phone=v)
            .exclude(pk=self.context["request"].user.pk)
            .exists()
        ):
            raise serializers.ValidationError("Phone already exists")
        return v

    def validate_username(self, v):
        """Ensure new username is not already in use by another user."""
        if (
            User.objects.filter(username=v)
            .exclude(pk=self.context["request"].user.pk)
            .exists()
        ):
            raise serializers.ValidationError("Username already exists")
        return v

    def validate_settings(self, value):
        """
        Validate settings object structure and allowed keys.
        
        Only allows specific settings keys and all values must be booleans.
        """
        allowed = {"auto_delete_chats", "show_nickname", "allow_calls"}

        if not isinstance(value, dict):
            raise serializers.ValidationError("settings must be an object")

        unknown = set(value.keys()) - allowed
        if unknown:
            raise serializers.ValidationError(
                f"Unknown keys: {', '.join(sorted(unknown))}"
            )

        for k, v in value.items():
            if not isinstance(v, bool):
                raise serializers.ValidationError(f"{k} must be boolean")

        return value

    def update(self, instance, validated_data):
        """
        Update user and profile with validated data.
        
        Args:
            instance (User): The user to update
            validated_data (dict): Validated data from serializer
            
        Returns:
            User: Updated user instance
        """
        profile = instance.profile

        # Update user model fields
        for f in ["email", "phone", "username"]:
            if f in validated_data:
                setattr(instance, f, validated_data[f])

        # Update settings (merge with existing)
        if "settings" in validated_data:
            current = profile.settings or {}
            current.update(validated_data["settings"])
            profile.settings = current

        # Update profile fields
        for f in [
            "name",
            "surname",
            "patronymic",
            "how_to_address",
            "about",
        ]:
            if f in validated_data:
                setattr(profile, f, validated_data[f])

        instance.save()
        profile.save()
        return instance


class ChatListSerializer(serializers.ModelSerializer):
    """
    Serializer for chat list response (GET /api/chats/).
    
    Returns active chats with the other participant's info and auto-delete status.
    Uses context to provide additional data efficiently.
    
    Fields:
        id (UUID): Chat ID
        type (str): Chat type ('direct')
        created_at (DateTime): When chat was created
        last_message_at (DateTime): When last message was sent
        auto_delete (bool): Whether auto-delete is enabled
        other_user (UserPublicSerializer): The other participant's public info
        auto_delete_enabled_at (DateTime): When auto-delete was turned on
    """
    auto_delete = serializers.SerializerMethodField()
    other_user = serializers.SerializerMethodField()
    auto_delete_enabled_at = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = [
            "id",
            "type",
            "created_at",
            "last_message_at",
            "auto_delete",
            "other_user",
            "auto_delete_enabled_at",
        ]

    def get_auto_delete(self, chat: Chat):
        """Get auto-delete status for this chat from context."""
        m = self.context.get("auto_delete_by_chat") or {}
        return bool(m.get(chat.id, False))

    def get_other_user(self, chat: Chat):
        """Get the other participant in this chat from context."""
        m = self.context.get("other_user_by_chat") or {}
        other = m.get(chat.id)
        if not other:
            return None

        request = self.context.get("request")
        return UserPublicSerializer(other, context={"request": request}).data

    def get_auto_delete_enabled_at(self, chat: Chat):
        """Get when auto-delete was enabled for this chat."""
        m = self.context.get("auto_delete_enabled_at_by_chat") or {}
        dt = m.get(chat.id)
        return dt


class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer for chat messages (GET/POST /api/chats/{id}/messages/).
    
    Handles message data including text, images, and sender information.
    Sender field is read-only to prevent users from impersonating others.
    
    Fields:
        id (UUID): Message ID (read-only)
        chat (UUID): Chat ID this message belongs to
        sender (UUID): User ID of sender (read-only)
        sender_username (str): Sender's username (read-only)
        body (str): Message text content
        image (ImageField): Attached image
        created_at (DateTime): When message was sent (read-only)
    """
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "chat",
            "sender",
            "sender_username",
            "body",
            "image",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "sender"]


class CallSerializer(serializers.ModelSerializer):
    """
    Serializer for call history and call information.
    
    Returns call details including participants, timing, and current status.
    
    Fields:
        id (UUID): Call ID
        caller (UUID): User ID of call initiator
        receiver (UUID): User ID of call recipient
        started_at (DateTime): When call started
        ended_at (DateTime): When call ended
        status (str): Current call status
        call_token (UUID): Token for WebRTC signaling
    """
    class Meta:
        model = Call
        fields = [
            "id",
            "caller",
            "receiver",
            "started_at",
            "ended_at",
            "status",
            "call_token",
        ]


class UserPublicSerializer(serializers.ModelSerializer):
    """
    Serializer for publicly visible user information.
    
    Returns limited user data shown in search results and user profiles.
    Includes calculated fields like rating and display name based on preferences.
    Includes blocking status relative to the requesting user.
    
    Fields:
        id (UUID): User ID
        username (str): Username
        display_name (str): Formatted name (nickname or full name)
        about (str): User bio
        photo (ImageField): Profile photo URL
        rating (float): Average rating
        isBlocked (bool): Whether requesting user has blocked this user
    """
    display_name = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    about = serializers.CharField(
        source="profile.about", read_only=True, allow_null=True
    )
    photo = serializers.ImageField(
        source="profile.photo", read_only=True, allow_null=True
    )
    isBlocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "about",
            "photo",
            "rating",
            "isBlocked",
        ]

    def get_display_name(self, obj):
        """
        Return appropriate display name based on user's preferences.
        
        If show_nickname is True, returns the nickname (how_to_address).
        Otherwise returns full name (surname + name + patronymic).
        Falls back to nickname if full name is empty.
        """
        profile = obj.profile
        show_nickname = profile.settings.get("show_nickname", True)

        if show_nickname:
            return profile.how_to_address or None

        parts = [
            profile.surname,
            profile.name,
            profile.patronymic,
        ]
        full_name = " ".join(p for p in parts if p).strip()

        return full_name or profile.how_to_address or None

    def get_rating(self, obj):
        """Return average rating rounded to 2 decimal places, or None if no ratings."""
        r = getattr(obj, "rating", None)
        return None if r is None else round(float(r), 2)

    def get_isBlocked(self, obj):
        """
        Check if the requesting user has blocked this user or vice versa.
        
        Returns False if no authenticated user in request context.
        """
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return (
            BlockedUser.objects.filter(blocker=request.user, blocked=obj).exists()
            or BlockedUser.objects.filter(blocker=obj, blocked=request.user).exists()
        )


class BlockedUserSerializer(serializers.ModelSerializer):
    """
    Serializer for blocked user records (GET /api/blocked/).
    
    Returns the list of users blocked by the requesting user.
    
    Fields:
        created_at (DateTime): When the user was blocked
        user (UserPublicSerializer): The blocked user's public information
    """
    user = serializers.SerializerMethodField()

    class Meta:
        model = BlockedUser
        fields = ["created_at", "user"]

    def get_user(self, obj):
        """Return public data of the blocked user."""
        return UserPublicSerializer(obj.blocked).data


class BlockUserSerializer(serializers.Serializer):
    """
    Serializer for blocking a user (POST /api/block/).
    
    Validates that the user to block exists and isn't the requesting user.
    Creates or retrieves a BlockedUser record.
    
    Fields:
        user_id (UUID): ID of user to block
    """
    user_id = serializers.UUIDField()

    def validate_user_id(self, value):
        """
        Validate that the user exists and isn't the requesting user.
        
        Raises:
            ValidationError: If user doesn't exist or is the requesting user
        """
        request = self.context["request"]
        if str(request.user.id) == str(value):
            raise serializers.ValidationError("You cannot block yourself")

        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found")

        return value

    def create(self, validated_data):
        """
        Create or get BlockedUser record.
        
        Uses get_or_create to handle idempotent blocking.
        """
        request = self.context["request"]
        blocked_id = validated_data["user_id"]
        obj, _created = BlockedUser.objects.get_or_create(
            blocker=request.user, blocked_id=blocked_id
        )
        return obj


class SendEmailSerializer(serializers.Serializer):
    """
    Serializer for sending emails to users (POST /api/email/send/).
    
    Validates email content and target user.
    
    Fields:
        to (UUID): ID of user to send email to
        subject (str): Email subject (max 150 chars)
        body (str): Email body/message (max 5000 chars)
    """
    to = serializers.UUIDField()
    subject = serializers.CharField(max_length=150)
    body = serializers.CharField(max_length=5000)
