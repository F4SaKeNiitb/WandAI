"""
Base Agent class for all specialized worker agents.
Provides common functionality like retry logic, event emission, and tool binding.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool

from config import config
from core.llm import get_llm
from core.state import AgentState, AgentType, AgentLog
from core.logging import (
    agent_logger as logger,
    llm_logger,
    log_agent_execution
)


class BaseAgent(ABC):
    """
    Abstract base class for all worker agents.
    Each agent is a stateless worker that performs atomic actions.
    """
    
    agent_type: AgentType = AgentType.ORCHESTRATOR
    system_prompt: str = "You are a helpful AI assistant."
    
    def __init__(self, event_callback: Callable = None):
        """
        Initialize the agent.
        
        Args:
            event_callback: Async function to send real-time events
        """
        self.llm = get_llm()
        self.event_callback = event_callback
        self.tools: list[BaseTool] = []
        logger.debug(f"Initialized {self.agent_type.value} agent")
    
    async def emit_event(self, event_type: str, state: AgentState, extra: dict = None):
        """Emit a real-time event if callback is configured."""
        if self.event_callback:
            event = {
                "type": event_type,
                "agent_type": self.agent_type.value,
                "session_id": state.session_id,
                "timestamp": datetime.now().isoformat()
            }
            if extra:
                event.update(extra)
            await self.event_callback(event)
    
    def bind_tools(self, tools: list[BaseTool]):
        """Bind tools to the agent's LLM."""
        self.tools = tools
        if tools:
            self.llm = self.llm.bind_tools(tools)
    
    @abstractmethod
    async def execute(
        self, 
        state: AgentState, 
        step_id: str,
        task_description: str
    ) -> tuple[bool, Any, str | None]:
        """
        Execute the agent's task.
        
        Args:
            state: Current shared state
            step_id: ID of the step being executed
            task_description: Description of what to do
            
        Returns:
            Tuple of (success: bool, result: Any, error: str | None)
        """
        pass
    
    async def execute_with_retry(
        self, 
        state: AgentState, 
        step_id: str,
        task_description: str,
        max_retries: int = None
    ) -> tuple[bool, Any, str | None]:
        """
        Execute with automatic retry logic.
        
        Args:
            state: Current shared state
            step_id: ID of the step being executed
            task_description: Description of what to do
            max_retries: Maximum retry attempts (defaults to config)
            
        Returns:
            Tuple of (success: bool, result: Any, error: str | None)
        """
        max_retries = max_retries or config.agent.max_retries
        last_error = None
        
        logger.info(f"🚀 [{self.agent_type.value}] Starting '{step_id}': {task_description[:80]}...")
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"   [{self.agent_type.value}] Attempt {attempt + 1}/{max_retries}")
                
                state.add_log(
                    self.agent_type,
                    f"Executing task (attempt {attempt + 1}/{max_retries})",
                    step_id=step_id
                )
                await self.emit_event("agent_executing", state, {
                    "step_id": step_id,
                    "attempt": attempt + 1
                })
                
                start_time = datetime.now()
                success, result, error = await self.execute(
                    state, step_id, task_description
                )
                duration = (datetime.now() - start_time).total_seconds()
                
                if success:
                    logger.info(f"✅ [{self.agent_type.value}] '{step_id}' completed ({duration:.2f}s)")
                    if result:
                        logger.debug(f"   Result: {str(result)[:150]}...")
                    
                    state.add_log(
                        self.agent_type,
                        "Task completed successfully",
                        step_id=step_id
                    )
                    await self.emit_event("agent_success", state, {
                        "step_id": step_id
                    })
                    return True, result, None
                
                last_error = error
                logger.warning(f"⚠️ [{self.agent_type.value}] '{step_id}' failed ({duration:.2f}s): {error}")
                
                state.add_log(
                    self.agent_type,
                    f"Task failed: {error}",
                    level="warning",
                    step_id=step_id
                )
                
                # Self-correction: Include error in next attempt
                if attempt < max_retries - 1:
                    logger.debug(f"   [{self.agent_type.value}] Retrying with self-correction...")
                    task_description = f"{task_description}\n\nPrevious attempt failed with error: {error}\nPlease try a different approach."
                    await self.emit_event("agent_retrying", state, {
                        "step_id": step_id,
                        "error": error
                    })
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"❌ [{self.agent_type.value}] '{step_id}' exception: {last_error}")
                state.add_log(
                    self.agent_type,
                    f"Unexpected error: {last_error}",
                    level="error",
                    step_id=step_id
                )
        
        logger.error(f"💥 [{self.agent_type.value}] '{step_id}' failed after {max_retries} attempts")
        await self.emit_event("agent_failed", state, {
            "step_id": step_id,
            "error": last_error
        })
        return False, None, last_error
    
    def get_context_from_state(self, state: AgentState) -> str:
        """
        Extract relevant context from the shared state.
        This includes artifacts from previous steps that might be needed.
        """
        # Handle dict state
        if isinstance(state, dict):
            user_request = state.get('user_request', '')
            plan = state.get('plan', [])
            artifacts = state.get('artifacts', {})
        else:
            user_request = state.user_request
            plan = state.plan
            artifacts = state.artifacts
        
        context_parts = [f"User's original request: {user_request}"]
        
        # Get completed step results
        for step in plan:
            # Handle both PlanStep objects and dicts
            if isinstance(step, dict):
                step_status = step.get('status', '')
                if hasattr(step_status, 'value'):
                    step_status = step_status.value
                step_status = str(step_status)
                
                if step_status == "completed" and step.get('result'):
                    context_parts.append(
                        f"\nResult from step '{step.get('id')}' ({step.get('agent_type')}):\n{step.get('result')}"
                    )
            else:
                step_status = step.status.value if hasattr(step.status, 'value') else str(step.status)
                if step_status == "completed" and step.result:
                    context_parts.append(
                        f"\nResult from step '{step.id}' ({step.agent_type}):\n{step.result}"
                    )
        
        # Get relevant artifacts
        if artifacts:
            context_parts.append("\nAvailable artifacts:")
            for artifact_id, artifact in artifacts.items():
                if isinstance(artifact, dict):
                    if artifact.get('type') != "image":
                        preview = str(artifact.get('content', ''))[:500]
                        context_parts.append(f"- {artifact.get('name', artifact_id)} ({artifact.get('type', 'text')}): {preview}")
                else:
                    if artifact.type != "image":
                        preview = str(artifact.content)[:500]
                        context_parts.append(f"- {artifact.name} ({artifact.type}): {preview}")
        
        return "\n".join(context_parts)
