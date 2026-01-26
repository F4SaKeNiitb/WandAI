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
        agent_val = self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type)
        logger.debug(f"Initialized {agent_val} agent")
    
    async def emit_event(self, event_type: str, state: AgentState, extra: dict = None):
        """Emit a real-time event if callback is configured."""
        if self.event_callback:
            event = {
                "type": event_type,
                "agent_type": self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type),
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
    
    async def check_task_clarity(
        self, 
        task_description: str, 
        context: str
    ) -> tuple[bool, list[str]]:
        """
        Check if the task description is clear enough to execute.
        
        Args:
            task_description: The specific task this agent should perform
            context: Additional context from previous steps
            
        Returns:
            Tuple of (is_clear: bool, questions: list[str])
        """
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser
        
        agent_val = self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a {agent_val} agent analyzing if a task is clear enough to execute.

Your capabilities as a {agent_val}:
- researcher: Web searches, data retrieval, fact-finding
- coder: Python code execution, calculations, data processing  
- analyst: Data analysis, chart generation, statistical analysis
- writer: Text summarization, formatting, report generation

Analyze the task and determine if you have enough information to proceed.
Consider:
1. Are the inputs/data sources specified or obtainable?
2. Are the expected outputs clear?
3. Are there ambiguous terms that could lead to wrong results?
4. Can you reasonably infer missing details from context?

IMPORTANT: Be practical. If the task is reasonably clear and you can make sensible assumptions, mark it as clear.
Only ask for clarification if critical information is truly missing.

Respond in JSON:
{{{{
    "is_clear": true/false,
    "confidence": 0-10,
    "questions": ["question1", "question2"] // Only if is_clear is false, max 2 questions
}}}}"""),
            ("user", """Task: {task}

Context from previous steps:
{context}

Is this task clear enough for you to execute?""")
        ])
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            result = await chain.ainvoke({
                "task": task_description,
                "context": context[:2000]  # Limit context size
            })
            
            is_clear = result.get("is_clear", True)
            confidence = result.get("confidence", 10)
            questions = result.get("questions", [])

            # Only flag as unclear if confidence is very low
            if confidence >= 6:
                is_clear = True
                questions = []
            
            logger.debug(f"[{agent_val}] Task clarity: {is_clear} (confidence: {confidence})")
            return is_clear, questions
            
        except Exception as e:
            logger.warning(f"[{agent_val}] Clarity check failed: {e}, assuming clear")
            return True, []
    
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
        
        agent_val = self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type)
        logger.info(f"🚀 [{agent_val}] Starting '{step_id}': {task_description[:80]}...")
        
        # Check task clarity before first execution (skip if clarification already provided)
        step_clarifications = getattr(state, 'step_clarifications', {}) or {}
        if step_id not in step_clarifications:
            context = self.get_context_from_state(state)
            is_clear, questions = await self.check_task_clarity(task_description, context)
            
            if not is_clear and questions:
                logger.warning(f"❓ [{agent_val}] Task unclear, requesting clarification: {questions}")
                state.add_log(
                    self.agent_type,
                    f"Task needs clarification: {questions}",
                    level="warning",
                    step_id=step_id
                )
                await self.emit_event("agent_needs_clarification", state, {
                    "step_id": step_id,
                    "questions": questions
                })
                # Return special marker for workflow to handle
                return False, {"needs_clarification": True, "questions": questions}, None
        else:
            # Append clarification context to task
            clarifications = step_clarifications[step_id]
            task_description = f"""{task_description}

## User Clarifications for this step:
{chr(10).join(f'- {c}' for c in clarifications)}"""
            logger.info(f"📝 [{agent_val}] Using provided clarifications for '{step_id}'")
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"   [{agent_val}] Attempt {attempt + 1}/{max_retries}")
                
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
                    logger.info(f"✅ [{agent_val}] '{step_id}' completed ({duration:.2f}s)")
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
                logger.warning(f"⚠️ [{agent_val}] '{step_id}' failed ({duration:.2f}s): {error}")
                
                state.add_log(
                    self.agent_type,
                    f"Task failed: {error}",
                    level="warning",
                    step_id=step_id
                )
                
                # Self-correction: Include error in next attempt
                if attempt < max_retries - 1:
                    logger.debug(f"   [{agent_val}] Retrying with self-correction...")
                    task_description = f"""{task_description}

## ⚠️ PREVIOUS FAILED ATTEMPT
The step failed with the following error:
{error}

Please analyze this error and adjust your approach to avoid repeating it."""
                    await self.emit_event("agent_retrying", state, {
                        "step_id": step_id,
                        "error": error
                    })
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"❌ [{agent_val}] '{step_id}' exception: {last_error}")
                state.add_log(
                    self.agent_type,
                    f"Unexpected error: {last_error}",
                    level="error",
                    step_id=step_id
                )
        
        logger.error(f"💥 [{agent_val}] '{step_id}' failed after {max_retries} attempts")
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
