"""
Main Orchestrator (The Hub)
Central controller that manages the execution flow, planning, and agent routing.
"""

from datetime import datetime
from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import config
from core.llm import get_llm
from core.state import (
    AgentState, AgentType, ExecutionStatus,
    PlanStep, StepStatus
)
from core.state_utils import (
    get_state_attr, set_state_attr, get_status_value,
    get_plan, get_step_attr, set_step_attr, get_step_status,
    add_log, state_to_event, get_artifact_attr,
)
from core.logging import (
    orchestrator_logger as logger,
    llm_logger,
    log_state_change,
    log_plan_created
)


class Orchestrator:
    """
    The Hub - Manages the entire orchestration flow.
    Does not execute tasks; it plans, routes, and aggregates.
    """

    def __init__(self, event_callback=None, token_tracker=None, guardrails_manager=None,
                 judge=None, metrics_store=None):
        self.llm = get_llm()
        self.event_callback = event_callback
        self.token_tracker = token_tracker
        self.guardrails_manager = guardrails_manager
        self.judge = judge
        self.metrics_store = metrics_store
        self._a2a_client = None
        self._external_agents: dict[str, Any] = {}  # url -> AgentCard

    async def discover_external_agents(self, agent_urls: list[str]) -> None:
        """Discover external A2A agents for potential delegation."""
        from a2a.client import A2AClient
        self._a2a_client = A2AClient()
        for url in agent_urls:
            try:
                card = await self._a2a_client.discover(url)
                self._external_agents[url] = card
                logger.info(f"Discovered external A2A agent: {card.name} at {url}")
            except Exception as e:
                logger.warning(f"Failed to discover A2A agent at {url}: {e}")

    async def delegate_to_external_agent(self, agent_url: str, task_text: str) -> str:
        """Delegate a task to an external A2A agent and return the result text."""
        if not self._a2a_client:
            raise RuntimeError("A2A client not initialized")
        task = await self._a2a_client.send_task(agent_url, task_text)
        # Extract text from the completed task
        if task.status.message:
            for part in task.status.message.parts:
                if hasattr(part, 'text'):
                    return part.text
        if task.artifacts:
            for artifact in task.artifacts:
                for part in artifact.parts:
                    if hasattr(part, 'text'):
                        return part.text
        return "External agent returned no text output"

    async def emit_event(self, event_type: str, state, extra: dict = None):
        """Emit a real-time event if callback is configured."""
        if self.event_callback:
            event = state_to_event(state, event_type)
            if extra:
                event.update(extra)
            await self.event_callback(event)

    async def check_ambiguity(self, state) -> Any:
        """
        Check if the user request is clear enough to proceed.
        Rates clarity 0-10 and generates clarifying questions if needed.
        Only asks for clarification ONCE.
        """
        user_clarifications = get_state_attr(state, 'user_clarifications', [])
        user_request = get_state_attr(state, 'user_request', '')

        logger.debug(f"check_ambiguity: user_clarifications = {user_clarifications}")
        logger.debug(f"check_ambiguity: user_request contains 'Clarifications:' = {'Clarifications:' in user_request}")

        already_clarified = (
            (user_clarifications and len(user_clarifications) > 0) or
            'Clarifications:' in user_request
        )

        if already_clarified:
            logger.info("Clarifications already provided, skipping ambiguity check")
            set_state_attr(state, 'status', ExecutionStatus.PLANNING)
            set_state_attr(state, 'clarity_score', 10)
            add_log(state, AgentType.ORCHESTRATOR,
                    "Clarifications already provided, skipping ambiguity check")
            return state

        logger.info("Analyzing request clarity...")
        set_state_attr(state, 'status', ExecutionStatus.PLANNING)
        add_log(state, AgentType.ORCHESTRATOR, "Analyzing request clarity...")

        await self.emit_event("ambiguity_check_started", state)

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a request clarity analyzer. Your job is to assess if a user's business request is clear enough to execute.

Analyze the request and provide:
1. A clarity score from 0-10 (10 = perfectly clear, 0 = completely ambiguous)
2. If score < 8, provide 1-3 specific clarifying questions

Consider these factors:
- Is the data source specified?
- Is the time period clear?
- Are the expected outputs defined?
- Are there ambiguous terms that need definition?

Respond in JSON format:
{{
    "clarity_score": <int 0-10>,
    "clarifying_questions": [<list of questions if score < 8, else empty>],
    "analysis": "<brief explanation>"
}}"""),
            ("user", "Analyze this request: {request}")
        ])

        fast_llm = get_llm(tier="fast")
        raw_chain = prompt | fast_llm

        try:
            from observability.tracing import get_tracer
            tracer = get_tracer("wandai.orchestrator")

            llm_logger.debug(f"Calling LLM for ambiguity check...")
            with tracer.start_as_current_span("orchestrator.check_ambiguity"):
                raw_response = await raw_chain.ainvoke({"request": user_request})

            # Track token usage
            usage = getattr(raw_response, 'usage_metadata', None)
            if self.token_tracker and usage:
                try:
                    session_id = get_state_attr(state, 'session_id', '')
                    self.token_tracker.record_usage(
                        session_id, "orchestrator", "check_ambiguity",
                        config.llm.model_name,
                        usage.get('input_tokens', 0),
                        usage.get('output_tokens', 0),
                    )
                except Exception:
                    pass

            result = JsonOutputParser().parse(raw_response.content)
            llm_logger.debug(f"LLM response: {result}")

            clarity_score = result.get("clarity_score", 10)
            clarifying_questions = result.get("clarifying_questions", [])

            set_state_attr(state, 'clarity_score', clarity_score)
            set_state_attr(state, 'clarifying_questions', clarifying_questions)

            if clarity_score < config.agent.clarity_threshold:
                logger.warning(f"Request needs clarification (score: {clarity_score}/10)")
                set_state_attr(state, 'status', ExecutionStatus.WAITING_CLARIFICATION)
            else:
                logger.info(f"Request is clear (score: {clarity_score}/10)")

            await self.emit_event("ambiguity_check_completed", state, {
                "clarity_score": clarity_score,
                "needs_clarification": clarity_score < config.agent.clarity_threshold
            })

        except Exception as e:
            logger.error(f"Ambiguity check failed: {str(e)}")
            set_state_attr(state, 'clarity_score', 10)

        return state

    async def create_plan(self, state) -> Any:
        """
        Decompose the user request into a sequence of executable steps.
        Each step is assigned to a specific agent type.
        """
        set_state_attr(state, 'status', ExecutionStatus.PLANNING)
        add_log(state, AgentType.ORCHESTRATOR, "Creating execution plan...")

        user_request = get_state_attr(state, 'user_request', '')
        user_clarifications = get_state_attr(state, 'user_clarifications', [])

        await self.emit_event("planning_started", state)

        context = user_request
        if user_clarifications:
            context += "\n\nUser clarifications:\n" + "\n".join(
                f"- {c}" for c in user_clarifications
            )

        # Load custom agents
        import json
        import os
        custom_agents_str = ""
        if os.path.exists("custom_agents.json"):
            try:
                with open("custom_agents.json", "r") as f:
                    custom_agents = json.load(f)
                    for ca in custom_agents:
                        custom_agents_str += f"- {ca['name']}: {ca['system_prompt'][:100]}...\n"
            except Exception as e:
                logger.error(f"Failed to load custom agents for planning: {e}")

        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a task planner for a multi-agent AI system. Your job is to decompose a business request into atomic, executable steps.

Available agents:
- researcher: Web searches, data retrieval from external sources
- coder: Python code execution, calculations, data processing
- analyst: Data analysis, chart generation, statistical analysis
- writer: Text summarization, formatting, report generation
{{custom_agents}}

Rules:
1. Break down the request into at least 3-5 granular steps. Avoid single-step plans.
2. Each step should be atomic and executable by a single agent
3. Order steps logically - data gathering before analysis, analysis before summarization
4. Encourage multi-agent collaboration (e.g., researcher finds data -> analyst processes it -> writer summarizes).
5. Specify clear dependencies between steps
6. Be specific about what each step should produce
7. IMPORTANT: Custom Agents vs Built-in Agents:
   - Use custom agents (e.g., 'poet') ONLY when the step specifically requires their unique persona or expertise.
   - Use 'researcher' for ALL data gathering, fact-checking, and history retrieval steps, even if the final goal is creative.
   - Use 'writer' for general summarization or report writing.
   - Example: For "Research coffee history and write a poem", use Researcher for history -> Poet for poem. Do NOT use Poet for research.

Respond in JSON format:
{{{{
    "plan": [
        {{{{
            "id": "<unique short id>",
            "description": "<clear description of what to do>",
            "agent_type": "<researcher|coder|analyst|writer|custom_agent_id>",
            "dependencies": [<list of step IDs this depends on>]
        }}}}
    ],
    "reasoning": "<brief explanation of the plan>"
}}}}"""),
            ("user", "Create a plan for this request: {context}")
        ])

        fast_llm = get_llm(tier="fast")
        raw_chain = prompt | fast_llm

        try:
            from observability.tracing import get_tracer
            tracer = get_tracer("wandai.orchestrator")
            with tracer.start_as_current_span("orchestrator.create_plan"):
                raw_response = await raw_chain.ainvoke({
                    "context": context,
                    "custom_agents": custom_agents_str
                })

            # Track token usage
            usage = getattr(raw_response, 'usage_metadata', None)
            if self.token_tracker and usage:
                try:
                    session_id = get_state_attr(state, 'session_id', '')
                    self.token_tracker.record_usage(
                        session_id, "orchestrator", "create_plan",
                        config.llm.model_name,
                        usage.get('input_tokens', 0),
                        usage.get('output_tokens', 0),
                    )
                except Exception:
                    pass

            result = JsonOutputParser().parse(raw_response.content)

            new_plan = []
            for step_data in result.get("plan", []):
                a_type = step_data.get("agent_type", "researcher")

                step = PlanStep(
                    id=step_data.get("id", f"step_{len(new_plan)+1}"),
                    description=step_data.get("description", ""),
                    agent_type=a_type,
                    dependencies=step_data.get("dependencies", [])
                )

                # Always store as dict for LangGraph compatibility
                if isinstance(state, dict):
                    new_plan.append(step.model_dump())
                else:
                    new_plan.append(step)

            set_state_attr(state, 'plan', new_plan)
            set_state_attr(state, 'current_step_index', 0)
            add_log(state, AgentType.ORCHESTRATOR,
                    f"Created plan with {len(new_plan)} steps")

            await self.emit_event("planning_completed", state, {
                "plan_size": len(new_plan),
                "reasoning": result.get("reasoning", "")
            })

        except Exception as e:
            error_msg = f"Planning failed: {str(e)}"
            set_state_attr(state, 'status', ExecutionStatus.ERROR)
            set_state_attr(state, 'error_message', error_msg)
            add_log(state, AgentType.ORCHESTRATOR, error_msg, level="error")

        return state

    async def route_to_agent(self, state) -> tuple[str | None, PlanStep | None]:
        """
        Determine which agent should handle the next step.
        Returns the agent type and step, or (None, None) if all done.
        """
        plan = get_plan(state)

        # Find first pending step with all dependencies satisfied
        completed_ids = set()
        for step in plan:
            if get_step_status(step) == "completed":
                completed_ids.add(get_step_attr(step, 'id'))

        for step in plan:
            status = get_step_status(step)
            if status in ["pending", "retrying"]:
                dependencies = get_step_attr(step, 'dependencies', [])
                deps_satisfied = all(dep in completed_ids for dep in dependencies)

                if deps_satisfied:
                    set_step_attr(step, 'status', StepStatus.IN_PROGRESS.value if isinstance(step, dict) else StepStatus.IN_PROGRESS)

                    agent_type_str = get_step_attr(step, 'agent_type', 'researcher')
                    if hasattr(agent_type_str, 'value'):
                        agent_type_str = agent_type_str.value
                    agent_type = str(agent_type_str)

                    logger.info(f"[ROUTE] Routing step '{get_step_attr(step, 'id')}' to agent: {agent_type}")

                    # Convert dict step to PlanStep object for return
                    if isinstance(step, dict):
                        step_obj = PlanStep(**step)
                    else:
                        step_obj = step
                    return agent_type, step_obj

        return None, None

    async def get_all_executable_steps(self, state) -> list[tuple[str, PlanStep]]:
        """
        Get ALL steps whose dependencies are satisfied (for parallel execution).
        Returns list of (agent_type, step) tuples.
        """
        plan = get_plan(state)

        completed_ids = set()
        for step in plan:
            if get_step_status(step) == "completed":
                completed_ids.add(get_step_attr(step, 'id'))

        executable = []
        for step in plan:
            status = get_step_status(step)
            if status in ["pending", "retrying"]:
                dependencies = get_step_attr(step, 'dependencies', [])
                if all(dep in completed_ids for dep in dependencies):
                    set_step_attr(step, 'status', StepStatus.IN_PROGRESS.value if isinstance(step, dict) else StepStatus.IN_PROGRESS)

                    agent_type_str = get_step_attr(step, 'agent_type', 'researcher')
                    if hasattr(agent_type_str, 'value'):
                        agent_type_str = agent_type_str.value

                    step_obj = PlanStep(**step) if isinstance(step, dict) else step
                    executable.append((str(agent_type_str), step_obj))

        return executable

    async def handle_step_result(
        self,
        state,
        step_id: str,
        success: bool,
        result: Any = None,
        error: str = None
    ) -> Any:
        """Process the result of an agent's step execution."""
        plan = get_plan(state)

        step = None
        for s in plan:
            if get_step_attr(s, 'id') == step_id:
                step = s
                break

        if not step:
            return state

        if success:
            # Data integrity check: detect if agent reported missing data despite "success"
            result_str = str(result) if result else ""
            _DATA_INTEGRITY_MARKERS = ["DATA_NOT_FOUND:", "ERROR_MISSING_DATA:"]
            data_integrity_issue = any(marker in result_str for marker in _DATA_INTEGRITY_MARKERS)

            if data_integrity_issue:
                # Mark step as completed but with a data quality warning
                set_step_attr(step, 'data_quality_warning', True)
                logger.warning(f"Step '{step_id}' completed but flagged missing/unavailable data")
                add_log(state, AgentType.ORCHESTRATOR,
                        f"WARNING: Step '{step_id}' could not find the requested data. "
                        "Downstream steps may be affected.",
                        level="warning")
                await self.emit_event("data_quality_warning", state, {
                    "step_id": step_id,
                    "message": "Step reported missing or unavailable data. Results may be incomplete."
                })

            set_step_attr(step, 'status', StepStatus.COMPLETED.value if isinstance(step, dict) else StepStatus.COMPLETED)
            set_step_attr(step, 'result', result)
            set_step_attr(step, 'completed_at', datetime.now().isoformat() if isinstance(step, dict) else datetime.now())

            # Fire non-blocking evaluation
            if self.judge and self.metrics_store and result:
                import asyncio
                async def _evaluate():
                    try:
                        step_desc = get_step_attr(step, 'description', '')
                        agent_type_str = get_step_attr(step, 'agent_type', 'unknown')
                        eval_result = await self.judge.evaluate_step(step_desc, str(result))
                        set_step_attr(step, 'evaluation_score', eval_result.to_dict())
                        session_id = get_state_attr(state, 'session_id', '')
                        self.metrics_store.record_step_eval(
                            session_id, step_id, agent_type_str, eval_result
                        )
                    except Exception as eval_err:
                        logger.debug(f"Step evaluation failed (non-critical): {eval_err}")
                task = asyncio.create_task(_evaluate())
                task.add_done_callback(lambda t: logger.error(f"Step eval task failed: {t.exception()}") if t.exception() else None)

            add_log(state, AgentType.ORCHESTRATOR,
                    f"Step '{step_id}' completed successfully")
            await self.emit_event("step_completed", state, {"step_id": step_id})
        else:
            retry_count = get_step_attr(step, 'retry_count', 0) + 1
            set_step_attr(step, 'retry_count', retry_count)

            if retry_count < config.agent.max_retries:
                set_step_attr(step, 'status', StepStatus.RETRYING.value if isinstance(step, dict) else StepStatus.RETRYING)
                set_step_attr(step, 'error', error)
                level = "warning"
                msg = f"Step '{step_id}' failed, retrying ({retry_count}/{config.agent.max_retries})"
                event_type = "step_retrying"
            else:
                set_step_attr(step, 'status', StepStatus.FAILED.value if isinstance(step, dict) else StepStatus.FAILED)
                set_step_attr(step, 'error', error)
                level = "error"
                msg = f"Step '{step_id}' failed after {retry_count} retries"
                event_type = "step_failed"

            add_log(state, AgentType.ORCHESTRATOR, msg, level=level)
            await self.emit_event(event_type, state, {
                "step_id": step_id,
                "error": error,
                "retry_count": retry_count
            })

        return state

    async def aggregate_results(self, state) -> Any:
        """
        Synthesize all artifacts into a final natural language response.
        """
        add_log(state, AgentType.ORCHESTRATOR, "Aggregating results...")
        artifacts = get_state_attr(state, 'artifacts', {})
        plan = get_plan(state)
        user_request = get_state_attr(state, 'user_request', '')

        await self.emit_event("aggregation_started", state)

        # Collect all artifacts
        artifacts_summary = []
        for artifact_id, artifact in artifacts.items():
            a_type = get_artifact_attr(artifact, 'type')
            a_name = get_artifact_attr(artifact, 'name')
            a_content = get_artifact_attr(artifact, 'content')

            if a_type == "image":
                artifacts_summary.append(f"- {a_name}: [Image generated]")
            elif a_type == "chart":
                title = a_content.get('title', 'Untitled') if isinstance(a_content, dict) else 'Untitled'
                artifacts_summary.append(f"- {a_name}: [Chart: {title}]")
            else:
                content_preview = str(a_content)[:200]
                artifacts_summary.append(f"- {a_name}: {content_preview}")

        # Collect step results and track data quality
        step_results = []
        failed_steps = []
        data_warnings = []
        for step in plan:
            s_result = get_step_attr(step, 'result')
            s_id = get_step_attr(step, 'id')
            s_type = get_step_attr(step, 'agent_type')
            s_status = get_step_status(step)
            s_error = get_step_attr(step, 'error', '')

            if s_status == "failed":
                failed_steps.append(f"Step '{s_id}' ({s_type}): FAILED - {s_error}")
            elif s_result:
                result_str = str(s_result)
                # Check for data integrity markers
                if "DATA_NOT_FOUND:" in result_str or "ERROR_MISSING_DATA:" in result_str:
                    data_warnings.append(f"Step '{s_id}' ({s_type}): Could not retrieve requested data")
                result_preview = result_str[:300]
                step_results.append(f"Step '{s_id}' ({s_type}): {result_preview}")

        # Build pipeline issues section for the prompt
        pipeline_issues = ""
        if failed_steps:
            pipeline_issues += "\n\nFAILED STEPS:\n" + "\n".join(failed_steps)
        if data_warnings:
            pipeline_issues += "\n\nDATA QUALITY WARNINGS:\n" + "\n".join(data_warnings)

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a results aggregator. Your job is to synthesize the outputs from multiple AI agents into a coherent, user-friendly response.

Create a clear, well-structured response that:
1. Directly answers the user's original request (including ALL specific constraints, text inclusions, or formatting requests).
2. Summarizes key findings
3. References any charts or visualizations created
4. Highlights important insights

CRITICAL HONESTY RULES:
- If any steps failed or could not retrieve the requested data, you MUST clearly inform the user about this.
- NEVER present fabricated or simulated data as if it were real.
- If the pipeline could not fulfill the user's request due to missing data, say so honestly and suggest alternatives (e.g., "The data could not be retrieved. You may try [alternative approach].").
- Add a visible warning section if there were data quality issues.

IMPORTANT: If the user request asks to include specific text, phrases, or formats, you MUST include them exactly as requested.

Be concise but comprehensive. Use markdown formatting for readability."""),
            ("user", """Original request: {request}

Step results:
{step_results}

Artifacts created:
{artifacts}
{pipeline_issues}

Synthesize these into a final response for the user. If there were failures or data quality issues, make sure to alert the user clearly.""")
        ])

        chain = prompt | self.llm

        try:
            from observability.tracing import get_tracer
            tracer = get_tracer("wandai.orchestrator")

            with tracer.start_as_current_span("orchestrator.aggregate_results"):
                full_content = ""
                last_chunk = None
                async for chunk in chain.astream({
                    "request": user_request,
                    "step_results": "\n".join(step_results) or "No step results available",
                    "artifacts": "\n".join(artifacts_summary) or "No artifacts created",
                    "pipeline_issues": pipeline_issues
                }):
                    token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if token:
                        full_content += token
                        await self.emit_event("streaming_token", state, {"token": token})
                    last_chunk = chunk

                await self.emit_event("streaming_complete", state, {
                    "total_length": len(full_content)
                })

            final_content = full_content

            # Track token usage for aggregation (some providers include usage on last chunk)
            usage = getattr(last_chunk, 'usage_metadata', None)
            if self.token_tracker and usage:
                try:
                    session_id = get_state_attr(state, 'session_id', '')
                    self.token_tracker.record_usage(
                        session_id, "orchestrator", "aggregate_results",
                        config.llm.model_name,
                        usage.get('input_tokens', 0),
                        usage.get('output_tokens', 0),
                    )
                except Exception:
                    pass

            # Output guardrails — redact PII from final response
            if self.guardrails_manager:
                final_content, filters = self.guardrails_manager.filter_output(final_content)
                if filters:
                    guardrail_flags = get_state_attr(state, 'guardrail_flags', []) or []
                    guardrail_flags.append({"stage": "aggregation", "filters": filters})
                    set_state_attr(state, 'guardrail_flags', guardrail_flags)

            set_state_attr(state, 'final_response', final_content)
            set_state_attr(state, 'status', ExecutionStatus.COMPLETED)
            add_log(state, AgentType.ORCHESTRATOR, "Results aggregated successfully")
            await self.emit_event("execution_completed", state)

            # Fire non-blocking session evaluation
            if self.judge and self.metrics_store:
                import asyncio
                async def _eval_session():
                    try:
                        eval_result = await self.judge.evaluate_session(user_request, final_content)
                        session_id = get_state_attr(state, 'session_id', '')
                        self.metrics_store.record_session_eval(session_id, eval_result)
                        set_state_attr(state, 'evaluation_scores', eval_result.to_dict())
                    except Exception as eval_err:
                        logger.debug(f"Session evaluation failed (non-critical): {eval_err}")
                task = asyncio.create_task(_eval_session())
                task.add_done_callback(lambda t: logger.error(f"Session eval task failed: {t.exception()}") if t.exception() else None)

        except Exception as e:
            error_msg = f"Aggregation failed: {str(e)}"
            set_state_attr(state, 'status', ExecutionStatus.ERROR)
            set_state_attr(state, 'error_message', error_msg)
            add_log(state, AgentType.ORCHESTRATOR, error_msg, level="error")

        return state
