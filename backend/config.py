"""
Configuration management for the multi-agent orchestration system.
Loads environment variables and provides typed configuration access.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel


# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")  # Fallback
    model_name: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))


class SearchConfig(BaseModel):
    """Search API configuration."""
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")


class AgentConfig(BaseModel):
    """Agent behavior configuration."""
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    step_timeout_seconds: int = int(os.getenv("STEP_TIMEOUT_SECONDS", "60"))
    clarity_threshold: int = int(os.getenv("CLARITY_THRESHOLD", "8"))


class AppConfig(BaseModel):
    """Application-level configuration."""
    env: str = os.getenv("APP_ENV", "development")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))


class Config:
    """Main configuration class aggregating all configs."""
    llm = LLMConfig()
    search = SearchConfig()
    agent = AgentConfig()
    app = AppConfig()
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of warnings/errors."""
        warnings = []
        
        if not cls.llm.gemini_api_key and not cls.llm.openai_api_key:
            warnings.append("No LLM API key configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")
        
        if not cls.search.tavily_api_key:
            warnings.append("TAVILY_API_KEY not set. Search functionality will be limited.")
        
        return warnings


# Singleton config instance
config = Config()
