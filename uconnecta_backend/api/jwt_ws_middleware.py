from django.contrib.auth.models import AnonymousUser
from api.ws_auth import get_user_for_ws


class JwtAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope["user"] = await get_user_for_ws(scope) or AnonymousUser()
        return await self.inner(scope, receive, send)
