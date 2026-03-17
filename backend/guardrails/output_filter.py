"""
Output filtering guardrails — PII redaction and content safety checks.
"""

import re

# PII detection patterns
_PII_PATTERNS: dict[str, re.Pattern] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "PHONE": re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"
    ),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "IP_ADDRESS": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
}

# Unsafe content patterns (basic heuristic)
_UNSAFE_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:how\s+to\s+)?(?:make|build|create)\s+(?:a\s+)?(?:bomb|explosive|weapon)", re.IGNORECASE),
    re.compile(r"(?:hack|exploit|compromise)\s+(?:into|a)\s+(?:bank|government|military)", re.IGNORECASE),
]


class OutputGuardrail:
    """Filters agent outputs for PII and unsafe content."""

    def __init__(self, pii_redaction: bool = True):
        self.pii_redaction = pii_redaction

    def redact_pii(self, text: str) -> tuple[str, list[dict]]:
        """
        Redact PII from text.

        Returns:
            (redacted_text, list of redaction records)
        """
        if not self.pii_redaction:
            return text, []

        redactions: list[dict] = []
        result = text
        for pii_type, pattern in _PII_PATTERNS.items():
            matches = list(pattern.finditer(result))
            if matches:
                redactions.append({
                    "type": pii_type,
                    "count": len(matches),
                })
                result = pattern.sub(f"[REDACTED_{pii_type}]", result)

        return result, redactions

    def check_content_safety(self, text: str) -> tuple[bool, str | None]:
        """
        Basic content safety check on output.

        Returns:
            (is_safe, reason)
        """
        for pattern in _UNSAFE_PATTERNS:
            match = pattern.search(text)
            if match:
                return False, f"Potentially unsafe content detected"
        return True, None

    def filter(self, text: str) -> tuple[str, list[dict]]:
        """
        Run all output filters.

        Returns:
            (filtered_text, list of applied filters)
        """
        filters_applied: list[dict] = []

        # PII redaction
        text, redactions = self.redact_pii(text)
        if redactions:
            filters_applied.append({"type": "pii_redaction", "redactions": redactions})

        # Content safety (log but don't block — agents should produce safe content)
        is_safe, reason = self.check_content_safety(text)
        if not is_safe:
            filters_applied.append({"type": "content_safety", "reason": reason})

        return text, filters_applied
