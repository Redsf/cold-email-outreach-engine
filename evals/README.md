# Cold email evals

12 lead fixtures, graded on deliverability, personalization, compliance, and
fabrication — before anything reaches a real inbox.

Outbound is the highest-blast-radius automation in this portfolio. A bad RAG
answer is seen by one employee who can ask again. A bad cold email is sent to a
stranger, with your name on it, and cannot be recalled.

## What is measured

Most failures here are checkable **without a model**, so the deterministic
checks run free and never flake:

| Check | Why it matters |
|---|---|
| `no_placeholder_leak` | **Blocking.** Catches `Your Name`, `Your Company`, `Your City`, `you@example.com`, `[brackets]`, `{{handlebars}}` — the exact placeholders this workflow ships with baked into its prompts and HTML templates. |
| `has_opt_out` | **Blocking.** No opt-out line means the send is not compliant (see the compliance section in the main README). |
| `subject_present` | **Blocking.** An empty subject usually means the JSON parse fell back and nobody noticed. |
| `personalized` | Names the lead and their company. If it doesn't, it's a mass blast wearing a personalization prompt. |
| `within_length` | 50–150 words. |
| `has_cta` | One clear ask. |
| `no_spam_phrases` | Classic deliverability killers. |
| `subject_length_ok` | ≤ 60 characters, so it isn't truncated in the inbox. |
| `subject_not_shouty` | No ALL CAPS, no multiple exclamation marks. |

One axis genuinely needs a model, and it's the one that matters most:

| Metric | Why it matters |
|---|---|
| **Fabrication rate** | Given four fields about a lead, an LLM will happily assert a funding round, a headcount, a tool stack, or a specific pain point it has no source for. The judge sees only the lead record the workflow had — anything specific beyond it is a fabrication. |
| **Tone** | Flags manipulation, false urgency, and fake familiarity ("great catching up last week"). |

The judge draws the line where it belongs: `"teams in logistics often lose hours
to manual entry"` is a generic observation and fine. `"your logistics team is
losing 12 hours a week"` is a fabricated claim about a company you know four
fields about.

## The cases

| Type | Cases | What it catches |
|---|---|---|
| `standard` | 4 | Baseline personas across industries. |
| `sparse_record` | 2 | Missing job title, missing first name — the email must not invent either. |
| `ambiguous_company` | 1 | A company named "Anchor". Maximum fabrication temptation. |
| `regulated_industry` | 2 | Healthcare and financial services, where implied compliance or ROI claims are a real problem. |
| `long_names` | 1 | Subject line must still fit its character budget. |
| `non_latin_name` | 1 | Name must not be mangled or dropped. |
| `adversarial_injection` | 1 | Injection planted in a lead field. A scraped or form-submitted list is untrusted input, and this workflow feeds it straight into a prompt. |

## Running it

Deterministic checks only — no API key needed, runs in under a second:

```bash
python evals/run_eval.py --emails emails.jsonl --no-judge
```

Full run including the fabrication judge:

```bash
OPENAI_API_KEY=sk-... python evals/run_eval.py --emails emails.jsonl
```

Live mode regenerates copy from the lead fixtures through the OpenAI API, using
a prompt that mirrors the workflow's **Personalize E-mail** agent:

```bash
OPENAI_API_KEY=sk-... python evals/run_eval.py --live
```

`emails.jsonl` is one `{"id": "...", "email": {"subject": "...", "body": "..."}}`
per line, exported from the workflow's **Code in JavaScript** node output.

Both write `scores.json` and `report.md` to this directory.

## Taking the blocking checks to production

The three blocking checks in [score.py](score.py) are pure string work with no
dependencies. Port them into a Code node between **Code in JavaScript** and
**Send Cold Email**, and route any failure to a review queue instead of to
Gmail. A placeholder leak caught in CI is a warning; one caught in the send path
is an incident that never happened.
