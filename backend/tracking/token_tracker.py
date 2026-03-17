"""
Per-session, per-agent token usage tracking with real-time cost estimation.
Provides granular LLM spend visibility across the multi-agent pipeline.
"""

from datetime import datetime
from threading import Lock


# Cost per 1K tokens (input, output) for common models
COST_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    # Gemini models
    "gemini-2.0-flash": (0.0001, 0.0004),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "gemini-1.5-pro": (0.00125, 0.005),
    "gemini-2.0-pro": (0.00125, 0.005),
    # Anthropic Claude models
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5-20251001": (0.0008, 0.004),
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-haiku-20240307": (0.00025, 0.00125),
    # OpenAI models
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-3.5-turbo": (0.0005, 0.0015),
}

# Default cost if model not found
DEFAULT_COST_PER_1K = (0.001, 0.002)


class UsageRecord:
    """Single token usage record."""
    __slots__ = (
        "session_id", "agent_type", "step_id", "model",
        "input_tokens", "output_tokens", "estimated_cost", "timestamp",
    )

    def __init__(
        self,
        session_id: str,
        agent_type: str,
        step_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
    ):
        self.session_id = session_id
        self.agent_type = agent_type
        self.step_id = step_id
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.estimated_cost = estimated_cost
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "step_id": self.step_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost": self.estimated_cost,
            "timestamp": self.timestamp,
        }


class TokenTracker:
    """
    Tracks token usage and estimated costs across sessions and agents.
    Thread-safe in-memory store.
    """

    def __init__(self):
        self._records: list[UsageRecord] = []
        self._lock = Lock()

    def _calc_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        input_rate, output_rate = COST_PER_1K_TOKENS.get(model, DEFAULT_COST_PER_1K)
        return (input_tokens / 1000) * input_rate + (output_tokens / 1000) * output_rate

    def record_usage(
        self,
        session_id: str,
        agent_type: str,
        step_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageRecord:
        """Record a token usage event and return the record."""
        cost = self._calc_cost(model, input_tokens, output_tokens)
        record = UsageRecord(
            session_id=session_id,
            agent_type=agent_type,
            step_id=step_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=cost,
        )
        with self._lock:
            self._records.append(record)
        return record

    def get_session_usage(self, session_id: str) -> dict:
        """Get aggregated token usage for a session."""
        with self._lock:
            records = [r for r in self._records if r.session_id == session_id]

        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.estimated_cost for r in records)

        by_agent: dict[str, dict] = {}
        for r in records:
            if r.agent_type not in by_agent:
                by_agent[r.agent_type] = {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0, "calls": 0}
            by_agent[r.agent_type]["input_tokens"] += r.input_tokens
            by_agent[r.agent_type]["output_tokens"] += r.output_tokens
            by_agent[r.agent_type]["estimated_cost"] += r.estimated_cost
            by_agent[r.agent_type]["calls"] += 1

        return {
            "session_id": session_id,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "estimated_cost": round(total_cost, 6),
            "by_agent": by_agent,
            "call_count": len(records),
            "records": [r.to_dict() for r in records],
        }

    def get_agent_usage(self, agent_type: str) -> dict:
        """Get aggregated token usage for an agent type across all sessions."""
        with self._lock:
            records = [r for r in self._records if r.agent_type == agent_type]

        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.estimated_cost for r in records)
        sessions = set(r.session_id for r in records)

        return {
            "agent_type": agent_type,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "estimated_cost": round(total_cost, 6),
            "session_count": len(sessions),
            "call_count": len(records),
        }

    def get_overall_usage(self) -> dict:
        """Get overall usage across all sessions and agents."""
        with self._lock:
            records = list(self._records)

        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.estimated_cost for r in records)
        sessions = set(r.session_id for r in records)

        by_model: dict[str, dict] = {}
        for r in records:
            if r.model not in by_model:
                by_model[r.model] = {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0, "calls": 0}
            by_model[r.model]["input_tokens"] += r.input_tokens
            by_model[r.model]["output_tokens"] += r.output_tokens
            by_model[r.model]["estimated_cost"] += r.estimated_cost
            by_model[r.model]["calls"] += 1

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "estimated_cost": round(total_cost, 6),
            "session_count": len(sessions),
            "call_count": len(records),
            "by_model": by_model,
        }
