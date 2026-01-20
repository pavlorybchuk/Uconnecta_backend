from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, Chat, ChatParticipant, Message, Rate, BlockedUser, PasswordReset

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = [
            "user_id",
            "email",
            "phone",
            "username",
            "country_code",
            "isPremium",
            "created_at",
            "password",
        ]
        read_only_fields = ["user_id", "created_at", "isPremium"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = ["user", "name", "surname", "patronymic", "how_to_address", "photo", "about", "settings"]

class ChatParticipantSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = ChatParticipant
        fields = ["user", "deleted_at", "auto_delete"]

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "chat", "sender", "body", "created_at"]
        read_only_fields = ["id", "created_at", "sender"]

class ChatSerializer(serializers.ModelSerializer):
    participants = ChatParticipantSerializer(source="chatparticipant_set", many=True, read_only=True)
    messages = MessageSerializer(source="message_set", many=True, read_only=True)

    class Meta:
        model = Chat
        fields = ["id", "created_at", "last_message", "participants", "messages"]
        read_only_fields = ["id", "created_at", "last_message", "participants", "messages"]

class RateSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    addressee = UserSerializer(read_only=True)

    class Meta:
        model = Rate
        fields = ["id", "sender", "addressee", "rate"]

class BlockedUserSerializer(serializers.ModelSerializer):
    blocker = UserSerializer(read_only=True)
    blocked = UserSerializer(read_only=True)

    class Meta:
        model = BlockedUser
        fields = ["blocker", "blocked", "created_at"]
        read_only_fields = ["created_at"]

class PasswordResetSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = PasswordReset
        fields = ["id", "user", "token", "expires_at", "used", "created_at"]
        read_only_fields = ["id", "created_at", "used"]

class LocalPasswordSerializer(serializers.ModelSerializer):
    local_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ["local_password"]

    def update(self, instance, validated_data):
        instance.local_password = validated_data["local_password"]
        instance.save()
        return instance