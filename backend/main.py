"""
Multi-Agent AI Orchestration System
FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config import config
from api.routes import router as api_router, get_workflow_manager
from api.websocket import router as ws_router, get_event_callback
from core.logging import (
    setup_logging,
    get_logger,
    log_api_request
)

# Initialize logging
logger = get_logger('MAIN')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("🚀 Starting Multi-Agent Orchestration System...")
    
    # Validate configuration
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)
    
    # Log config status
    logger.info(f"LLM Provider: {'Gemini' if config.llm.gemini_api_key else 'OpenAI' if config.llm.openai_api_key else 'None'}")
    logger.info(f"LLM Model: {config.llm.model_name}")
    logger.info(f"Search API: {'Configured' if config.search.tavily_api_key else 'Not configured'}")
    logger.debug(f"Debug mode: {config.app.debug}")
    
    # Initialize workflow manager with event callback
    from core.graph import WorkflowManager
    from api.routes import workflow_manager
    import api.routes as routes_module
    
    routes_module.workflow_manager = WorkflowManager(event_callback=get_event_callback())
    await routes_module.workflow_manager.initialize()
    
    logger.info("✅ System initialized successfully")
    logger.info(f"📡 API: http://{config.app.host}:{config.app.port}")
    logger.info(f"📚 Docs: http://{config.app.host}:{config.app.port}/docs")

    # Debug: Print all routes
    for route in app.routes:
        if hasattr(route, 'methods'):
            logger.info(f"Route: {route.path} [{route.methods}]")
        else:
            logger.info(f"Route: {route.path} [WebSocket]")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down...")
    if routes_module.workflow_manager:
        await routes_module.workflow_manager.cleanup()


# Create FastAPI application
app = FastAPI(
    title="WandAI - Multi-Agent Orchestration System",
    description="""
    A system that accepts high-level business requests in plain language,
    uses multiple specialized AI agents to break down tasks, execute subtasks,
    and return structured results with real-time visibility.
    
    ## Features
    
    - **Intelligent Planning**: Decomposes complex requests into actionable steps
    - **Specialized Agents**: Researcher, Coder, Analyst, and Writer agents
    - **Real-time Updates**: WebSocket support for live progress streaming
    - **Ambiguity Handling**: Asks clarifying questions for vague requests
    - **Human-in-the-Loop**: Optional plan approval before execution
    
    ## Quick Start
    
    1. Submit a request to `/api/execute`
    2. Connect to WebSocket at `/ws/{session_id}` for real-time updates
    3. Check status at `/api/status/{session_id}`
    """,
    version="1.0.0",
    lifespan=lifespan
)


# API Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing."""
    start_time = datetime.now()
    
    # Skip logging for docs and static files
    if request.url.path in ["/docs", "/openapi.json", "/redoc"]:
        return await call_next(request)
    
    logger.debug(f"→ {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    duration = (datetime.now() - start_time).total_seconds()
    log_api_request(request.method, request.url.path, response.status_code, duration)
    
    return response


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)
app.include_router(ws_router)


@app.get("/", tags=["health"])
async def root():
    """Root endpoint - API information."""
    return {
        "name": "WandAI - Multi-Agent Orchestration System",
        "version": "1.0.0",
        "status": "running",
        "docs_url": "/docs",
        "endpoints": {
            "execute": "/api/execute",
            "clarify": "/api/clarify",
            "approve": "/api/approve",
            "status": "/api/status/{session_id}",
            "websocket": "/ws/{session_id}"
        }
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "llm_configured": bool(config.llm.gemini_api_key or config.llm.openai_api_key),
        "search_configured": bool(config.search.tavily_api_key)
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if config.app.debug else "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.app.host,
        port=config.app.port,
        reload=config.app.debug
    )

