"""Abstract base for CCaaS telephony adapters (Twilio, Amazon Connect, generic SIP)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, Response


@dataclass
class CallFormData:
    call_sid: str
    from_number: str
    speech_result: str | None = None


@dataclass
class CcaasSessionEntry:
    orchestrator: Any
    last_access: float = field(default_factory=lambda: __import__("time").time())


class CcaasVoiceHandler(ABC):
    """Common interface for inbound PSTN voice calls from any CCaaS provider.

    Subclasses bridge provider-specific webhook formats (TwiML, Amazon Connect
    Lambda payload, generic SIP JSON-RPC) into a uniform agent invocation flow.
    """

    agent_id: str
    config: dict
    telephony_config: dict
    sessions: dict[str, CcaasSessionEntry]

    @abstractmethod
    async def handle_inbound(self, request: Request) -> Response:
        """Initial inbound — greet caller, start speech collection."""
        ...

    @abstractmethod
    async def handle_process(self, request: Request) -> Response:
        """Process speech result — invoke agent, return provider-native response."""
        ...

    @abstractmethod
    async def handle_status_callback(self, request: Request) -> dict[str, Any]:
        """Handle provider lifecycle events (completed, failed, etc.)."""
        ...

    @abstractmethod
    async def simulate(self, call_sid: str, from_number: str, speech_result: str | None = None) -> str:
        """Simulate a webhook without a real phone call (for dev/demo)."""
        ...
