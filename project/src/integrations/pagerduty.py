"""PagerDuty adapter for incident management and on-call alerting."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class PagerDutyClient:
    def __init__(self, api_key: str | None = None, service_id: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.pagerduty_api_key
        self.service_id = service_id or settings.pagerduty_service_id
        self.base_url = "https://api.pagerduty.com"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Token token={self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }

    async def create_incident(self, title: str, body: str = "", urgency: str = "high") -> dict:
        if not self._is_configured():
            return {"id": "inc-mock-001", "title": title, "status": "triggered"}

        payload = {
            "incident": {
                "type": "incident",
                "title": title,
                "service": {"id": self.service_id, "type": "service_reference"} if self.service_id else None,
                "body": {"type": "incident_body", "details": body or title},
                "urgency": urgency,
            }
        }
        if not self.service_id:
            payload["incident"].pop("service")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/incidents",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("pagerduty_incident_failed", status=resp.status_code)
                return {"id": None, "title": title, "status": "failed"}
            data = resp.json().get("incident", {})
            return {"id": data.get("id"), "title": data.get("title"), "status": data.get("status")}
