"""
LLM-as-Judge evaluation — scores agent outputs on relevance, completeness, and accuracy.
"""

from dataclasses import dataclass, field
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from core.llm import get_llm
from core.logging import get_logger

logger = get_logger("EVAL")


@dataclass
class EvalResult:
    """Result of an LLM-as-judge evaluation."""

    relevance: float = 0.0  # 0-10
    completeness: float = 0.0  # 0-10
    accuracy: float = 0.0  # 0-10
    overall: float = 0.0  # 0-10
    reasoning: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "relevance": self.relevance,
            "completeness": self.completeness,
            "accuracy": self.accuracy,
            "overall": self.overall,
            "reasoning": self.reasoning,
            "evaluated_at": self.evaluated_at,
        }


class LLMJudge:
    """Evaluates agent outputs using an LLM-as-judge approach."""

    def __init__(self):
        self.llm = get_llm()

    async def evaluate_step(
        self, task_description: str, result: str
    ) -> EvalResult:
        """
        Evaluate a single step's output.

        Scores on relevance, completeness, and accuracy (0-10).
        """
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a quality evaluator for AI agent outputs. Score the result on three dimensions:
1. **Relevance** (0-10): Does the result address what was asked?
2. **Completeness** (0-10): Does it cover all aspects of the task?
3. **Accuracy** (0-10): Is the information correct and well-reasoned?

Respond in JSON:
{{
    "relevance": <float 0-10>,
    "completeness": <float 0-10>,
    "accuracy": <float 0-10>,
    "overall": <float 0-10>,
    "reasoning": "<brief explanation>"
}}""",
                ),
                (
                    "user",
                    "Task: {task}\n\nResult:\n{result}\n\nEvaluate this result.",
                ),
            ]
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            scores = await chain.ainvoke(
                {"task": task_description, "result": str(result)[:3000]}
            )
            return EvalResult(
                relevance=float(scores.get("relevance", 0)),
                completeness=float(scores.get("completeness", 0)),
                accuracy=float(scores.get("accuracy", 0)),
                overall=float(scores.get("overall", 0)),
                reasoning=scores.get("reasoning", ""),
            )
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            return EvalResult(reasoning=f"Evaluation failed: {e}")

    async def evaluate_session(
        self, user_request: str, final_response: str
    ) -> EvalResult:
        """Evaluate the final session response against the original request."""
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are evaluating the final output of a multi-agent AI system. Score how well the response satisfies the user's original request.

Dimensions:
1. **Relevance** (0-10): Does it answer what was asked?
2. **Completeness** (0-10): Are all parts of the request addressed?
3. **Accuracy** (0-10): Is the response accurate and well-structured?

Respond in JSON:
{{
    "relevance": <float 0-10>,
    "completeness": <float 0-10>,
    "accuracy": <float 0-10>,
    "overall": <float 0-10>,
    "reasoning": "<brief explanation>"
}}""",
                ),
                (
                    "user",
                    "Original Request: {request}\n\nFinal Response:\n{response}\n\nEvaluate.",
                ),
            ]
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            scores = await chain.ainvoke(
                {
                    "request": user_request,
                    "response": str(final_response)[:4000],
                }
            )
            return EvalResult(
                relevance=float(scores.get("relevance", 0)),
                completeness=float(scores.get("completeness", 0)),
                accuracy=float(scores.get("accuracy", 0)),
                overall=float(scores.get("overall", 0)),
                reasoning=scores.get("reasoning", ""),
            )
        except Exception as e:
            logger.warning(f"Session evaluation failed: {e}")
            return EvalResult(reasoning=f"Evaluation failed: {e}")
