# Evaluation

How Mojo Picón is measured (vault: *Plan de evaluación*). What code can check is checked by code; the
judge only scores what is subjective.

| File | What it holds |
| --- | --- |
| `cases/safety.yaml` | Risky requests (must be referred) and a legitimate twin for each (must not be) |
| `cases/attacks.yaml` | Injection, jailbreak, prompt leak, another user's data, excessive agency, text in a photo |
| `cases/conversations.yaml` | Conversations with code checks (tools, guardian, allergens…) and the judge's rubric |
| `cases/planner.yaml` | Remaining targets for the planner: verified at the first attempt, after correcting, or not |
| `cases/rag.yaml` | Questions with the guideline that must be retrieved (recall@k) |
| `cases/numbers.yaml` | Labelled answers for the numbers-with-origin checker (no LLM) |
| `checks.py` | The code checks |
| `harness.py` | Runs a case through the real API (SSE), real Gemini and Qdrant, an in-memory store per case |
| `judge.py`, `metrics.py` | G-Eval with fixed evaluation steps; judge GPT-OSS 120B on Groq (ADR-13) |
| `run.py`, `run.sh` | Runs the sets and writes `results/<date>.json` and `.md` |

```bash
evals/run.sh                                   # every set, judge included
evals/run.sh --sets safety,attacks --no-judge  # some sets, no judge
evals/run.sh --partition prueba --repeat 3     # the frozen test partition, 3 runs per case
evals/run.sh --sets safety --ids seg-13,seg-13b --no-judge  # a few cases, for a quick check
uv run --group eval python -m evals.baseline evals/results/<run>.json  # chatbot with RAG in one call vs the agent
```

`run.sh` needs `GROQ_API_KEY` in `.env` (the judge) and gcloud access to the Qdrant key.

**Cases.** Every case carries its origin (a use case `CU-xx` or a risk `OWASP-LLMxx`) and `validado`:
`false` until the author has reviewed it as the domain expert. Phrasings differ from the examples inside
the prompts, so the test set does not measure what the model was shown.

**Partitions.** Cases are split by seed (`cases.partition`): about 40 % *desarrollo* (to tune prompts and
for the CI gate) and 60 % *prueba* (frozen, only for the report). A twin or a variant always goes with
its seed, so the test set never contains a near copy of a development case. Regression cases (bugs found
while using the app) go to *desarrollo*.

**Costs.** Gemini is billed per run (roughly a cent per conversation); the judge runs on Groq's free tier
(about 8,000 tokens per minute, so the judged conversations run two at a time).
