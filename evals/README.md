# Evals

`seed.jsonl` is the golden set. One JSON object per line.

| Field | Meaning |
| --- | --- |
| `input` | The customer message, including order id and email when the case needs them. |
| `expected_output` | The decision a correct agent states. It must contain every string in `metadata.quotes`. |
| `metadata.source` | Always `support_handbook.md`. |
| `metadata.section` | Handbook section the case is about. |
| `metadata.case_type` | `policy`, `order`, or `refusal`. |
| `metadata.expected_tools` | Tools the agent must call. Extras are allowed. |
| `metadata.should_escalate` | Whether `escalate_to_human` must be called. Calling it when this is false is a miss. |
| `metadata.quotes` | Exact handbook sentences. Label `1` cases have at least one. |
| `metadata.order_id`, `email`, `reason`, `eligibility_code` | Present on order cases. The code must match `check_refund`. |
| `label` | `1` if the decision is grounded in the handbook or the order book. `0` if the question is outside the handbook and the correct behavior is "I do not know". |
| `critique` | Why this golden is fair. Not shown to the agent. |

`label` describes the golden, not a prediction of the live answer. `refusal_recall` uses `label == 0`: those questions are unanswerable, so the hallucination judge should score them below 0.5.

Regenerate the file after a rule change:

```sh
PYTHONPATH=src python scripts/write_seed.py
support-loop check
```

Then push a new Opik dataset version with `support-loop seed`.

## Metrics

Higher is better, except `hallucination`.

| Metric | What it measures |
| --- | --- |
| `answer_relevance` | Opik judge. Does the answer address the customer? |
| `hallucination` | Opik judge. Are claims supported by the retrieved handbook text and the tool payloads? Lower is better. |
| `answer_quality` | GEval. Specific, concise, and a refusal counts as quality when the reference says to refuse. |
| `policy_compliance` | GEval. The answer does not contradict the reference decision, leak a mismatched order, invent an amount, or ask for a secret. |
| `tool_selection` | Deterministic. Recall of `expected_tools`, cut to at most 0.5 if escalation is wrong. |
| `refusal_recall` | Share of `label == 0` items with hallucination under 0.5. Experiment-level score. |

Judge temperature is 0. The judge model is `eval_model` in `src/support_loop/config.py` and uses `OPENAI_API_KEY`.
