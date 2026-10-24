"""Deterministic undisputed-balance negotiation and outbound guard."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_UP
import hashlib
import re

from app.services.receivables import split_balance
from app.services.security import detect_prompt_injection


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
                   undisputed_cents: int | None = None) -> tuple[bool, str | None]:
    if not body or len(body) > 2000:
        return False, "Message length is invalid"
    if detect_prompt_injection(body)[0]:
        return False, "Adversarial instruction or waiver text is blocked"
    if re.search(r"\b(waiv(?:e|ed|ing)|forgiv(?:e|en)|write[ -]?off|cancel|concede|refund|credit note)\b",
                 body, re.IGNORECASE):
        return False, "A waiver, refund, credit note, or cancellation is blocked"
    if disputed_cents and re.search(r"\bdisput(?:e|ed)\b.{0,65}\b(settled|paid|zero|closed|resolved)\b",
                                     body, re.IGNORECASE):
        return False, "The disputed amount must remain open"
    stated = re.search(r"\bdisputed\s+(?:amount|balance|portion)?\s*(?:is|of|:)\s*(?:INR|₹)\s*([\d,]+(?:\.\d{1,2})?)",
                       body, re.IGNORECASE)
    if stated:
        parsed = Decimal(stated.group(1).replace(",", ""))
        if parsed != Decimal(disputed_cents) / Decimal(100):
            return False, "Stated disputed amount does not match the ledger"
    if undisputed_cents is not None:
        for match in re.finditer(
            r"\b(?:pay|payment|transfer|send|settle)\b.{0,75}?(?:INR|₹)\s*([\d,]+(?:\.\d{1,2})?)",
            body, re.IGNORECASE):
            requested = Decimal(match.group(1).replace(",", ""))
            if requested > Decimal(undisputed_cents) / Decimal(100):
                return False, "Requested payment exceeds the undisputed balance"
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
    return "ambiguous"


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
