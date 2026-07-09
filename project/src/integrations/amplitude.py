"""Amplitude adapter for product analytics and event tracking."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class AmplitudeClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.amplitude_api_key

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    async def track_event(
        self,
        event_type: str,
        user_id: str = "",
        session_id: str = "",
        properties: dict | None = None,
    ) -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "event_type": event_type}

        event = {
            "event_type": event_type,
            "user_id": user_id or session_id or "anonymous",
            "session_id": session_id or None,
            "event_properties": properties or {},
        }
        payload = {"api_key": self.api_key, "events": [event]}

        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api2.amplitude.com/2/httpapi", json=payload)
            if resp.status_code != 200:
                logger.error("amplitude_track_failed", status=resp.status_code)
                return {"status": "failed", "event_type": event_type}
            return {"status": "ok", "event_type": event_type}

    async def track_conversation_ended(self, session_id: str, channel: str, sentiment: str = "") -> dict:
        return await self.track_event(
            "conversation_ended",
            session_id=session_id,
            properties={"channel": channel, "sentiment": sentiment},
        )
