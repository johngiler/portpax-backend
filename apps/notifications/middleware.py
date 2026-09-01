from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.accounts.services.frontend_access import user_may_use_frontend


@database_sync_to_async
def _user_from_token(token: str | None):
    if not token:
        return AnonymousUser()
    auth = JWTAuthentication()
    try:
        validated = auth.get_validated_token(token)
        user = auth.get_user(validated)
    except (InvalidToken, TokenError):
        return AnonymousUser()
    if not user_may_use_frontend(user):
        return AnonymousUser()
    return user


class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            raw = scope.get("query_string", b"")
            query = parse_qs(raw.decode())
            token = query.get("token", [None])[0]
            scope["user"] = await _user_from_token(token)
        return await super().__call__(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(inner)
