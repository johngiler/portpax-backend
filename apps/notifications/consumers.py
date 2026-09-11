from __future__ import annotations

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.notifications.services.frontend_build import (
    APP_UPDATES_GROUP,
    get_frontend_build_id,
)

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    user_group: str
    updates_group: str

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.user_group = f"notifications_{user.pk}"
        self.updates_group = APP_UPDATES_GROUP
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.updates_group, self.channel_name)

        # Resolve before accept so the first frame can go out immediately.
        build_id = await database_sync_to_async(get_frontend_build_id)()
        await self.accept()

        if build_id:
            await self._send_json_safe(
                {"type": "app_update", "payload": {"build_id": build_id}}
            )

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, "updates_group"):
            await self.channel_layer.group_discard(
                self.updates_group, self.channel_name
            )

    async def notification_message(self, event):
        payload = event.get("payload") or {}
        await self._send_json_safe({"type": "notification", "payload": payload})

    async def app_update_message(self, event):
        payload = event.get("payload") or {}
        await self._send_json_safe({"type": "app_update", "payload": payload})

    async def _send_json_safe(self, data: dict) -> None:
        """Ignore races where the browser already closed (HMR / Strict Mode)."""
        try:
            await self.send(text_data=json.dumps(data))
        except Exception:
            logger.debug("WebSocket send skipped; connection already closed", exc_info=True)
