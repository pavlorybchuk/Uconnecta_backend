from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, Car, Chat, Message, Call, BlockedUser
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

User = get_user_model()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        self.token = attrs["refresh"]
        return attrs

    def save(self, **kwargs):
        try:
            RefreshToken(self.token).blacklist()
        except TokenError:
            raise serializers.ValidationError({"refresh": "Invalid or expired token"})


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=16)
    username = serializers.CharField(max_length=8)
    password = serializers.CharField(write_only=True, min_length=6)
    repeat_password = serializers.CharField(write_only=True, min_length=6)
    how_to_address = serializers.CharField(
        max_length=30, required=False, allow_blank=True
    )

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists")
        return value

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("User with this phone already exists")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("User with this username already exists")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["repeat_password"]:
            raise serializers.ValidationError(
                {"repeat_password": "Passwords do not match"}
            )
        return attrs

    def create(self, validated_data):
        how_to_address = validated_data.pop("how_to_address")
        validated_data.pop("repeat_password")

        user = User.objects.create_user(**validated_data)

        user.profile.how_to_address = how_to_address
        user.profile.save(update_fields=["how_to_address"])

        return user


class CarCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = ["car_number"]

    def validate_car_number(self, value):
        value = value.upper().strip()
        if Car.objects.filter(car_number=value).exists():
            raise serializers.ValidationError("Car with this number already exists")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        return Car.objects.create(user=user, **validated_data)


class ProfilePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        exclude = ["settings"]


class ProfileSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["settings"]


class MeSerializer(serializers.ModelSerializer):
    how_to_address = serializers.CharField(
        source="profile.how_to_address", read_only=True
    )
    profile = ProfilePublicSerializer(read_only=True)
    cars = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    def get_cars(self, obj):
        return list(obj.cars.values_list("car_number", flat=True))

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
        ]

    def get_rating(self, obj):
        r = getattr(obj, "rating", None)
        return None if r is None else round(float(r), 2)


class MeUpdateSerializer(serializers.Serializer):
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
        if (
            User.objects.filter(email=v)
            .exclude(pk=self.context["request"].user.pk)
            .exists()
        ):
            raise serializers.ValidationError("Email already exists")
        return v

    def validate_phone(self, v):
        if (
            User.objects.filter(phone=v)
            .exclude(pk=self.context["request"].user.pk)
            .exists()
        ):
            raise serializers.ValidationError("Phone already exists")
        return v

    def validate_username(self, v):
        if (
            User.objects.filter(username=v)
            .exclude(pk=self.context["request"].user.pk)
            .exists()
        ):
            raise serializers.ValidationError("Username already exists")
        return v

    def update(self, instance, validated_data):
        profile = instance.profile

        for f in ["email", "phone", "username"]:
            if f in validated_data:
                setattr(instance, f, validated_data[f])

        for f in [
            "name",
            "surname",
            "patronymic",
            "how_to_address",
            "about",
            "settings",
        ]:
            if f in validated_data:
                setattr(profile, f, validated_data[f])

        instance.save()
        profile.save()
        return instance


class ChatListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["id", "type", "created_at", "last_message_at"]


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    image = serializers.ImageField(read_only=True, allow_null=True)

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
        read_only_fields = ["id", "created_at", "sender", "chat"]


class CallSerializer(serializers.ModelSerializer):
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
        profile = obj.profile

        show_nickname = profile.settings.get("show_nickname", True)

        if show_nickname:
            return profile.how_to_address
        parts = [
            profile.surname,
            profile.name,
            profile.patronymic,
        ]
        full_name = " ".join(p for p in parts if p)
        return full_name or profile.how_to_address

    def get_rating(self, obj):
        r = getattr(obj, "rating", None)
        return None if r is None else round(float(r), 2)

    def get_isBlocked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return (
            BlockedUser.objects.filter(blocker=request.user, blocked=obj).exists()
            or BlockedUser.objects.filter(blocker=obj, blocked=request.user).exists()
        )


class BlockedUserSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = BlockedUser
        fields = ["created_at", "user"]

    def get_user(self, obj):
        return UserPublicSerializer(obj.blocked).data


class BlockUserSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()

    def validate_user_id(self, value):
        request = self.context["request"]
        if str(request.user.id) == str(value):
            raise serializers.ValidationError("You cannot block yourself")

        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found")

        return value

    def create(self, validated_data):
        request = self.context["request"]
        blocked_id = validated_data["user_id"]
        obj, _created = BlockedUser.objects.get_or_create(
            blocker=request.user, blocked_id=blocked_id
        )
        return obj


class SendEmailSerializer(serializers.Serializer):
    to = serializers.UUIDField()
    subject = serializers.CharField(max_length=150)
    body = serializers.CharField(max_length=5000)
