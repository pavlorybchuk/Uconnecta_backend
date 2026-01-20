from django.contrib import admin
import models
# Register your models here.

admin.site.register(models.User)
admin.site.register(models.Profile)
admin.site.register(models.Chat)
admin.site.register(models.ChatParticipant)
admin.site.register(models.BlockedUser)
admin.site.register(models.Message)
admin.site.register(models.Rate)
admin.site.register(models.PasswordReset)