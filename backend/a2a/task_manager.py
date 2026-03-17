"""
A2A Task Manager.
Maps A2A task lifecycle to WandAI's internal session/execution model.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from a2a.models import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskStatusUpdate,
    TaskStatusUpdateEvent,
    TextPart,
)


class A2ATaskManager:
    """Manages A2A tasks and bridges them to WandAI workflow sessions."""

    def __init__(self, workflow_manager=None):
        self._tasks: dict[str, Task] = {}
        self._task_sessions: dict[str, str] = {}  # task_id -> session_id
        self._event_queues: dict[str, asyncio.Queue] = {}
        self.workflow_manager = workflow_manager

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    async def create_task(self, message: Message, agent_name: str) -> Task:
        """Create a new A2A task from an incoming message."""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            status=TaskStatusUpdate(state=TaskStatus.SUBMITTED),
            messages=[message],
        )
        self._tasks[task_id] = task
        return task

    async def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    async def cancel_task(self, task_id: str) -> Task | None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatusUpdate(state=TaskStatus.CANCELED)
        return task

    # ------------------------------------------------------------------
    # Task execution — delegates to WandAI workflow
    # ------------------------------------------------------------------

    async def execute_task(self, task_id: str, agent_name: str) -> Task:
        """Run the task through the WandAI workflow and return the completed task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Extract user text from the first message
        user_text = self._extract_text(task.messages[0])

        # Update status to working
        task.status = TaskStatusUpdate(
            state=TaskStatus.WORKING,
            message=Message(
                role="agent",
                parts=[TextPart(text=f"Agent '{agent_name}' is processing your request...")],
            ),
        )

        try:
            if agent_name == "orchestrator":
                result = await self._run_orchestrator(task_id, user_text)
            else:
                result = await self._run_single_agent(task_id, agent_name, user_text)

            # Convert WandAI result to A2A artifacts
            artifacts = self._build_artifacts(result)
            task.artifacts = artifacts

            task.status = TaskStatusUpdate(
                state=TaskStatus.COMPLETED,
                message=Message(
                    role="agent",
                    parts=[TextPart(text=str(result.get("final_response", result.get("output", ""))))],
                ),
            )
        except Exception as e:
            task.status = TaskStatusUpdate(
                state=TaskStatus.FAILED,
                message=Message(
                    role="agent",
                    parts=[TextPart(text=f"Task failed: {e}")],
                ),
            )

        return task

    # ------------------------------------------------------------------
    # Streaming execution
    # ------------------------------------------------------------------

    async def execute_task_streaming(
        self, task_id: str, agent_name: str
    ) -> AsyncIterator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent]:
        """Execute a task and yield SSE events as it progresses."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        user_text = self._extract_text(task.messages[0])

        # Emit working status
        task.status = TaskStatusUpdate(state=TaskStatus.WORKING)
        yield TaskStatusUpdateEvent(
            task_id=task_id,
            status=task.status,
        )

        queue: asyncio.Queue = asyncio.Queue()
        self._event_queues[task_id] = queue

        async def _event_callback(event: dict):
            await queue.put(event)

        try:
            # Start execution in background
            exec_task = asyncio.create_task(
                self._run_with_events(task_id, agent_name, user_text, _event_callback)
            )

            # Yield events from queue until execution completes
            while not exec_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    sse_event = self._wandai_event_to_a2a(task_id, event)
                    if sse_event:
                        yield sse_event
                except asyncio.TimeoutError:
                    continue

            # Drain remaining events
            while not queue.empty():
                event = await queue.get()
                sse_event = self._wandai_event_to_a2a(task_id, event)
                if sse_event:
                    yield sse_event

            # Get final result
            result = await exec_task
            artifacts = self._build_artifacts(result)
            task.artifacts = artifacts

            for artifact in artifacts:
                yield TaskArtifactUpdateEvent(task_id=task_id, artifact=artifact)

            task.status = TaskStatusUpdate(
                state=TaskStatus.COMPLETED,
                message=Message(
                    role="agent",
                    parts=[TextPart(text=str(result.get("final_response", result.get("output", ""))))],
                ),
            )
            yield TaskStatusUpdateEvent(task_id=task_id, status=task.status)

        except Exception as e:
            task.status = TaskStatusUpdate(
                state=TaskStatus.FAILED,
                message=Message(
                    role="agent",
                    parts=[TextPart(text=f"Task failed: {e}")],
                ),
            )
            yield TaskStatusUpdateEvent(task_id=task_id, status=task.status)

        finally:
            self._event_queues.pop(task_id, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_orchestrator(self, task_id: str, user_text: str) -> dict:
        """Run full orchestrator workflow."""
        if not self.workflow_manager:
            return {"final_response": "Workflow manager not available", "output": ""}

        session_id, result = await self.workflow_manager.execute(user_text)
        self._task_sessions[task_id] = session_id
        return result if isinstance(result, dict) else {"final_response": str(result), "output": str(result)}

    async def _run_single_agent(self, task_id: str, agent_name: str, user_text: str) -> dict:
        """Run a single WandAI agent directly."""
        if not self.workflow_manager:
            return {"output": "Workflow manager not available"}

        agents = getattr(self.workflow_manager, "agents", {})
        agent = agents.get(agent_name)
        if not agent:
            return {"output": f"Agent '{agent_name}' not found"}

        # Create a minimal state for single-agent execution
        from core.state import AgentState
        state: dict[str, Any] = {
            "session_id": str(uuid.uuid4()),
            "user_request": user_text,
            "plan": [],
            "artifacts": {},
            "logs": [],
            "status": "executing",
        }

        success, result, error = await agent.execute_with_retry(
            state, step_id="a2a_task", task_description=user_text
        )

        if success:
            return {"output": str(result), "artifacts": state.get("artifacts", {})}
        return {"output": f"Agent failed: {error}"}

    async def _run_with_events(
        self, task_id: str, agent_name: str, user_text: str, event_callback
    ) -> dict:
        """Run workflow with an event callback for streaming."""
        if not self.workflow_manager:
            return {"final_response": "Workflow manager not available"}

        # Temporarily inject our callback
        original_callback = self.workflow_manager.event_callback
        self.workflow_manager.event_callback = event_callback

        try:
            if agent_name == "orchestrator":
                return await self._run_orchestrator(task_id, user_text)
            else:
                return await self._run_single_agent(task_id, agent_name, user_text)
        finally:
            self.workflow_manager.event_callback = original_callback

    def _extract_text(self, message: Message) -> str:
        """Extract plain text from a Message's parts."""
        texts = []
        for part in message.parts:
            if isinstance(part, TextPart):
                texts.append(part.text)
            elif isinstance(part, DataPart):
                texts.append(str(part.data))
        return " ".join(texts)

    def _build_artifacts(self, result: dict) -> list[Artifact]:
        """Convert WandAI result dict to A2A Artifacts."""
        artifacts: list[Artifact] = []
        idx = 0

        # Main text output
        text_output = result.get("final_response") or result.get("output", "")
        if text_output:
            artifacts.append(
                Artifact(
                    name="response",
                    parts=[TextPart(text=str(text_output))],
                    index=idx,
                )
            )
            idx += 1

        # WandAI artifacts (charts, code, etc.)
        wandai_artifacts = result.get("artifacts", {})
        for artifact_id, artifact_data in wandai_artifacts.items():
            a_type = artifact_data.get("type", "text") if isinstance(artifact_data, dict) else "text"
            a_content = artifact_data.get("content", "") if isinstance(artifact_data, dict) else str(artifact_data)
            a_name = artifact_data.get("name", artifact_id) if isinstance(artifact_data, dict) else artifact_id

            parts: list[Part] = []
            if a_type == "chart" and isinstance(a_content, dict) and a_content.get("image_base64"):
                parts.append(
                    FilePart(
                        file={
                            "name": f"{a_name}.png",
                            "mimeType": "image/png",
                            "bytes": a_content["image_base64"],
                        }
                    )
                )
            elif a_type == "code" and isinstance(a_content, dict):
                parts.append(DataPart(data=a_content))
            else:
                parts.append(TextPart(text=str(a_content)))

            artifacts.append(Artifact(name=a_name, parts=parts, index=idx))
            idx += 1

        return artifacts

    def _wandai_event_to_a2a(
        self, task_id: str, event: dict
    ) -> TaskStatusUpdateEvent | None:
        """Convert a WandAI internal event to an A2A SSE event."""
        event_type = event.get("type", "")
        message_text = None

        if event_type == "planning_started":
            message_text = "Creating execution plan..."
        elif event_type == "planning_completed":
            plan_size = event.get("plan_size", 0)
            message_text = f"Plan created with {plan_size} steps"
        elif event_type == "agent_executing":
            step_id = event.get("step_id", "")
            attempt = event.get("attempt", 1)
            message_text = f"Executing step '{step_id}' (attempt {attempt})"
        elif event_type == "agent_success":
            step_id = event.get("step_id", "")
            message_text = f"Step '{step_id}' completed"
        elif event_type == "step_completed":
            step_id = event.get("step_id", "")
            message_text = f"Step '{step_id}' finished"
        elif event_type == "aggregation_started":
            message_text = "Aggregating results..."
        elif event_type in ("research_started", "coding_started", "analysis_started"):
            message_text = f"Agent started: {event_type}"
        elif event_type in ("research_completed", "code_completed", "chart_completed", "analysis_completed"):
            message_text = f"Agent finished: {event_type}"
        else:
            return None

        if message_text:
            return TaskStatusUpdateEvent(
                task_id=task_id,
                status=TaskStatusUpdate(
                    state=TaskStatus.WORKING,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text=message_text)],
                    ),
                ),
            )
        return None
