"""Scoring for generated cold-email copy.

Most of what makes outbound copy unsendable is checkable without a model:
a leaked "Your Name" placeholder, a missing opt-out line, a subject line in
shouty caps, a body that never mentions the lead's company. Those are all
deterministic, so they run free and never flake.

Only one axis genuinely needs a model — whether the email invented a specific
claim about the lead's company that was not in the lead record. That lives in
judge.py and is the expensive check, so it runs last.
"""

from __future__ import annotations

import re

# The exact placeholders this workflow's prompts and HTML templates ship with.
# Any of these reaching a real send is an incident, not a style nit.
PLACEHOLDER_PATTERNS = (
    re.compile(r"\byour name\b", re.IGNORECASE),
    re.compile(r"\byour company\b", re.IGNORECASE),
    re.compile(r"\byour city\b", re.IGNORECASE),
    re.compile(r"\byou@example\.com\b", re.IGNORECASE),
    re.compile(r"\[[a-z_ ]+\]", re.IGNORECASE),
    re.compile(r"\{\{.*?\}\}"),
)

# Phrases that reliably move mail to spam or read as mass-blast.
SPAM_PHRASES = (
    "act now", "limited time", "risk free", "risk-free", "100% free",
    "guaranteed", "no obligation", "click here", "buy now", "cash bonus",
    "make money", "once in a lifetime", "urgent", "congratulations",
    "dear sir or madam", "to whom it may concern",
)

CTA_PATTERNS = (
    re.compile(r"\?\s*$", re.MULTILINE),
    re.compile(r"\b(worth a|open to|free for|grab \d+|book a|quick call|"
               r"15 minutes|20 minutes|next week|this week)\b", re.IGNORECASE),
)

OPT_OUT_PATTERNS = (
    re.compile(r"\b(unsubscribe|opt out|opt-out|reply\s+stop|no longer wish|"
               r"stop hearing from me|take you off)\b", re.IGNORECASE),
    # "Not interested — just reply and I'll stop" and its many punctuations.
    re.compile(r"\bnot interested\b[\s,\-–—:]*(just\s+)?(reply|let me know|say)",
               re.IGNORECASE),
)

WORD_MIN = 50
WORD_MAX = 150
SUBJECT_MAX_CHARS = 60


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def find_placeholders(text: str) -> list[str]:
    found = []
    for pattern in PLACEHOLDER_PATTERNS:
        found.extend(match.group(0) for match in pattern.finditer(text))
    return found


def find_spam_phrases(text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in SPAM_PHRASES if phrase in lowered]


def matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def personalization_hits(body: str, lead: dict) -> dict[str, bool]:
    lowered = body.lower()
    return {
        field: bool(value) and str(value).lower() in lowered
        for field, value in (
            ("first_name", lead.get("First_Name")),
            ("company", lead.get("Company")),
            ("job_title", lead.get("Job_Title")),
            ("industry", lead.get("Industry")),
        )
    }


def is_shouty(subject: str) -> bool:
    letters = [c for c in subject if c.isalpha()]
    if len(letters) < 4:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.6 or subject.count("!") > 1


def score_email(case: dict, email: dict) -> dict:
    """Score one generated email against its lead record.

    email: {"subject": "...", "body": "..."} — body may be plain text or HTML.
    """
    lead = case.get("lead", {})
    subject = (email.get("subject") or "").strip()
    body = strip_html(email.get("body") or "").strip()
    full = f"{subject}\n{body}"

    words = len(body.split())
    personalization = personalization_hits(body, lead)
    # A cold email must at minimum name the person and their company.
    personalized = personalization["first_name"] and personalization["company"]

    placeholders = find_placeholders(full)
    spam = find_spam_phrases(full)

    checks = {
        "personalized": personalized,
        "no_placeholder_leak": not placeholders,
        "within_length": WORD_MIN <= words <= WORD_MAX,
        "has_cta": matches_any(body, CTA_PATTERNS),
        "has_opt_out": matches_any(body, OPT_OUT_PATTERNS),
        "no_spam_phrases": not spam,
        "subject_present": bool(subject),
        "subject_length_ok": bool(subject) and len(subject) <= SUBJECT_MAX_CHARS,
        "subject_not_shouty": not is_shouty(subject),
    }

    return {
        "checks": checks,
        "passed": all(checks.values()),
        # A leaked placeholder or a missing opt-out is a blocker regardless of
        # how good the copy reads.
        "blocking_failures": [
            name for name in ("no_placeholder_leak", "has_opt_out", "subject_present")
            if not checks[name]
        ],
        "details": {
            "word_count": words,
            "subject_chars": len(subject),
            "personalization": personalization,
            "placeholders_found": placeholders,
            "spam_phrases_found": spam,
        },
    }
