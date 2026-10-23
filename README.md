# edd-support-agent

Eval-driven development for a tool-using customer support agent.

This is an original port of the loop in [lucifertrj/edd-opik](https://github.com/lucifertrj/edd-opik): one variable changes, Opik scores it against a golden set, and git keeps the change or puts the code back. The domain is support, not document question-answering. The stack is the same.

Alder & Co. is a fictional Bengaluru home-goods shop. The customers, orders, and prices are made up.

## Stack

| Piece | Role |
| --- | --- |
| Python 3.11+ | Package and CLI (`support-loop`) |
| LangGraph | Agent loop: model, tools, model, until it stops |
| Gemini | The support agent (`GEMINI_API_KEY`) |
| FastEmbed | Local embeddings, no key (`jinaai/jina-embeddings-v2-small-en`) |
| Qdrant | Handbook search (`QDRANT_URL`, `QDRANT_API_KEY`) |
| Opik | Traces, dataset versions, experiments, judges (`OPIK_API_KEY`, `OPIK_WORKSPACE`) |
| OpenAI | Judge model only (`OPENAI_API_KEY`) |

Model ids and retrieval settings live in [`src/support_loop/config.py`](src/support_loop/config.py), not in `.env`.

Background on the method: [DeepEval on EDD](https://deepeval.com/blog/eval-driven-development), [Fiddler on automating it](https://www.fiddler.ai/blog/automating-eval-driven-development-agentic-applications), and [Eugene Yan on product evals](https://eugeneyan.com/writing/product-evals/).

## What the agent can do

The graph is a tool loop, not a single retrieve-then-answer chain.

| Tool | Behavior |
| --- | --- |
| `search_handbook` | Top-k chunks from the handbook in Qdrant |
| `get_order` | Order id plus the email on the order. A mismatch looks like an unknown order |
| `check_refund_eligibility` | Deterministic decision for `return`, `damaged`, `cancel`, `warranty`, or `price_adjustment` |
| `escalate_to_human` | Opens a specialist ticket. This is the only write. The agent never moves money |

Policy text and the Python rules are the same sentences. [`src/support_loop/policy.py`](src/support_loop/policy.py) holds them, and [`data/support_handbook.md`](data/support_handbook.md) must contain each one. Windows are frozen at **15 October 2026**, so a golden does not flip when the calendar does.

Eligible refunds, replacements, cancellations, warranty reviews, and price adjustments are escalated. A denial is not. A chargeback, a lawyer, or a consumer forum is escalated even when the refund was already issued.

## Setup

From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `GEMINI_API_KEY`, `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `OPIK_API_KEY`, and `OPIK_WORKSPACE`. `QDRANT_API_KEY` can be empty for a local Qdrant. Re-index if you change `chunk_size`, `chunk_overlap`, or the handbook.

```sh
support-loop check
support-loop index
support-loop ask "How much is standard shipping, and when is it free?"
```

`support-loop check` does not call a model. It checks that every rule is in the handbook and that the seed file is well formed. The unit tests also recompute every order golden against the eligibility function.

## The loop

The picture is in [flowchart.md](flowchart.md). The instructions a coding agent should follow are in [`.agents/skills/edd/SKILL.md`](.agents/skills/edd/SKILL.md).

```sh
support-loop seed          # push evals/seed.jsonl to Opik
support-loop run baseline  # compare_against is null, so this becomes the reference
```

Then add one entry to [`evals/experiments.json`](evals/experiments.json) and run that name. `retrieval-k-6` is already there: retrieval `k` goes from 4 to 6, and it is kept only if it is flat or better than `baseline` on every required metric.

```sh
support-loop run retrieval-k-6
support-loop report retrieval-k-6   # if it was rejected
```

Git history is the experiment log.

- Kept: `<name>: <change>`, including the `src/` diff.
- Rejected: `src/` is restored, and the commit is `<name> (rejected): <change>` with the score record only.

`evals/experiments.json` stores the decision, the deltas, and whether the loop has plateaued. Plateaued means two kept runs in a row moved no metric. That is the point to change the graph, the tools, or retrieval, not another sentence in the prompt.

A sweep that does not keep or reject:

```sh
support-loop loop --config evals/configs.json
```

## Metrics

| Metric | Direction | Kind |
| --- | --- | --- |
| `answer_relevance` | higher | Opik judge |
| `hallucination` | lower | Opik judge, over handbook chunks and tool payloads |
| `answer_quality` | higher | GEval, and a correct refusal counts |
| `policy_compliance` | higher | GEval against the golden decision |
| `tool_selection` | higher | Deterministic recall, plus an escalation bit |
| `refusal_recall` | higher | Share of out-of-handbook questions with hallucination under 0.5 |

Judge temperature is 0. Details of the golden file are in [evals/README.md](evals/README.md). There are 28 goldens: policy questions, order decisions, one privacy mismatch, one legal escalation, and four questions the handbook cannot answer.

Grow the file by editing [`scripts/write_seed.py`](scripts/write_seed.py) and running it. Do not paste answers the handbook does not support. A useful set stays small and sharp; somewhere around 50 to 100 hand-checked goldens is enough, and generated slop is not.

## Offline tests

These run in CI without keys:

```sh
pytest
```

They cover the refund table, the privacy non-leak, keep/reject/plateau, tool-selection scoring, and the seed file.

## Publish

This folder is its own git repo. Create an empty public repo named `edd-support-agent`, then:

```sh
git remote add origin git@github.com:BharatReddyThavva/edd-support-agent.git
git push -u origin main
```

Do not commit `.env`.

## License

MIT. Copyright 2026 Bharat Reddy Thavva.
