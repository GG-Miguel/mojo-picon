# Mojo Picón

> *Dale sabor a tu vida.* Agentic nutrition assistant.

Mojo Picón logs meals (also from photos), adjusts energy needs to training and context, proposes what to eat for the rest of the day with **numbers verified by code**, builds the shopping list and refers risky cases to a health professional.

Final project of the Master's in Generative AI. The app's user interface is in Spanish; code and technical documentation are in English.

## Core principle

**The LLM decides, the code calculates.** No number reaches the user unless it comes from a tool. See [`specs/`](specs/) and [`CLAUDE.md`](CLAUDE.md).

## Status

Early development (milestone 1, demo v0.1). Implemented so far:

| Module | What it does |
|---|---|
| `domain/` | Pydantic models: profile, food, nutrients, plan, macro targets |
| `tools/energy.py` | BMR (Mifflin-St Jeor), TDEE, daily target, training energy (MET), per-kg amounts |
| `tools/verify_plan.py` | Deterministic check of the Planner's proposals: kcal ±10 %, macros, allergens, realistic quantities |
| `guardrails/number_origin.py` | Output guardrail: every number in an answer must have a valid origin (ADR-19) |
| `tools/food_search.py` | `search_food` (candidates, confidence and status; plurals, typos), `get_nutrients`, `check_allergens` |
| `tools/diary.py` | `log_meal` (idempotent, nutrients from the table), `log_activity` (MET, by time or distance), `get_day_balance`, profile; diary day in the user's timezone |
| `auth/` · `store/` | Firebase ID token verification → `UserContext`; data access scoped to the context's uid (Firestore and in-memory) |
| `agents/` · `guardrails/` · `llm.py` | LangGraph turn graph: input guardian (rules + LLM classifier, fixed answers without LLM), Coach (ReAct, 12-step limit), Planner subgraph (propose → `verify_plan` → correct, max. 3), output guardian (numbers with origin, warning, forbidden advice); `get_model(role)` with Gemini on Vertex AI |
| `api/` · `observability.py` | FastAPI: `POST /chat` (Server-Sent Events with the agent's steps), `GET /day`, `GET/PUT /me/profile`; Firebase token, rate limit, sessions; Langfuse traces when its keys are set |
| `frontend/` | React + Vite + TypeScript + Tailwind: chat with the agent's steps (SSE), day panel, profile form, Firebase login |
| `Dockerfile` · `deploy/` · `scripts/bootstrap_gcp.sh` | One image (API + built frontend) on Cloud Run `europe-west1`; Cloud Build and Workload Identity Federation from GitLab CI |
| `mcp_server/` | MCP server (FastMCP, Streamable HTTP) over the same tools: only deterministic tools (ADR-21), personal tokens stored as hashes, user taken from the token |
| `tools/foods.py` + `data/` | Curated food table (202 foods: CIQUAL, 6 from BEDCA, recipes and approximations), build script and validation |

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install   # ruff + gitleaks before each commit
API_DEV_TOKENS="dev-token-ana:ana" uv run uvicorn mojo_picon.api.dev:app --port 8080   # API with real Gemini, dev tokens, in-memory data
(cd frontend && npm ci && VITE_DEV_TOKEN=dev-token-ana npx vite)   # web at http://localhost:5173 (proxies the API on :8080)
MCP_DEV_TOKENS="dev-token-ana:ana" uv run python -m mojo_picon.mcp_server   # local MCP server at http://localhost:8000/mcp
docker compose up -d firestore   # Firestore emulator for integration tests
FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest -m integration
uv run --group data python data/fetch_bedca.py   # download the BEDCA foods (cached)
uv run --group data python data/build_foods.py   # rebuild the food table (see data/DATASHEET.md)
```

Configuration is read from environment variables; see [`.env.example`](.env.example). Never commit a `.env` file.

## Data and licences

The code is under the [MIT licence](LICENSE). The data and texts below are not the author's and keep their own terms; the MIT licence does not cover them.

- **Food composition:** *Anses. 2020. Ciqual French food composition table*, [Etalab Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) (reuse, including commercial, with attribution).
- **Six Spanish and Canary products** (gofio, mojo picón, queso majorero, vieja, chorizo, paella): *AESAN/BEDCA Base de Datos Española de Composición de Alimentos v1.0 (2010)*. AESAN replied by email (October 2026) that their use in this educational, non-commercial project is fine. Values are kept unmodified; any commercial use needs AESAN's authorisation. A table without them: `uv run --group data python data/build_foods.py --no-bedca`. See [`data/DATASHEET.md`](data/DATASHEET.md).
- **Guidelines of the RAG:** the repository keeps only their references and licences ([`data/guides.json`](data/guides.json)); the texts are downloaded from the official sites by `scripts/fetch_guides.py` and are not redistributed.
- **Package photos** for the evaluation: Open Food Facts contributors, [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); each file and its source in [`evals/fixtures/packages/SOURCES.md`](evals/fixtures/packages/SOURCES.md).
- **Activity METs:** *Compendium of Physical Activities* (Ainsworth et al., 2011), cited by activity code in `data/met_table.csv`.

## License

[MIT](LICENSE) for the code; the data keep their own terms (see above).
