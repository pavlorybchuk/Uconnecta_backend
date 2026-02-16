# uconnecta_backend/asgi.py
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "uconnecta_backend.settings")

django_asgi_app = get_asgi_application()  # <-- ОЦЕ МАЄ БУТИ ПЕРШИМ (до routing)

from channels.routing import ProtocolTypeRouter, URLRouter
from api.routing import websocket_urlpatterns
from api.jwt_ws_middleware import JwtAuthMiddleware

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
