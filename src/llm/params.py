"""Resolve LLM generation parameters from agent config."""

from typing import Any


DEFAULT_LLM_PARAMS = {
    "temperature": 0.3,
    "max_tokens": 1024,
    "top_p": 1.0,
    "top_k": 40,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "n": 1,
    "stop_sequences": [],
    "chain_of_thought": False,
    "few_shot_enabled": True,
}


def resolve_llm_params(agent_config: dict[str, Any], global_defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = {**DEFAULT_LLM_PARAMS, **(global_defaults or {})}
    params = {**defaults}

    for key in DEFAULT_LLM_PARAMS:
        if key in agent_config:
            params[key] = agent_config[key]

    llm_block = agent_config.get("llm", {})
    if isinstance(llm_block, dict):
        params.update({k: v for k, v in llm_block.items() if k in DEFAULT_LLM_PARAMS})

    return params
