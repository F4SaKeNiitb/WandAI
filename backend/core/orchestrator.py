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
    
    def __init__(self, event_callback=None):
        """
        Initialize the orchestrator.
        
        Args:
            event_callback: Async function to send real-time events
        """
        self.llm = get_llm()
        self.event_callback = event_callback
    
    async def emit_event(self, event_type: str, state: AgentState, extra: dict = None):
        """Emit a real-time event if callback is configured."""
        if self.event_callback:
            event = state.to_event(event_type)
            if extra:
                event.update(extra)
            await self.event_callback(event)
    
    async def check_ambiguity(self, state: AgentState) -> AgentState:
        """
        Check if the user request is clear enough to proceed.
        Rates clarity 0-10 and generates clarifying questions if needed.
        Only asks for clarification ONCE - if user has already provided clarifications, skip.
        """
        # Handle dict state - get user_clarifications
        if isinstance(state, dict):
            user_clarifications = state.get('user_clarifications', [])
            user_request = state.get('user_request', '')
        else:
            user_clarifications = getattr(state, 'user_clarifications', [])
            user_request = state.user_request
        
        logger.debug(f"check_ambiguity: user_clarifications = {user_clarifications}")
        logger.debug(f"check_ambiguity: user_request contains 'Clarifications:' = {'Clarifications:' in user_request}")
        
        # Skip clarification if already provided (only ask once)
        # Check both the list AND if the request already contains clarifications text
        already_clarified = (
            (user_clarifications and len(user_clarifications) > 0) or
            'Clarifications:' in user_request
        )
        
        if already_clarified:
            logger.info("Clarifications already provided, skipping ambiguity check")
            if isinstance(state, dict):
                state['status'] = ExecutionStatus.PLANNING
                state['clarity_score'] = 10  # Assume clear after user clarified
                # Add log entry for dict state
                from core.state import AgentLog
                if 'logs' not in state:
                    state['logs'] = []
                state['logs'].append(AgentLog(
                    timestamp=datetime.now(),
                    agent_type=AgentType.ORCHESTRATOR,
                    message="Clarifications already provided, skipping ambiguity check"
                ))
            else:
                state.status = ExecutionStatus.PLANNING
                state.clarity_score = 10
                state.add_log(
                    AgentType.ORCHESTRATOR,
                    "Clarifications already provided, skipping ambiguity check"
                )
            return state
        
        logger.info("Analyzing request clarity...")
        if isinstance(state, dict):
            state['status'] = ExecutionStatus.PLANNING
        else:
            state.status = ExecutionStatus.PLANNING
        
        # Add log entry
        if isinstance(state, dict):
            from core.state import AgentLog
            if 'logs' not in state:
                state['logs'] = []
            state['logs'].append(AgentLog(
                timestamp=datetime.now(),
                agent_type=AgentType.ORCHESTRATOR,
                message="Analyzing request clarity..."
            ))
        else:
            state.add_log(AgentType.ORCHESTRATOR, "Analyzing request clarity...")
        
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
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            llm_logger.debug(f"📤 Calling LLM for ambiguity check...")
            result = await chain.ainvoke({"request": user_request})
            llm_logger.debug(f"📥 LLM response: {result}")
            
            clarity_score = result.get("clarity_score", 10)
            clarifying_questions = result.get("clarifying_questions", [])
            
            if isinstance(state, dict):
                state['clarity_score'] = clarity_score
                state['clarifying_questions'] = clarifying_questions
            else:
                state.clarity_score = clarity_score
                state.clarifying_questions = clarifying_questions
            
            if clarity_score < config.agent.clarity_threshold:
                logger.warning(f"Request needs clarification (score: {clarity_score}/10)")
                if isinstance(state, dict):
                    state['status'] = ExecutionStatus.WAITING_CLARIFICATION
                else:
                    state.status = ExecutionStatus.WAITING_CLARIFICATION
            else:
                logger.info(f"Request is clear (score: {clarity_score}/10)")
            
            await self.emit_event("ambiguity_check_completed", state, {
                "clarity_score": clarity_score,
                "needs_clarification": clarity_score < config.agent.clarity_threshold
            })
            
        except Exception as e:
            logger.error(f"Ambiguity check failed: {str(e)}")
            # Assume clear if check fails
            if isinstance(state, dict):
                state['clarity_score'] = 10
            else:
                state.clarity_score = 10
        
        return state
    
    async def create_plan(self, state: AgentState) -> AgentState:
        """
        Decompose the user request into a sequence of executable steps.
        Each step is assigned to a specific agent type.
        """
        # Handle dict state
        if isinstance(state, dict):
            state['status'] = ExecutionStatus.PLANNING
            state['logs'] = state.get('logs', [])
            state['logs'].append({
                "timestamp": datetime.now().isoformat(),
                "agent_type": "orchestrator",
                "message": "Creating execution plan...",
                "level": "info",
                "data": {}
            })
            user_request = state.get('user_request', '')
            user_clarifications = state.get('user_clarifications', [])
        else:
            state.status = ExecutionStatus.PLANNING
            state.add_log(AgentType.ORCHESTRATOR, "Creating execution plan...")
            user_request = state.user_request
            user_clarifications = state.user_clarifications
            
        await self.emit_event("planning_started", state)
        
        # Include any clarifications in the context
        context = user_request
        if user_clarifications:
            context += "\n\nUser clarifications:\n" + "\n".join(
                f"- {c}" for c in user_clarifications
            )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a task planner for a multi-agent AI system. Your job is to decompose a business request into atomic, executable steps.

Available agents:
- researcher: Web searches, data retrieval from external sources
- coder: Python code execution, calculations, data processing
- analyst: Data analysis, chart generation, statistical analysis
- writer: Text summarization, formatting, report generation

Rules:
1. Each step should be atomic and executable by a single agent
2. Order steps logically - data gathering before analysis, analysis before summarization
3. Specify clear dependencies between steps
4. Be specific about what each step should produce

Respond in JSON format:
{{
    "plan": [
        {{
            "id": "<unique short id>",
            "description": "<clear description of what to do>",
            "agent_type": "<researcher|coder|analyst|writer>",
            "dependencies": [<list of step IDs this depends on>]
        }}
    ],
    "reasoning": "<brief explanation of the plan>"
}}"""),
            ("user", "Create a plan for this request: {context}")
        ])
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            result = await chain.ainvoke({"context": context})
            
            # Convert to PlanStep objects (or dicts)
            new_plan = []
            for step_data in result.get("plan", []):
                # Ensure agent_type is valid
                a_type = step_data.get("agent_type", "researcher")
                try:
                    AgentType(a_type)
                except ValueError:
                    a_type = "researcher"
                
                step = PlanStep(
                    id=step_data.get("id", f"step_{len(new_plan)+1}"),
                    description=step_data.get("description", ""),
                    agent_type=AgentType(a_type),
                    dependencies=step_data.get("dependencies", [])
                )
                
                if isinstance(state, dict):
                    new_plan.append(step.model_dump())
                else:
                    new_plan.append(step)
            
            if isinstance(state, dict):
                state['plan'] = new_plan
                state['current_step_index'] = 0
                state['logs'].append({
                    "timestamp": datetime.now().isoformat(),
                    "agent_type": "orchestrator",
                    "message": f"Created plan with {len(new_plan)} steps",
                    "level": "info",
                    "data": {}
                })
            else:
                state.plan = new_plan
                state.current_step_index = 0
                state.add_log(
                    AgentType.ORCHESTRATOR,
                    f"Created plan with {len(new_plan)} steps"
                )
            
            await self.emit_event("planning_completed", state, {
                "plan_size": len(new_plan),
                "reasoning": result.get("reasoning", "")
            })
            
        except Exception as e:
            error_msg = f"Planning failed: {str(e)}"
            if isinstance(state, dict):
                state['status'] = ExecutionStatus.ERROR
                state['error_message'] = error_msg
                state['logs'].append({
                    "timestamp": datetime.now().isoformat(),
                    "agent_type": "orchestrator",
                    "message": error_msg,
                    "level": "error",
                    "data": {}
                })
            else:
                state.status = ExecutionStatus.ERROR
                state.error_message = error_msg
                state.add_log(
                    AgentType.ORCHESTRATOR,
                    state.error_message,
                    level="error"
                )
        
        return state
    
    async def route_to_agent(self, state: AgentState) -> tuple[AgentType | None, PlanStep | None]:
        """
        Determine which agent should handle the next step.
        Returns the agent type and step, or (None, None) if all done.
        """
        # Handle dict state
        if isinstance(state, dict):
            plan = state.get('plan', [])
        else:
            plan = state.plan
            
        # Find first pending step with all dependencies satisfied
        completed_ids = set()
        for step in plan:
            if isinstance(step, dict):
                status = step.get('status', 'pending')
                if hasattr(status, 'value'): status = status.value
            else:
                status = step.status.value if hasattr(step.status, 'value') else str(step.status)
                
            if str(status) == "completed":
                if isinstance(step, dict):
                    completed_ids.add(step.get('id'))
                else:
                    completed_ids.add(step.id)
        
        for step in plan:
            if isinstance(step, dict):
                status = step.get('status', 'pending')
                if hasattr(status, 'value'): status = status.value
            else:
                status = step.status.value if hasattr(step.status, 'value') else str(step.status)
                
            if str(status) in ["pending", "retrying"]:
                # Check if all dependencies are satisfied
                if isinstance(step, dict):
                    dependencies = step.get('dependencies', [])
                else:
                    dependencies = step.dependencies
                    
                deps_satisfied = all(dep in completed_ids for dep in dependencies)
                
                if deps_satisfied:
                    # Update status to in_progress
                    if isinstance(step, dict):
                        step['status'] = StepStatus.IN_PROGRESS.value
                        agent_type_str = step.get('agent_type', 'researcher')
                        if hasattr(agent_type_str, 'value'): agent_type_str = agent_type_str.value
                        try:
                            agent_type = AgentType(agent_type_str)
                        except:
                            agent_type = AgentType.RESEARCHER
                        
                        # Convert dict step to PlanStep object for return
                        step_obj = PlanStep(**step)
                        return agent_type, step_obj
                    else:
                        step.status = StepStatus.IN_PROGRESS
                        return step.agent_type, step
        
        return None, None
    
    async def handle_step_result(
        self, 
        state: AgentState, 
        step_id: str, 
        success: bool, 
        result: Any = None,
        error: str = None
    ) -> AgentState:
        """Process the result of an agent's step execution."""
        if isinstance(state, dict):
            plan = state.get('plan', [])
        else:
            plan = state.plan
            
        step = None
        for s in plan:
            if isinstance(s, dict):
                if s.get('id') == step_id:
                    step = s
                    break
            elif s.id == step_id:
                step = s
                break
                
        if not step:
            return state
        
        if success:
            if isinstance(step, dict):
                step['status'] = StepStatus.COMPLETED.value
                step['result'] = result
                step['completed_at'] = datetime.now().isoformat()
            else:
                step.status = StepStatus.COMPLETED
                step.result = result
                step.completed_at = datetime.now()
                
            if isinstance(state, dict):
                state['logs'] = state.get('logs', [])
                state['logs'].append({
                    "timestamp": datetime.now().isoformat(),
                    "agent_type": "orchestrator",
                    "message": f"Step '{step_id}' completed successfully",
                    "level": "info",
                    "data": {}
                })
            else:
                state.add_log(
                    AgentType.ORCHESTRATOR,
                    f"Step '{step_id}' completed successfully"
                )
            await self.emit_event("step_completed", state, {"step_id": step_id})
        else:
            if isinstance(step, dict):
                retry_count = step.get('retry_count', 0) + 1
                step['retry_count'] = retry_count
                
                if retry_count < config.agent.max_retries:
                    step['status'] = StepStatus.RETRYING.value
                    step['error'] = error
                    level = "warning"
                    msg = f"Step '{step_id}' failed, retrying ({retry_count}/{config.agent.max_retries})"
                    event_type = "step_retrying"
                else:
                    step['status'] = StepStatus.FAILED.value
                    step['error'] = error
                    level = "error"
                    msg = f"Step '{step_id}' failed after {retry_count} retries"
                    event_type = "step_failed"
            else:
                step.retry_count += 1
                retry_count = step.retry_count
                
                if step.retry_count < config.agent.max_retries:
                    step.status = StepStatus.RETRYING
                    step.error = error
                    level = "warning"
                    msg = f"Step '{step_id}' failed, retrying ({step.retry_count}/{config.agent.max_retries})"
                    event_type = "step_retrying"
                else:
                    step.status = StepStatus.FAILED
                    step.error = error
                    level = "error"
                    msg = f"Step '{step_id}' failed after {step.retry_count} retries"
                    event_type = "step_failed"
            
            if isinstance(state, dict):
                state['logs'] = state.get('logs', [])
                state['logs'].append({
                    "timestamp": datetime.now().isoformat(),
                    "agent_type": "orchestrator",
                    "message": msg,
                    "level": level,
                    "data": {}
                })
            else:
                state.add_log(
                    AgentType.ORCHESTRATOR,
                    msg,
                    level=level
                )
            
            await self.emit_event(event_type, state, {
                "step_id": step_id,
                "error": error,
                "retry_count": retry_count
            })
        
        return state
    
    async def aggregate_results(self, state: AgentState) -> AgentState:
        """
        Synthesize all artifacts into a final natural language response.
        """
        if isinstance(state, dict):
            state['logs'] = state.get('logs', [])
            state['logs'].append({
                "timestamp": datetime.now().isoformat(),
                "agent_type": "orchestrator",
                "message": "Aggregating results...",
                "level": "info",
                "data": {}
            })
            artifacts = state.get('artifacts', {})
            plan = state.get('plan', [])
            user_request = state.get('user_request', '')
        else:
            state.add_log(AgentType.ORCHESTRATOR, "Aggregating results...")
            artifacts = state.artifacts
            plan = state.plan
            user_request = state.user_request
            
        await self.emit_event("aggregation_started", state)
        
        # Collect all artifacts
        artifacts_summary = []
        for artifact_id, artifact in artifacts.items():
            if isinstance(artifact, dict):
                a_type = artifact.get('type')
                a_name = artifact.get('name')
                a_content = artifact.get('content')
            else:
                a_type = artifact.type
                a_name = artifact.name
                a_content = artifact.content
                
            if a_type == "image":
                artifacts_summary.append(f"- {a_name}: [Image generated]")
            elif a_type == "chart":
                title = a_content.get('title', 'Untitled') if isinstance(a_content, dict) else 'Untitled'
                artifacts_summary.append(f"- {a_name}: [Chart: {title}]")
            else:
                content_preview = str(a_content)[:200]
                artifacts_summary.append(f"- {a_name}: {content_preview}")
        
        # Collect step results
        step_results = []
        for step in plan:
            if isinstance(step, dict):
                s_result = step.get('result')
                s_id = step.get('id')
                s_type = step.get('agent_type')
            else:
                s_result = step.result
                s_id = step.id
                s_type = step.agent_type
                
            if s_result:
                result_preview = str(s_result)[:300]
                step_results.append(f"Step '{s_id}' ({s_type}): {result_preview}")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a results aggregator. Your job is to synthesize the outputs from multiple AI agents into a coherent, user-friendly response.

Create a clear, well-structured response that:
1. Directly answers the user's original request (including ALL specific constraints, text inclusions, or formatting requests).
2. Summarizes key findings
3. References any charts or visualizations created
4. Highlights important insights

IMPORTANT: If the user request asks to include specific text, phrases, or formats, you MUST include them exactly as requested.

Be concise but comprehensive. Use markdown formatting for readability."""),
            ("user", """Original request: {request}

Step results:
{step_results}

Artifacts created:
{artifacts}

Synthesize these into a final response for the user.""")
        ])
        
        chain = prompt | self.llm
        
        try:
            result = await chain.ainvoke({
                "request": user_request,
                "step_results": "\n".join(step_results) or "No step results available",
                "artifacts": "\n".join(artifacts_summary) or "No artifacts created"
            })
            
            if isinstance(state, dict):
                state['final_response'] = result.content
                state['status'] = ExecutionStatus.COMPLETED
                state['logs'].append({
                    "timestamp": datetime.now().isoformat(),
                    "agent_type": "orchestrator",
                    "message": "Results aggregated successfully",
                    "level": "info",
                    "data": {}
                })
            else:
                state.final_response = result.content
                state.status = ExecutionStatus.COMPLETED
                state.add_log(AgentType.ORCHESTRATOR, "Results aggregated successfully")
                
            await self.emit_event("execution_completed", state)
            
        except Exception as e:
            error_msg = f"Aggregation failed: {str(e)}"
            if isinstance(state, dict):
                state['status'] = ExecutionStatus.ERROR
                state['error_message'] = error_msg
                state['logs'].append({
                    "timestamp": datetime.now().isoformat(),
                    "agent_type": "orchestrator",
                    "message": error_msg,
                    "level": "error",
                    "data": {}
                })
            else:
                state.status = ExecutionStatus.ERROR
                state.error_message = error_msg
                state.add_log(
                    AgentType.ORCHESTRATOR,
                    state.error_message,
                    level="error"
                )
        
        return state
