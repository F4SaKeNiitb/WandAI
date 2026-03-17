"""
Tests for agent retry logic, self-correction, and context extraction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from core.state import AgentState, ExecutionStatus, PlanStep, StepStatus, AgentType
from agents.base import BaseAgent


class ConcreteTestAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""
    agent_type = AgentType.RESEARCHER
    system_prompt = "You are a test agent."

    def __init__(self, execute_results=None, **kwargs):
        with patch('core.llm.get_llm', return_value=MagicMock()):
            super().__init__(**kwargs)
        self._execute_results = execute_results or []
        self._call_count = 0

    async def execute(self, state, step_id, task_description):
        if self._call_count < len(self._execute_results):
            result = self._execute_results[self._call_count]
            self._call_count += 1
            return result
        return True, "default result", None


@pytest.fixture
def state_dict():
    return {
        "session_id": "test-123",
        "user_request": "Test request",
        "plan": [
            {
                "id": "s1",
                "description": "Step 1",
                "agent_type": "researcher",
                "dependencies": [],
                "status": "completed",
                "result": "Step 1 result data",
                "error": None,
                "retry_count": 0,
            },
            {
                "id": "s2",
                "description": "Step 2",
                "agent_type": "coder",
                "dependencies": ["s1"],
                "status": "pending",
                "result": None,
                "error": None,
                "retry_count": 0,
            },
        ],
        "artifacts": {
            "art1": {
                "id": "art1",
                "name": "Research Results",
                "type": "text",
                "content": "Some research content here",
                "created_by": "researcher",
                "step_id": "s1",
            }
        },
        "logs": [],
        "status": ExecutionStatus.EXECUTING,
        "step_clarifications": {},
        "conversation_history": [],
    }


class TestGetContextFromState:

    def test_extracts_user_request(self, state_dict):
        agent = ConcreteTestAgent()
        context = agent.get_context_from_state(state_dict)
        assert "Test request" in context

    def test_includes_completed_step_results(self, state_dict):
        agent = ConcreteTestAgent()
        context = agent.get_context_from_state(state_dict)
        assert "Step 1 result data" in context
        assert "s1" in context

    def test_excludes_pending_step_results(self, state_dict):
        agent = ConcreteTestAgent()
        context = agent.get_context_from_state(state_dict)
        assert "s2" not in context or "Step 2" not in context

    def test_includes_artifact_content(self, state_dict):
        agent = ConcreteTestAgent()
        context = agent.get_context_from_state(state_dict)
        assert "Research Results" in context
        assert "Some research content" in context

    def test_works_with_agent_state_object(self):
        state = AgentState(user_request="Object request")
        agent = ConcreteTestAgent()
        context = agent.get_context_from_state(state)
        assert "Object request" in context


class TestRetryLogic:

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self, state_dict):
        agent = ConcreteTestAgent(
            execute_results=[(True, "success", None)]
        )
        with patch.object(agent, 'check_task_clarity', new_callable=AsyncMock, return_value=(True, [])):
            success, result, error = await agent.execute_with_retry(
                state_dict, "s2", "Do something", max_retries=3
            )
        assert success
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, state_dict):
        agent = ConcreteTestAgent(
            execute_results=[
                (False, None, "Error 1"),
                (False, None, "Error 2"),
                (True, "success on 3rd", None),
            ]
        )
        with patch.object(agent, 'check_task_clarity', new_callable=AsyncMock, return_value=(True, [])):
            success, result, error = await agent.execute_with_retry(
                state_dict, "s2", "Do something", max_retries=3
            )
        assert success
        assert result == "success on 3rd"
        assert agent._call_count == 3

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self, state_dict):
        agent = ConcreteTestAgent(
            execute_results=[
                (False, None, "Error 1"),
                (False, None, "Error 2"),
                (False, None, "Error 3"),
            ]
        )
        with patch.object(agent, 'check_task_clarity', new_callable=AsyncMock, return_value=(True, [])):
            success, result, error = await agent.execute_with_retry(
                state_dict, "s2", "Do something", max_retries=3
            )
        assert not success
        assert error == "Error 3"

    @pytest.mark.asyncio
    async def test_clarification_request_returned(self, state_dict):
        agent = ConcreteTestAgent()
        with patch.object(agent, 'check_task_clarity', new_callable=AsyncMock,
                          return_value=(False, ["What data format?"])):
            success, result, error = await agent.execute_with_retry(
                state_dict, "s2", "Do something", max_retries=3
            )
        assert not success
        assert isinstance(result, dict)
        assert result["needs_clarification"] is True
        assert "What data format?" in result["questions"]

    @pytest.mark.asyncio
    async def test_skips_clarity_check_when_clarifications_provided(self, state_dict):
        state_dict['step_clarifications'] = {"s2": ["Use CSV format"]}
        agent = ConcreteTestAgent(
            execute_results=[(True, "done with clarification", None)]
        )
        clarity_mock = AsyncMock(return_value=(True, []))
        with patch.object(agent, 'check_task_clarity', clarity_mock):
            success, result, error = await agent.execute_with_retry(
                state_dict, "s2", "Do something", max_retries=3
            )
        assert success
        # check_task_clarity should NOT have been called
        clarity_mock.assert_not_called()
