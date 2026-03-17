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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model_name: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    temperature: float = max(0.0, min(2.0, float(os.getenv("LLM_TEMPERATURE", "0.7") or "0.7")))
    fast_model: str = os.getenv("LLM_FAST_MODEL", "")
    powerful_model: str = os.getenv("LLM_POWERFUL_MODEL", "")
    provider_priority: str = os.getenv("LLM_PROVIDER_PRIORITY", "gemini,openai,anthropic")


class SearchConfig(BaseModel):
    """Search API configuration."""
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")


class AgentConfig(BaseModel):
    """Agent behavior configuration."""
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    step_timeout_seconds: int = int(os.getenv("STEP_TIMEOUT_SECONDS", "60"))
    clarity_threshold: int = int(os.getenv("CLARITY_THRESHOLD", "8"))


class MCPServerConfig(BaseModel):
    """MCP server connection configuration."""
    search: dict = {
        "command": "python",
        "args": ["-m", "mcp_servers.search_server"],
        "transport": "stdio",
    }
    code: dict = {
        "command": "python",
        "args": ["-m", "mcp_servers.code_server"],
        "transport": "stdio",
    }
    chart: dict = {
        "command": "python",
        "args": ["-m", "mcp_servers.chart_server"],
        "transport": "stdio",
    }


class ExternalAgentsConfig(BaseModel):
    """External A2A agent URLs for discovery."""
    agent_urls: list[str] = []  # e.g. ["http://other-host:9000/a2a/agent"]


class RAGConfig(BaseModel):
    """RAG pipeline configuration."""
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    chroma_host: str = os.getenv("CHROMA_HOST", "")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8001"))
    chunk_size: int = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))


class GuardrailsConfig(BaseModel):
    """AI safety guardrails configuration."""
    enabled: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    pii_redaction: bool = os.getenv("PII_REDACTION", "true").lower() == "true"
    injection_detection: bool = os.getenv("INJECTION_DETECTION", "true").lower() == "true"
    max_input_length: int = int(os.getenv("MAX_INPUT_LENGTH", "10000"))


class TracingConfig(BaseModel):
    """OpenTelemetry tracing configuration."""
    enabled: bool = os.getenv("TRACING_ENABLED", "false").lower() == "true"
    exporter: str = os.getenv("TRACING_EXPORTER", "console")  # "console" | "otlp"
    endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


class MemoryConfig(BaseModel):
    """Cross-session agent memory configuration."""
    enabled: bool = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
    persist_dir: str = os.getenv("MEMORY_PERSIST_DIR", "./chroma_data")
    max_recall_results: int = int(os.getenv("MEMORY_MAX_RECALL", "3"))


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
    mcp_servers = MCPServerConfig()
    external_agents = ExternalAgentsConfig()
    rag = RAGConfig()
    guardrails = GuardrailsConfig()
    tracing = TracingConfig()
    memory = MemoryConfig()
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of warnings/errors."""
        warnings = []
        
        if not cls.llm.gemini_api_key and not cls.llm.openai_api_key and not cls.llm.anthropic_api_key:
            warnings.append("No LLM API key configured. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")
        
        if not cls.search.tavily_api_key:
            warnings.append("TAVILY_API_KEY not set. Search functionality will be limited.")
        
        return warnings


# Singleton config instance
config = Config()
