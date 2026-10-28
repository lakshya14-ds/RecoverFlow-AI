# P1 multilingual communication and queues (Milestone 4)

## Languages

`app/services/multilingual.py` supports English, Hindi, and Hinglish
classification and drafting. Detection is rules-based (Devanagari share,
then roman Hindi markers, else English); intent labels match the English
classifier, extended with Hindi/Hinglish keyword sets. Injection detection
was already multilingual and is unchanged.

Markers are elective Hindi only: grammar plus content words with an easy
English equivalent. Goods names, packaging terms, address tokens,
Indian-English business terms, English collisions, and personal names are
deliberately excluded so English text with Indian terms stays English (see
the documented list in `app/services/multilingual.py`). One known tradeoff:
the common verb `kar` can flip an English sentence mentioning the Bengali
surname Kar; drafts still need staff approval, which bounds the harm.

No multilingual reliability is claimed beyond the tested keyword/template
coverage; measured evaluation is M5 work.

## Structured message and triple validation

Every communication draft starts as a structured object (recipient, channel,
language, requested amount, currency, installment dates, dispute statement,
commitments, source IDs, case version) built from server facts. Validation
runs three times: on the object before wording, on the prose after wording,
and on the exact stored body at approval. Amounts, dates, negation, and the
disputed-versus-undisputed meaning must survive byte-identical; invented
commitments, unverified destinations, unauthorized concessions, stale
versions, and disputed-money requests are blocked.

Model wording is opt-in per task and rephrases only fact-free carrier
sentences; facts are server-spliced back and re-validated, with a template
fallback. The default path is fully deterministic offline.

## Owner queue and agent activity

`GET /api/v1/supervisor/queue` returns one next action per case (action,
reason, owner, deadline, affected amount, uncertainty, source, approval
requirement), derived from flags, allocations, clarifications, pending
approvals, explanations, promises, and uploads. The Control view renders the
queue plus the specialist task activity (kinds, retries, pauses, outcomes)
from the existing task history API. Both reuse the established navigation and
responsive styles; no new top-level view was added.
