from urllib.parse import parse_qs
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

User = get_user_model()


class NotificationConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        qs = parse_qs(self.scope["query_string"].decode())
        token = qs.get("token", [None])[0]

        if not token:
            await self.close(code=4001)
            return

        try:
            payload = AccessToken(token)
            self.user = await database_sync_to_async(User.objects.get)(id=payload["user_id"])
        except (TokenError, User.DoesNotExist, KeyError):
            await self.close(code=4001)
            return

        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"[WS] Connected: user_{self.user.id}")

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            print(f"[WS] Disconnected: {self.group_name}")

    async def receive_json(self, content):
        pass

    async def notification_message(self, event):
        await self.send_json(event["data"])