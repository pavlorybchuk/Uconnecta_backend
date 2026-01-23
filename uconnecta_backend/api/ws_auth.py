from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

User = get_user_model()

@database_sync_to_async
def get_user_for_ws(scope):
    query = scope.get("query_string", b"").decode()
    token = (parse_qs(query).get("token") or [None])[0]
    if not token:
        return AnonymousUser()

    try:
        access = AccessToken(token)
        user_id = access.get("user_id")
        return User.objects.filter(id=user_id).first() or AnonymousUser()
    except TokenError:
        return AnonymousUser()