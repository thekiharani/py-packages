from __future__ import annotations

from .channels.sms.gateways.base import AsyncSmsGateway, SmsGateway
from .channels.sms.service import AsyncSmsService, SmsService
from .channels.whatsapp.gateways.base import AsyncWhatsAppGateway, WhatsAppGateway
from .channels.whatsapp.service import AsyncWhatsAppService, WhatsAppService


class MessagingClient:
    def __init__(
        self,
        *,
        sms: SmsGateway | None = None,
        whatsapp: WhatsAppGateway | None = None,
    ) -> None:
        self.sms = SmsService(sms)
        self.whatsapp = WhatsAppService(whatsapp)

    def close(self) -> None:
        self.sms.close()
        self.whatsapp.close()

    def __enter__(self) -> MessagingClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class AsyncMessagingClient:
    def __init__(
        self,
        *,
        sms: AsyncSmsGateway | None = None,
        whatsapp: AsyncWhatsAppGateway | None = None,
    ) -> None:
        self.sms = AsyncSmsService(sms)
        self.whatsapp = AsyncWhatsAppService(whatsapp)

    async def aclose(self) -> None:
        await self.sms.aclose()
        await self.whatsapp.aclose()

    async def __aenter__(self) -> AsyncMessagingClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()
