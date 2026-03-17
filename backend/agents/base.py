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
from core.state_utils import (
    get_state_attr, get_plan, get_step_attr, get_step_status,
    get_artifact_attr, add_log as state_add_log,
)
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

    def __init__(
        self,
        event_callback: Callable = None,
        mcp_manager=None,
        rag_pipeline=None,
        memory=None,
        token_tracker=None,
        guardrails_manager=None,
    ):
        """
        Initialize the agent.

        Args:
            event_callback: Async function to send real-time events
            mcp_manager: Optional MCPToolManager for MCP-based tool discovery
            rag_pipeline: Optional RAGPipeline for document retrieval
            memory: Optional AgentMemory for cross-session recall
            token_tracker: Optional TokenTracker for usage tracking
            guardrails_manager: Optional GuardrailsManager for output filtering
        """
        self.llm = get_llm()
        self.event_callback = event_callback
        self.mcp_manager = mcp_manager
        self.rag_pipeline = rag_pipeline
        self.memory = memory
        self.token_tracker = token_tracker
        self.guardrails_manager = guardrails_manager
        self.tools: list[BaseTool] = []
        self._last_usage = None
        agent_val = self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type)
        logger.debug(f"Initialized {agent_val} agent")
    
    async def emit_event(self, event_type: str, state, extra: dict = None):
        """Emit a real-time event if callback is configured."""
        if self.event_callback:
            event = {
                "type": event_type,
                "agent_type": self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type),
                "session_id": get_state_attr(state, 'session_id', ''),
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

    async def bind_mcp_tools(self):
        """Discover and bind tools from the MCP manager, if available."""
        if self.mcp_manager:
            mcp_tools = self.mcp_manager.as_langchain_tools()
            if mcp_tools:
                self.bind_tools(mcp_tools)
                agent_val = self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type)
                logger.debug(f"[{agent_val}] Bound {len(mcp_tools)} MCP tools")
    
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
        
        fast_llm = get_llm(tier="fast")
        chain = prompt | fast_llm | JsonOutputParser()
        
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
        step_clarifications = get_state_attr(state, 'step_clarifications', {}) or {}
        if step_id not in step_clarifications:
            context = self.get_context_from_state(state)
            is_clear, questions = await self.check_task_clarity(task_description, context)

            if not is_clear and questions:
                logger.warning(f"❓ [{agent_val}] Task unclear, requesting clarification: {questions}")
                state_add_log(
                    state, self.agent_type,
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
        
        # Get tracer for distributed tracing
        from observability.tracing import get_tracer
        tracer = get_tracer("wandai.agents")

        for attempt in range(max_retries):
            try:
                logger.debug(f"   [{agent_val}] Attempt {attempt + 1}/{max_retries}")

                state_add_log(
                    state, self.agent_type,
                    f"Executing task (attempt {attempt + 1}/{max_retries})",
                    step_id=step_id
                )
                await self.emit_event("agent_executing", state, {
                    "step_id": step_id,
                    "attempt": attempt + 1
                })

                start_time = datetime.now()

                with tracer.start_as_current_span(
                    f"agent.{agent_val}.execute",
                    attributes={
                        "agent.type": agent_val,
                        "step.id": step_id,
                        "attempt": attempt + 1,
                    },
                ) as span:
                    success, result, error = await self.execute(
                        state, step_id, task_description
                    )
                    duration = (datetime.now() - start_time).total_seconds()
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_attribute("success", success)

                if success:
                    logger.info(f"✅ [{agent_val}] '{step_id}' completed ({duration:.2f}s)")
                    if result:
                        logger.debug(f"   Result: {str(result)[:150]}...")

                    # Output guardrails — filter PII from result
                    if self.guardrails_manager and isinstance(result, str):
                        result, filters = self.guardrails_manager.filter_output(result)
                        if filters:
                            guardrail_flags = get_state_attr(state, 'guardrail_flags', []) or []
                            guardrail_flags.append({"step_id": step_id, "filters": filters})
                            from core.state_utils import set_state_attr
                            set_state_attr(state, 'guardrail_flags', guardrail_flags)

                    # Token tracking — extract usage_metadata from last LLM call
                    self._track_tokens(state, step_id, agent_val)

                    # Memory — store successful interaction
                    if self.memory:
                        try:
                            session_id = get_state_attr(state, 'session_id', '')
                            self.memory.store_interaction(
                                session_id=session_id,
                                agent_type=agent_val,
                                task=task_description[:500],
                                result=str(result)[:2000] if result else "",
                            )
                        except Exception as mem_err:
                            logger.debug(f"Memory store failed (non-critical): {mem_err}")

                    state_add_log(
                        state, self.agent_type,
                        "Task completed successfully",
                        step_id=step_id
                    )
                    await self.emit_event("agent_success", state, {
                        "step_id": step_id
                    })
                    return True, result, None

                last_error = error
                logger.warning(f"⚠️ [{agent_val}] '{step_id}' failed ({duration:.2f}s): {error}")

                state_add_log(
                    state, self.agent_type,
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
                state_add_log(
                    state, self.agent_type,
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

    def _track_tokens(self, state, step_id: str, agent_val: str):
        """Extract token usage from last LLM response and record it."""
        if not self.token_tracker:
            return
        if not self._last_usage:
            return
        try:
            session_id = get_state_attr(state, 'session_id', '')
            model_name = config.llm.model_name
            self.token_tracker.record_usage(
                session_id,
                agent_val,
                step_id,
                model_name,
                self._last_usage.get('input_tokens', 0),
                self._last_usage.get('output_tokens', 0),
            )
        except Exception as e:
            logger.debug(f"Token tracking failed (non-critical): {e}")
        finally:
            self._last_usage = None
    
    def get_rag_context(self, state, query: str) -> str:
        """
        Query the RAG pipeline for uploaded document context.
        Returns formatted context string or empty string.
        """
        if not self.rag_pipeline:
            return ""
        try:
            session_id = get_state_attr(state, 'session_id', '')
            results = self.rag_pipeline.query(query, session_id, k=5)
            if not results:
                return ""
            chunks = [r["content"] for r in results]
            return "Context from uploaded documents:\n" + "\n---\n".join(chunks)
        except Exception as e:
            logger.debug(f"RAG query failed (non-critical): {e}")
            return ""

    def get_memory_context(self, task_description: str) -> str:
        """
        Recall relevant past interactions from agent memory.
        Returns formatted context string or empty string.
        """
        if not self.memory:
            return ""
        try:
            agent_val = self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type)
            memories = self.memory.recall(task_description, agent_type=agent_val)
            if not memories:
                return ""
            parts = []
            for m in memories:
                parts.append(f"- {m['content'][:300]}")
            return "Relevant past interactions:\n" + "\n".join(parts)
        except Exception as e:
            logger.debug(f"Memory recall failed (non-critical): {e}")
            return ""

    def get_context_from_state(self, state: AgentState) -> str:
        """
        Extract relevant context from the shared state.
        This includes artifacts from previous steps that might be needed.
        """
        user_request = get_state_attr(state, 'user_request', '')
        plan = get_plan(state)
        artifacts = get_state_attr(state, 'artifacts', {})

        context_parts = [f"User's original request: {user_request}"]

        for step in plan:
            if get_step_status(step) == "completed" and get_step_attr(step, 'result'):
                context_parts.append(
                    f"\nResult from step '{get_step_attr(step, 'id')}' "
                    f"({get_step_attr(step, 'agent_type')}):\n{get_step_attr(step, 'result')}"
                )

        if artifacts:
            context_parts.append("\nAvailable artifacts:")
            for artifact_id, artifact in artifacts.items():
                a_type = get_artifact_attr(artifact, 'type', 'text')
                if a_type != "image":
                    preview = str(get_artifact_attr(artifact, 'content', ''))[:500]
                    a_name = get_artifact_attr(artifact, 'name', artifact_id)
                    context_parts.append(f"- {a_name} ({a_type}): {preview}")

        # RAG context from uploaded documents
        rag_context = self.get_rag_context(state, user_request)
        if rag_context:
            context_parts.append(f"\n{rag_context}")

        # Memory context from past interactions
        memory_context = self.get_memory_context(user_request)
        if memory_context:
            context_parts.append(f"\n{memory_context}")

        return "\n".join(context_parts)
