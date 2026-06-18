"""Grounding and hallucination checks against retrieved context."""

import re
from dataclasses import dataclass


@dataclass
class GroundingScore:
    score: float
    grounded: bool
    matched_terms: list[str]
    hallucination_risk: str


def _tokenize(text: str) -> set[str]:
    stop = {"the", "a", "an", "to", "and", "or", "is", "are", "for", "you", "your", "can", "with", "that", "this"}
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in stop}


def score_grounding(response: str, context: str) -> GroundingScore:
    """Measure how much of the response overlaps with retrieved KB context."""
    if not context or "No relevant knowledge base" in context:
        return GroundingScore(
            score=1.0,
            grounded=True,
            matched_terms=[],
            hallucination_risk="low",
        )

    response_tokens = _tokenize(response)
    context_tokens = _tokenize(context)
    if not response_tokens:
        return GroundingScore(score=0.0, grounded=False, matched_terms=[], hallucination_risk="high")

    overlap = response_tokens & context_tokens
    score = len(overlap) / len(response_tokens)

    if score >= 0.15:
        risk = "low"
        grounded = True
    elif score >= 0.05:
        risk = "medium"
        grounded = True
    else:
        risk = "high"
        grounded = False

    return GroundingScore(
        score=round(score, 3),
        grounded=grounded,
        matched_terms=sorted(overlap)[:10],
        hallucination_risk=risk,
    )
