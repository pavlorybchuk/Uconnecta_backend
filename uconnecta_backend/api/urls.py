from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AcceptCallView, AddCarView, BlockUserView, CreateCallView, DeleteCarView, DeleteMessageView, EndCallView, IceServersView, RegisterView, RejectCallView, SearchUserView,
    MeView, MeSettingsView,
    ChatsListView, CreateDirectChatView,
    DeleteChatForMeView, DeleteChatForAllView,
    ChatMessagesView, CallsHistoryView, BlockedUsersListView, UnblockUserView, SendEmailView, LogoutView
)

urlpatterns = [
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/logout/", LogoutView.as_view(), name="token_logout"),
    path("users/search/", SearchUserView.as_view(), name="user_search"),
    path("me/", MeView.as_view(), name="me"),
    path("chats/", ChatsListView.as_view(), name="chats_list"),
    path("chats/direct/", CreateDirectChatView.as_view(), name="create_direct_chat"),
    path("chats/<uuid:chat_id>/delete-for-me/", DeleteChatForMeView.as_view(), name="delete_for_me"),
    path("chats/<uuid:chat_id>/delete-for-all/", DeleteChatForAllView.as_view(), name="delete_for_all"),
    path("chats/<uuid:chat_id>/messages/", ChatMessagesView.as_view(), name="chat_messages"),
    path("messages/delete/<int:message_id>/", DeleteMessageView.as_view(), name="delete_message"),
    path("calls/history/", CallsHistoryView.as_view(), name="calls_history"),
    path("blocked/", BlockedUsersListView.as_view(), name="calls_history"),
    path("add/car/", AddCarView.as_view(), name="add_car"),
    path("delete/car/<str:car_number>/", DeleteCarView.as_view(), name="delete_car"),
    path("blocked/<uuid:user_id>/", UnblockUserView.as_view(), name="unblock_user"),
    path("block/", BlockUserView.as_view(), name="block_user"),
    path("calls/create/", CreateCallView.as_view()),
    path("calls/<uuid:call_id>/accept/", AcceptCallView.as_view()),
    path("calls/<uuid:call_id>/reject/", RejectCallView.as_view()),
    path("calls/<uuid:call_id>/end/", EndCallView.as_view()),
    path("webrtc/ice-servers/", IceServersView.as_view()),
    path("email/send/", SendEmailView.as_view(), name="email-send"),
]
