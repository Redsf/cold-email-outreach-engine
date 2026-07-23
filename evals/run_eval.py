"""Run the cold-email eval suite.

Grades generated emails on deliverability, personalization, compliance, and
fabrication — before any of them reach a real inbox.

Two modes:

1. Offline mode — grade emails already produced by an n8n run.
       python evals/run_eval.py --emails emails.jsonl
   emails.jsonl format: one {"id": "...", "email": {"subject": "...", "body": "..."}}
   per line. Export these from the workflow's Code node output.

2. Live mode — re-run the workflow's personalization prompt against each lead
   fixture via the OpenAI API and grade the result.
       python evals/run_eval.py --live

--no-judge skips the LLM fabrication check and runs only the deterministic
checks, which needs no API key at all.

Outputs scores.json and report.md next to this file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from judge import judge_email
from score import score_email

EVAL_DIR = Path(__file__).parent
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("OUTREACH_MODEL", "gpt-4o-mini")

# Mirrors the workflow's "Personalize E-mail" agent prompt closely enough that a
# change here is a fair proxy for a change there.
OUTREACH_PROMPT = """Write a personalized cold email to this lead.

Lead:
{lead}

Return ONLY a JSON object: {{"subject": "...", "body": "..."}}

Requirements:
- Reference the lead by first name and name their company.
- Do not state any specific fact about their company that is not given above.
- One clear call to action.
- Include a one-line opt-out ("not interested — just reply and I'll stop").
- 50-150 words.
"""


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate_live(lead: dict, api_key: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": OUTREACH_PROMPT.format(lead=json.dumps(lead, indent=2))}],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        OPENAI_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.load(resp)
    return json.loads(payload["choices"][0]["message"]["content"])


def collect(cases: list[dict], args: argparse.Namespace, api_key: str | None) -> dict[str, dict]:
    if args.emails:
        return {row["id"]: row["email"] for row in load_jsonl(Path(args.emails))}

    if not api_key:
        sys.exit("OPENAI_API_KEY is not set; live mode needs it.")

    emails = {}
    for case in cases:
        print(f"  generating {case['id']} ...", file=sys.stderr)
        try:
            emails[case["id"]] = generate_live(case["lead"], api_key)
        except Exception as exc:  # noqa: BLE001 - a failed generation is a failed case
            print(f"    failed: {exc}", file=sys.stderr)
            emails[case["id"]] = {"subject": "", "body": ""}
    return emails


def summarize(results: list[dict]) -> dict:
    total = len(results)
    if not total:
        return {"total_cases": 0}

    check_names = list(results[0]["score"]["checks"])
    judged = [r for r in results if r.get("verdict")]

    return {
        "total_cases": total,
        "sendable_rate": round(sum(1 for r in results if r["score"]["passed"]) / total, 3),
        "blocked_count": sum(1 for r in results if r["score"]["blocking_failures"]),
        "check_pass_rates": {
            name: round(sum(1 for r in results if r["score"]["checks"][name]) / total, 3)
            for name in check_names
        },
        "fabrication_rate": (
            round(sum(1 for r in judged if r["verdict"]["fabricated"]) / len(judged), 3)
            if judged else None
        ),
        "tone_pass_rate": (
            round(sum(1 for r in judged if r["verdict"]["tone_ok"]) / len(judged), 3)
            if judged else None
        ),
    }


def write_report(results: list[dict], summary: dict) -> None:
    lines = [
        "# Cold Email Eval Report",
        "",
        f"- **Cases:** {summary['total_cases']}",
        f"- **Sendable (all checks pass):** {summary['sendable_rate']:.0%}",
        f"- **Blocked (placeholder leak / no opt-out / no subject):** {summary['blocked_count']}",
    ]
    if summary["fabrication_rate"] is not None:
        lines.append(f"- **Fabricated a claim about the lead:** {summary['fabrication_rate']:.0%}")
        lines.append(f"- **Tone acceptable:** {summary['tone_pass_rate']:.0%}")

    lines += ["", "## Check pass rates", "", "| Check | Pass rate |", "|---|---|"]
    for name, rate in summary["check_pass_rates"].items():
        lines.append(f"| {name} | {rate:.0%} |")

    lines += ["", "## Cases", "", "| Case | Words | Sendable | Blocking | Fabricated |", "|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        verdict = r.get("verdict")
        fabricated = "—" if not verdict else ("❌ " + "; ".join(verdict.get("fabrications") or ["yes"]) if verdict["fabricated"] else "✅")
        lines.append(
            f"| {r['id']} | {s['details']['word_count']} | {'✅' if s['passed'] else '❌'} "
            f"| {', '.join(s['blocking_failures']) or '—'} | {fabricated} |"
        )
    (EVAL_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--emails", help="grade pre-generated emails (JSONL)")
    group.add_argument("--live", action="store_true", help="generate emails via the OpenAI API")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM fabrication check")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    cases = load_jsonl(EVAL_DIR / "test_cases.jsonl")
    emails = collect(cases, args, api_key)

    use_judge = not args.no_judge
    if use_judge and not api_key:
        print("OPENAI_API_KEY not set — running deterministic checks only.", file=sys.stderr)
        use_judge = False

    results = []
    for case in cases:
        email = emails.get(case["id"])
        if email is None:
            print(f"  skipping {case['id']}: no email provided", file=sys.stderr)
            continue
        result = {"id": case["id"], "email": email, "score": score_email(case, email)}
        if use_judge:
            print(f"  judging {case['id']} ...", file=sys.stderr)
            result["verdict"] = judge_email(case, email, api_key)
        results.append(result)

    summary = summarize(results)
    (EVAL_DIR / "scores.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8"
    )
    write_report(results, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
