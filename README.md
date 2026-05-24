# UconnectA — Backend

A Django-based REST + WebSocket backend for the **UconnectA** mobile platform — a real-time communication app featuring direct messaging, WebRTC voice/video calls, user profiles with car registration, a rating system, and Firebase push notifications.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Project Structure](#project-structure)
3. [Data Models](#data-models)
4. [REST API Reference](#rest-api-reference)
5. [WebSocket API](#websocket-api)
6. [Background Tasks (Celery)](#background-tasks-celery)
7. [Push Notifications (FCM)](#push-notifications-fcm)
8. [Photo Recognition](#photo-recognition)
9. [Authentication](#authentication)
10. [Configuration & Environment Variables](#configuration--environment-variables)
11. [Local Development Setup](#local-development-setup)
12. [Running in Production](#running-in-production)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Django 6.0.1 |
| REST API | Django REST Framework 3.16.1 |
| Async / WebSockets | Django Channels 4.3.2 + Daphne 4.2.1 |
| Channel layer | channels-redis 4.3.0 + Redis 7 |
| Database | PostgreSQL (psycopg2-binary) |
| Auth | JWT via `djangorestframework-simplejwt` 5.5.1 |
| Task queue | Celery 5.6.2 + Redis broker |
| Push notifications | Firebase Admin SDK 7.1.0 (FCM) |
| Static files | WhiteNoise 6.11.0 |
| Image handling | Pillow 12.1.0 |

---

## Project Structure

```
backend/
└── uconnecta_backend/          # Django project root
    ├── manage.py
    ├── requirements.txt
    ├── media/                  # User-uploaded files
    │   ├── profile_photos/
    │   └── chat_images/
    ├── api/                    # Main application
    │   ├── models.py           # All data models
    │   ├── views.py            # REST API views
    │   ├── serializers.py      # DRF serializers
    │   ├── urls.py             # API URL routing
    │   ├── consumers.py        # WebSocket consumers
    │   ├── routing.py          # WebSocket URL routing
    │   ├── tasks.py            # Celery async tasks
    │   ├── fcm.py              # Firebase push notification helpers
    │   ├── recognize_view.py   # Photo recognition proxy view
    │   ├── permissions.py      # Custom DRF permission classes
    │   ├── signals.py          # Django signals
    │   ├── ws_auth.py          # WebSocket JWT authentication
    │   ├── jwt_ws_middleware.py # JWT middleware for WS connections
    │   ├── admin.py            # Django admin registrations
    │   └── migrations/         # Database migrations
    └── uconnecta_backend/      # Django settings package
        ├── settings.py
        ├── urls.py             # Root URL configuration
        ├── asgi.py             # ASGI entry point (Daphne)
        ├── wsgi.py             # WSGI entry point
        └── celery.py           # Celery application
```

---

## Data Models

### User
Custom user model (`AbstractBaseUser`) identified by email. UUID primary key.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK, auto-generated |
| `email` | EmailField | unique, used as `USERNAME_FIELD` |
| `phone` | CharField(16) | unique |
| `username` | CharField(8) | unique |
| `country_code` | CharField(2) | default `UA` |
| `fcm_token` | CharField(255) | Firebase Cloud Messaging device token |
| `is_staff` | BooleanField | admin access |
| `created_at` | DateTimeField | |

### Profile
One-to-one extension of `User`. Contains display information and per-user settings.

| Field | Type | Notes |
|---|---|---|
| `user` | OneToOne(User) | PK |
| `name` / `surname` / `patronymic` | CharField(50) | |
| `how_to_address` | CharField(30) | preferred form of address |
| `photo` | ImageField | stored under `media/profile_photos/` with UUID filenames |
| `about` | TextField | bio |
| `settings` | JSONField | default: `{"auto_delete_chats": false, "show_nickname": true, "allow_calls": true}` |

### Car
Associates a vehicle registration plate with a user.

| Field | Notes |
|---|---|
| `car_number` (PK) | up to 8 characters |
| `user` | FK → User |

### Chat & ChatParticipant
Supports direct (1-to-1) chats. Each chat has a `direct_key` (unique composite key of the two user IDs) to prevent duplicate direct chats.

`ChatParticipant` stores per-user membership state:
- `deleted_at` — soft-delete timestamp (chat hidden for this user)
- `auto_delete` — whether the chat auto-deletes after 24 h
- `auto_delete_enabled_at` — when auto-delete was turned on

### Message
Belongs to a `Chat`. Can carry text body, an image, or both.

- Supports per-user soft deletion via the `DeletedMessage` join table.
- Indexed on `(chat, -created_at)` for efficient paginated retrieval.
- Images stored under `media/chat_images/` with UUID filenames.

### Rate
User-to-user rating, value between **0.0 – 5.0** (enforced at both validation and DB constraint levels).

### BlockedUser
Bidirectional block table. A block from A → B or B → A prevents messaging and calls in either direction.

### Call
Tracks voice/video call sessions used for WebRTC signalling.

| Status | Meaning |
|---|---|
| `initiated` | caller sent invite |
| `accepted` | receiver answered |
| `declined` | receiver rejected |
| `ended` | either party ended the call |

Each call has a UUID `call_token` used as the shared WebRTC room identifier.

### PasswordReset
One-time token records for password-reset flows, with expiry and `used` flag.

---

## REST API Reference

All endpoints are prefixed with `/api/` (configured in the root `urls.py`). Every endpoint except registration and login requires a valid `Authorization: Bearer <access_token>` header.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Create a new account |
| POST | `/api/auth/login/` | Obtain access + refresh JWT pair |
| POST | `/api/auth/refresh/` | Rotate the refresh token and get a new access token |
| POST | `/api/auth/logout/` | Blacklist the current refresh token |

### Current User

| Method | Endpoint | Description |
|---|---|---|
| GET / PATCH | `/api/me/` | Retrieve or update the authenticated user's profile |
| POST | `/api/me/fcm/` | Save or update the device FCM token |

### User Search

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/users/search/?q=<query>` | Search users by username, name, or phone |

### Chats

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/chats/` | List all chats for the current user |
| POST | `/api/chats/direct/` | Get or create a direct chat with another user |
| DELETE | `/api/chats/<chat_id>/delete-for-me/` | Soft-delete the chat for the current user only |
| DELETE | `/api/chats/<chat_id>/delete-for-all/` | Delete the chat for all participants |
| POST | `/api/chats/<chat_id>/toggle-auto-delete/` | Enable / disable 24-hour auto-delete for this chat |

### Messages

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/chats/<chat_id>/messages/` | Paginated message history |
| DELETE | `/api/chats/<chat_id>/messages/<msg_id>/delete_for_me/` | Hide message for current user |
| DELETE | `/api/chats/<chat_id>/messages/<msg_id>/delete_for_all/` | Delete message for everyone |
| PATCH | `/api/chats/<chat_id>/messages/<msg_id>/` | Edit message body |

### Calls

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/calls/create/` | Initiate a new call |
| POST | `/api/calls/<call_id>/accept/` | Accept an incoming call |
| POST | `/api/calls/<call_id>/reject/` | Decline an incoming call |
| POST | `/api/calls/<call_id>/end/` | End an active call |
| POST | `/api/calls/<call_id>/missed/` | Mark a call as missed |
| GET | `/api/calls/history/` | Retrieve the call history |
| GET | `/api/webrtc/ice-servers/` | Get STUN/TURN server list for WebRTC |

### Block / Unblock

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/blocked/` | List blocked users |
| POST | `/api/block/` | Block a user |
| DELETE | `/api/blocked/<user_id>/` | Unblock a user |

### Cars

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/add/car/` | Register a car number to the current user |
| DELETE | `/api/delete/car/<car_number>/` | Remove a car from the current user |

### Miscellaneous

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/email/send/` | Send a transactional email |
| POST | `/api/recognize-photo/` | Proxy a ZIP-packaged image to the external photo recognition service |

---

## WebSocket API

The server uses Django Channels with Redis as the channel layer. All WebSocket connections authenticate via a JWT token passed as a query parameter (`?token=<access_token>`).

WebSocket base path: `ws://<host>/ws/`

### `/ws/ping/`
A simple health-check socket. On connect it immediately sends `{"type": "welcome"}`.

### `/ws/user/`
**Per-user notification stream.** Each authenticated user connects to their own private channel group (`user_<uuid>`). The server pushes JSON payloads for the following events:

| Event type | Triggered when |
|---|---|
| `message.created` | A new message arrives in any of the user's chats |
| `chat.restored` | A previously soft-deleted chat is restored |
| `call.incoming` | Another user initiates a call |
| `call.accepted` / `call.declined` / `call.ended` | Call status changes |

### `/ws/chat/<chat_id>/`
**Per-chat real-time messaging.** Only active participants (not soft-deleted) may connect. Pushes:

| Event type | Payload |
|---|---|
| `message.created` | Full serialized message object |
| `message.edited` | Updated message object |
| `message.deleted` | `{"id": <msg_id>}` |

### `/ws/calls/<call_id>/`
**WebRTC signalling channel.** Both the caller and receiver connect here. The consumer relays the following message types between peers without echoing back to the sender:

- `offer` — SDP offer from caller
- `answer` — SDP answer from receiver
- `ice` — ICE candidate
- `ready` — peer-ready signal
- `hangup` — end the call

Access is restricted to the two participants of the call, and blocked pairs cannot connect.

---

## Background Tasks (Celery)

Celery uses Redis as both the broker and result backend. The beat schedule is embedded in `settings.py`.

### `api.tasks.send_push_task`
Sends a Firebase Cloud Messaging push notification to a single device token. Called asynchronously (`.delay()`) whenever a notification needs to be dispatched.

**Arguments:** `token`, `title`, `body`, `data` (dict)

### `api.tasks.auto_delete_chats_for_users`
**Schedule:** every 2 minutes (via Celery Beat).

Soft-deletes `ChatParticipant` records where `auto_delete=True` and the chat was created more than **24 hours** ago. This implements the "disappearing messages" feature at the chat level.

---

## Push Notifications (FCM)

Firebase credentials are loaded at runtime from the `FIREBASE_SERVICE_ACCOUNT_JSON` environment variable (a JSON string of the service account key file). The `fcm.py` module is lazy-initialised — it only calls `firebase_admin.initialize_app()` once.

Push notifications are sent via `firebase_admin.messaging` with Android high-priority delivery. All string values in the `data` payload are coerced to `str` to comply with FCM requirements.

---

## Photo Recognition

`POST /api/recognize-photo/` accepts a multipart upload of a `.zip` archive containing a single image (JPG, PNG, WEBP, BMP, or GIF). The view:

1. Validates that the file is a valid ZIP.
2. Extracts the first supported image inside (ignoring `__MACOSX` entries).
3. Forwards the image to the external recognition service configured via `RECOGNITION_BASE_URL`, authenticated with `RECOGNITION_API_KEY` (`X-Api-Key` header).
4. Returns the JSON response from the upstream service, or a structured error on timeout / connection failure.

---

## Authentication

The project uses **JWT authentication** via `djangorestframework-simplejwt`:

- **Access token lifetime:** configurable via `ACCESS_TOKEN_LIFETIME_DAYS` (default: 7 days)
- **Refresh token lifetime:** configurable via `REFRESH_TOKEN_LIFETIME_DAYS` (default: 30 days)
- **Token rotation:** enabled — each refresh call issues a new refresh token
- **Blacklisting:** enabled — old refresh tokens are blacklisted on rotation and logout

WebSocket connections authenticate by passing the access token as a query string parameter, handled by the custom `jwt_ws_middleware.py` / `ws_auth.py` layer.

---

## Configuration & Environment Variables

Create a `.env` file in the project root (`uconnecta_backend/`) with the following variables:

```env
# Django
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost, 127.0.0.1
TIME_ZONE=Europe/Kyiv

# Database (PostgreSQL)
DB_NAME=uconnecta
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# Celery (defaults to REDIS_URL if not set)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TIMEZONE=Europe/Kyiv

# JWT token lifetimes (in days)
ACCESS_TOKEN_LIFETIME_DAYS=7
REFRESH_TOKEN_LIFETIME_DAYS=30

# Email
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@example.com
EMAIL_HOST_PASSWORD=yourpassword
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=noreply@example.com

# Firebase (paste full JSON content as a single-line string)
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}

# Photo recognition service
RECOGNITION_BASE_URL=https://your-recognition-api.example.com/recognize
RECOGNITION_API_KEY=your-api-key
```

---

## Local Development Setup

**Prerequisites:** Python 3.12+, PostgreSQL, Redis.

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd backend/uconnecta_backend

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file (see section above)
cp .env.example .env
# Edit .env with your local values

# 5. Apply database migrations
python manage.py migrate

# 6. Create a superuser (admin access)
python manage.py create_admin

# 7. Start the Django development server (HTTP + WebSocket via Daphne)
python manage.py runserver

# 8. In a separate terminal — start the Celery worker
celery -A uconnecta_backend worker -l info

# 9. In another terminal — start Celery Beat (periodic tasks)
celery -A uconnecta_backend beat -l info
```

The API will be available at `http://localhost:8000/api/` and the Django admin at `http://localhost:8000/admin/`.

---

## Running in Production

The project is designed to run behind a reverse proxy (e.g. Nginx) with TLS termination. Key production settings already in place:

- `DEBUG = False`
- `CSRF_COOKIE_SECURE = True`
- `SESSION_COOKIE_SECURE = True`
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `USE_X_FORWARDED_HOST = True`
- Static files served by WhiteNoise

**Start the ASGI server (Daphne):**

```bash
daphne -b 0.0.0.0 -p 8000 uconnecta_backend.asgi:application
```

**Start workers:**

```bash
# Celery worker (can run multiple with -c <concurrency>)
celery -A uconnecta_backend worker -l warning -c 4

# Celery Beat scheduler (run exactly one instance)
celery -A uconnecta_backend beat -l warning --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

**Collect static files:**

```bash
python manage.py collectstatic --noinput
```

Media files (`MEDIA_ROOT`) should be persisted on a volume or object storage and served by Nginx / a CDN at the `/media/` path.