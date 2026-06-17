"""LLM provider factory supporting OpenAI, Anthropic, Gemini, and a local mock mode."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config import get_settings


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> BaseChatModel:
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    model = model or settings.default_llm_model

    if provider == "openai":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.openai_api_key or None,
        )
    if provider == "anthropic":
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.anthropic_api_key or None,
        )
    if provider == "gemini":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.openai_api_key or None,
        )

    # "mock" is intentionally handled in the orchestrator (rule-based, no LLM needed).
    # We keep this branch for clarity and error messaging.
    if provider == "mock":
        raise ValueError(
            "LLM provider 'mock' is supported only via AgentOrchestrator mock path. "
            "Set agent llm_provider to 'mock' and run through the API/orchestrator."
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
