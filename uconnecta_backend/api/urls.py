from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    UserViewSet, ProfileViewSet, ChatViewSet,
    ChatParticipantViewSet, MessageViewSet,
    RateViewSet, BlockedUserViewSet, PasswordResetViewSet, search_user
)
from django.conf import settings
from django.conf.urls.static import static

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'profiles', ProfileViewSet)
router.register(r'chats', ChatViewSet)
router.register(r'participants', ChatParticipantViewSet)
router.register(r'messages', MessageViewSet)
router.register(r'rates', RateViewSet)
router.register(r'blocked', BlockedUserViewSet)
router.register(r'password-resets', PasswordResetViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('users/search/', search_user, name='search_user'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)