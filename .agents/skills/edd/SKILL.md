# Eval-driven development for this repo

Use this when changing the Alder & Co. support agent. The loop is the spec. A change that is not scored does not land.

## Before editing

- Run `support-loop check`. It must pass with no network.
- Read `data/support_handbook.md` and `src/support_loop/policy.py`. They are the same rules. If you change a rule, change both, then `PYTHONPATH=src python scripts/write_seed.py`.
- Do not invent an `expected_output`. Quote `policy.RULES` and the order record.
- Do not put API keys in the repo.

## One change

Add one object to `evals/experiments.json` before you run it. `support-loop run` looks up a name. It does not create one.

Change one variable:

- `retrieval_k`
- `chat_model`
- `max_tool_rounds`
- `prompt_style` (`baseline` or `strict`)
- or one edit in `src/support_loop/agent.py` (the prompt or the graph)

`compare_against` must name an experiment that already has `evals/results/<name>.json`. The first run is `baseline`, whose `compare_against` is null. That run is kept and becomes the reference.

Required metrics, and the direction that counts as a regression:

- higher is better: `answer_relevance`, `answer_quality`, `policy_compliance`, `tool_selection`, `refusal_recall`
- lower is better: `hallucination`

## Run

```sh
support-loop seed
support-loop run baseline
support-loop run <name>
```

- `keep` or `no_baseline`: the code stays, and git commits `<name>: <change>`.
- `reject`: `src/` is restored, and git commits `<name> (rejected): <change>` with the score record only.
- `support-loop report <name>` shows the worst cases. Read those before the next idea.
- Plateaued means two kept runs in a row moved no metric. Stop editing adjectives. Change retrieval, chunking, a tool, or the graph.

`support-loop loop --config evals/configs.json` scores a sweep and does not keep or reject.

## Do not

- Do not weaken a golden to make a run pass.
- Do not add a metric that the change cannot affect and then call that a win.
- Do not grant a refund the eligibility tool denied.
- Do not reveal an order when the email does not match. That response is "the order cannot be found".
- Do not use today's date. The tools use 15 October 2026.
