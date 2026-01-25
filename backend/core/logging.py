"""
Centralized Logging Module
Provides structured logging for the entire application with different log levels
and formatting for LLM calls, agent execution, API requests, and WebSocket events.
"""

import logging
import sys
from datetime import datetime
from functools import wraps
from typing import Any
import json

# Create formatters
class ColoredFormatter(logging.Formatter):
    """Colored formatter for terminal output."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m',
    }
    
    ICONS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨',
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        icon = self.ICONS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Add component tag if available
        component = getattr(record, 'component', 'SYSTEM')
        
        record.msg = f"{color}{icon} [{component}] {record.msg}{reset}"
        return super().format(record)


def setup_logging(debug: bool = True) -> logging.Logger:
    """
    Set up centralized logging for the application.
    
    Args:
        debug: Enable debug level logging
        
    Returns:
        Configured root logger
    """
    level = logging.DEBUG if debug else logging.INFO
    
    # Create main logger
    logger = logging.getLogger("wandai")
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


# Create the main logger
logger = setup_logging(debug=True)


def get_logger(component: str) -> logging.LoggerAdapter:
    """Get a logger adapter for a specific component."""
    return logging.LoggerAdapter(logger, {'component': component})


# Component-specific loggers
llm_logger = get_logger('LLM')
agent_logger = get_logger('AGENT')
api_logger = get_logger('API')
ws_logger = get_logger('WEBSOCKET')
orchestrator_logger = get_logger('ORCHESTRATOR')
tool_logger = get_logger('TOOL')


def log_llm_call(func):
    """Decorator to log LLM calls with inputs and outputs."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = datetime.now()
        func_name = func.__name__
        
        # Log input
        llm_logger.debug(f"📤 LLM Call: {func_name}")
        if 'request' in kwargs:
            llm_logger.debug(f"   Input: {str(kwargs['request'])[:200]}...")
        
        try:
            result = await func(*args, **kwargs)
            
            # Log output
            duration = (datetime.now() - start_time).total_seconds()
            llm_logger.info(f"📥 LLM Response ({duration:.2f}s): {func_name}")
            if hasattr(result, 'content'):
                llm_logger.debug(f"   Output: {str(result.content)[:200]}...")
            
            return result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            llm_logger.error(f"💥 LLM Error ({duration:.2f}s): {func_name} - {str(e)}")
            raise
    
    return wrapper


def log_agent_execution(agent_type: str, step_id: str):
    """Context manager style logging for agent execution."""
    class AgentExecutionLogger:
        def __init__(self):
            self.start_time = None
            
        def start(self, task: str):
            self.start_time = datetime.now()
            agent_logger.info(f"🚀 [{agent_type}] Starting step '{step_id}': {task[:100]}...")
            
        def progress(self, message: str):
            agent_logger.debug(f"   [{agent_type}] {message}")
            
        def success(self, result: Any = None):
            duration = (datetime.now() - self.start_time).total_seconds()
            agent_logger.info(f"✅ [{agent_type}] Step '{step_id}' completed ({duration:.2f}s)")
            if result:
                agent_logger.debug(f"   Result: {str(result)[:200]}...")
                
        def error(self, error: str):
            duration = (datetime.now() - self.start_time).total_seconds()
            agent_logger.error(f"❌ [{agent_type}] Step '{step_id}' failed ({duration:.2f}s): {error}")
            
        def retry(self, attempt: int, max_attempts: int):
            agent_logger.warning(f"🔄 [{agent_type}] Retrying step '{step_id}' ({attempt}/{max_attempts})")
    
    return AgentExecutionLogger()


def log_api_request(method: str, path: str, status: int = None, duration: float = None):
    """Log API request details."""
    if status:
        if status < 400:
            api_logger.info(f"📡 {method} {path} → {status} ({duration:.3f}s)")
        else:
            api_logger.error(f"📡 {method} {path} → {status} ({duration:.3f}s)")
    else:
        api_logger.debug(f"📡 {method} {path}")


def log_websocket_event(event_type: str, session_id: str, data: dict = None):
    """Log WebSocket events."""
    ws_logger.info(f"🔌 Event: {event_type} | Session: {session_id[:8]}...")
    if data:
        ws_logger.debug(f"   Data: {json.dumps(data, default=str)[:200]}...")


def log_tool_execution(tool_name: str, inputs: dict = None, output: Any = None, error: str = None):
    """Log tool execution."""
    if error:
        tool_logger.error(f"🔧 Tool '{tool_name}' failed: {error}")
    elif output:
        tool_logger.info(f"🔧 Tool '{tool_name}' completed")
        tool_logger.debug(f"   Output: {str(output)[:200]}...")
    else:
        tool_logger.debug(f"🔧 Tool '{tool_name}' starting...")
        if inputs:
            tool_logger.debug(f"   Inputs: {json.dumps(inputs, default=str)[:200]}...")


def log_state_change(session_id: str, old_status: str, new_status: str):
    """Log state transitions."""
    orchestrator_logger.info(f"📊 State: {old_status} → {new_status} | Session: {session_id[:8]}...")


def log_plan_created(session_id: str, plan: list):
    """Log plan creation."""
    orchestrator_logger.info(f"📋 Plan created with {len(plan)} steps | Session: {session_id[:8]}...")
    for i, step in enumerate(plan):
        if hasattr(step, 'description'):
            orchestrator_logger.debug(f"   {i+1}. [{step.agent_type}] {step.description[:60]}...")
        elif isinstance(step, dict):
            orchestrator_logger.debug(f"   {i+1}. [{step.get('agent_type', '?')}] {step.get('description', '')[:60]}...")
