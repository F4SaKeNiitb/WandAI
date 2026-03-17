"""
LLM Provider Factory — Multi-provider with tier routing and automatic fallback.
Supports Gemini, OpenAI, and Anthropic Claude.
"""
from config import config
import logging

logger = logging.getLogger("wandai.llm")

_TIER_DEFAULTS = {
    "fast": {"gemini": "gemini-2.0-flash", "openai": "gpt-4o-mini", "anthropic": "claude-haiku-4-5-20251001"},
    "powerful": {"gemini": "gemini-2.0-pro", "openai": "gpt-4o", "anthropic": "claude-sonnet-4-6"},
}


def _create_provider(provider, model_name, temperature):
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name, temperature=temperature,
            google_api_key=config.llm.gemini_api_key, convert_system_message_to_human=True
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name, temperature=temperature, api_key=config.llm.openai_api_key
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_name, temperature=temperature, api_key=config.llm.anthropic_api_key
        )


def _provider_available(provider):
    keys = {
        "gemini": config.llm.gemini_api_key,
        "openai": config.llm.openai_api_key,
        "anthropic": config.llm.anthropic_api_key,
    }
    return bool(keys.get(provider))


def _resolve_model(tier, provider):
    if tier == "fast" and config.llm.fast_model:
        return config.llm.fast_model
    if tier == "powerful" and config.llm.powerful_model:
        return config.llm.powerful_model
    if tier in _TIER_DEFAULTS and provider in _TIER_DEFAULTS[tier]:
        return _TIER_DEFAULTS[tier][provider]
    model = config.llm.model_name
    # Don't send gemini model to openai/anthropic
    if provider != "gemini" and model.startswith("gemini"):
        return _TIER_DEFAULTS.get("fast", {}).get(provider, "gpt-4o-mini")
    return model


def get_llm(tier="default"):
    """
    Get a configured LLM instance with automatic fallback across providers.

    Args:
        tier: "fast" for cheap/quick tasks, "powerful" for complex tasks,
              "default" for the configured model_name.
    """
    priority = [p.strip() for p in config.llm.provider_priority.split(",")]
    available = [p for p in priority if _provider_available(p)]
    if not available:
        raise ValueError("No LLM API key configured. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")

    instances = []
    for provider in available:
        model = _resolve_model(tier, provider)
        instances.append(_create_provider(provider, model, config.llm.temperature))
        logger.debug(f"LLM provider ready: {provider} ({model}), tier={tier}")

    if len(instances) == 1:
        return instances[0]
    return instances[0].with_fallbacks(instances[1:])


def get_llm_provider_name() -> str:
    """Get the name of the primary configured LLM provider."""
    priority = [p.strip() for p in config.llm.provider_priority.split(",")]
    for p in priority:
        if _provider_available(p):
            return p
    return "none"
