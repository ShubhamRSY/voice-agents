"""LLM provider factory supporting OpenAI, Anthropic, Gemini, and a local mock mode."""

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.llm.params import resolve_llm_params


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    agent_config: dict[str, Any] | None = None,
    global_defaults: dict[str, Any] | None = None,
    **overrides: Any,
) -> BaseChatModel:
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    model = model or settings.default_llm_model

    params = resolve_llm_params(agent_config or {}, global_defaults)
    params.update(overrides)

    temperature = params["temperature"]
    max_tokens = params["max_tokens"]
    top_p = params["top_p"]
    frequency_penalty = params["frequency_penalty"]
    presence_penalty = params["presence_penalty"]
    stop = params["stop_sequences"] or None
    n = params["n"]
    top_k = params["top_k"]

    if provider == "openai":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
            n=n,
            api_key=settings.openai_api_key or None,
        )
    if provider == "anthropic":
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            stop_sequences=stop,
            api_key=settings.anthropic_api_key or None,
        )
    if provider == "gemini":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
            n=n,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.openai_api_key or None,
        )

    if provider == "mock":
        raise ValueError(
            "LLM provider 'mock' is supported only via AgentOrchestrator mock path."
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
