"""
Embedding provider wrapper — matches the LLM provider pattern in core/llm.py.
Uses GoogleGenerativeAIEmbeddings (Gemini) or falls back to OpenAI.
"""

from config import config
from core.logging import get_logger

logger = get_logger("EMBEDDINGS")


def get_embeddings():
    """
    Get an embeddings model matching the configured LLM provider.
    Priority: Gemini > OpenAI. Falls back to next provider on failure.
    """
    if config.llm.gemini_api_key:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            return GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=config.llm.gemini_api_key,
            )
        except Exception as e:
            logger.warning(f"Gemini embeddings failed: {e}")

    if config.llm.openai_api_key:
        try:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(openai_api_key=config.llm.openai_api_key)
        except Exception as e:
            logger.warning(f"OpenAI embeddings failed: {e}")

    raise ValueError(
        "No embedding provider available. Set GEMINI_API_KEY or OPENAI_API_KEY."
    )
