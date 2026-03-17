"""
MetricsStore — in-memory storage for evaluation results with aggregation.
"""

from threading import Lock
from evaluation.judge import EvalResult


class MetricsStore:
    """Stores and aggregates LLM-as-judge evaluation results."""

    def __init__(self):
        self._step_evals: list[dict] = []  # per-step evaluations
        self._session_evals: list[dict] = []  # per-session evaluations
        self._lock = Lock()

    def record_step_eval(
        self,
        session_id: str,
        step_id: str,
        agent_type: str,
        eval_result: EvalResult,
    ):
        """Record a step-level evaluation."""
        with self._lock:
            self._step_evals.append({
                "session_id": session_id,
                "step_id": step_id,
                "agent_type": agent_type,
                **eval_result.to_dict(),
            })

    def record_session_eval(self, session_id: str, eval_result: EvalResult):
        """Record a session-level evaluation."""
        with self._lock:
            self._session_evals.append({
                "session_id": session_id,
                **eval_result.to_dict(),
            })

    def get_session_metrics(self, session_id: str) -> dict:
        """Get all evaluations for a session."""
        with self._lock:
            steps = [e for e in self._step_evals if e["session_id"] == session_id]
            session = [e for e in self._session_evals if e["session_id"] == session_id]

        avg_overall = (
            sum(e["overall"] for e in steps) / len(steps) if steps else 0.0
        )
        return {
            "session_id": session_id,
            "step_evaluations": steps,
            "session_evaluation": session[0] if session else None,
            "average_step_score": round(avg_overall, 2),
            "step_count": len(steps),
        }

    def get_agent_metrics(self, agent_type: str) -> dict:
        """Get aggregated metrics for an agent type."""
        with self._lock:
            evals = [e for e in self._step_evals if e["agent_type"] == agent_type]

        if not evals:
            return {"agent_type": agent_type, "eval_count": 0}

        avg_relevance = sum(e["relevance"] for e in evals) / len(evals)
        avg_completeness = sum(e["completeness"] for e in evals) / len(evals)
        avg_accuracy = sum(e["accuracy"] for e in evals) / len(evals)
        avg_overall = sum(e["overall"] for e in evals) / len(evals)

        return {
            "agent_type": agent_type,
            "eval_count": len(evals),
            "avg_relevance": round(avg_relevance, 2),
            "avg_completeness": round(avg_completeness, 2),
            "avg_accuracy": round(avg_accuracy, 2),
            "avg_overall": round(avg_overall, 2),
        }

    def get_overall_metrics(self) -> dict:
        """Get overall metrics across all agents and sessions."""
        with self._lock:
            step_evals = list(self._step_evals)
            session_evals = list(self._session_evals)

        agent_types = set(e["agent_type"] for e in step_evals)
        by_agent = {}
        for at in agent_types:
            at_evals = [e for e in step_evals if e["agent_type"] == at]
            by_agent[at] = {
                "count": len(at_evals),
                "avg_overall": round(
                    sum(e["overall"] for e in at_evals) / len(at_evals), 2
                ),
            }

        avg_session = (
            sum(e["overall"] for e in session_evals) / len(session_evals)
            if session_evals
            else 0.0
        )

        return {
            "total_step_evaluations": len(step_evals),
            "total_session_evaluations": len(session_evals),
            "avg_session_score": round(avg_session, 2),
            "by_agent": by_agent,
        }
