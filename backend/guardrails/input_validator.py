"""
Input validation guardrails — prompt injection detection and input length checks.
"""

import re


# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions|prompts|rules|guidelines)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*system\s*:\s*", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*###?\s*(system|instruction|prompt)\s*(message|override)?:?\s*", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"show\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(your\s+)?(previous\s+)?(instructions|rules|training)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if|though)\s+you\s+(have\s+)?no\s+(rules|restrictions|guidelines)", re.IGNORECASE),
    re.compile(r"override\s+(your\s+)?(safety|content)\s+(filter|policy|rules)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<\|im_start\|>", re.IGNORECASE),
]


class InputGuardrail:
    """Validates user inputs for safety before processing."""

    def __init__(self, max_input_length: int = 10000):
        self.max_input_length = max_input_length

    def check_prompt_injection(self, text: str) -> tuple[bool, str | None]:
        """
        Check if the input contains prompt injection patterns.

        Returns:
            (is_safe, reason) — is_safe=False means injection detected.
        """
        for pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return False, f"Potential prompt injection detected: '{match.group().strip()}'"
        return True, None

    def check_input_length(self, text: str) -> tuple[bool, str | None]:
        """
        Check if the input exceeds the maximum allowed length.

        Returns:
            (is_valid, reason)
        """
        if len(text) > self.max_input_length:
            return False, f"Input exceeds maximum length ({len(text)} > {self.max_input_length} chars)"
        return True, None

    def validate(self, text: str) -> tuple[bool, list[str]]:
        """
        Run all input validations.

        Returns:
            (is_valid, list_of_issues)
        """
        issues: list[str] = []

        safe, reason = self.check_prompt_injection(text)
        if not safe:
            issues.append(reason)

        valid, reason = self.check_input_length(text)
        if not valid:
            issues.append(reason)

        return len(issues) == 0, issues
