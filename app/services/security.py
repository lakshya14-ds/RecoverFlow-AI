"""Supplementary detection of untrusted instructions; authority is enforced separately."""
import html
import re
import unicodedata


def normalize_untrusted(text: str) -> str:
    text = html.unescape(unicodedata.normalize("NFKC", text or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return re.sub(r"\s+", " ", text).casefold()


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+|your\s+)?(instructions|rules|directives)",
    r"cancel\s+(this\s+|the\s+)?invoice",
    r"waive\s+(this\s+|the\s+)?(debt|balance|amount)",
    r"disregard\s+(all\s+)?(previous\s+)?(instructions|rules)",
    r"system\s+prompt", r"developer\s+mode", r"admin\s+override",
    r"set\s+balance\s+to\s+0", r"mark\s+(as\s+)?paid",
    r"grant\s+(100%|full)\s+discount", r"you\s+are\s+now\s+a",
    r"forget\s+(all\s+)?your\s+rules", r"override\s+(the\s+)?policy",
    r"(?:niyam|rules|instructions|nirdesh).{0,30}(?:bhool|ignore|hata)",
    r"(?:invoice|bill|karz|balance).{0,25}(?:maaf|radd|cancel|zero|shunya)",
    r"(?:नियम|निर्देश).{0,30}(?:भूल|अनदेखा)",
    r"(?:बिल|इनवॉइस|कर्ज|बकाया).{0,30}(?:माफ|रद्द|शून्य)",
]
INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(text: str) -> tuple[bool, str | None]:
    match = INJECTION_REGEX.search(normalize_untrusted(text))
    if match:
        return True, ("Adversarial instruction override detected. Untrusted customer input "
                      "is retained as evidence and cannot authorize an action.")
    return False, None
