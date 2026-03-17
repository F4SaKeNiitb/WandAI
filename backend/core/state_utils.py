"""
State access utilities.
Provides uniform access to AgentState regardless of whether it's a dict or object.
All state manipulation should go through these helpers to eliminate isinstance checks.
"""

from datetime import datetime
from typing import Any
from core.state import AgentLog, AgentType, Artifact, StepStatus
import uuid


def get_state_attr(state, attr: str, default=None):
    """Get attribute from state, handling both dict and object."""
    if isinstance(state, dict):
        return state.get(attr, default)
    return getattr(state, attr, default)


def set_state_attr(state, attr: str, value):
    """Set attribute on state, handling both dict and object."""
    if isinstance(state, dict):
        state[attr] = value
    else:
        setattr(state, attr, value)


def get_status_value(status) -> str:
    """Get string value from status, handling both enum and string."""
    if hasattr(status, 'value'):
        return status.value
    return str(status)


def get_plan(state) -> list:
    """Get plan from state."""
    return get_state_attr(state, 'plan', [])


def get_step_attr(step, attr: str, default=None):
    """Get attribute from a step (dict or PlanStep object)."""
    if isinstance(step, dict):
        return step.get(attr, default)
    return getattr(step, attr, default)


def set_step_attr(step, attr: str, value):
    """Set attribute on a step (dict or PlanStep object)."""
    if isinstance(step, dict):
        step[attr] = value
    else:
        setattr(step, attr, value)


def get_step_status(step) -> str:
    """Get the string status of a step."""
    raw = get_step_attr(step, 'status', 'pending')
    return get_status_value(raw)


def add_log(state, agent_type, message: str, level: str = "info",
            step_id: str = None, data: dict = None):
    """Add a log entry to state, handling both dict and object."""
    if isinstance(state, dict):
        logs = state.setdefault('logs', [])
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "agent_type": agent_type.value if hasattr(agent_type, 'value') else str(agent_type),
            "step_id": step_id,
            "message": message,
            "level": level,
            "data": data or {}
        })
    else:
        state.add_log(agent_type, message, level=level, step_id=step_id, data=data)


def add_artifact(state, name: str, artifact_type: str, content: Any,
                 created_by: str, step_id: str) -> str:
    """Add an artifact to state, handling both dict and object. Returns artifact ID."""
    artifact_id = str(uuid.uuid4())[:8]
    if isinstance(state, dict):
        artifacts = state.setdefault('artifacts', {})
        artifacts[artifact_id] = {
            "id": artifact_id,
            "name": name,
            "type": artifact_type,
            "content": content,
            "created_by": created_by,
            "step_id": step_id,
            "created_at": datetime.now().isoformat()
        }
    else:
        return state.add_artifact(name, artifact_type, content, created_by, step_id)
    return artifact_id


def get_artifact_attr(artifact, attr: str, default=None):
    """Get attribute from artifact (dict or Artifact object)."""
    if isinstance(artifact, dict):
        return artifact.get(attr, default)
    return getattr(artifact, attr, default)


def state_to_event(state, event_type: str) -> dict:
    """Convert state to a WebSocket event format, handling both dict and object."""
    if isinstance(state, dict):
        plan = state.get('plan', [])
        logs = state.get('logs', [])
        return {
            "type": event_type,
            "session_id": state.get('session_id', ''),
            "status": get_status_value(state.get('status', '')),
            "current_step": state.get('current_step_index', 0),
            "total_steps": len(plan),
            "plan": [
                s.model_dump() if hasattr(s, 'model_dump') else s
                for s in plan
            ],
            "latest_log": (
                logs[-1].model_dump() if hasattr(logs[-1], 'model_dump') else logs[-1]
            ) if logs else None,
            "artifacts_count": len(state.get('artifacts', {})),
            "conversation_history": state.get('conversation_history', []),
            "timestamp": datetime.now().isoformat()
        }
    else:
        return state.to_event(event_type)
