"""Security checks for untrusted customer messages and prompt injection defense."""
import re
from typing import Tuple, Optional

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+|your\s+)?(instructions|rules|directives)",
    r"cancel\s+(this\s+|the\s+)?invoice",
    r"waive\s+(this\s+|the\s+)?(debt|balance|amount)",
    r"disregard\s+(all\s+)?(previous\s+)?(instructions|rules)",
    r"system\s+prompt",
    r"developer\s+mode",
    r"admin\s+override",
    r"set\s+balance\s+to\s+0",
    r"mark\s+(as\s+)?paid",
    r"grant\s+(100%|full)\s+discount",
    r"you\s+are\s+now\s+a",
    r"forget\s+(all\s+)?your\s+rules",
    r"override\s+(the\s+)?policy",
]

INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_injection, reason).
    Classifies untrusted input as adversarial if it attempts rule overriding,
    financial write-offs, or prompt injection.
    """
    if not text:
        return False, None
    match = INJECTION_REGEX.search(text)
    if match:
        matched_phrase = match.group(0)
        return True, (
            f"Adversarial instruction override detected ('{matched_phrase}'). "
            "Untrusted customer input is classified as evidence and rejected by the policy check."
        )
    return False, None
