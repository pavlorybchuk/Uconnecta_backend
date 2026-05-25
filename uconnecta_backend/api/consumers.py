"""
Django Channels WebSocket Consumers for UConecta Backend.

WebSocket consumers handle real-time communication between clients and server
using Django Channels. Supports:

1. PingConsumer: Simple health-check WebSocket endpoint
2. UserConsumer: Per-user notification channel for real-time updates
3. CallSignalingConsumer: WebRTC signaling for peer-to-peer calls
4. ChatConsumer: Real-time chat messaging within specific chats

WebSocket connections automatically handle:
- Authentication via JWT tokens in query string
- Permission checks (chat participation, call involvement)
- Blocking relationships
- Group broadcast to multiple connected clients
"""

import json
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .ws_auth import get_user_for_ws
from .models import Call, BlockedUser, ChatParticipant, Message, Chat


class PingConsumer(AsyncWebsocketConsumer):
    """
    Simple WebSocket endpoint for health checks and testing.
    
    Endpoint: ws://host/ws/ping/
    
    On connection:
        - Accepts the connection
        - Sends a welcome message
    
    On disconnect:
        - Cleans up group membership if exists
    
    This is a read-only consumer - clients can connect to verify server is running.
    """

    async def connect(self):
        """Accept the WebSocket connection and send welcome message."""
        await self.accept()
        await self.send(text_data=json.dumps({"type": "welcome"}))

    async def disconnect(self, close_code):
        """Clean up group membership on disconnect."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)


@database_sync_to_async
def is_blocked(a, b):
    """
    Async wrapper to check if users are blocked relative to each other.
    
    Args:
        a (User): First user
        b (User): Second user
        
    Returns:
        bool: True if any blocking relationship exists
    """

    return (
        BlockedUser.objects.filter(blocker=a, blocked=b).exists()
        or BlockedUser.objects.filter(blocker=b, blocked=a).exists()
    )


@database_sync_to_async
def get_call(call_id):
    """
    Async wrapper to fetch a call with related users.
    
    Args:
        call_id (UUID): ID of call to fetch
        
    Returns:
        Call: Call instance with caller and receiver, or None if not found
    """
    
    return Call.objects.select_related("caller", "receiver").filter(id=call_id).first()


class UserConsumer(AsyncWebsocketConsumer):
    """
    Per-user WebSocket channel for receiving notifications.
    
    Endpoint: ws://host/ws/user/<user_id>/
    
    Purpose:
        - Notify user of new messages from chats they've soft-deleted
        - Notify of other real-time events (calls, status updates)
        - Provides a reliable way to reach the user regardless of which chat view they're in
    
    Authentication:
        - Requires valid JWT token in query string
        - Rejects connection if user not authenticated (close code 4401)
    
    Connection flow:
        1. Extract user from JWT in scope
        2. Check authentication
        3. Join group named 'user_{user_id}'
        4. Accept connection
    
    Incoming messages:
        - This consumer is receive-only (no incoming messages expected)
    
    Outgoing messages:
        - Server sends notifications via group_send to 'user_{user_id}'
        - Example: {"type": "notify", "payload": {...}}
    """

    async def connect(self):
        """Authenticate and join user's notification group."""
        self.user = await get_user_for_ws(self.scope)

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """Leave user's notification group."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        """
        Send notification to user.
        
        Called by group_send with event containing:
            - type: 'notify' (routing key)
            - payload: actual data to send to client
        
        Args:
            event (dict): {"type": "notify", "payload": {...}}
        """

        await self.send(text_data=json.dumps(event["payload"]))


class CallSignalingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket channel for WebRTC call signaling.
    
    Endpoint: ws://host/ws/call/<call_id>/
    
    Purpose:
        - Exchange WebRTC offer/answer and ICE candidates between peers
        - Coordinate call state changes (ready, hangup)
        - Relay signaling messages between caller and receiver
    
    Authentication:
        - Requires valid JWT token
        - User must be either caller or receiver of the call
        - Both users must not be blocking each other
        - Rejects with code 4401 (unauthorized), 4404 (not found), or 4403 (forbidden)
    
    Message types (received from client):
        - 'offer': WebRTC SessionDescription (from initiator)
        - 'answer': WebRTC SessionDescription (from receiver)
        - 'ice': ICE candidate for NAT traversal
        - 'hangup': User ending the call
        - 'ready': User ready to receive media
    
    Message routing:
        1. Client sends message via WebSocket
        2. Consumer validates message type
        3. Adds sender_id to prevent echo
        4. Broadcasts to call group (all participants)
        5. CallSignalingConsumer.relay() filters out sender's own message
    
    Connection security:
        - Validates user is a participant of the call
        - Checks for mutual blocking
        - Only allows expected message types
    """

    async def connect(self):
        """Authenticate and join user's notification group."""
        self.call_id = self.scope["url_route"]["kwargs"]["call_id"]
        self.user = await get_user_for_ws(self.scope)

        # Verify authentication
        if isinstance(self.user, AnonymousUser) or not self.user.is_authenticated:
            """Leave user's notification group."""
            await self.close(code=4401)
            return

        # Verify call exists
        call = await get_call(self.call_id)
        if not call:
            await self.close(code=4404)
            return

        # Verify user is participant of call
        if self.user not in (call.caller, call.receiver):
            await self.close(code=4403)
            return

        # Verify users aren't blocked
        other = call.receiver if self.user == call.caller else call.caller
        if await is_blocked(self.user, other):
            await self.close(code=4403)
            return

        # Join call signaling group
        self.group_name = f"call_{self.call_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected"}))

    async def disconnect(self, close_code):
        """Leave call signaling group."""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Receive and validate signaling message from client.
        
        Validates message format and type, then broadcasts to call group.
        Adds sender_id to prevent client from receiving echo of own message.
        
        Args:
            text_data (str): JSON message from client
        """
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "detail": "Invalid JSON"})
            )
            return

        # Only allow specific message types
        if payload.get("type") not in ("offer", "answer", "ice", "hangup", "ready"):
            await self.send(
                text_data=json.dumps({"type": "error", "detail": "Invalid type"})
            )
            return
        
        # Add sender identification
        payload["sender_id"] = str(self.user.id)

        # Broadcast to all users in this call
        await self.channel_layer.group_send(
            self.group_name, {"type": "relay", "payload": payload}
        )

    async def relay(self, event):
        """
        Relay signaling message to peers (but not sender).
        
        Prevents echoing the sender's own message back to them.
        This is called via group_send after receive() broadcasts the message.
        
        Args:
            event (dict): {"type": "relay", "payload": {...}}
        """
        # Don't send message back to the sender
        if event["payload"].get("sender_id") == str(self.user.id):
            return
        await self.send(text_data=json.dumps(event["payload"]))


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket channel for real-time chat messaging.
    
    Endpoint: ws://host/ws/chat/<chat_id>/
    
    Purpose:
        - Real-time message broadcasting within a specific chat
        - Live editing notifications
        - Message deletion notifications
    
    Authentication:
        - Requires valid JWT token
        - User must be an active participant of the chat (not deleted)
        - Rejects with code 4401 (unauthorized) or 4403 (forbidden)
    
    Incoming messages:
        - This consumer is receive-only from WebSocket perspective
        - Messages are created via REST API (POST /api/chats/{id}/messages/)
        - Messages are then broadcast to chat group via server group_send
    
    Outgoing message types (from server):
        - 'message.created': New message in chat
        - 'message.edited': Existing message was edited
        - 'message.deleted': Message was deleted for all users
        - 'chat.restored': Chat was restored from soft-delete
    
    Connection flow:
        1. Extract chat_id from URL
        2. Authenticate user via JWT
        3. Verify user is active participant of chat
        4. Join group 'chat_{chat_id}'
        5. Accept connection
    
    How messages reach clients:
        1. Client A posts message via REST API
        2. CreateMessageView validates and saves message
        3. CreateMessageView calls group_send to broadcast
        4. All connected ChatConsumers receive message
        5. ChatConsumer.chat_message() sends to client
    """
    
    async def connect(self):
        """Authenticate and join chat group if user is a participant."""
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.user = await get_user_for_ws(self.scope)

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Verify user is an active participant
        allowed = await self.is_participant(self.chat_id, self.user)
        if not allowed:
            await self.close(code=4403)
            return

        # Join chat group
        self.group_name = f"chat_{self.chat_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        """Leave chat group on disconnect."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def chat_message(self, event):
        """
        Send new message to client.
        
        Called via group_send when a new message is posted.
        Wraps the message data with type information.
        
        Args:
            event (dict): {"type": "chat_message", "message": {...}}
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message.created",
                    "payload": event["message"],
                }
            )
        )

    async def chat_event(self, event):
        """
        Send generic chat event to client.
        
        Forwards payload as-is (payload should contain "type" field).
        
        Args:
            event (dict): {"type": "chat_event", "payload": {...}}
        """
        await self.send(text_data=json.dumps(event["payload"]))

    async def chat_message_edited(self, event):
        """
        Notify client that a message was edited.
        
        Called via group_send when MessageEditView updates a message.
        
        Args:
            event (dict): {"type": "chat_message_edited", "message": {...}}
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message.edited",
                    "payload": event["message"],
                }
            )
        )

    async def chat_message_deleted(self, event):
        """
        Notify client that a message was deleted.
        
        Called via group_send when DeleteMessageView soft-deletes for user.
        
        Args:
            event (dict): {"type": "chat_message_deleted", "message_id": "..."}
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message.deleted",
                    "payload": {"id": event["message_id"]},
                }
            )
        )

    @database_sync_to_async
    def is_participant(self, chat_id, user):
        """
        Check if user is an active (not deleted) participant of chat.
        
        Args:
            chat_id (UUID): Chat to check
            user (User): User to verify
            
        Returns:
            bool: True if user is active participant
        """
        return ChatParticipant.objects.filter(
            chat_id=chat_id, user=user, deleted_at__isnull=True
        ).exists()

    @database_sync_to_async
    def create_message(self, chat_id, user, body):
        """
        Create a new message in the chat.
        
        Also updates chat's last_message_at timestamp.
        
        Args:
            chat_id (UUID): Chat to create message in
            user (User): Message sender
            body (str): Message text
            
        Returns:
            Message: The created message instance
        """
        msg = Message.objects.create(chat_id=chat_id, sender=user, body=body)
        Chat.objects.filter(id=chat_id).update(last_message_at=timezone.now())
        return msg