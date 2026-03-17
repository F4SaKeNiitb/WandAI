"""
A2A Protocol Pydantic Models.
Defines the data structures for Google's Agent-to-Agent protocol.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Task status enum
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# ---------------------------------------------------------------------------
# Message parts
# ---------------------------------------------------------------------------

class TextPart(BaseModel):
    type: str = "text"
    text: str


class FilePart(BaseModel):
    type: str = "file"
    file: dict  # {"name": str, "mimeType": str, "bytes": str (base64)}


class DataPart(BaseModel):
    type: str = "data"
    data: dict


Part = TextPart | FilePart | DataPart


# ---------------------------------------------------------------------------
# Messages & Artifacts
# ---------------------------------------------------------------------------

class Message(BaseModel):
    role: str  # "user" or "agent"
    parts: list[Part]
    metadata: dict[str, Any] | None = None


class Artifact(BaseModel):
    name: str | None = None
    parts: list[Part] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    index: int = 0


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class TaskStatusUpdate(BaseModel):
    state: TaskStatus
    message: Message | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class Task(BaseModel):
    id: str
    status: TaskStatusUpdate
    messages: list[Message] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# AgentCard
# ---------------------------------------------------------------------------

class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class AgentCapabilities(BaseModel):
    streaming: bool = True
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentAuthentication(BaseModel):
    schemes: list[str] = Field(default_factory=list)
    credentials: str | None = None


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    skills: list[AgentSkill] = Field(default_factory=list)
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    authentication: AgentAuthentication | None = None
    defaultInputModes: list[str] = Field(default_factory=lambda: ["text/plain"])
    defaultOutputModes: list[str] = Field(default_factory=lambda: ["text/plain"])


# ---------------------------------------------------------------------------
# JSON-RPC 2.0
# ---------------------------------------------------------------------------

class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JSONRPCError | None = None


# ---------------------------------------------------------------------------
# SSE Event wrappers
# ---------------------------------------------------------------------------

class TaskStatusUpdateEvent(BaseModel):
    type: str = "status"
    task_id: str
    status: TaskStatusUpdate


class TaskArtifactUpdateEvent(BaseModel):
    type: str = "artifact"
    task_id: str
    artifact: Artifact
