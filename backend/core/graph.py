"""
LangGraph Workflow Definition
Defines the state graph for multi-agent orchestration.
"""

from typing import Literal
from langgraph.graph import StateGraph, END


from langchain_core.output_parsers import JsonOutputParser
from core.state import AgentState, ExecutionStatus, AgentType, StepStatus
from core.orchestrator import Orchestrator
from agents.researcher import ResearcherAgent
from agents.coder import CoderAgent
from agents.analyst import AnalystAgent
from agents.writer import WriterAgent
from agents.writer import WriterAgent
from config import config
from core.logging import get_logger

logger = get_logger('WORKFLOW')


# Helper functions for dict-safe state access
def get_state_attr(state, attr, default=None):
    """Get attribute from state, handling both dict and object."""
    if isinstance(state, dict):
        return state.get(attr, default)
    return getattr(state, attr, default)

def set_state_attr(state, attr, value):
    """Set attribute on state, handling both dict and object."""
    if isinstance(state, dict):
        state[attr] = value
    else:
        setattr(state, attr, value)

def get_status_value(status):
    """Get string value from status, handling both enum and string."""
    if hasattr(status, 'value'):
        return status.value
    return str(status)


class WorkflowManager:
    """
    Manages the LangGraph workflow for multi-agent orchestration.
    """
    
    def __init__(self, event_callback=None):
        """
        Initialize the workflow manager.
        
        Args:
            event_callback: Async function to emit real-time events
        """
        self.event_callback = event_callback
        self.orchestrator = Orchestrator(event_callback)
        
        # Initialize agents
        self.agents = {
            AgentType.RESEARCHER: ResearcherAgent(event_callback),
            AgentType.CODER: CoderAgent(event_callback),
            AgentType.ANALYST: AnalystAgent(event_callback),
            AgentType.WRITER: WriterAgent(event_callback),
        }
        
        # Load custom agents
        self._load_custom_agents()
    
    def _load_custom_agents(self):
        """Load custom agents from storage."""
        import json
        import os
        from agents.generic import GenericAgent
        
        try:
            if os.path.exists("custom_agents.json"):
                with open("custom_agents.json", "r") as f:
                    custom_agents = json.load(f)
                    for agent_data in custom_agents:
                        name = agent_data.get("name")
                        prompt = agent_data.get("system_prompt")
                        if name and prompt:
                            # Register the new agent
                            self.agents[name] = GenericAgent(name, prompt, self.event_callback)
                            logger.info(f"Registered custom agent: {name}")
        except Exception as e:
            logger.error(f"Failed to load custom agents: {e}")

    def register_custom_agent(self, name: str, system_prompt: str):
        """Register a new custom agent and save to storage."""
        import json
        import os
        from agents.generic import GenericAgent
        
        # 1. Edge Case: Prevent overwriting built-in agents
        reserved_names = {a.value if hasattr(a, 'value') else str(a) for a in AgentType}
        if name.lower() in reserved_names:
            logger.warning(f"Attempted to overwrite reserved agent: {name}")
            return False, f"Cannot overwrite built-in agent '{name}'"

        # Create and register
        self.agents[name] = GenericAgent(name, system_prompt, self.event_callback)
        
        # Persist
        try:
            agents_list = []
            if os.path.exists("custom_agents.json"):
                with open("custom_agents.json", "r") as f:
                    agents_list = json.load(f)
            
            # Update or add
            existing = next((a for a in agents_list if a["name"] == name), None)
            if existing:
                existing["system_prompt"] = system_prompt
            else:
                agents_list.append({"name": name, "system_prompt": system_prompt})
                
            with open("custom_agents.json", "w") as f:
                json.dump(agents_list, f, indent=2)
                
            logger.info(f"Persisted custom agent: {name}")
            return True, "Agent registered successfully"
        except Exception as e:
            logger.error(f"Failed to persist custom agent: {e}")
            return False, str(e)

    def unregister_custom_agent(self, name: str):
        """Unregister a custom agent and remove from storage."""
        import json
        import os
        
        # 1. Prevent deleting built-in agents
        reserved_names = {a.value if hasattr(a, 'value') else str(a) for a in AgentType}
        if name.lower() in reserved_names:
            logger.warning(f"Attempted to delete reserved agent: {name}")
            return False, f"Cannot delete built-in agent '{name}'"

        # Remove from memory
        if name in self.agents:
            del self.agents[name]
        
        # Remove from storage
        try:
            if os.path.exists("custom_agents.json"):
                with open("custom_agents.json", "r") as f:
                    agents_list = json.load(f)
                
                initial_len = len(agents_list)
                agents_list = [a for a in agents_list if a["name"] != name]
                
                if len(agents_list) < initial_len:
                    with open("custom_agents.json", "w") as f:
                        json.dump(agents_list, f, indent=2)
                    logger.info(f"Deleted custom agent: {name}")
                    return True, "Agent deleted successfully"
                else:
                    return False, "Agent not found in storage"
            return False, "Storage file not found"
        except Exception as e:
            logger.error(f"Failed to delete custom agent: {e}")
            return False, str(e)

    async def update_plan(self, session_id: str, new_plan: list[dict]) -> None:
        """
        Update the plan mid-execution with intelligent partial re-execution.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"📝 [UPDATE_PLAN] Starting plan update for session {session_id[:8]}...")
        
        # 2. Edge Case: Clean up orphaned dependencies
        # If a step was deleted, any other step depending on it will hang.
        # We must remove invalid IDs from dependencies.
        valid_ids = set()
        for step in new_plan:
             if isinstance(step, dict): valid_ids.add(step.get('id'))
             else: valid_ids.add(step.id)
             
        for step in new_plan:
            deps = step.get('dependencies', []) if isinstance(step, dict) else step.dependencies
            # Filter out IDs that are no longer in the plan
            clean_deps = [d for d in deps if d in valid_ids]
            
            if len(clean_deps) != len(deps):
                logger.warning(f"📝 [UPDATE_PLAN] cleaned orphaned dependencies for step. Removed: {set(deps) - set(clean_deps)}")
                
            if isinstance(step, dict):
                step['dependencies'] = clean_deps
            else:
                step.dependencies = clean_deps

        config_dict = {"configurable": {"thread_id": session_id}}
        current_state = await self.graph.aget_state(config_dict)
        if current_state is None:
            logger.error(f"📝 [UPDATE_PLAN] No session found: {session_id}")
            raise ValueError(f"No session found: {session_id}")
        
        state = current_state.values
        # ... rest of the function ...
        
        # Resources to be initialized async
        self.conn = None
        self.memory = None
        self.graph = None
        
    async def initialize(self):
        """Initialize async resources (database connection)."""
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        
        # Connect to SQLite database for persistence
        self.conn = await aiosqlite.connect("checkpoints.db")
        self.memory = AsyncSqliteSaver(self.conn)
        
        # Ensure tables exist
        await self.memory.setup()
        
        # Build the graph
        self.graph = self._build_graph()
        
    async def cleanup(self):
        """Cleanup async resources."""
        if self.conn:
            await self.conn.close()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph."""
        
        # Define the graph with AgentState as the state type
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("check_ambiguity", self._check_ambiguity_node)
        graph.add_node("create_plan", self._create_plan_node)
        graph.add_node("execute_step", self._execute_step_node)
        graph.add_node("aggregate_results", self._aggregate_results_node)
        graph.add_node("request_clarification", self._request_clarification_node)
        graph.add_node("request_approval", self._request_approval_node)
        
        graph.add_node("apply_pending_refinement", self._apply_pending_refinement_node)
        
        # Set entry point
        graph.set_entry_point("check_ambiguity")
        
        # Add conditional edges from ambiguity check
        graph.add_conditional_edges(
            "check_ambiguity",
            self._route_after_ambiguity,
            {
                "needs_clarification": "request_clarification",
                "proceed": "create_plan"
            }
        )
        
        # Edge from clarification back to start (will be handled externally)
        graph.add_edge("request_clarification", END)
        
        # Conditional edges from planning
        graph.add_conditional_edges(
            "create_plan",
            self._route_after_planning,
            {
                "needs_approval": "request_approval",
                "execute": "execute_step",
                "error": END
            }
        )
        
        # Approval goes to execution or end
        graph.add_edge("request_approval", END)
        
        # Conditional edges from execution
        graph.add_conditional_edges(
            "execute_step",
            self._route_after_execution,
            {
                "continue": "execute_step",
                "aggregate": "aggregate_results",
                "error": END,
                "end": END  # Pause for step clarification
            }
        )
        
        # Check for pending refinements after aggregation
        graph.add_conditional_edges(
            "aggregate_results",
            self._route_after_aggregation,
            {
                "refine": "apply_pending_refinement",
                "end": END
            }
        )
        
        # Refinement loop
        graph.add_edge("apply_pending_refinement", "create_plan")
        
        return graph.compile(checkpointer=self.memory)
    
    async def _check_ambiguity_node(self, state: AgentState) -> dict:
        """Node: Check if request needs clarification."""
        state = await self.orchestrator.check_ambiguity(state)
        return state.model_dump(exclude={'conversation_history'})
    
    async def _create_plan_node(self, state: AgentState) -> dict:
        """Node: Create execution plan."""
        state = await self.orchestrator.create_plan(state)
        return state.model_dump(exclude={'conversation_history'})
    
    async def _execute_step_node(self, state: AgentState) -> AgentState:
        """Node: Execute the current step using appropriate agent."""
        agent_type, step = await self.orchestrator.route_to_agent(state)
        
        if agent_type is None or step is None:
            # No more steps to execute
            return state
        
        agent = self.agents.get(agent_type)
        if not agent:
            state = await self.orchestrator.handle_step_result(
                state, step.id, False, error=f"Unknown agent type: {agent_type}"
            )
            return state
        
        # Execute the step
        success, result, error = await agent.execute_with_retry(
            state, step.id, step.description
        )
        
        # Check if agent is requesting step-level clarification
        if isinstance(result, dict) and result.get("needs_clarification"):
            questions = result.get("questions", [])
            logger.info(f"❓ Step '{step.id}' needs clarification: {questions}")
            
            # Set step clarification state
            if isinstance(state, dict):
                state['status'] = ExecutionStatus.WAITING_STEP_CLARIFICATION.value
                state['step_clarification_step_id'] = step.id
                state['step_clarification_questions'] = questions
                # Reset step status to pending so it can be re-executed
                for s in state.get('plan', []):
                    if s.get('id') == step.id:
                        s['status'] = 'pending'
                        break
            else:
                state.status = ExecutionStatus.WAITING_STEP_CLARIFICATION
                state.step_clarification_step_id = step.id
                state.step_clarification_questions = questions
                # Reset step status
                for s in state.plan:
                    if s.id == step.id:
                        s.status = StepStatus.PENDING
                        break
            
            # Emit event for frontend
            if self.event_callback:
                await self.event_callback({
                    "type": "step_clarification_needed",
                    "session_id": state.session_id if hasattr(state, 'session_id') else state.get('session_id'),
                    "step_id": step.id,
                    "agent_type": agent_type,
                    "questions": questions
                })
            
            return state.model_dump(exclude={'conversation_history'}) if hasattr(state, 'model_dump') else state
        
        # Update state with result
        state = await self.orchestrator.handle_step_result(
            state, step.id, success, result, error
        )
        
        # Return dict, excluding conversation_history to avoid overwriting concurrent chat updates
        return state.model_dump(exclude={'conversation_history'})
    
    async def _aggregate_results_node(self, state: AgentState) -> dict:
        """Node: Aggregate all results into final response."""
        state = await self.orchestrator.aggregate_results(state)
        return state.model_dump(exclude={'conversation_history'})
    
    async def _request_clarification_node(self, state: AgentState) -> AgentState:
        """Node: Request clarification from user."""
        set_state_attr(state, 'status', ExecutionStatus.WAITING_CLARIFICATION)
        if self.event_callback:
            # Handle dict state for to_event
            if isinstance(state, dict):
                from core.state import AgentLog
                event = {
                    "type": "clarification_needed",
                    "session_id": state.get('session_id', ''),
                    "status": get_status_value(state.get('status', '')),
                    "current_step": state.get('current_step_index', 0),
                    "total_steps": len(state.get('plan', [])),
                    "plan": [],
                    "latest_log": None,
                }
                event["questions"] = state.get('clarifying_questions', [])
            else:
                event = state.to_event("clarification_needed")
                event["questions"] = state.clarifying_questions
            await self.event_callback(event)
        return state
    
    async def _request_approval_node(self, state: AgentState) -> AgentState:
        """Node: Request plan approval from user (stretch goal)."""
        # Hardcode to false for now as per user request to remove approval feature
        set_state_attr(state, 'status', ExecutionStatus.WAITING_APPROVAL)
        set_state_attr(state, 'requires_approval', False)
        if self.event_callback:
            plan = get_state_attr(state, 'plan', [])
            plan_data = []
            for s in plan:
                if hasattr(s, 'model_dump'):
                    plan_data.append(s.model_dump())
                elif isinstance(s, dict):
                    plan_data.append(s)
            
            if isinstance(state, dict):
                event = {
                    "type": "approval_needed",
                    "session_id": state.get('session_id', ''),
                    "status": get_status_value(state.get('status', '')),
                    "current_step": state.get('current_step_index', 0),
                    "total_steps": len(plan),
                    "plan": plan_data,
                }
            else:
                event = state.to_event("approval_needed")
                event["plan"] = plan_data
            await self.event_callback(event)
        return state
    
    def _route_after_ambiguity(self, state: AgentState) -> str:
        """Determine next step after ambiguity check."""
        clarity_score = get_state_attr(state, 'clarity_score', 10)
        if clarity_score < config.agent.clarity_threshold:
            return "needs_clarification"
        return "proceed"
    
    def _route_after_planning(self, state: AgentState) -> str:
        """Determine next step after planning."""
        status = get_state_attr(state, 'status', '')
        status_val = get_status_value(status)
        
        if status == ExecutionStatus.ERROR or status_val == 'error':
            return "error"
        if get_state_attr(state, 'requires_approval', False):
            return "needs_approval"
        if get_state_attr(state, 'plan', []):
            set_state_attr(state, 'status', ExecutionStatus.EXECUTING)
            return "execute"
        return "error"
    
    def _route_after_execution(self, state: AgentState) -> str:
        """Determine next step after executing a step."""
        status = get_state_attr(state, 'status', '')
        status_val = get_status_value(status)
        
        # Check for step clarification (pause workflow)
        if status == ExecutionStatus.WAITING_STEP_CLARIFICATION or status_val == 'waiting_step_clarification':
            return "end"  # Pause workflow until clarification provided
        
        if status == ExecutionStatus.ERROR or status_val == 'error':
            return "error"
        
        # Check if all steps are completed
        plan = get_state_attr(state, 'plan', [])
        all_completed = True
        has_pending = False
        
        for s in plan:
            if isinstance(s, dict):
                s_status = get_status_value(s.get('status', ''))
            else:
                s_status = get_status_value(s.status)
            
            if s_status != 'completed':
                all_completed = False
            if s_status in ['pending', 'retrying']:
                has_pending = True
        
        if all_completed and plan:
            return "aggregate"
        
        # Check if there are any EXECUTABLE steps (pending/retrying AND deps satisfied)
        has_executable = False
        
        # Get set of completed steps for quick lookup
        completed_ids = set()
        for s in plan:
            s_id = s.get('id') if isinstance(s, dict) else s.id
            if isinstance(s, dict):
                s_status = get_status_value(s.get('status', ''))
            else:
                s_status = get_status_value(s.status)
            
            if s_status == 'completed':
                completed_ids.add(s_id)
        
        # Check each pending step for executable status
        for s in plan:
            if isinstance(s, dict):
                s_status = get_status_value(s.get('status', ''))
                deps = s.get('dependencies', [])
            else:
                s_status = get_status_value(s.status)
                deps = s.dependencies
            
            if s_status in ['pending', 'retrying']:
                # Are dependencies met?
                deps_met = all(d in completed_ids for d in deps)
                if deps_met:
                    has_executable = True
                    break
        
        if has_executable:
            return "continue"
        
        # All pending steps are blocked or no pending steps
        return "aggregate"
        
    def _route_after_aggregation(self, state: AgentState) -> str:
        """Determine next step after aggregation."""
        pending = get_state_attr(state, 'pending_refinement')
        if pending:
             return "refine"
        return "end"
        
    async def _apply_pending_refinement_node(self, state: AgentState) -> dict:
        """Node: Apply pending refinement to the user request."""
        pending = get_state_attr(state, 'pending_refinement', '')
        user_request = get_state_attr(state, 'user_request', '')
        
        # Build refined request similar to refine_execution logic
        refined_request = f"""CONTINUOUS REFINEMENT REQUEST
        
Previous Request: {user_request}

Pending Refinements (Queued):
{pending}

Please update the plan to address these pending requests."""

        # Return update
        return {
            "user_request": refined_request,
            "pending_refinement": None,
            "status": ExecutionStatus.PLANNING.value,
            "plan": [],
            "current_step_index": 0,
            "final_response": None
        }

    async def execute(self, user_request: str, session_id: str = None) -> AgentState:
        """
        Execute the workflow for a user request.
        
        Args:
            user_request: The user's business request
            session_id: Optional session ID for checkpointing
            
        Returns:
            Final AgentState after execution
        """
        from core.state import create_initial_state
        
        initial_state = create_initial_state(user_request)
        if session_id:
            initial_state.session_id = session_id
        
        config_dict = {"configurable": {"thread_id": initial_state.session_id}}
        
        # NUCLEAR OPTION: Explicitly clear any existing state for this session
        # This ensures conversation_history is reset even if session_id is reused.
        try:
            # Try standard LangGraph delete if available
            if hasattr(self.memory, 'adelete'):
                await self.memory.adelete(config_dict)
            else:
                # Manual SQLite cleanup since we have the connection
                # This handles cases where operator.add would otherwise preserve old history
                try:
                    await self.conn.execute(
                        "DELETE FROM checkpoints WHERE thread_id = ?", 
                        (initial_state.session_id,)
                    )
                    await self.conn.execute(
                        "DELETE FROM checkpoint_blobs WHERE thread_id = ?", 
                        (initial_state.session_id,)
                    )
                    await self.conn.commit()
                    logger.info(f"🧹 [EXECUTE] Cleared existing state for session {initial_state.session_id}")
                except Exception as db_e:
                    logger.warning(f"⚠️ [EXECUTE] Failed to clear DB state: {db_e}")
        except Exception as e:
            logger.warning(f"⚠️ [EXECUTE] Error clearing state: {e}")
        
        # Run the graph
        final_state = await self.graph.ainvoke(initial_state, config=config_dict)
        
        return final_state
    
    async def resume_after_clarification(
        self, 
        session_id: str, 
        clarifications: list[str]
    ) -> AgentState:
        """
        Resume workflow after user provides clarifications.
        
        Args:
            session_id: Session ID to resume
            clarifications: User's clarifying answers
            
        Returns:
            Final AgentState after execution
        """
        config_dict = {"configurable": {"thread_id": session_id}}
        
        # Get current state
        current_state = await self.graph.aget_state(config_dict)
        if current_state is None:
            raise ValueError(f"No session found with ID: {session_id}")
        
        state = current_state.values
        
        # Handle both dict and AgentState
        if isinstance(state, dict):
            state['user_clarifications'] = clarifications
            state['status'] = ExecutionStatus.PLANNING
            state['user_request'] = (
                f"{state.get('user_request', '')}\n\nClarifications:\n" +
                "\n".join(f"- {c}" for c in clarifications)
            )
        else:
            state.user_clarifications = clarifications
            state.status = ExecutionStatus.PLANNING
            state.user_request = (
                f"{state.user_request}\n\nClarifications:\n" +
                "\n".join(f"- {c}" for c in clarifications)
            )
        
        # Re-run from planning
        final_state = await self.graph.ainvoke(state, config=config_dict)
        
        return final_state
    
    async def resume_after_step_clarification(
        self, 
        session_id: str, 
        step_id: str,
        clarifications: list[str]
    ) -> AgentState:
        """
        Resume workflow after user provides clarification for a specific step.
        
        Args:
            session_id: Session ID to resume
            step_id: ID of the step that needed clarification
            clarifications: User's clarifying answers for this step
            
        Returns:
            Final AgentState after execution
        """
        config_dict = {"configurable": {"thread_id": session_id}}
        
        # Get current state
        current_state = await self.graph.aget_state(config_dict)
        if current_state is None:
            raise ValueError(f"No session found with ID: {session_id}")
        
        state = current_state.values
        
        # Store step-specific clarifications
        if isinstance(state, dict):
            if 'step_clarifications' not in state:
                state['step_clarifications'] = {}
            state['step_clarifications'][step_id] = clarifications
            state['status'] = ExecutionStatus.EXECUTING.value
            state['step_clarification_step_id'] = None
            state['step_clarification_questions'] = []
        else:
            if not state.step_clarifications:
                state.step_clarifications = {}
            state.step_clarifications[step_id] = clarifications
            state.status = ExecutionStatus.EXECUTING
            state.step_clarification_step_id = None
            state.step_clarification_questions = []
        
        logger.info(f"📝 Resuming step '{step_id}' with clarifications: {clarifications}")
        
        # Re-run from execute_step
        final_state = await self.graph.ainvoke(state, config=config_dict)
        
        return final_state
    
    async def resume_after_approval(
        self,
        session_id: str,
        approved: bool,
        modifications: str = None,
        new_plan: list[dict] = None
    ) -> AgentState:
        """
        Resume workflow after user approves/modifies plan.
        
        Args:
            session_id: Session ID to resume
            approved: Whether the plan is approved
            modifications: Optional modifications to the plan (for re-planning)
            new_plan: Optional manual override of the plan (for prompt editing)
            
        Returns:
            Final AgentState after execution
        """
        config_dict = {"configurable": {"thread_id": session_id}}
        
        current_state = await self.graph.aget_state(config_dict)
        if current_state is None:
            raise ValueError(f"No session found with ID: {session_id}")
        
        state = current_state.values
        
        # Handle both dict and AgentState
        if isinstance(state, dict):
            state['requires_approval'] = False
            
            if approved:
                if new_plan:
                    # Apply manual plan edits
                    # Ensure plan steps are properly formatted?
                    # LangGraph/Pydantic should handle validation if passed correctly
                    from core.state import PlanStep
                    steps = []
                    for p in new_plan:
                         # Handle if p is dict or obj
                         if isinstance(p, dict): steps.append(PlanStep(**p))
                         else: steps.append(p)
                    state['plan'] = [s.model_dump() for s in steps]
                
                state['status'] = ExecutionStatus.EXECUTING
                final_state = await self.graph.ainvoke(state, config=config_dict)
            else:
                if modifications:
                    state['user_request'] = f"{state.get('user_request', '')}\n\nModifications requested: {modifications}"
                state['status'] = ExecutionStatus.PLANNING
                state['plan'] = []
                final_state = await self.graph.ainvoke(state, config=config_dict)
        else:
            state.requires_approval = False
            
            if approved:
                if new_plan:
                    from core.state import PlanStep
                    steps = []
                    for p in new_plan:
                         if isinstance(p, dict): steps.append(PlanStep(**p))
                         else: steps.append(p)
                    state.plan = steps
                
                state.status = ExecutionStatus.EXECUTING
                final_state = await self.graph.ainvoke(state, config=config_dict)
            else:
                if modifications:
                    state.user_request = f"{state.user_request}\n\nModifications requested: {modifications}"
                state.status = ExecutionStatus.PLANNING
                state.plan = []
                final_state = await self.graph.ainvoke(state, config=config_dict)
        
        return final_state

    async def update_plan(self, session_id: str, new_plan: list[dict]) -> None:
        """
        Update the plan mid-execution with intelligent partial re-execution.
        
        - If a step hasn't run yet: just update the plan.
        - If a step has already run (completed/failed): reset it and all downstream steps,
          then re-execute from that point.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"📝 [UPDATE_PLAN] Starting plan update for session {session_id[:8]}...")
        logger.debug(f"📝 [UPDATE_PLAN] New plan has {len(new_plan)} steps")
        
        config_dict = {"configurable": {"thread_id": session_id}}
        current_state = await self.graph.aget_state(config_dict)
        if current_state is None:
            logger.error(f"📝 [UPDATE_PLAN] No session found: {session_id}")
            raise ValueError(f"No session found: {session_id}")
        
        state = current_state.values
        current_status = state.get('status') if isinstance(state, dict) else getattr(state, 'status', None)
        current_step_idx = state.get('current_step_index', 0) if isinstance(state, dict) else getattr(state, 'current_step_index', 0)
        logger.info(f"📝 [UPDATE_PLAN] Current state: status={current_status}, step_index={current_step_idx}")
        
        old_plan = state.get('plan', []) if isinstance(state, dict) else getattr(state, 'plan', [])
        logger.debug(f"📝 [UPDATE_PLAN] Old plan has {len(old_plan)} steps")
        
        # Create a map of old steps by ID
        old_plan_map = {}
        for step in old_plan:
            if isinstance(step, dict):
                old_plan_map[step.get('id')] = step
            else:
                old_plan_map[step.id] = step
        
        rerun_from_index = -1
        
        # Detect which steps have changed
        # We walk through both plans. The moment we see a divergence in ID, 
        # it means a step was inserted or deleted (or completely changed).
        # We must re-run from this index onwards.
        
        max_len = max(len(vars(s) if not isinstance(s, dict) else s) for s in [old_plan]) # Dummy usage to keep simpler
        max_idx = max(len(old_plan), len(new_plan))
        
        for i in range(max_idx):
            # If we've gone past the length of either plan, we have a structure change
            if i >= len(old_plan) or i >= len(new_plan):
                if rerun_from_index == -1 or i < rerun_from_index:
                    rerun_from_index = i
                    logger.info(f"📝 [UPDATE_PLAN] Structure change at index {i} (Length mismatch)")
                break
                
            old_step = old_plan[i]
            new_step = new_plan[i]
            
            # Normalize to dicts/objects
            old_id = old_step.get('id') if isinstance(old_step, dict) else old_step.id
            new_id = new_step.get('id') if isinstance(new_step, dict) else new_step.id
            
            # Structural check: IDs must match
            if old_id != new_id:
                if rerun_from_index == -1 or i < rerun_from_index:
                    rerun_from_index = i
                    logger.info(f"📝 [UPDATE_PLAN] Structure change at index {i}: ID {old_id} != {new_id}")
                break
            
            # Content check: If IDs match, check for description/agent changes
            old_desc = old_step.get('description', '') if isinstance(old_step, dict) else getattr(old_step, 'description', '')
            old_agent = old_step.get('agent_type', '') if isinstance(old_step, dict) else getattr(old_step, 'agent_type', '')
            old_status = old_step.get('status', 'pending') if isinstance(old_step, dict) else get_status_value(getattr(old_step, 'status', 'pending'))

            new_desc = new_step.get('description', '') if isinstance(new_step, dict) else new_step.description
            new_agent = new_step.get('agent_type', '') if isinstance(new_step, dict) else new_step.agent_type

            if old_desc != new_desc or old_agent != new_agent:
                logger.info(f"📝 [UPDATE_PLAN] Step {i} ({old_id}) changed content")
                if old_status in ['completed', 'failed']:
                    if rerun_from_index == -1 or i < rerun_from_index:
                        rerun_from_index = i
                        
        # Reset status for modified and downstream steps
        if rerun_from_index >= 0:
            logger.info(f"📝 [UPDATE_PLAN] Resetting steps {rerun_from_index} to {len(new_plan)-1}")
            for j in range(rerun_from_index, len(new_plan)):
                if isinstance(new_plan[j], dict):
                    new_plan[j]['status'] = 'pending'
                    new_plan[j]['result'] = None
                    new_plan[j]['error'] = None
                else:
                    new_plan[j].status = 'pending'
                    new_plan[j].result = None
                    new_plan[j].error = None
            
            # Log the re-execution trigger
            if self.event_callback:
                await self.event_callback({
                    "type": "log",
                    "session_id": session_id,
                    "agent_type": "orchestrator",
                    "message": f"Re-executing from step {rerun_from_index + 1} due to plan edit.",
                    "level": "info"
                })
            
            # Update state with new plan and step index
            logger.info(f"📝 [UPDATE_PLAN] Updating state: current_step_index={rerun_from_index}, status=EXECUTING")
            await self.graph.aupdate_state(config_dict, {
                "plan": new_plan,
                "current_step_index": rerun_from_index,
                "status": ExecutionStatus.EXECUTING
            })

            # Emit plan update event immediately so frontend reflects changes
            if self.event_callback:
                try:
                    # Fetch latest state to be sure
                    latest = await self.graph.aget_state(config_dict)
                    if latest and latest.values:
                        val = latest.values
                        # Handle dict vs object
                        if isinstance(val, dict):
                            from core.state import AgentState
                            st = AgentState(**val)
                        else:
                            st = val
                        await self.event_callback(st.to_event("plan_updated"))
                except Exception as e:
                     logger.error(f"Failed to emit plan_updated event: {e}")
            
            # Directly execute the edited step and downstream steps (bypass orchestrator)
            import asyncio
            async def _execute_steps_directly():
                logger.info(f"📝 [UPDATE_PLAN] Direct step execution starting...")
                try:
                    # Get the updated state
                    current_state = await self.graph.aget_state(config_dict)
                    if not current_state:
                         logger.error("📝 [UPDATE_PLAN] Failed to get state for execution")
                         return

                    state = current_state.values
                    
                    # Convert state to AgentState if needed
                    if isinstance(state, dict):
                        from core.state import AgentState
                        # Handle potential extra fields by filtering or using construct
                        # Best effort: use model_validate with strict=False or just **state if we trust it
                        try:
                            state = AgentState(**state)
                        except Exception as e:
                            logger.warning(f"📝 [UPDATE_PLAN] State conversion warning: {e}. Trying to filter fields.")
                            valid_keys = AgentState.model_fields.keys()
                            filtered_state = {k: v for k, v in state.items() if k in valid_keys}
                            state = AgentState(**filtered_state)
                    
                    # Execute steps from rerun_from_index onwards
                    plan = state.plan
                    for step_idx in range(rerun_from_index, len(plan)):
                        step = plan[step_idx]
                        step_id = step.id if hasattr(step, 'id') else step.get('id')
                        agent_type = step.agent_type if hasattr(step, 'agent_type') else step.get('agent_type')
                        description = step.description if hasattr(step, 'description') else step.get('description')
                        
                        logger.info(f"📝 [UPDATE_PLAN] Executing step {step_idx + 1}: {step_id} ({agent_type})")
                        
                        # Get the agent
                        agent = self.agents.get(agent_type)
                        if not agent:
                            logger.error(f"📝 [UPDATE_PLAN] Unknown agent type: {agent_type}")
                            state = await self.orchestrator.handle_step_result(
                                state, step_id, False, error=f"Unknown agent type: {agent_type}"
                            )
                            continue
                        
                        # Execute the step
                        success, result, error = await agent.execute_with_retry(
                            state, step_id, description
                        )
                        
                        # Update state with result
                        state = await self.orchestrator.handle_step_result(
                            state, step_id, success, result, error
                        )
                        
                        # Update graph state after each step
                        await self.graph.aupdate_state(config_dict, state.model_dump())
                        
                        # Send step completed event
                        if self.event_callback:
                            await self.event_callback(state.to_event("step_completed"))
                        
                        if not success:
                            logger.error(f"📝 [UPDATE_PLAN] Step {step_id} failed: {error}")
                            break
                    
                    # Aggregate results and complete
                    logger.info(f"📝 [UPDATE_PLAN] All steps completed, aggregating results...")
                    state = await self.orchestrator.aggregate_results(state)
                    state.status = ExecutionStatus.COMPLETED
                    
                    # Save final state
                    await self.graph.aupdate_state(config_dict, state.model_dump())
                    
                    # Send completion event
                    if self.event_callback:
                        await self.event_callback(state.to_event("execution_completed"))
                    
                    logger.info(f"📝 [UPDATE_PLAN] Direct step execution completed successfully")
                    
                except Exception as e:
                    logger.error(f"📝 [UPDATE_PLAN] Direct step execution failed: {str(e)}")
                    import traceback
                    logger.error(f"📝 [UPDATE_PLAN] Traceback: {traceback.format_exc()}")
                    if self.event_callback:
                        await self.event_callback({
                            "type": "error",
                            "session_id": session_id,
                            "message": f"Re-execution failed: {str(e)}"
                        })
            
            asyncio.create_task(_execute_steps_directly())
            logger.info(f"📝 [UPDATE_PLAN] Background task created, returning from update_plan")
        else:
            # Just update the plan, no re-run needed (pending steps updated in place)
            logger.info(f"📝 [UPDATE_PLAN] No completed steps changed, just updating plan in place")
            await self.graph.aupdate_state(config_dict, {"plan": new_plan})
            logger.info(f"📝 [UPDATE_PLAN] Plan updated successfully (no re-run needed)")
    
    # ============================================================
    # STRETCH GOALS: Live Conversation & Multi-turn Refinement
    # ============================================================
    
    async def handle_chat_message(
        self,
        session_id: str,
        message: str,
        state: 'AgentState'
    ) -> str:
        """
        Handle a live chat message during execution.
        
        This allows users to interact with the orchestrator mid-execution,
        providing additional context, asking questions, or requesting changes.
        
        Args:
            session_id: Session ID
            message: User's chat message
            state: Current agent state
            
        Returns:
            Response message from the orchestrator
        """
        logger.info(f"💬 [CHAT] Handling message for session {session_id}: {message[:50]}...")
        from core.llm import get_llm
        from langchain_core.prompts import ChatPromptTemplate
        
        llm = get_llm()
        
        # Build context from current state
        user_request = get_state_attr(state, 'user_request', '')
        status = get_state_attr(state, 'status', '')
        status_val = get_status_value(status)
        plan = get_state_attr(state, 'plan', [])
        current_step = get_state_attr(state, 'current_step_index', 0)
        logs = get_state_attr(state, 'logs', [])
        artifacts = get_state_attr(state, 'artifacts', {})
        
        context_parts = [
            f"Original request: {user_request}",
            f"Current status: {status_val}",
            f"Plan: {len(plan)} steps, currently on step {current_step + 1}",
        ]
        
        # Add recent logs
        if logs:
            recent_logs = logs[-5:]
            context_parts.append("Recent activity:")
            for log in recent_logs:
                if isinstance(log, dict):
                    msg = log.get('message', '')
                    agent = log.get('agent_type', 'system')
                else:
                    msg = log.message
                    agent = log.agent_type
                context_parts.append(f"  - [{agent}] {msg}")
        
        # Add available artifacts
        if artifacts:
            names = []
            if isinstance(artifacts, dict):
                for a in artifacts.values():
                    if isinstance(a, dict): names.append(a.get('name', ''))
                    else: names.append(a.name)
            else:
                names = [a.name for a in artifacts.values()]
                
            context_parts.append(f"Artifacts created: {', '.join(names)}")
            
        # Add conversation history to context
        conversation_history = get_state_attr(state, 'conversation_history', [])
        if conversation_history:
            context_parts.append("Conversation History:")
            # Show last 10 messages
            for msg in conversation_history[-10:]:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                context_parts.append(f"  [{role.upper()}]: {content}")
            
        context_str = "\n".join(context_parts)
        
        # Intent Classification Logic
        # Check intent for all messages to allow queuing
        intent = "CHAT"
        refinement_query = None
        
        intent_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an intent classifier for an AI agent system.
    Display Context:
    {context}
    
    User Input: {message}
    
    Determine if the user's message is:
    1. "CHAT": A general question, clarification, or social interaction.
    2. "REFINE": A request to modify the previous result, add new criteria, change scope, or fix an issue.
    
    Respond in JSON format:
    {{
        "intent": "CHAT" | "REFINE",
        "refinement_query": "<extracted refinement request if REFINE, else null>",
        "reasoning": "<brief explanation>"
    }}"""),
            ("user", "{message}")
        ])
        
        classifier_chain = intent_prompt | llm | JsonOutputParser()
        
        try:
            classification = await classifier_chain.ainvoke({
                "context": context_str,
                "message": message
            })
            logger.info(f"💬 [CHAT] Intent classification: {classification}")
            intent = classification.get("intent", "CHAT")
            refinement_query = classification.get("refinement_query")
        except Exception as e:
            # Fallback to chat if classification fails
            print(f"Intent classification failed: {e}")
            intent = "CHAT"
    
        # Handle Refinement
        if intent == "REFINE" and refinement_query:
            # Add user message to history
            user_msg = {"role": "user", "content": message, "type": "refinement"}
            
            # Check if we can execute immediately (Completed/Error) or need to Queue (Running)
            if status_val in ['completed', 'error']:
                ai_msg = {"role": "assistant", "content": f"Starting refinement: {refinement_query}", "type": "chat"}
                
                # Persist history
                config_dict = {"configurable": {"thread_id": session_id}}
                await self.graph.aupdate_state(config_dict, {
                    "conversation_history": [user_msg, ai_msg]
                })

                # Emit event to notify frontend
                if self.event_callback:
                    await self.event_callback({
                        "type": "chat_response",
                        "session_id": session_id,
                        "response": f"I've understood your request to refine the results: \"{refinement_query}\".\n\nStarting refinement process now..."
                    })
                
                # Extract previous state data
                prev_response = get_state_attr(state, 'final_response', '')
                prev_artifacts = get_state_attr(state, 'artifacts', {})
                
                # Execute refinement
                await self.refine_execution(
                    session_id,
                    refinement_query,
                    prev_response,
                    prev_artifacts,
                    state
                )
                
                return "Refinement execution completed. Please check the updated plan and results."
            else:
                # Execution is running, Queue the refinement
                current_pending = get_state_attr(state, 'pending_refinement') or ""
                new_pending = f"{current_pending}\n{refinement_query}".strip()
                
                ai_msg = {"role": "assistant", "content": f"Queued refinement: {refinement_query}", "type": "chat"}
                
                config_dict = {"configurable": {"thread_id": session_id}}
                await self.graph.aupdate_state(config_dict, {
                    "pending_refinement": new_pending,
                    "conversation_history": [user_msg, ai_msg]
                })
                
                # Emit event
                if self.event_callback:
                    await self.event_callback({
                        "type": "chat_response",
                        "session_id": session_id,
                        "response": f"I've queued your request intent: \"{refinement_query}\".\n\nI will automaticallly apply this refinement immediately after the current tasks complete."
                    })
                
                return f"Request queued. I will process \"{refinement_query}\" after the current execution finishes."

        # Handle Normal Chat
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the Orchestrator AI assistant for a multi-agent system.
The user is interacting with you while a task is being executed.

You can:
1. Answer questions about the current execution status
2. Acknowledge new instructions or context
3. Explain what the agents are doing
4. Provide estimated completion time
5. Note any modifications for the next steps

Be helpful, concise, and informative. If the user wants to modify the execution,
acknowledge their request and explain how it will be incorporated.

Current execution context:
{context}"""),
            ("user", "{message}")
        ])
        
        chain = prompt | llm
        
        try:
            response = await chain.ainvoke({
                "context": context_str,
                "message": message
            })
            
            logger.info(f"💬 [CHAT] Generated response type: {type(response)}")
            response_text = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"💬 [CHAT] Generated response text: {response_text[:50]}...")
            
            # Persist to state
            user_msg = {"role": "user", "content": message, "type": "chat"}
            ai_msg = {"role": "assistant", "content": response_text, "type": "chat"}
            
            config_dict = {"configurable": {"thread_id": session_id}}
            await self.graph.aupdate_state(config_dict, {
                "conversation_history": [user_msg, ai_msg]
            })
            
            # Emit event for the chat response matching frontend expectations
            if self.event_callback:
                logger.info(f"💬 [CHAT] Emitting chat_response event")
                await self.event_callback({
                    "type": "chat_response",
                    "session_id": session_id,
                    "response": response_text
                })
            else:
                logger.warning(f"💬 [CHAT] No event_callback configured")
            
            return response_text
            
        except Exception as e:
            error_msg = f"I encountered an error processing your message: {str(e)}"
            return error_msg
    
    async def refine_execution(
        self,
        session_id: str,
        refinement: str,
        previous_response: str,
        previous_artifacts: dict,
        state: 'AgentState'
    ) -> 'AgentState':
        """
        Refine a completed execution based on user feedback.
        
        This enables multi-turn refinement where users can iterate
        on the output after seeing initial results.
        
        Args:
            session_id: Session ID
            refinement: User's refinement request
            previous_response: The previous final response
            previous_artifacts: Artifacts from previous execution
            state: Current agent state
            
        Returns:
            Updated AgentState after refinement
        """
        from core.state import create_initial_state, PlanStep
        from datetime import datetime
        
        # Create a refined request that includes context
        user_request = get_state_attr(state, 'user_request', '')
        
        # Include conversation history for context
        history = get_state_attr(state, 'conversation_history', [])
        history_text = ""
        if history:
            history_lines = []
            for msg in history:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                history_lines.append(f"{role.upper()}: {content}")
            history_text = "\n".join(history_lines)
        
        refined_request = f"""REFINEMENT REQUEST
        
Original request: {user_request}

Previous response summary:
{previous_response[:500] if previous_response else 'No previous response'}...

Conversation History (Context):
{history_text if history_text else 'No prior conversation'}

Available artifacts from previous execution:
{', '.join((a.get('name', 'Unknown') if isinstance(a, dict) else a.name) for a in previous_artifacts.values()) if previous_artifacts else 'None'}

User's refinement:
{refinement}

Please build upon the previous work to address the user's refinement request.
Reuse existing artifacts where possible."""

        # Prepare updates dictionary instead of modifying state directly
        # This avoids issues with reducer fields (like conversation_history) being duplicated
        # if we passed the full state object back to ainvoke.
        updates = {}
        
        updates['user_request'] = refined_request
        updates['status'] = ExecutionStatus.PLANNING
        updates['plan'] = []
        updates['current_step_index'] = 0
        updates['final_response'] = None
        updates['error_message'] = None
        
        # Keep existing artifacts if requested
        if previous_artifacts:
            updates['artifacts'] = previous_artifacts
        
        # Add log entry
        new_log = {
            "timestamp": datetime.now().isoformat(),
            "agent_type": "orchestrator",
            "message": f"Starting refinement: {refinement[:100]}...",
            "level": "info",
            "data": {}
        }
        
        # For logs (which likely overwrite or append depending on config), 
        # we generally want to append. But if we pass a list, it might replace?
        # Safe strategy: Get existing logs and append? 
        # Or better: if logs field is not annotated with add, it replaces.
        # But we want to KEEP history.
        # Let's assume standard behavior: we should pass the FULL updated list for non-reduced fields.
        previous_logs = get_state_attr(state, 'logs', [])
        # Convert Pydantic models to dicts if needed
        previous_logs_dicts = []
        for log in previous_logs:
            if hasattr(log, 'model_dump'):
                previous_logs_dicts.append(log.model_dump())
            elif isinstance(log, dict):
                previous_logs_dicts.append(log)
            else:
                 # fallback
                 previous_logs_dicts.append(log)
                 
        updates['logs'] = previous_logs_dicts + [new_log]
        
        # Emit event
        if self.event_callback:
            await self.event_callback({
                "type": "refinement_started",
                "session_id": session_id,
                "refinement": refinement
            })
        
        # Re-run the workflow with the refined request
        config_dict = {"configurable": {"thread_id": session_id}}
        
        try:
            # We pass ONLY the updates to ainvoke. 
            # LangGraph merging logic will handle merging these into the thread state.
            final_state = await self.graph.ainvoke(updates, config=config_dict)
            
            # Emit completion event
            if self.event_callback:
                await self.event_callback({
                    "type": "refinement_completed",
                    "session_id": session_id
                })
            
            return final_state
            
        except Exception as e:
            # Handle error by updating state
            error_updates = {
                "status": ExecutionStatus.ERROR,
                "error_message": f"Refinement failed: {str(e)}"
            }
            await self.graph.aupdate_state(config_dict, error_updates)
            return state

