import os
import json
import firebase_admin
import logging
logger = logging.getLogger(__name__)
from firebase_admin import credentials, messaging


def init_firebase():
    if firebase_admin._apps:
        return True

    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return False

    cred_dict = json.loads(raw)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    return True


def send_push_to_token(*, token: str, title: str, body: str, data: dict | None = None):
    """
    Безпечна відправка: якщо Firebase не ініціалізований — просто повертаємо False.
    """
    if not token:
        return False

    if not init_firebase():
        return False

    data_payload = {k: str(v) for k, v in (data or {}).items()}

    msg = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data_payload,
        token=token,
        android=messaging.AndroidConfig(
            priority="high",
        ),
    )

    response = messaging.send(msg)
    return response
