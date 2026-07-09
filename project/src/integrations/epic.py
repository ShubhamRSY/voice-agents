"""Epic FHIR adapter for healthcare patient context (read-only lookup)."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class EpicClient:
    def __init__(self, base_url: str | None = None, access_token: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.epic_fhir_base_url).rstrip("/")
        self.access_token = access_token or settings.epic_fhir_access_token

    def _is_configured(self) -> bool:
        return bool(self.base_url and self.access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Accept": "application/fhir+json"}

    async def search_patient(self, identifier: str) -> dict | None:
        if not self._is_configured():
            return {"id": "epic-mock-001", "identifier": identifier, "name": "Mock Patient"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/Patient", params={"identifier": identifier}, headers=self._headers())
            if resp.status_code != 200:
                logger.error("epic_patient_failed", status=resp.status_code)
                return None
            entries = resp.json().get("entry", [])
            return entries[0].get("resource") if entries else None

    async def get_patient_summary(self, patient_id: str) -> dict:
        if not self._is_configured():
            return {"patient_id": patient_id, "summary": "Mock patient context"}
        patient = await self.search_patient(patient_id)
        if not patient:
            return {"patient_id": patient_id, "summary": "Not found"}
        names = patient.get("name", [{}])
        display = names[0].get("text", patient_id) if names else patient_id
        return {"patient_id": patient.get("id", patient_id), "summary": display}
