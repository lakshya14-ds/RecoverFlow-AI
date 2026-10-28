"""Deterministic undisputed-balance negotiation and outbound guard."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_UP
import hashlib
import re

from app.services.receivables import split_balance
from app.services.security import detect_prompt_injection, normalize_untrusted


def money(cents: int) -> str:
    return f"INR {Decimal(cents) / Decimal(100):,.2f}"


def offer_ladder(db, invoice, session, round_number: int) -> dict:
    split = split_balance(db, invoice)
    undisputed = split["undisputed_cents"]
    if undisputed <= 0:
        raise ValueError("No undisputed amount remains to negotiate")
    if round_number < 1 or round_number > session.max_ai_rounds:
        raise ValueError("AI negotiation round limit reached")
    instalments = min(max(1, round_number), session.max_instalments)
    first = int((Decimal(undisputed) * Decimal(session.min_first_percent) /
                 Decimal(100)).quantize(Decimal("1"), rounding=ROUND_UP))
    if instalments == 1:
        amounts = [undisputed]
    else:
        remaining = undisputed - first
        each = remaining // (instalments - 1)
        amounts = [first] + [each] * (instalments - 2) + [remaining - each * (instalments - 2)]
    extension = min(session.max_extension_days, 7 * round_number)
    due = date.today() + timedelta(days=extension)
    return {"undisputed_cents": undisputed, "disputed_cents": split["disputed_cents"],
            "instalments_cents": amounts, "due_date": due.isoformat(),
            "round": round_number, "extension_days": extension}


def phrase_offer(invoice, offer: dict) -> str:
    instalments = offer["instalments_cents"]
    if len(instalments) == 1:
        terms = f"Please pay the undisputed {money(instalments[0])} by {offer['due_date']}."
    else:
        pieces = ", ".join(money(amount) for amount in instalments)
        terms = (f"For the undisputed {money(offer['undisputed_cents'])}, "
                 f"we can arrange {len(instalments)} instalments ({pieces}) "
                 f"with the schedule ending by {offer['due_date']}.")
    disputed = offer["disputed_cents"]
    note = (f" The disputed {money(disputed)} remains open for review and is not part of this request."
            if disputed else "")
    return f"Regarding invoice {invoice.invoice_number}: {terms}{note}"


def guard_outbound(body: str, disputed_cents: int,
                   undisputed_cents: int | None = None, *,
                   allowed_instalments: list[int] | None = None) -> tuple[bool, str | None]:
    """Check financial mentions against server facts, with conservative language limits."""
    if not body or len(body) > 2000:
        return False, "Message length is invalid"
    text = normalize_untrusted(body)
    if detect_prompt_injection(text)[0]:
        return False, "Adversarial instruction or waiver text is blocked"
    if re.search(r"https?://|www\.|[\w.+-]+@[\w.-]+|\b(?:upi|bank account|pay to)\b", text):
        return False, "Payment destinations require a verified payment-link workflow"
    if re.search(r"\b(waiv(?:e|ed|ing)|forgiv(?:e|en)|write[ -]?off|cancel|concede|refund|credit note|maaf|radd)\b|माफ|रद्द", text):
        return False, "A waiver, refund, credit note, or cancellation is blocked"
    if disputed_cents and re.search(r"\bdisput(?:e|ed)\b.{0,65}\b(settled|paid|zero|closed|resolved)\b", text):
        return False, "The disputed amount must remain open"
    if re.search(r"\b(?:pay|transfer|send|collect|settle)\b[^.!?]{0,45}\bdisputed\b", text):
        return False, "A disputed amount cannot be requested"
    if re.search(r"\b(?:twice|double|additional|extra|times|lakh|crore|thousand|hundred)\b|हजार|लाख|करोड़", text):
        return False, "Use explicit numeric amounts from a structured offer"
    amounts = re.compile(r"(?:\b(?:inr|usd|eur|gbp|rs\.?|rupees)\s*|[₹$€£]\s*)([0-9][0-9,]*(?:\.[0-9]+)?)(?![0-9])", re.I)
    spans = []
    permitted = {undisputed_cents} | set(allowed_instalments or [])
    for match in amounts.finditer(text):
        raw = match.group(1)
        if ',' in raw and not re.fullmatch(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]{1,2})?", raw):
            return False, "Invalid monetary grouping"
        value = Decimal(raw.replace(',', '')) * 100
        if value != value.to_integral_value():
            return False, "Amounts must have at most two decimal places"
        prefix = text[max(0, match.start()-55):match.start()]
        disputed_mention = bool(re.search(r"(?:\bdisputed|(?<!\S)विवादित)\s*(?:(?:amount|balance|portion|rashi|राशि)\s*)?(?:(?:is|of|:)\s*)?$", prefix))
        if disputed_mention:
            if int(value) != disputed_cents:
                return False, "Stated disputed amount does not match the ledger"
        elif undisputed_cents is not None and int(value) not in permitted:
            return False, "Amount is not part of the server-calculated balance or offer"
        spans.append(match.span())
    remainder = text
    for start, end in reversed(spans):
        remainder = remainder[:start] + " VERIFIED_AMOUNT " + remainder[end:]
    if re.search(r"\b(?:pay|transfer|send|settle|payment|bhugtan)\s+(?:of\s+)?(?:[0-9]|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b|ten\b|fifty\b|sixty\b)|भुगतान\s*[0-9]", remainder):
        return False, "Payment amounts require an explicit currency and verified numeric amount"
    return True, None


def classify_inbound(body: str) -> str:
    if detect_prompt_injection(body)[0]:
        return "injection"
    if re.search(r"\b(lawyer|legal action|court|sue|notice)\b", body, re.IGNORECASE):
        return "legal_threat"
    if re.search(r"\b(angry|furious|harass|stop bothering)\b", body, re.IGNORECASE):
        return "anger"
    if re.search(r"\b(promise|will pay|i'll pay)\b", body, re.IGNORECASE):
        return "commitment"
    if re.search(r"\b(dispute|wrong item|shortfall|damaged)\b", body, re.IGNORECASE):
        return "dispute"
    if re.search(r"\b(more time|instalment|installment|extend|later)\b", body, re.IGNORECASE):
        return "haggling"
    folded = normalize_untrusted(body)
    for label, keywords in (
            ("commitment", ("wada", "vada", "karenge", "denge", "pay karenge", "bhej denge", "वादा", "करेंगे", "देंगे")),
            ("dispute", ("galat", "vivaad", "vivad", "kami", "toota", "kharab", "गलत", "विवाद", "कमी", "टूटा", "खराब")),
            ("haggling", ("mohlat", "samay", "kist", "thode", "zyada", "baad", "मोहलत", "समय", "किस्त", "थोड़ा", "बाद")),
            ("anger", ("gussa", "pareshan", "tang", "गुस्सा", "परेशान", "तंग")),
            ("legal_threat", ("vakeel", "kanooni", "case karenge", "वकील", "कानूनी", "कोर्ट"))):
        if any(keyword in folded for keyword in keywords):
            return label
    return "ambiguous"


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
