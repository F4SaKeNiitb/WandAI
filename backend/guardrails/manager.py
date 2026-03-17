"""
GuardrailsManager — orchestrates input validation and output filtering.
"""

from guardrails.input_validator import InputGuardrail
from guardrails.output_filter import OutputGuardrail


class GuardrailsManager:
    """Central manager for all guardrail checks."""

    def __init__(
        self,
        enabled: bool = True,
        pii_redaction: bool = True,
        injection_detection: bool = True,
        max_input_length: int = 10000,
    ):
        self.enabled = enabled
        self.input_guardrail = InputGuardrail(max_input_length=max_input_length)
        self.output_guardrail = OutputGuardrail(pii_redaction=pii_redaction)
        self.injection_detection = injection_detection

    def check_input(self, text: str) -> tuple[bool, list[str]]:
        """
        Validate user input through all input guardrails.

        Returns:
            (is_valid, list_of_issues)
        """
        if not self.enabled:
            return True, []

        issues: list[str] = []

        if self.injection_detection:
            safe, reason = self.input_guardrail.check_prompt_injection(text)
            if not safe:
                issues.append(reason)

        valid, reason = self.input_guardrail.check_input_length(text)
        if not valid:
            issues.append(reason)

        return len(issues) == 0, issues

    def filter_output(self, text: str) -> tuple[str, list[dict]]:
        """
        Filter agent output through all output guardrails.

        Returns:
            (filtered_text, list_of_applied_filters)
        """
        if not self.enabled:
            return text, []

        return self.output_guardrail.filter(text)
