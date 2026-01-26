"""
REST API Routes
Endpoints for the multi-agent orchestration system.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import uuid

from core.state import AgentState, ExecutionStatus
from core.graph import WorkflowManager
from core.logging import get_logger

logger = get_logger('API')

router = APIRouter(prefix="/api", tags=["orchestration"])

# In-memory session store (would use Redis/database in production)
sessions: dict[str, AgentState] = {}
workflow_manager: WorkflowManager = None


def get_workflow_manager() -> WorkflowManager:
    """Get or create WorkflowManager instance."""
    global workflow_manager
    if workflow_manager is None:
        workflow_manager = WorkflowManager()
    return workflow_manager


class ExecuteRequest(BaseModel):
    """Request body for executing a business request."""
    request: str
    session_id: Optional[str] = None
    require_approval: bool = False


class ExecuteResponse(BaseModel):
    """Response for execute endpoint."""
    session_id: str
    status: str
    message: str


class ClarifyRequest(BaseModel):
    """Request body for providing clarifications."""
    session_id: str
    clarifications: list[str]


class ApprovalRequest(BaseModel):
    """Request body for plan approval."""
    session_id: str
    approved: bool
    modifications: Optional[str] = None
    plan: Optional[list[dict]] = None


class PlanUpdateRequest(BaseModel):
    """Request body for mid-execution plan updates."""
    session_id: str
    plan: list[dict]


class SessionStatus(BaseModel):
    """Session status response."""
    session_id: str
    status: str
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    plan: Optional[list[dict]] = None
    artifacts: Optional[list[dict]] = None
    logs: Optional[list[dict]] = None
    final_response: Optional[str] = None
    clarifying_questions: Optional[list[str]] = None
    error_message: Optional[str] = None
    conversation_history: Optional[list[dict]] = None
    # Step-level clarification fields
    step_clarification_step_id: Optional[str] = None
    step_clarification_questions: Optional[list[str]] = None


@router.post("/execute", response_model=ExecuteResponse)
async def execute_request(
    request: ExecuteRequest,
    background_tasks: BackgroundTasks
):
    """
    Submit a new business request for execution.
    
    The request will be processed asynchronously. Use the session_id
    to track progress via WebSocket or the status endpoint.
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    wm = get_workflow_manager()
    
    # Store initial state
    from core.state import create_initial_state
    initial_state = create_initial_state(request.request)
    initial_state.session_id = session_id
    initial_state.requires_approval = request.require_approval
    sessions[session_id] = initial_state
    
    # Execute in background
    async def run_workflow():
        try:
            final_state = await wm.execute(request.request, session_id)
            sessions[session_id] = final_state
        except Exception as e:
            # Persist error to DB
            config_dict = {"configurable": {"thread_id": session_id}}
            await wm.graph.aupdate_state(config_dict, {
                "status": ExecutionStatus.ERROR,
                "error_message": str(e)
            })
            
            # Update local cache just in case
            if session_id in sessions:
                sessions[session_id].status = ExecutionStatus.ERROR
                sessions[session_id].error_message = str(e)
    
    background_tasks.add_task(run_workflow)
    
    return ExecuteResponse(
        session_id=session_id,
        status="accepted",
        message="Request submitted for processing. Connect via WebSocket for real-time updates."
    )


def get_state_status(state):
    """Helper to get status from either dict or AgentState."""
    if isinstance(state, dict):
        status = state.get('status', 'pending')
        if hasattr(status, 'value'):
            return status.value
        return str(status)
    else:
        return state.status.value if hasattr(state.status, 'value') else str(state.status)


@router.post("/clarify", response_model=ExecuteResponse)
async def provide_clarification(
    request: ClarifyRequest,
    background_tasks: BackgroundTasks
):
    """
    Provide clarifications for an ambiguous request.
    """
    wm = get_workflow_manager()
    
    # Check state in DB
    config_dict = {"configurable": {"thread_id": request.session_id}}
    snapshot = await wm.graph.aget_state(config_dict)
    
    if not snapshot or not snapshot.values:
        # Fallback check if it was just created (unlikely for clarification)
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        state = sessions[request.session_id]
    else:
        state = snapshot.values
    
    status = get_state_status(state)
    
    if status != 'waiting_clarification':
        raise HTTPException(
            status_code=400, 
            detail=f"Session is not waiting for clarification. Status: {status}"
        )
    
    # Resume workflow with clarifications
    async def resume_workflow():
        try:
            final_state = await wm.resume_after_clarification(
                request.session_id,
                request.clarifications
            )
            sessions[request.session_id] = final_state
        except Exception as e:
            # Persist error to DB
            config_dict = {"configurable": {"thread_id": request.session_id}}
            await wm.graph.aupdate_state(config_dict, {
                "status": ExecutionStatus.ERROR,
                "error_message": str(e)
            })
            
            if isinstance(sessions.get(request.session_id), dict):
                sessions[request.session_id]['status'] = ExecutionStatus.ERROR
                sessions[request.session_id]['error_message'] = str(e)
            elif request.session_id in sessions:
                sessions[request.session_id].status = ExecutionStatus.ERROR
                sessions[request.session_id].error_message = str(e)
    
    background_tasks.add_task(resume_workflow)
    
    return ExecuteResponse(
        session_id=request.session_id,
        status="accepted",
        message="Clarifications received. Resuming execution."
    )


class StepClarifyRequest(BaseModel):
    """Request body for providing step-level clarifications."""
    session_id: str
    step_id: str
    clarifications: list[str]


@router.post("/step-clarify", response_model=ExecuteResponse)
async def provide_step_clarification(
    request: StepClarifyRequest,
    background_tasks: BackgroundTasks
):
    """
    Provide clarifications for a specific step that an agent flagged as ambiguous.
    """
    wm = get_workflow_manager()
    
    # Check state in DB
    config_dict = {"configurable": {"thread_id": request.session_id}}
    snapshot = await wm.graph.aget_state(config_dict)
    
    if not snapshot or not snapshot.values:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        state = sessions[request.session_id]
    else:
        state = snapshot.values
    
    status = get_state_status(state)
    
    if status != 'waiting_step_clarification':
        raise HTTPException(
            status_code=400, 
            detail=f"Session is not waiting for step clarification. Status: {status}"
        )
    
    # Verify the step_id matches
    expected_step = state.get('step_clarification_step_id') if isinstance(state, dict) else getattr(state, 'step_clarification_step_id', None)
    if expected_step and expected_step != request.step_id:
        raise HTTPException(
            status_code=400,
            detail=f"Step ID mismatch. Expected: {expected_step}, got: {request.step_id}"
        )
    
    # Resume workflow with step clarifications
    async def resume_workflow():
        try:
            final_state = await wm.resume_after_step_clarification(
                request.session_id,
                request.step_id,
                request.clarifications
            )
            sessions[request.session_id] = final_state
        except Exception as e:
            config_dict = {"configurable": {"thread_id": request.session_id}}
            await wm.graph.aupdate_state(config_dict, {
                "status": ExecutionStatus.ERROR,
                "error_message": str(e)
            })
            
            if isinstance(sessions.get(request.session_id), dict):
                sessions[request.session_id]['status'] = ExecutionStatus.ERROR
                sessions[request.session_id]['error_message'] = str(e)
            elif request.session_id in sessions:
                sessions[request.session_id].status = ExecutionStatus.ERROR
                sessions[request.session_id].error_message = str(e)
    
    background_tasks.add_task(resume_workflow)
    
    return ExecuteResponse(
        session_id=request.session_id,
        status="accepted",
        message=f"Step clarifications received for '{request.step_id}'. Resuming execution."
    )


@router.post("/approve", response_model=ExecuteResponse)
async def approve_plan(
    request: ApprovalRequest,
    background_tasks: BackgroundTasks
):
    """
    Approve or modify the execution plan.
    """
    wm = get_workflow_manager()
    
    # Check state in DB
    config_dict = {"configurable": {"thread_id": request.session_id}}
    snapshot = await wm.graph.aget_state(config_dict)
    
    if not snapshot or not snapshot.values:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        state = sessions[request.session_id]
    else:
        state = snapshot.values
        
    status = get_state_status(state)
    
    if status != 'waiting_approval':
        raise HTTPException(
            status_code=400,
            detail=f"Session is not waiting for approval. Status: {status}"
        )
    
    # Resume workflow with approval decision
    async def resume_workflow():
        try:
            final_state = await wm.resume_after_approval(
                request.session_id,
                request.approved,
                request.modifications,
                request.plan
            )
            sessions[request.session_id] = final_state
        except Exception as e:
            # Persist error to DB
            config_dict = {"configurable": {"thread_id": request.session_id}}
            await wm.graph.aupdate_state(config_dict, {
                "status": ExecutionStatus.ERROR,
                "error_message": str(e)
            })

            if isinstance(sessions.get(request.session_id), dict):
                sessions[request.session_id]['status'] = ExecutionStatus.ERROR
                sessions[request.session_id]['error_message'] = str(e)
            elif request.session_id in sessions:
                sessions[request.session_id].status = ExecutionStatus.ERROR
                sessions[request.session_id].error_message = str(e)
    
    background_tasks.add_task(resume_workflow)
    
    return ExecuteResponse(
        session_id=request.session_id,
        status="accepted",
        message=f"Plan {'approved' if request.approved else 'modifications requested'}. Resuming execution."
    )


@router.get("/status/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """
    Get the current status of a session.
    """
    wm = get_workflow_manager()
    
    # Try to get from persistent storage first
    try:
        config_dict = {"configurable": {"thread_id": session_id}}
        snapshot = await wm.graph.aget_state(config_dict)
        
        if snapshot and snapshot.values:
            state = snapshot.values
        else:
            # Fallback to memory for just-created sessions
            if session_id in sessions:
                state = sessions[session_id]
            else:
                raise HTTPException(status_code=404, detail="Session not found")
    except Exception:
        # If DB check fails or state is invalid
        if session_id in sessions:
            state = sessions[session_id]
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    
    # DEBUG: Log history size to trace vanishing chat
    ch_len = 0
    if isinstance(state, dict):
        ch_len = len(state.get('conversation_history', []))
    else:
        ch_len = len(state.conversation_history) if hasattr(state, 'conversation_history') else 0
    
    if ch_len == 0:
        logger.warning(f"⚠️ [API] get_session_status returning EMPTY history for {session_id}. State type: {type(state)}")

    # Handle both dict (from LangGraph) and AgentState objects
    if isinstance(state, dict):
        status_val = state.get('status', 'pending')
        if hasattr(status_val, 'value'):
            status_val = status_val.value
        
        plan = state.get('plan', [])
        plan_list = []
        for s in plan:
            if hasattr(s, 'model_dump'):
                plan_list.append(s.model_dump())
            elif isinstance(s, dict):
                plan_list.append(s)
        
        artifacts = state.get('artifacts', {})
        artifacts_list = []
        for k, v in artifacts.items():
            if hasattr(v, 'name'):
                artifacts_list.append({"id": k, "name": v.name, "type": v.type, "content": v.content})
            elif isinstance(v, dict):
                artifacts_list.append({"id": k, "name": v.get('name', k), "type": v.get('type', 'text'), "content": v.get('content')})
        
        logs = state.get('logs', [])
        logs_list = []
        for l in logs[-20:]:
            if hasattr(l, 'model_dump'):
                logs_list.append(l.model_dump())
            elif isinstance(l, dict):
                logs_list.append(l)
        
        clarifying_questions = None
        if status_val == ExecutionStatus.WAITING_CLARIFICATION or status_val == 'waiting_clarification':
            clarifying_questions = state.get('clarifying_questions', [])
        
        return SessionStatus(
            session_id=session_id,
            status=str(status_val),
            current_step=state.get('current_step_index', 0),
            total_steps=len(plan),
            plan=plan_list,
            artifacts=artifacts_list,
            logs=logs_list,
            final_response=state.get('final_response'),
            clarifying_questions=clarifying_questions,
            error_message=state.get('error_message'),
            conversation_history=state.get('conversation_history', []),
            step_clarification_step_id=state.get('step_clarification_step_id'),
            step_clarification_questions=state.get('step_clarification_questions', [])
        )
    else:
        # Original AgentState object handling
        return SessionStatus(
            session_id=session_id,
            status=state.status.value if hasattr(state.status, 'value') else str(state.status),
            current_step=state.current_step_index,
            total_steps=len(state.plan),
            plan=[s.model_dump() for s in state.plan],
            artifacts=[
                {"id": k, "name": v.name, "type": v.type, "content": v.content}
                for k, v in state.artifacts.items()
            ],
            logs=[l.model_dump() for l in state.logs[-20:]],
            final_response=state.final_response,
            clarifying_questions=state.clarifying_questions if state.status == ExecutionStatus.WAITING_CLARIFICATION else None,
            error_message=state.error_message,
            conversation_history=state.conversation_history if hasattr(state, 'conversation_history') else [],
            step_clarification_step_id=state.step_clarification_step_id,
            step_clarification_questions=state.step_clarification_questions
        )


@router.get("/sessions")
async def list_sessions():
    """
    List all active sessions.
    """
    return [
        {
            "session_id": sid,
            "status": state.status.value if hasattr(state.status, 'value') else str(state.status),
            "request_preview": state.user_request[:100] + "..." if len(state.user_request) > 100 else state.user_request,
            "created_at": state.created_at.isoformat() if state.created_at else None
        }
        for sid, state in sessions.items()
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del sessions[session_id]
    return {"message": "Session deleted", "session_id": session_id}


@router.get("/artifacts/{session_id}/{artifact_id}")
async def get_artifact(session_id: str, artifact_id: str):
    """
    Get a specific artifact from a session.
    """
    wm = get_workflow_manager()
    
    # Check state in DB
    config_dict = {"configurable": {"thread_id": session_id}}
    snapshot = await wm.graph.aget_state(config_dict)
    
    if not snapshot or not snapshot.values:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        state = sessions[session_id]
    else:
        state = snapshot.values
    if artifact_id not in state.artifacts:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    artifact = state.artifacts[artifact_id]
    return artifact.model_dump()


@router.get("/agents")
async def list_agents():
    """
    List all available agents (builtin + custom).
    """
    wm = get_workflow_manager()
    
    # Builtin agents
    agents = [
        {"id": "orchestrator", "name": "Orchestrator", "type": "system"},
        {"id": "researcher", "name": "Researcher", "type": "builtin"},
        {"id": "coder", "name": "Coder", "type": "builtin"},
        {"id": "analyst", "name": "Analyst", "type": "builtin"},
        {"id": "writer", "name": "Writer", "type": "builtin"},
    ]
    
    # Custom agents
    import json
    import os
    if os.path.exists("custom_agents.json"):
        try:
            with open("custom_agents.json", "r") as f:
                custom_agents = json.load(f)
                for ca in custom_agents:
                    agents.append({
                        "id": ca["name"], 
                        "name": ca["name"].replace("_", " ").title(),
                        "type": "custom",
                        "system_prompt": ca["system_prompt"]
                    })
        except Exception as e:
            logger.error(f"Failed to list custom agents: {e}")
            
    return agents


class CustomAgentRequest(BaseModel):
    """Request body for creating a custom agent."""
    name: str
    system_prompt: str


@router.post("/agents")
async def create_custom_agent(request: CustomAgentRequest):
    """
    Create or update a custom agent.
    """
    wm = get_workflow_manager()
    
    success, message = wm.register_custom_agent(request.name, request.system_prompt)
    if not success:
        raise HTTPException(status_code=400, detail=message)
        
    return {"message": "Agent registered successfully", "id": request.name}


@router.delete("/agents/{agent_id}")
async def delete_custom_agent(agent_id: str):
    """
    Delete a custom agent.
    """
    wm = get_workflow_manager()
    
    success, message = wm.unregister_custom_agent(agent_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
        
    return {"message": "Agent deleted successfully", "id": agent_id}

@router.post("/plan", response_model=ExecuteResponse)
async def update_plan_midway(
    request: PlanUpdateRequest
):
    """
    Update the execution plan mid-flight.
    """
    wm = get_workflow_manager()
    try:
        await wm.update_plan(request.session_id, request.plan)
        return ExecuteResponse(
            session_id=request.session_id,
            status="accepted",
            message="Plan updated successfully."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# STRETCH GOALS: Live Conversation & Multi-turn Refinement
# ============================================================

class ChatMessage(BaseModel):
    """Request body for sending a chat message during execution."""
    session_id: str
    message: str


class RefineRequest(BaseModel):
    """Request body for refining a completed request."""
    session_id: str
    refinement: str
    keep_artifacts: bool = True


class ConversationEntry(BaseModel):
    """A single entry in the conversation history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str


@router.post("/chat", response_model=ExecuteResponse)
async def send_chat_message(
    request: ChatMessage,
    background_tasks: BackgroundTasks
):
    """
    Send a chat message during execution (Live Conversation Mode).
    
    This allows users to:
    - Provide additional context mid-execution
    - Request modifications to the current approach
    - Ask for status updates
    - Pause or redirect the execution
    
    The orchestrator will process the message and adjust accordingly.
    """
    wm = get_workflow_manager()
    
    # Process chat message asynchronously
    async def process_chat():
        try:
            # We don't need to manually update state here because wm.handle_chat_message
            # (and graph.py) now handles state persistence and event emission.
            # We just need to fetch the current state to pass to it.
            
            config_dict = {"configurable": {"thread_id": request.session_id}}
            snapshot = await wm.graph.aget_state(config_dict)
            
            if not snapshot or not snapshot.values:
                # Fallback to cache if not in DB yet (unlikely for running session)
                if request.session_id in sessions:
                    state = sessions[request.session_id]
                else: 
                     # If session lost, we can't really chat. 
                     # But we should log error.
                     logger.error(f"Session {request.session_id} not found for chat")
                     return
            else:
                state = snapshot.values

            await wm.handle_chat_message(request.session_id, request.message, state)
            
        except Exception as e:
            logger.error(f"Error processing chat: {e}")
            # Persist error to DB
            config_dict = {"configurable": {"thread_id": request.session_id}}
            await wm.graph.aupdate_state(config_dict, {
                "status": ExecutionStatus.ERROR,
                "error_message": str(e)
            })
    
    background_tasks.add_task(process_chat)
    
    return ExecuteResponse(
        session_id=request.session_id,
        status="accepted",
        message="Message received. The orchestrator will respond shortly."
    )


@router.post("/refine", response_model=ExecuteResponse)
async def refine_request(
    request: RefineRequest,
    background_tasks: BackgroundTasks
):
    """
    Refine a completed request (Multi-turn Refinement).
    
    After seeing the initial output, users can:
    - Request modifications or additions
    - Ask for a different format
    - Drill deeper into specific aspects
    - Combine with new data sources
    
    The system will use the existing artifacts and context to build upon.
    """
    wm = get_workflow_manager()
    
    # Check state in DB
    config_dict = {"configurable": {"thread_id": request.session_id}}
    snapshot = await wm.graph.aget_state(config_dict)
    
    if not snapshot or not snapshot.values:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        state = sessions[request.session_id]
    else:
        state = snapshot.values
    
    if state.status not in [ExecutionStatus.COMPLETED, ExecutionStatus.ERROR]:
        raise HTTPException(
            status_code=400,
            detail=f"Session must be completed to refine. Current status: {state.status}"
        )
    
    # Store the refinement in conversation history
    from datetime import datetime
    
    if isinstance(state, dict):
        history = state.get('conversation_history') or []
        
        history.append({
            "role": "user",
            "content": f"[Refinement]: {request.refinement}",
            "timestamp": datetime.now().isoformat()
        })
        
        # Persist to DB
        await wm.graph.aupdate_state(config_dict, {
            "conversation_history": history
        })
        
        previous_response = state.get('final_response')
        previous_artifacts = state.get('artifacts', {}) if request.keep_artifacts else {}
    else:
        if not hasattr(state, 'conversation_history') or state.conversation_history is None:
            state.conversation_history = []
        
        state.conversation_history.append({
            "role": "user",
            "content": f"[Refinement]: {request.refinement}",
            "timestamp": datetime.now().isoformat()
        })
        
        previous_response = state.final_response
        previous_artifacts = dict(state.artifacts) if request.keep_artifacts else {}
    
    wm = get_workflow_manager()
    
    # Process refinement
    async def process_refinement():
        try:
            final_state = await wm.refine_execution(
                request.session_id,
                request.refinement,
                previous_response,
                previous_artifacts,
                state
            )
            
            # Store assistant response
            # Store assistant response
            final_response = final_state.get('final_response') if isinstance(final_state, dict) else final_state.final_response

            if final_response:
                if isinstance(state, dict):
                    new_msg = {
                        "role": "assistant",
                        "content": final_response,
                        "timestamp": datetime.now().isoformat()
                    }
                    # Persist DELTA to DB
                    config_dict = {"configurable": {"thread_id": request.session_id}}
                    await wm.graph.aupdate_state(config_dict, {
                        "conversation_history": [new_msg]
                    })
                    # Update local state
                    history = state.get('conversation_history', [])
                    history.append(new_msg)
                    state['conversation_history'] = history
                else:
                    state.conversation_history.append({
                        "role": "assistant",
                        "content": final_response,
                        "timestamp": datetime.now().isoformat()
                    })
            
            sessions[request.session_id] = final_state
            
        except Exception as e:
            # Persist error to DB
            config_dict = {"configurable": {"thread_id": request.session_id}}
            await wm.graph.aupdate_state(config_dict, {
                "status": ExecutionStatus.ERROR,
                "error_message": str(e)
            })
            
            if isinstance(sessions.get(request.session_id), dict):
                sessions[request.session_id]['status'] = ExecutionStatus.ERROR
                sessions[request.session_id]['error_message'] = str(e)
            elif request.session_id in sessions:
                sessions[request.session_id].status = ExecutionStatus.ERROR
                sessions[request.session_id].error_message = str(e)
    
    background_tasks.add_task(process_refinement)
    
    return ExecuteResponse(
        session_id=request.session_id,
        status="accepted",
        message="Refinement request received. Processing with existing context."
    )


@router.get("/conversation/{session_id}")
async def get_conversation_history(session_id: str):
    """
    Get the full conversation history for a session.
    
    Includes all user messages, assistant responses, and refinements.
    """
    wm = get_workflow_manager()
    
    # Check state in DB
    config_dict = {"configurable": {"thread_id": session_id}}
    snapshot = await wm.graph.aget_state(config_dict)
    
    if not snapshot or not snapshot.values:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        state = sessions[session_id]
    else:
        state = snapshot.values
    
    first_request = state.get('user_request', '') if isinstance(state, dict) else state.user_request
    created_at = (state.get('created_at').isoformat() if state.get('created_at') else None) if isinstance(state, dict) else (state.created_at.isoformat() if state.created_at else None)
    
    # Build conversation from initial request + history
    conversation = [
        {
            "role": "user",
            "content": first_request,
            "timestamp": created_at,
            "type": "initial_request"
        }
    ]
    
    user_clarifications = state.get('user_clarifications') if isinstance(state, dict) else state.user_clarifications
    
    # Add clarifications if any
    if user_clarifications:
        for clarification in user_clarifications:
            conversation.append({
                "role": "user",
                "content": clarification,
                "type": "clarification"
            })
    
    conv_history = state.get('conversation_history') if isinstance(state, dict) else getattr(state, 'conversation_history', [])
    
    # Add conversation history
    if conv_history:
        for entry in conv_history:
            conversation.append({
                **entry,
                "type": "chat" if "[Refinement]" not in entry.get("content", "") else "refinement"
            })
    
    final_response = state.get('final_response') if isinstance(state, dict) else state.final_response
    updated_at = (state.get('updated_at').isoformat() if state.get('updated_at') else None) if isinstance(state, dict) else (state.updated_at.isoformat() if state.updated_at else None)
    
    # Add final response if completed
    if final_response:
        conversation.append({
            "role": "assistant",
            "content": final_response,
            "timestamp": updated_at,
            "type": "final_response"
        })
    
    return {
        "session_id": session_id,
        "status": state.status.value if hasattr(state.status, 'value') else str(state.status),
        "conversation": conversation,
        "artifacts_count": len(state.artifacts)
    }

