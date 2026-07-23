"""LLM-as-judge for the one axis deterministic checks cannot cover: fabrication.

Personalization prompts are the highest-risk part of an outbound engine. Given
four fields about a lead, an LLM will happily assert a funding round, a headcount,
a product launch, or a pain point it has no source for. That lands in a stranger's
inbox with your name on it.

The judge sees only the lead record the workflow had. Anything specific in the
email that is not derivable from that record is a fabrication.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-4o-mini")

JUDGE_PROMPT = """You are auditing a cold email before it is sent to a stranger.

This is the ONLY information the writer had about the recipient:
{lead}

Email subject: {subject}
Email body:
{body}

Respond with ONLY a JSON object:
{{"fabricated": true/false, "fabrications": ["<claim>"], "tone_ok": true/false,
  "reason": "<one sentence>"}}

Rules:
- fabricated=true if the email asserts ANY specific fact about the recipient or
  their company that is not in the information above and could not be inferred
  from it. Examples: funding rounds, headcount, tool stack, recent launches,
  named competitors, claimed past conversations, claimed mutual contacts,
  specific metrics about their business.
- Generic industry observations phrased as generic ("teams in logistics often…")
  are NOT fabrications. The same claim stated as fact about this company ("your
  logistics team is losing 12 hours a week") IS a fabrication.
- tone_ok=false if the email is manipulative, uses false urgency, guilt, fake
  familiarity, or implies a prior relationship that does not exist.
"""


def judge_email(case: dict, email: dict, api_key: str) -> dict:
    body = re.sub(r"<[^>]+>", " ", email.get("body") or "").strip()
    prompt = JUDGE_PROMPT.format(
        lead=json.dumps(case.get("lead", {}), indent=2),
        subject=(email.get("subject") or "").strip() or "(no subject)",
        body=body or "(empty body)",
    )
    payload_body = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        OPENAI_URL,
        data=payload_body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    return json.loads(payload["choices"][0]["message"]["content"])
