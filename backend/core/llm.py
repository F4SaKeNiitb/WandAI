"""
LLM Provider Factory
Creates the appropriate LLM instance based on configuration.
Priority: Gemini > OpenAI
"""

from config import config


def get_llm():
    """
    Get the configured LLM instance.
    
    Returns ChatGoogleGenerativeAI if GEMINI_API_KEY is set,
    otherwise falls back to ChatOpenAI.
    """
    if config.llm.gemini_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.llm.model_name,
            temperature=config.llm.temperature,
            google_api_key=config.llm.gemini_api_key,
            convert_system_message_to_human=True
        )
    elif config.llm.openai_api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.llm.model_name if not config.llm.model_name.startswith("gemini") else "gpt-4o-mini",
            temperature=config.llm.temperature,
            api_key=config.llm.openai_api_key
        )
    else:
        raise ValueError(
            "No LLM API key configured. Set GEMINI_API_KEY or OPENAI_API_KEY."
        )


def get_llm_provider_name() -> str:
    """Get the name of the currently configured LLM provider."""
    if config.llm.gemini_api_key:
        return "gemini"
    elif config.llm.openai_api_key:
        return "openai"
    return "none"
