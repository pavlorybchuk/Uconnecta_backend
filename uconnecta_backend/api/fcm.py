"""Handles sending push notifications to mobile devices via Firebase."""

import os
import json
import firebase_admin
import logging

logger = logging.getLogger(__name__)
from firebase_admin import credentials, messaging


def init_firebase():
    """
    Initialize Firebase Admin SDK if not already initialized.
    
    Reads Firebase credentials from environment variable:
        FIREBASE_SERVICE_ACCOUNT_JSON='{json_string_of_creds}'
    
    Returns:
        bool: True if successfully initialized or already initialized,
              False if credentials not found or initialization failed
    
    Example environment setup:
        export FIREBASE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
    
    Firebase service account JSON should contain:
    - type
    - project_id
    - private_key_id
    - private_key
    - client_email
    - client_id
    - auth_uri
    - token_uri
    - auth_provider_x509_cert_url
    - client_x509_cert_url
    """
    # Check if already initialized
    if firebase_admin._apps:
        return True

    # Try to load credentials from environment
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return False

    try:
        # Parse JSON and initialize app
        cred_dict = json.loads(raw)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        return False


def send_push_to_token(
    *, token: str, title: str, body: str, data: dict | None = None
):
    """
    Send a push notification to a specific device token.
    
    Safe wrapper that gracefully handles missing/invalid credentials.
    If Firebase is not configured, returns False instead of raising error.
    
    Args:
        token (str): Firebase Cloud Messaging device token
        title (str): Notification title (shown in system notifications)
        body (str): Notification body text
        data (dict): Optional key-value pairs (max 5000 chars per key, max 100 keys)
                    Useful for deep linking, custom data, etc.
    
    Returns:
        str: Firebase message response ID if successful
        bool: False if not initialized, invalid token, or Firebase not configured
    
    Example usage:
        send_push_to_token(
            token=user.fcm_token,
            title="New message",
            body="You got a message from John",
            data={"chat_id": "abc123", "type": "message"}
        )
    
    Android-specific config:
        - priority="high" ensures notification arrives ASAP
        - Works with FCM and GCM
    
    Message flow:
        1. Device registers with Firebase, gets token
        2. Client sends token to backend (stored in User.fcm_token)
        3. Server calls this function to send notification
        4. Firebase delivers to device based on priority and platform
    
    Security:
        - Token should never be exposed in client-side code
        - Tokens can be revoked by users
        - Private key should never be shared (use environment variables)
    """
    if not token:
        return False

    if not init_firebase():
        return False

    # Convert all data values to strings (Firebase requirement)
    data_payload = {k: str(v) for k, v in (data or {}).items()}

    # Build FCM message
    msg = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data_payload,
        token=token,
        # Android-specific options for high priority delivery
        android=messaging.AndroidConfig(
            priority="high",
        ),
    )

    # Send the message
    response = messaging.send(msg)
    return response