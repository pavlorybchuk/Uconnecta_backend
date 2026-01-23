import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .ws_auth import get_user_for_ws
from .models import Call, BlockedUser

class PingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send(text_data=json.dumps({"type": "welcome"}))
        
    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

@database_sync_to_async
def is_blocked(a, b):
    return (BlockedUser.objects.filter(blocker=a, blocked=b).exists() or
            BlockedUser.objects.filter(blocker=b, blocked=a).exists())

@database_sync_to_async
def get_call(call_id):
    return Call.objects.select_related("caller", "receiver").filter(id=call_id).first()

class CallSignalingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.call_id = self.scope["url_route"]["kwargs"]["call_id"]
        self.user = await get_user_for_ws(self.scope)

        if isinstance(self.user, AnonymousUser) or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        call = await get_call(self.call_id)
        if not call:
            await self.close(code=4404)
            return

        if self.user not in (call.caller, call.receiver):
            await self.close(code=4403)
            return

        other = call.receiver if self.user == call.caller else call.caller
        if await is_blocked(self.user, other):
            await self.close(code=4403)
            return

        self.group_name = f"call_{self.call_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected"}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"type": "error", "detail": "Invalid JSON"}))
            return

        if payload.get("type") not in ("offer", "answer", "ice", "hangup"):
            await self.send(text_data=json.dumps({"type": "error", "detail": "Invalid type"}))
            return

        payload["sender_id"] = str(self.user.id)

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "relay", "payload": payload}
        )

    async def relay(self, event):
        await self.send(text_data=json.dumps(event["payload"]))