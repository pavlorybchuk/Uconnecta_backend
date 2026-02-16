from django.urls import path
from .consumers import CallSignalingConsumer, ChatConsumer, PingConsumer, UserConsumer

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
    path("ws/user/", UserConsumer.as_asgi()),
    path("ws/calls/<uuid:call_id>/", CallSignalingConsumer.as_asgi()),
    path("ws/chats/<uuid:chat_id>/", ChatConsumer.as_asgi()),
]
