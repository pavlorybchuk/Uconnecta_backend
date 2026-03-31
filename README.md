# UconnectA — Backend

Django + Channels + Celery backend для системи анонімної комунікації між водіями.

---

## Стек технологій

| Компонент | Технологія |
|---|---|
| Web-фреймворк | Django 4+ |
| ASGI-сервер | Daphne |
| REST API | Django REST Framework |
| Автентифікація | JWT (SimpleJWT) |
| WebSocket | Django Channels + Redis |
| Черги завдань | Celery + Redis |
| База даних | PostgreSQL |
| Push-сповіщення | Firebase Cloud Messaging (FCM) |
| Статичні файли | WhiteNoise |

---

## Структура проєкту

```
backend/
├── api/                        # Основний застосунок
│   ├── models.py               # Моделі БД
│   ├── views.py                # REST API ендпоінти
│   ├── serializers.py          # DRF серіалізатори
│   ├── consumers.py            # WebSocket consumers
│   ├── urls.py                 # URL маршрути
│   ├── routing.py              # WebSocket маршрути
│   ├── tasks.py                # Celery завдання
│   ├── fcm.py                  # Firebase push-сповіщення
│   ├── permissions.py          # Кастомні права доступу
│   ├── signals.py              # Django signals
│   ├── jwt_ws_middleware.py    # JWT middleware для WS
│   ├── ws_auth.py              # Автентифікація WebSocket
│   ├── admin.py                # Адмін-панель
│   └── migrations/             # Міграції БД
└── uconnecta_backend/
    ├── settings.py             # Налаштування
    ├── urls.py                 # Кореневі URL
    ├── asgi.py                 # ASGI-конфіг (HTTP + WS)
    ├── wsgi.py                 # WSGI-конфіг
    └── celery.py               # Celery-конфіг
```

---

## Вимоги

- Python 3.12+
- PostgreSQL 14+
- Redis 7+
- Firebase проєкт (для push-сповіщень)

---

## Встановлення та запуск

### 1. Клонування та середовище

```bash
git clone <repo-url>
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Змінні середовища

Створіть файл `.env` у корені папки `backend/`:

```env
# Django
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost, 127.0.0.1

# Database
DB_NAME=uconnecta_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# JWT
ACCESS_TOKEN_LIFETIME_DAYS=7
REFRESH_TOKEN_LIFETIME_DAYS=30

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your@email.com
EMAIL_HOST_PASSWORD=your_password
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=your@email.com

# Firebase (вставте весь JSON одним рядком)
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}

# Timezone
TIME_ZONE=Europe/Kyiv
CELERY_TIMEZONE=Europe/Kyiv
```

### 3. База даних та міграції

```bash
python manage.py migrate
python manage.py create_admin   # Створення адміна (кастомна команда)
```

### 4. Запуск

Потрібно запустити три процеси одночасно (наприклад, у трьох терміналах):

```bash
# Термінал 1 — ASGI-сервер (HTTP + WebSocket)
daphne uconnecta_backend.asgi:application

# Термінал 2 — Celery worker
celery -A uconnecta_backend worker --loglevel=info

# Термінал 3 — Celery beat (планувальник)
celery -A uconnecta_backend beat --loglevel=info
```

> **Примітка:** Без Celery beat не буде працювати автовидалення чатів (запускається кожні 2 хвилини).

---

## API Ендпоінти

### Автентифікація

| Метод | URL | Опис |
|---|---|---|
| `POST` | `/api/auth/register/` | Реєстрація нового користувача |
| `POST` | `/api/auth/login/` | Вхід (повертає access + refresh токени) |
| `POST` | `/api/auth/refresh/` | Оновлення access токена |
| `POST` | `/api/auth/logout/` | Вихід (blacklist refresh токена) |

### Профіль

| Метод | URL | Опис |
|---|---|---|
| `GET / PATCH` | `/api/me/` | Перегляд та редагування власного профілю |
| `POST` | `/api/me/fcm/` | Збереження FCM-токена для push |

### Пошук та авто

| Метод | URL | Опис |
|---|---|---|
| `GET` | `/api/users/search/?q=...` | Пошук водія за username або номером авто |
| `POST` | `/api/add/car/` | Додати номер авто до профілю |
| `DELETE` | `/api/delete/car/<car_number>/` | Видалити номер авто |

### Чати

| Метод | URL | Опис |
|---|---|---|
| `GET` | `/api/chats/` | Список чатів поточного користувача |
| `POST` | `/api/chats/direct/` | Створити або відкрити прямий чат |
| `GET` | `/api/chats/<chat_id>/messages/` | Повідомлення в чаті (з пагінацією) |
| `DELETE` | `/api/chats/<chat_id>/delete-for-me/` | Видалити чат для себе |
| `DELETE` | `/api/chats/<chat_id>/delete-for-all/` | Видалити чат для обох |
| `POST` | `/api/chats/<chat_id>/toggle-auto-delete/` | Перемикач автовидалення чату |
| `PATCH` | `/api/chats/<chat_id>/messages/<msg_id>/` | Редагувати повідомлення |
| `DELETE` | `/api/chats/<chat_id>/messages/<msg_id>/delete_for_me/` | Видалити повідомлення для себе |
| `DELETE` | `/api/chats/<chat_id>/messages/<msg_id>/delete_for_all/` | Видалити повідомлення для всіх |

### Дзвінки (WebRTC)

| Метод | URL | Опис |
|---|---|---|
| `POST` | `/api/calls/create/` | Ініціювати дзвінок |
| `POST` | `/api/calls/<call_id>/accept/` | Прийняти дзвінок |
| `POST` | `/api/calls/<call_id>/reject/` | Відхилити дзвінок |
| `POST` | `/api/calls/<call_id>/end/` | Завершити дзвінок |
| `GET` | `/api/calls/history/` | Історія дзвінків |
| `GET` | `/api/webrtc/ice-servers/` | TURN/STUN конфігурація |

### Блокування

| Метод | URL | Опис |
|---|---|---|
| `POST` | `/api/block/` | Заблокувати користувача |
| `GET` | `/api/blocked/` | Список заблокованих |
| `DELETE` | `/api/blocked/<user_id>/` | Розблокувати |

### Інше

| Метод | URL | Опис |
|---|---|---|
| `POST` | `/api/email/send/` | Надіслати email (наприклад, скидання пароля) |

---

## WebSocket з'єднання

Всі WebSocket-з'єднання захищені JWT-токеном, який передається як query-параметр:

```
ws://<host>/ws/user/?token=<access_token>
ws://<host>/ws/chat/<chat_id>/?token=<access_token>
ws://<host>/ws/calls/<call_id>/?token=<access_token>
```

### Типи подій у `ChatConsumer`

| Подія | Напрямок | Опис |
|---|---|---|
| `message.created` | сервер → клієнт | Нове повідомлення |
| `message.edited` | сервер → клієнт | Редаговане повідомлення |
| `message.deleted` | сервер → клієнт | Видалене повідомлення |

### Типи подій у `CallSignalingConsumer`

| Подія | Опис |
|---|---|
| `offer` | WebRTC offer |
| `answer` | WebRTC answer |
| `ice` | ICE candidate |
| `hangup` | Завершення дзвінка |

---

## Celery завдання

| Завдання | Розклад | Опис |
|---|---|---|
| `auto_delete_chats_for_users` | Кожні 2 хвилини | Видаляє чати, де увімкнено автовидалення і чат існує більше 24 годин |
| `send_push_task` | За потреби (async) | Надсилає FCM push-сповіщення |

---

## Моделі бази даних

```
User          — кастомна модель (email, phone, username)
Profile       — ПІБ, фото, налаштування (JSONField)
Car           — номер авто (формат ХХ0000ХХ), прив'язаний до User
Chat          — чат між двома водіями (тільки direct)
ChatParticipant — учасник чату (з флагами auto_delete, deleted_at)
Message       — повідомлення (текст або зображення)
DeletedMessage — помітка "видалено для мене"
Call          — запис дзвінка (статуси: initiated, accepted, declined, ended)
Rate          — оцінка водія (0.0–5.0)
BlockedUser   — пари заблокованих користувачів
PasswordReset — токен скидання пароля
```

---

## Адмін-панель

Доступна за адресою `/admin/`. Для створення суперкористувача:

```bash
python manage.py create_admin
```

або стандартно:

```bash
python manage.py createsuperuser
```

---

## Продакшн-деплой

1. Встановіть `DEBUG=False` (вже встановлено в settings.py)
2. Налаштуйте `ALLOWED_HOSTS` у `.env`
3. Зберіть статику: `python manage.py collectstatic`
4. Запускайте через `daphne` за nginx-проксі
5. Використовуйте `supervisor` або `systemd` для керування процесами Daphne, Celery worker та Celery beat
6. Redis та PostgreSQL мають бути доступні до старту застосунку
