# Cost model

What outbound costs per lead, and the reply rate below which it stops working.
The formula is the durable part; unit prices are a snapshot and should be
re-checked against current vendor pricing before you quote anyone.

## Cost per lead

```
cost_per_lead
  = (first_touch_tokens + followup_tokens × followup_probability) × token_rate
  + sheets_and_gmail_operations × operation_rate
  + n8n_executions × execution_rate
```

Two LLM generations happen per lead in the worst case: the first-touch email
always, and the follow-up whenever no reply arrives — which is most of the time.
At a 10% reply rate, roughly 90% of leads trigger a second generation, so budget
for **1.9 generations per lead**, not one.

### Worked example

Assumptions, all stated so you can replace them:

| Input | Value | Source |
|---|---|---|
| Leads/month | 1,000 | Volume assumption |
| Input per generation | ~350 tokens | Lead record plus prompt |
| Output per generation | ~250 tokens | Structured JSON email |
| Reply rate | 8% | Result from the production deployment |
| Generations per lead | 1.92 | 1 + (1 − 0.08) |
| n8n | Self-hosted | Marginal execution cost ≈ 0 |
| Google Workspace | Existing seat | No marginal cost |

```
1,000 leads × 1.92 generations × 600 tokens ≈ 1.15M tokens/month
```

At small-tier pricing that is **low single-digit dollars per month**. Gmail and
Sheets operations sit inside an existing Workspace seat.

**Infrastructure is not the constraint here either.** The real costs are the ones
that do not appear on an invoice.

## The costs that are not on the invoice

This is the model that matters for outbound, and the one most automation
proposals leave out:

| Cost | How it bites |
|---|---|
| **Domain reputation** | Send too fast from a cold domain and deliverability collapses. Recovery takes weeks. This is the single largest risk on the list and it is not billed to you — it is billed to every future campaign. |
| **Sending limits** | Gmail caps daily sends per account. Volume above the cap needs more mailboxes or a dedicated ESP, which is a real per-seat cost. |
| **Human review time** | Whatever fraction of generated emails a person still reads before sending. At 1,000/month, even 10% review at 30 seconds each is ~1 hour. |
| **Reputational cost of a bad send** | A hallucinated claim or a leaked `Your Name` placeholder reaching a prospect. Unrecoverable per recipient. Cheap to prevent — see [the eval suite](../evals/). |
| **Compliance exposure** | Missing opt-out handling or ignored suppression requests. See the compliance section in the main README. |

## The number that decides everything

Not cost per lead. **Cost per booked meeting:**

```
cost_per_meeting = total_monthly_cost / (leads × reply_rate × meeting_conversion)
```

At 1,000 leads, an 8% reply rate, and half of replies converting to a meeting,
that is 40 meetings/month. Even generously loading in review time and mailbox
costs, this lands far below any paid acquisition channel — **provided the reply
rate holds**.

Reply rate is the entire model. Halve it and cost per meeting doubles, because
every cost term is fixed per lead while the denominator collapses. Which is why
the eval suite grades personalization and fabrication rather than token spend:
**copy quality is the cost lever, not model choice**.

## When this stops being worth it

Be able to say when the answer is no:

| Condition | Why it breaks |
|---|---|
| **Reply rate under ~2%** | Cost per meeting stops beating paid channels, and you are burning domain reputation to get there. Fix targeting or copy before adding volume. |
| **Lead list is unqualified or scraped indiscriminately** | Volume does not fix relevance. It accelerates the deliverability damage. |
| **No suppression list or opt-out handling** | Not a cost question. Do not run it. |
| **Under ~100 leads/month** | Write them by hand. They will be better, and the build does not pay back. |
| **Above Gmail's daily send limits** | The model changes — you now need a dedicated ESP and warmed domains, and per-seat cost becomes a real term. |
| **Regulated buyer, unreviewed copy** | Healthcare and financial services need review on every send. That review time swamps the automation saving. |

## Scaling

| Leads/month | Generations | Tokens | Real constraint |
|---|---|---|---|
| 100 | 192 | 0.1M | Nothing — write by hand instead |
| 1,000 | 1,920 | 1.2M | Gmail daily send limits |
| 5,000 | 9,600 | 5.8M | Domain reputation, mailbox count |
| 20,000 | 38,400 | 23M | Dedicated ESP, warmed domain pool, compliance process |

Token cost never becomes the binding constraint at any of these volumes.
Deliverability does, at every one of them.

## Measuring it in production

Track per-lead token usage, send success rate, bounce rate, spam-complaint rate,
reply rate, and meeting conversion in the same sheet the workflow already writes
to. Bounce and complaint rates are the leading indicators — they move before
reply rate does, and they are the ones that predict whether the channel still
exists next quarter.
