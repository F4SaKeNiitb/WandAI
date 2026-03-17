"""
Tests for A2A protocol endpoints and models.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a.models import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Artifact,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    Message,
    Task,
    TaskStatus,
    TaskStatusUpdate,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TextPart,
    DataPart,
    FilePart,
)
from a2a.agent_cards import get_agent_cards
from a2a.task_manager import A2ATaskManager


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestA2AModels:
    def test_task_status_enum(self):
        assert TaskStatus.SUBMITTED == "submitted"
        assert TaskStatus.WORKING == "working"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELED == "canceled"
        assert TaskStatus.INPUT_REQUIRED == "input-required"

    def test_text_part(self):
        part = TextPart(text="hello")
        assert part.type == "text"
        assert part.text == "hello"

    def test_file_part(self):
        part = FilePart(file={"name": "chart.png", "mimeType": "image/png", "bytes": "abc123"})
        assert part.type == "file"
        assert part.file["name"] == "chart.png"

    def test_data_part(self):
        part = DataPart(data={"key": "value"})
        assert part.type == "data"
        assert part.data["key"] == "value"

    def test_message(self):
        msg = Message(
            role="user",
            parts=[TextPart(text="hello")],
            metadata={"source": "test"},
        )
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.metadata["source"] == "test"

    def test_artifact(self):
        artifact = Artifact(
            name="result",
            parts=[TextPart(text="some output")],
            index=0,
        )
        assert artifact.name == "result"
        assert artifact.index == 0

    def test_task(self):
        task = Task(
            id="test-123",
            status=TaskStatusUpdate(state=TaskStatus.SUBMITTED),
            messages=[
                Message(role="user", parts=[TextPart(text="do something")])
            ],
        )
        assert task.id == "test-123"
        assert task.status.state == TaskStatus.SUBMITTED
        assert len(task.messages) == 1

    def test_agent_card(self):
        card = AgentCard(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8000/a2a/test",
            skills=[
                AgentSkill(id="test-skill", name="Test", description="A test skill")
            ],
        )
        assert card.name == "Test Agent"
        assert card.version == "1.0.0"
        assert len(card.skills) == 1
        assert card.capabilities.streaming is True

    def test_jsonrpc_request(self):
        req = JSONRPCRequest(id="1", method="tasks/send", params={"key": "val"})
        assert req.jsonrpc == "2.0"
        assert req.method == "tasks/send"

    def test_jsonrpc_response_success(self):
        resp = JSONRPCResponse(id="1", result={"status": "ok"})
        assert resp.error is None
        assert resp.result["status"] == "ok"

    def test_jsonrpc_response_error(self):
        resp = JSONRPCResponse(
            id="1",
            error=JSONRPCError(code=-32601, message="Method not found"),
        )
        assert resp.result is None
        assert resp.error.code == -32601

    def test_task_status_update_event(self):
        event = TaskStatusUpdateEvent(
            task_id="t1",
            status=TaskStatusUpdate(state=TaskStatus.WORKING),
        )
        assert event.type == "status"
        assert event.task_id == "t1"

    def test_task_artifact_update_event(self):
        event = TaskArtifactUpdateEvent(
            task_id="t1",
            artifact=Artifact(name="output", parts=[TextPart(text="result")]),
        )
        assert event.type == "artifact"
        assert event.artifact.name == "output"

    def test_task_serialization_roundtrip(self):
        task = Task(
            id="round-trip",
            status=TaskStatusUpdate(state=TaskStatus.COMPLETED),
            messages=[Message(role="user", parts=[TextPart(text="test")])],
            artifacts=[Artifact(name="out", parts=[TextPart(text="done")])],
        )
        data = task.model_dump()
        restored = Task(**data)
        assert restored.id == "round-trip"
        assert restored.status.state == TaskStatus.COMPLETED
        assert len(restored.artifacts) == 1


# ---------------------------------------------------------------------------
# AgentCard tests
# ---------------------------------------------------------------------------

class TestAgentCards:
    def test_all_agents_have_cards(self):
        cards = get_agent_cards()
        expected = {"researcher", "coder", "analyst", "writer", "orchestrator"}
        assert set(cards.keys()) == expected

    def test_card_urls_include_base(self):
        cards = get_agent_cards("http://example.com")
        for name, card in cards.items():
            assert card.url.startswith("http://example.com/a2a/")

    def test_each_card_has_skills(self):
        cards = get_agent_cards()
        for name, card in cards.items():
            assert len(card.skills) > 0, f"{name} has no skills"
            for skill in card.skills:
                assert skill.id
                assert skill.name
                assert skill.description

    def test_orchestrator_has_planning_skill(self):
        cards = get_agent_cards()
        orch = cards["orchestrator"]
        skill_ids = {s.id for s in orch.skills}
        assert "task-planning" in skill_ids
        assert "multi-agent-coordination" in skill_ids


# ---------------------------------------------------------------------------
# TaskManager tests
# ---------------------------------------------------------------------------

class TestA2ATaskManager:
    @pytest.fixture
    def manager(self):
        return A2ATaskManager()

    @pytest.mark.asyncio
    async def test_create_task(self, manager):
        msg = Message(role="user", parts=[TextPart(text="hello")])
        task = await manager.create_task(msg, "researcher")
        assert task.id
        assert task.status.state == TaskStatus.SUBMITTED
        assert len(task.messages) == 1

    @pytest.mark.asyncio
    async def test_get_task(self, manager):
        msg = Message(role="user", parts=[TextPart(text="hello")])
        task = await manager.create_task(msg, "researcher")
        retrieved = await manager.get_task(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, manager):
        result = await manager.get_task("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_task(self, manager):
        msg = Message(role="user", parts=[TextPart(text="hello")])
        task = await manager.create_task(msg, "researcher")
        cancelled = await manager.cancel_task(task.id)
        assert cancelled.status.state == TaskStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, manager):
        result = await manager.cancel_task("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_task_no_workflow(self, manager):
        """Without a workflow manager, tasks should fail gracefully."""
        msg = Message(role="user", parts=[TextPart(text="do something")])
        task = await manager.create_task(msg, "orchestrator")
        result = await manager.execute_task(task.id, "orchestrator")
        # Should complete (the manager handles missing workflow gracefully)
        assert result.status.state in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    def test_extract_text(self, manager):
        msg = Message(
            role="user",
            parts=[TextPart(text="hello"), TextPart(text="world")],
        )
        text = manager._extract_text(msg)
        assert text == "hello world"

    def test_build_artifacts_text(self, manager):
        result = {"final_response": "Here is the answer"}
        artifacts = manager._build_artifacts(result)
        assert len(artifacts) == 1
        assert artifacts[0].name == "response"

    def test_build_artifacts_with_wandai_artifacts(self, manager):
        result = {
            "final_response": "Done",
            "artifacts": {
                "chart_1": {
                    "type": "chart",
                    "name": "revenue_chart",
                    "content": {"image_base64": "abc123", "title": "Revenue"},
                },
                "code_1": {
                    "type": "code",
                    "name": "calc_code",
                    "content": {"code": "print(1+1)", "output": "2"},
                },
            },
        }
        artifacts = manager._build_artifacts(result)
        assert len(artifacts) == 3  # response + chart + code

    def test_wandai_event_to_a2a_known_events(self, manager):
        events_that_should_map = [
            {"type": "planning_started"},
            {"type": "planning_completed", "plan_size": 3},
            {"type": "agent_executing", "step_id": "s1", "attempt": 1},
            {"type": "agent_success", "step_id": "s1"},
            {"type": "aggregation_started"},
        ]
        for event in events_that_should_map:
            result = manager._wandai_event_to_a2a("task-1", event)
            assert result is not None, f"Event {event['type']} should map to an SSE event"
            assert result.task_id == "task-1"

    def test_wandai_event_to_a2a_unknown_event(self, manager):
        result = manager._wandai_event_to_a2a("task-1", {"type": "unknown_event"})
        assert result is None


# ---------------------------------------------------------------------------
# FastAPI route tests (using TestClient)
# ---------------------------------------------------------------------------

class TestA2ARoutes:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from a2a.routes import router, task_manager as _tm
        import a2a.routes as routes_module

        app = FastAPI()
        app.include_router(router)

        # Initialize a task manager for tests
        routes_module.task_manager = A2ATaskManager()

        return TestClient(app)

    def test_get_agent_card(self, client):
        resp = client.get("/a2a/researcher/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "WandAI Researcher"
        assert "skills" in data

    def test_get_unknown_agent_card(self, client):
        resp = client.get("/a2a/unknown/.well-known/agent.json")
        assert resp.status_code == 404

    def test_list_agent_cards(self, client):
        resp = client.get("/a2a/.well-known/agents.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "researcher" in data
        assert "orchestrator" in data

    def test_jsonrpc_unknown_method(self, client):
        resp = client.post(
            "/a2a/researcher",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "unknown/method",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"]["code"] == -32601

    def test_jsonrpc_unknown_agent(self, client):
        resp = client.post(
            "/a2a/unknown",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/send",
            },
        )
        assert resp.status_code == 404

    def test_tasks_get_missing_id(self, client):
        resp = client.post(
            "/a2a/researcher",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/get",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"]["code"] == -32602

    def test_tasks_cancel_missing_id(self, client):
        resp = client.post(
            "/a2a/researcher",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/cancel",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"]["code"] == -32602
