# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Planner prompt: minimally processed foods (AESAN), no fried food, pastries, chocolate or juices unless asked; protein in every main meal. Measured with real Gemini: 0 such items in 6/6 plans (3 before in 3/3 after a 10 km run), all verified at the first attempt.
- Photo analysis hardened against text written in the photo (OWASP LLM01): food names and questions are length-limited, and the summary reaches the Coach between `<datos_foto>` tags that cannot be closed from inside.
- Guideline retrieval (RAG): corpus manifest and download script; PDF transcription with Gemini (tables kept, numbers checked against the PDF text); hybrid index in Qdrant Cloud (gemini-embedding-2 + BM25, RRF); `search_guides` tool for the Coach, whose passages count as number origin only when cited; `scripts/ingest_rag.py` with a report.
- Meal photos (UC-03): the vision extractor (Gemini, structured output) returns foods with gram ranges, confidence and questions; the photo is cleaned in memory (EXIF and GPS removed, resized) and never stored; only the result goes to the Coach, as data. Photo upload in the web chat.
- `scripts/seed_demo_user.py`: demo profile and breakfast for the demo account.
- Web app (React, Vite, TypeScript, Tailwind): chat with live agent steps, day panel, profile form, Firebase login, AI notice; served by the API from the same image.
- `GET /day` entries carry food and activity names.
- Dockerfile (multi-stage, non-root), Cloud Run service config, Cloud Build config, GCP bootstrap script with Workload Identity Federation, CI jobs for the frontend and the deploy from `main`.
- Project scaffold: uv, ruff, pytest, pre-commit with gitleaks, merge request template.
- Domain models: profile, food, nutrients, plan, macro targets.
- Energy tools: BMR, TDEE, daily target, net training energy (MET), per-kg amounts.
- `verify_plan`: kcal, macros, allergens and realistic quantities.
- Output guardrail for numbers with origin (ADR-19).
- Specifications in `specs/` (principles, functional spec, guardrails, food table, ADR-01 … ADR-25).
- `search_food`, `get_nutrients` and `check_allergens` over the food table.
- FastAPI app: `POST /chat` with SSE events, `GET /day`, profile endpoints, sessions (recent messages), rate limit, Langfuse tracing; development server with dev tokens.
- Gemini through the Vertex AI EU endpoint (`gemini-3.8-flash`), checked with real calls.
- GitLab CI: lint, tests and secret detection.
- `config.py` (all settings from the environment) and `devtools.py` (development servers).

### Fixed
- Security review (2026-10-16): photos are checked for pixel count before decoding (a 165 KB PNG used 887 MB of memory); JPEGs are decoded already reduced. Security headers (nosniff, Referrer-Policy, no framing); API docs off in production; trace links not sent to users in production; the guardian's delimiters cannot be closed from the message.
- Planner: Gemini's reasoning used up the 2048-token output limit and half of the plans arrived cut; limits raised (reasoning counts inside them) and an unreadable proposal now counts as one failed attempt.
- Number origin: a citation with a page ("[EFSA DRV 2017, p. 21]") was split into two sentences.
- Numbers with origin: digits inside strings of tool results (e.g. random entry ids) were accepted as the origin of a figure; JSON lists were dropped as if they were citations.
- Logging tools return the balance read after writing (Gemini can call `log_meal` and `get_day_balance` in parallel).
- Code review (2026-10-12): tool and planner errors go back to the model instead of aborting the turn; a meal saved before a failed balance is reported, not lost or duplicated; numbers with origin no longer skip unitless numbers, unaccented units, UI, compound number words, empty or made-up citations, or profile values used as kcal; forbidden advice limited to medication (calcium in mg or caffeine are allowed); fast rule for extreme goals covers days, weeks, months and «esta semana»; profile rejects rates above 1 kg/week and unknown timezones; MCP uses the profile's timezone and validates `request_id`; disabled Firebase accounts get 401; risky turns are not kept in the session; recipes keep missing nutrients missing; salt/sodium mismatches are warned; `guardrails/` no longer imports `agents/`.
- Agents in LangGraph: input and output guardians, Coach, Planner subgraph, prompts, Gemini provider with safety-block handling; tested with scripted models.
- Local MCP server: `search_food`, `get_nutrients`, `check_allergens`, `list_activities`, `log_meal`, `log_activity`, `get_day_balance`; resources `profile://me`, `diary://today`; prompt `resumen_de_mi_semana`; development token registry; attack test over HTTP.
- Diary tools (`log_meal`, `log_activity`, `get_day_balance`, profile), Firebase token verification, `UserContext` and the Store (Firestore and in-memory), with the «another user's diary» attack tests.
- Food table: 202 foods from CIQUAL 2020 and 6 from BEDCA (educational use, authorisation pending), with recipe or approximation fallbacks (`--no-bedca`), build script, validation and datasheet (ADR-25).
