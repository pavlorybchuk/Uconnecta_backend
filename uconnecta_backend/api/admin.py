from django.contrib import admin
from .models import (
    User,
    Profile,
    Chat,
    ChatParticipant,
    BlockedUser,
    Message,
    Rate,
    PasswordReset,
    Car,
    Call
)


admin.site.register(User)
admin.site.register(Profile)
admin.site.register(Chat)
admin.site.register(ChatParticipant)
admin.site.register(BlockedUser)
admin.site.register(Message)
admin.site.register(Rate)
admin.site.register(PasswordReset)
admin.site.register(Call)
admin.site.register(Car)
