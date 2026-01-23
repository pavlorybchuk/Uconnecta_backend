from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import (
    Profile, Car, Chat, ChatParticipant,
    Message, Call, Rate, BlockedUser, PasswordReset
)

User = get_user_model()


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "username", "phone", "isPremium", "is_staff", "created_at")
    list_filter = ("isPremium", "is_staff")
    search_fields = ("email", "username", "phone")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "isPremium")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "how_to_address")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("user",)


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("car_number", "user")
    search_fields = ("car_number", "user__username")


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "created_at", "last_message_at")
    search_fields = ("id", "direct_key")
    list_filter = ("type",)


@admin.register(ChatParticipant)
class ChatParticipantAdmin(admin.ModelAdmin):
    list_display = ("chat", "user", "deleted_at", "auto_delete")
    list_filter = ("auto_delete",)
    search_fields = ("user__username", "chat__id")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("chat", "sender", "created_at")
    search_fields = ("sender__username", "body")
    ordering = ("-created_at",)


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ("caller", "receiver", "status", "started_at", "ended_at")
    list_filter = ("status",)
    search_fields = ("caller__username", "receiver__username")


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = ("sender", "addressee", "rate")


@admin.register(BlockedUser)
class BlockedUserAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")


@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ("user", "used", "expires_at")
    list_filter = ("used",)