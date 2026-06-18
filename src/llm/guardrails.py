"""Input/output guardrails for safe agent behavior."""

import re
from dataclasses import dataclass

BLOCKED_INPUT_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(your\s+)?(system\s+)?prompt",
    r"jailbreak",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"pretend\s+you\s+are\s+not",
]

BLOCKED_TOPICS = [
    "hack into",
    "bypass security",
    "steal credentials",
    "illegal activity",
]

SYSTEM_LEAK_PATTERNS = [
    r"you are \{agent_name\}",
    r"## voice guidelines",
    r"## guidelines",
    r"available context:",
]


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str = ""
    sanitized_output: str | None = None


def check_input(text: str) -> GuardrailResult:
    lower = text.lower()
    for pattern in BLOCKED_INPUT_PATTERNS:
        if re.search(pattern, lower):
            return GuardrailResult(
                allowed=False,
                reason="Prompt injection or jailbreak pattern detected.",
            )
    for topic in BLOCKED_TOPICS:
        if topic in lower:
            return GuardrailResult(
                allowed=False,
                reason="Request touches a blocked topic for this support agent.",
            )
    return GuardrailResult(allowed=True)


def check_output(text: str) -> GuardrailResult:
    lower = text.lower()
    for pattern in SYSTEM_LEAK_PATTERNS:
        if re.search(pattern, lower):
            return GuardrailResult(
                allowed=True,
                reason="System prompt leakage trimmed.",
                sanitized_output="I'm here to help with Acme support. What can I assist you with?",
            )
    if len(text) > 4000:
        return GuardrailResult(
            allowed=True,
            reason="Output truncated for safety.",
            sanitized_output=text[:4000] + "...",
        )
    return GuardrailResult(allowed=True, sanitized_output=text)
