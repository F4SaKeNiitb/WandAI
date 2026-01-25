"""
Shared State Schema (The Blackboard)
Central state management for the multi-agent orchestration system.
All agents read from and write to this shared state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Annotated
import operator
from pydantic import BaseModel
import uuid


class AgentType(str, Enum):
    """Types of specialized agents in the system."""
    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    CODER = "coder"
    ANALYST = "analyst"
    WRITER = "writer"


class StepStatus(str, Enum):
    """Status of individual plan steps."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ExecutionStatus(str, Enum):
    """Overall execution status."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_CLARIFICATION = "waiting_clarification"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    ERROR = "error"


class PlanStep(BaseModel):
    """Individual step in the execution plan."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    agent_type: AgentType
    dependencies: list[str] = []  # IDs of steps this depends on
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    retry_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    class Config:
        use_enum_values = True


class AgentLog(BaseModel):
    """Log entry from an agent's execution."""
    timestamp: datetime
    agent_type: AgentType
    step_id: str | None = None
    level: Literal["info", "warning", "error", "debug"] = "info"
    message: str
    data: dict[str, Any] = {}
    
    class Config:
        use_enum_values = True


class Artifact(BaseModel):
    """Artifact produced by an agent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    type: Literal["text", "code", "chart", "data", "image"]
    content: Any
    created_by: AgentType
    step_id: str
    created_at: datetime = field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


class AgentState(BaseModel):
    """
    The Blackboard - Central shared state for all agents.
    This is the single source of truth passed through the LangGraph workflow.
    """
    # Session identification
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # User request
    user_request: str = ""
    
    # Clarity assessment
    clarity_score: int = 10  # 0-10, lower means more ambiguous
    clarifying_questions: list[str] = []
    user_clarifications: list[str] = []
    
    # Execution plan
    plan: list[PlanStep] = []
    current_step_index: int = 0
    
    # Artifacts storage
    artifacts: dict[str, Artifact] = {}
    
    # Execution logs
    logs: list[AgentLog] = []
    
    # Final output
    final_response: str | None = None
    
    # Status tracking
    status: ExecutionStatus = ExecutionStatus.PENDING
    error_message: str | None = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Human-in-the-loop
    requires_approval: bool = False
    approval_message: str | None = None
    
    # Conversation history for live chat and refinement
    conversation_history: Annotated[list[dict], operator.add] = []
    
    # Dynamic refinement queue
    pending_refinement: str | None = None
    
    class Config:
        use_enum_values = True
    
    def add_log(
        self,
        agent_type: AgentType,
        message: str,
        level: str = "info",
        step_id: str | None = None,
        data: dict = None
    ):
        """Add a log entry."""
        self.logs.append(AgentLog(
            timestamp=datetime.now(),
            agent_type=agent_type,
            step_id=step_id,
            level=level,
            message=message,
            data=data or {}
        ))
        self.updated_at = datetime.now()
    
    def add_artifact(
        self,
        name: str,
        artifact_type: str,
        content: Any,
        created_by: AgentType,
        step_id: str
    ) -> str:
        """Add an artifact and return its ID."""
        artifact = Artifact(
            name=name,
            type=artifact_type,
            content=content,
            created_by=created_by,
            step_id=step_id
        )
        self.artifacts[artifact.id] = artifact
        self.updated_at = datetime.now()
        return artifact.id
    
    def get_current_step(self) -> PlanStep | None:
        """Get the current step being executed."""
        if 0 <= self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None
    
    def advance_step(self):
        """Move to the next step in the plan."""
        self.current_step_index += 1
        self.updated_at = datetime.now()
    
    def all_steps_completed(self) -> bool:
        """Check if all steps are completed."""
        return all(step.status == StepStatus.COMPLETED for step in self.plan)
    
    def to_event(self, event_type: str) -> dict:
        """Convert state to a WebSocket event format."""
        return {
            "type": event_type,
            "session_id": self.session_id,
            "status": self.status,
            "current_step": self.current_step_index,
            "total_steps": len(self.plan),
            "plan": [step.model_dump() for step in self.plan],
            "latest_log": self.logs[-1].model_dump() if self.logs else None,
            "artifacts_count": len(self.artifacts),
            "conversation_history": self.conversation_history,
            "timestamp": datetime.now().isoformat()
        }


def create_initial_state(user_request: str) -> AgentState:
    """Factory function to create initial state from user request."""
    return AgentState(
        user_request=user_request,
        status=ExecutionStatus.PENDING
    )
