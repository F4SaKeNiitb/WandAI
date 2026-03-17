"""
Tests for the Orchestrator planning, routing, and aggregation logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from core.state import (
    AgentState, ExecutionStatus, StepStatus, PlanStep, AgentType
)
from core.orchestrator import Orchestrator
from core.state_utils import get_state_attr, get_step_status


# ============================================================
# Helper Fixtures
# ============================================================

@pytest.fixture
def orchestrator():
    """Create an Orchestrator with a mocked LLM."""
    with patch('core.orchestrator.get_llm') as mock_llm:
        mock_llm.return_value = MagicMock()
        orch = Orchestrator(event_callback=AsyncMock())
        return orch


@pytest.fixture
def sample_state_dict():
    """Create a sample state as dict (as LangGraph provides)."""
    return {
        "session_id": "test-session-123",
        "user_request": "Analyze sales data for Q4",
        "clarity_score": 10,
        "clarifying_questions": [],
        "user_clarifications": [],
        "plan": [],
        "current_step_index": 0,
        "artifacts": {},
        "logs": [],
        "final_response": None,
        "status": ExecutionStatus.PENDING,
        "error_message": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "requires_approval": False,
        "approval_message": None,
        "conversation_history": [],
        "pending_refinement": None,
        "step_clarification_step_id": None,
        "step_clarification_questions": [],
        "step_clarifications": {},
    }


@pytest.fixture
def sample_plan():
    """Create a sample plan with dependencies."""
    return [
        {
            "id": "step1",
            "description": "Research Q4 sales data",
            "agent_type": "researcher",
            "dependencies": [],
            "status": "pending",
            "result": None,
            "error": None,
            "retry_count": 0,
        },
        {
            "id": "step2",
            "description": "Analyze the data using pandas",
            "agent_type": "coder",
            "dependencies": ["step1"],
            "status": "pending",
            "result": None,
            "error": None,
            "retry_count": 0,
        },
        {
            "id": "step3",
            "description": "Create visualization chart",
            "agent_type": "analyst",
            "dependencies": ["step1"],
            "status": "pending",
            "result": None,
            "error": None,
            "retry_count": 0,
        },
        {
            "id": "step4",
            "description": "Write summary report",
            "agent_type": "writer",
            "dependencies": ["step2", "step3"],
            "status": "pending",
            "result": None,
            "error": None,
            "retry_count": 0,
        },
    ]


# ============================================================
# Routing Tests
# ============================================================

class TestRouteToAgent:

    @pytest.mark.asyncio
    async def test_routes_first_pending_step(self, orchestrator, sample_state_dict, sample_plan):
        sample_state_dict['plan'] = sample_plan
        agent_type, step = await orchestrator.route_to_agent(sample_state_dict)
        assert agent_type == "researcher"
        assert step.id == "step1"

    @pytest.mark.asyncio
    async def test_skips_blocked_steps(self, orchestrator, sample_state_dict, sample_plan):
        """step2 and step3 depend on step1, so they should be skipped if step1 is pending."""
        sample_plan[0]['status'] = 'in_progress'  # step1 running
        sample_state_dict['plan'] = sample_plan
        agent_type, step = await orchestrator.route_to_agent(sample_state_dict)
        # No step should be routable (step2/3 depend on step1 which isn't complete)
        assert agent_type is None
        assert step is None

    @pytest.mark.asyncio
    async def test_routes_after_dependency_met(self, orchestrator, sample_state_dict, sample_plan):
        """After step1 completes, step2 and step3 should be routable."""
        sample_plan[0]['status'] = 'completed'
        sample_state_dict['plan'] = sample_plan
        agent_type, step = await orchestrator.route_to_agent(sample_state_dict)
        # Either step2 or step3 (both have step1 as sole dependency)
        assert agent_type in ["coder", "analyst"]

    @pytest.mark.asyncio
    async def test_returns_none_when_all_completed(self, orchestrator, sample_state_dict, sample_plan):
        for s in sample_plan:
            s['status'] = 'completed'
        sample_state_dict['plan'] = sample_plan
        agent_type, step = await orchestrator.route_to_agent(sample_state_dict)
        assert agent_type is None
        assert step is None

    @pytest.mark.asyncio
    async def test_routes_retrying_step(self, orchestrator, sample_state_dict, sample_plan):
        sample_plan[0]['status'] = 'retrying'
        sample_state_dict['plan'] = sample_plan
        agent_type, step = await orchestrator.route_to_agent(sample_state_dict)
        assert step.id == "step1"


# ============================================================
# Parallel Execution Tests
# ============================================================

class TestGetAllExecutableSteps:

    @pytest.mark.asyncio
    async def test_parallel_steps_detected(self, orchestrator, sample_state_dict, sample_plan):
        """step2 and step3 both depend only on step1. If step1 is done, both are executable."""
        sample_plan[0]['status'] = 'completed'
        sample_state_dict['plan'] = sample_plan
        executable = await orchestrator.get_all_executable_steps(sample_state_dict)
        assert len(executable) == 2
        step_ids = {s.id for _, s in executable}
        assert step_ids == {"step2", "step3"}

    @pytest.mark.asyncio
    async def test_single_root_step(self, orchestrator, sample_state_dict, sample_plan):
        """Only step1 has no deps initially."""
        sample_state_dict['plan'] = sample_plan
        executable = await orchestrator.get_all_executable_steps(sample_state_dict)
        assert len(executable) == 1
        assert executable[0][1].id == "step1"

    @pytest.mark.asyncio
    async def test_no_executable_when_all_done(self, orchestrator, sample_state_dict, sample_plan):
        for s in sample_plan:
            s['status'] = 'completed'
        sample_state_dict['plan'] = sample_plan
        executable = await orchestrator.get_all_executable_steps(sample_state_dict)
        assert len(executable) == 0

    @pytest.mark.asyncio
    async def test_blocked_steps_not_executable(self, orchestrator, sample_state_dict, sample_plan):
        """step4 depends on step2 AND step3. If only step2 is done, step4 is NOT executable."""
        sample_plan[0]['status'] = 'completed'
        sample_plan[1]['status'] = 'completed'  # step2 done
        # step3 still pending
        sample_state_dict['plan'] = sample_plan
        executable = await orchestrator.get_all_executable_steps(sample_state_dict)
        step_ids = {s.id for _, s in executable}
        assert "step4" not in step_ids
        assert "step3" in step_ids


# ============================================================
# Handle Step Result Tests
# ============================================================

class TestHandleStepResult:

    @pytest.mark.asyncio
    async def test_successful_step(self, orchestrator, sample_state_dict, sample_plan):
        sample_state_dict['plan'] = sample_plan
        state = await orchestrator.handle_step_result(
            sample_state_dict, "step1", True, result="Found sales data"
        )
        step1 = state['plan'][0]
        assert step1['status'] == 'completed'
        assert step1['result'] == "Found sales data"

    @pytest.mark.asyncio
    async def test_failed_step_retries(self, orchestrator, sample_state_dict, sample_plan):
        sample_state_dict['plan'] = sample_plan
        state = await orchestrator.handle_step_result(
            sample_state_dict, "step1", False, error="Connection timeout"
        )
        step1 = state['plan'][0]
        assert step1['status'] == 'retrying'
        assert step1['retry_count'] == 1

    @pytest.mark.asyncio
    async def test_failed_step_marks_failed_after_max_retries(self, orchestrator, sample_state_dict, sample_plan):
        sample_plan[0]['retry_count'] = 2  # Already retried twice
        sample_state_dict['plan'] = sample_plan
        state = await orchestrator.handle_step_result(
            sample_state_dict, "step1", False, error="Persistent error"
        )
        step1 = state['plan'][0]
        assert step1['status'] == 'failed'

    @pytest.mark.asyncio
    async def test_unknown_step_id_noop(self, orchestrator, sample_state_dict, sample_plan):
        sample_state_dict['plan'] = sample_plan
        state = await orchestrator.handle_step_result(
            sample_state_dict, "nonexistent", True, result="data"
        )
        # All steps should remain unchanged
        for s in state['plan']:
            assert s['status'] == 'pending'


# ============================================================
# Ambiguity Check Tests
# ============================================================

class TestCheckAmbiguity:

    @pytest.mark.asyncio
    async def test_skips_if_already_clarified(self, orchestrator, sample_state_dict):
        sample_state_dict['user_clarifications'] = ["Yes, I mean Q4 2024"]
        state = await orchestrator.check_ambiguity(sample_state_dict)
        assert state['clarity_score'] == 10
        assert state['status'] == ExecutionStatus.PLANNING

    @pytest.mark.asyncio
    async def test_skips_if_request_contains_clarifications(self, orchestrator, sample_state_dict):
        sample_state_dict['user_request'] = "Original request\n\nClarifications:\n- Q4 2024"
        state = await orchestrator.check_ambiguity(sample_state_dict)
        assert state['clarity_score'] == 10


# ============================================================
# State Utils Integration
# ============================================================

class TestStateUtils:

    def test_get_state_attr_dict(self, sample_state_dict):
        assert get_state_attr(sample_state_dict, 'user_request') == "Analyze sales data for Q4"
        assert get_state_attr(sample_state_dict, 'nonexistent', 'default') == 'default'

    def test_get_state_attr_object(self):
        state = AgentState(user_request="test request")
        assert get_state_attr(state, 'user_request') == "test request"

    def test_get_step_status_dict(self, sample_plan):
        assert get_step_status(sample_plan[0]) == "pending"
        sample_plan[0]['status'] = StepStatus.COMPLETED
        assert get_step_status(sample_plan[0]) == "completed"

    def test_get_step_status_string(self, sample_plan):
        sample_plan[0]['status'] = "completed"
        assert get_step_status(sample_plan[0]) == "completed"
