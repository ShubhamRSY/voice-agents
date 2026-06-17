"""Call routing, metadata passing, and fallback configuration."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RoutingStrategy(Enum):
    DIRECT = "direct"
    ROUND_ROBIN = "round_robin"
    SKILL_BASED = "skill_based"


@dataclass
class CallMetadata:
    call_sid: str
    from_number: str
    to_number: str
    direction: str = "inbound"
    custom_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingRule:
    name: str
    condition: str
    destination: str
    priority: int = 0


class CallRouter:
    """Routes calls based on metadata, with fallback and SIP header support."""

    def __init__(self):
        self.rules: list[RoutingRule] = []
        self.fallback_destination: str = ""
        self._round_robin_index = 0

    def add_rule(self, rule: RoutingRule) -> None:
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def set_fallback(self, destination: str) -> None:
        self.fallback_destination = destination

    def route(
        self,
        metadata: CallMetadata,
        strategy: RoutingStrategy = RoutingStrategy.SKILL_BASED,
    ) -> str:
        for rule in self.rules:
            if self._matches(rule.condition, metadata):
                return rule.destination

        if strategy == RoutingStrategy.ROUND_ROBIN:
            destinations = [r.destination for r in self.rules]
            if destinations:
                dest = destinations[self._round_robin_index % len(destinations)]
                self._round_robin_index += 1
                return dest

        return self.fallback_destination

    def _matches(self, condition: str, metadata: CallMetadata) -> bool:
        if condition.startswith("from:"):
            prefix = condition.split(":", 1)[1]
            return metadata.from_number.startswith(prefix)
        if condition.startswith("field:"):
            key_val = condition.split(":", 1)[1]
            key, val = key_val.split("=", 1)
            return metadata.custom_fields.get(key) == val
        return False

    def extract_sip_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Extract X-* SIP headers passed through CCaaS providers."""
        return {k: v for k, v in headers.items() if k.lower().startswith("x-")}
