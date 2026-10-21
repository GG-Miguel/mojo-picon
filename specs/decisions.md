# Architecture Decision Records

Each decision has: context, decision, discarded alternatives, consequences and **evidence** (what has to be measured to defend it).

---

## ADR-01
**Mojo Picón instead of a research assistant for oceanography**
- **Context:** two project ideas; one had to be chosen for the master's.
- **Decision:** Mojo Picón.
- **Alternative:** a multi-agent assistant for writing physical oceanography papers.
- **Why:** it can be checked with code (kcal, allergens), evaluation is objective and cheap, any examiner understands the demo, and guardrails have a natural use. The research assistant is more original and more useful for the author, but its scientific quality is hard to guarantee in the time available and the examiners cannot judge it.
- **Consequence:** the architecture can be reused for the research assistant after the master's.

## ADR-02
**Bounded multi-agent system instead of a single agent**
- **Decision** (revised 2026-10-12): **two agents** (Coach, and Planner as a subgraph), an input and output **guardrail** (Guardian: rules + LLM classifier) and a **vision extractor** outside the graph.
- **Alternatives:** a single agent with all the tools; a chatbot with retrieval.
- **Why:** isolate contexts (the Planner's loop), limit each one separately and keep the **guardian independent** from whoever answers. "The more bounded the agent's task, the higher its success rate."
- **Why the guardian and the vision extractor are not agents:** they do not choose steps or use tools; they always do the same thing. The guardian is a guardrail ([guardrails.md](guardrails.md)). Vision is a preprocessing step: there is no decision to delegate to the LLM and, for privacy, the image never enters the graph.
- **Evidence:** comparison with both alternatives on quality, cost and latency. If there is no improvement, it is reported.

## ADR-03
**LangGraph as the framework**
- **Alternatives:** CrewAI, Google ADK, Pydantic AI, Agno, n8n.
- **Why:** explicit graph (state machine), fine control of limits and human interrupts, integration with MCP and Langfuse. n8n (no-code) limits control and evaluation in CI/CD.
- **LangChain and LangGraph do not compete:** LangChain provides the pieces (models, messages, tools) and LangGraph orchestrates them as a graph. Both are used.
- **Versus ADK:** also defensible (native to Gemini, A2A built in). LangGraph gives explicit control: guardrails as fixed nodes, bounded loops, a "refer" route without an LLM.
- **Use of state:** the graph state is used within each turn; persistence between turns is our own (ADR-18).
- **Consequence:** interoperability is shown with an external agent built with **another framework** (ADK) that uses the MCP server and the A2A agent. n8n is not used (decided 2026-10-10).

## ADR-04
**Models: Gemini Flash for the agents and Claude as judge**
- **Decision:** Gemini 3.8 Flash (Vertex AI, EU) for agents and vision; Claude Sonnet 5.5 as the **G-Eval** model (judge, ADR-13); in milestone 3, a cheaper model for the guardian and an open fallback model in LiteLLM.
- **Why:** Gemini is multimodal, cheap and native to GCP (no keys to manage on Cloud Run). The judge belongs to **another model family** to reduce self-evaluation bias.
- **Endpoint** (checked 2026-10-12): `gemini-3.8-flash` is not served on the `europe-west1`/`europe-west4` regional endpoints (Gemini 2.5 only), but it is on the **Vertex AI EU multi-region endpoint** (`aiplatform.eu.rep.googleapis.com`, location `eu`), which keeps data in the EU; that one is used. The `global` endpoint is discarded (no EU processing guarantee, Principle #8). Fallback: `gemini-2.5-flash` on `europe-west1`.
- **Plan B in use when needed** (2026-10-14): that day the EU endpoint took 60–130 s per `gemini-3.8-flash` call, or did not answer, while `gemini-2.5-flash` on `europe-west1` answered in about 2 s (agent turns of 4–9 s, with retrieval and citations). The switch is configuration only (`VERTEX_LOCATION`, `VERTEX_ENDPOINT`, `GEMINI_MODEL`), with EU residency kept either way. Embeddings stay on the EU endpoint (`EMBEDDING_*`), because the index was built with `gemini-embedding-2`. Every Gemini call has a timeout and one retry.
- **Plan B expires** (checked 2026-10-14): `gemini-2.5-flash` is **retired on 2026-10-20**, so it only covers the demo of 15 Oct. No Gemini 3.x model is served on a single European region: all of them are on the EU multi-region endpoint, which was also slow that day for `gemini-3.5-flash` (504 errors, turns of 30–45 s). After 20 Oct, the protection against a slow endpoint is a fallback to another provider through the AI gateway (LiteLLM, milestone 3), which should be brought forward.
- **AI gateway in use** (2026-10-18, brought forward from milestone 3): every chat call goes through **LiteLLM** (`llm.LiteLLMProvider`, a LiteLLM Router per role). Gemini 3.8 Flash answers first; if a call fails or times out, the same call goes to the **fallback models in order**, all on the same Vertex AI EU endpoint (same credentials and billing, EU processing whichever answers): **Gemini 3.5 Flash**, then **Claude Haiku 4.5**. Each model has its own quota, so the second Gemini covers the frequent 429 of Gemini 3.8's shared quota; Claude, another family, also covers an outage of Gemini (14 Oct). Claude was chosen over Mistral's API (a new account and key). Only the Gemini models get the thinking level (Claude would bill for it); the timeouts and output limits are the same for all. The judge (GPT-OSS on Groq) stays a separate family. `LLM_GATEWAY=direct` calls Gemini without LiteLLM; `FALLBACK_MODELS=` (empty) turns the fallback off. Embeddings and the PDF transcription keep calling Gemini directly. **Claude's quota:** 0 on the EU endpoint; the increase was refused on 18 Oct (new project, little billing history; Google asks to wait 48 h). Until it is granted, the chain is Gemini 3.8 → Gemini 3.5 and a call that reaches Claude fails with a 429. Checked through the gateway: safety 26/26, attacks 11/11, planner 10/10, conversations 10/10. **Fallback checked on 18 Oct** with the primary forced to fail (`GEMINI_MODEL=gemini-nonexistent-0`, so every call went to Gemini 3.5 Flash): safety 26/26, planner 10/10, conversations 9/10, no infrastructure errors; conv-10 failed only because the model asked for the amount without a question mark and the simulated user answers only to a «?» (a limit of the harness).
- **One model per role** (2026-10-21, after the tutor's review: choose the models with evaluation): `MODEL_COACH`, `MODEL_PLANNER`, `MODEL_GUARDIAN` and `MODEL_VISION` give a role its own model on the same endpoint (`Settings.model_for`); a role not set uses `GEMINI_MODEL`. The fallback chain stays the same, without the model the role already uses. Candidates served on the EU endpoint (checked on 21 Oct): Gemini 3.5 Flash, 3.5 Flash-Lite and 3.1 Flash-Lite; 3.8 Flash-Lite and the 2.5 family are not (2.5 is only on `europe-west1`). Production keeps Gemini 3.8 Flash for every role until the comparison (quality, cost and latency per role) says otherwise. The evaluation records the model of each role (`meta.models`) and the tokens per role, so each run is priced model by model. On 21 Oct Gemini 3.8 Flash answered a 429 and then nothing in 120 s, while the other three answered in 1–2.5 s.
- **Evidence:** table of model per agent with quality, cost and latency; comparison of two vision models with 20 photos.

## ADR-05
**The LLM decides, the code calculates**
- **Decision:** no number without a tool; deterministic verification (`verify_plan`).
- **Why:** LLMs do not calculate reliably; in nutrition an invented number is a serious error.
- **Evidence:** plans that pass on the first attempt vs after self-correction; 0 unsourced numbers in the output guardian tests.

## ADR-06
**FastAPI + React instead of Chainlit**
- **Why:** reusable API (web, a future iOS app, evaluation, MCP), custom views (day panel, shopping list), a product demo.
- **Cost:** about 6–8 h more; the weekly menu leaves the scope in exchange.

## ADR-07
**The MCP server exposes the product, not an internal catalogue**
- **Discarded alternative:** a food MCP used only by our own agent (adds nothing over a function).
- **Why:** real interoperability with other agents, even from other frameworks, use of the three MCP primitives, and a practical case of authorization in MCP servers.

## ADR-08
**Agentic retrieval with hybrid search**
- **Why:** the agent decides when to search and rewrites the query; hybrid search usually wins with technical terms.
- **Scope** (2026-10-12): **supporting** retrieval; cross-cutting knowledge goes in the expert brief (ADR-23). Engine: Qdrant (ADR-22).
- **Evidence:** recall@k of 3–4 configurations.
- **Implementation** (2026-10-14):
  - **Corpus** (`data/guides.json`, 9 documents, licence per document): WHO fact sheets on healthy diet and physical activity, WHO physical activity guidelines 2020, EFSA DRV summary report 2017, AESAN 2022, and four ISSN position stands (protein, nutrient timing, caffeine, sports nutrition review). Downloaded by `scripts/fetch_guides.py`, never committed.
  - **Parsing that keeps tables:** PDF pages are transcribed to Markdown by Gemini (EU endpoint; public documents only). Each number of the transcription is checked against pypdf's text of the same page, and the differences are listed in `data/guides_report.md` for manual review. ISSN articles come from Europe PMC's JATS XML, and WHO fact sheets from their HTML article.
  - **Chunks:** up to about 600 tokens, split at paragraphs, tables never split. Citation tag "<document tag>, <page or section>" (e.g. "EFSA DRV 2017, p. 21"), the same format as the expert brief.
  - **Search:** dense `gemini-embedding-2` plus sparse BM25 (computed in Python, IDF in Qdrant), fused with RRF, top 4.
  - **Agent:** the `search_guides` tool adds the passages to the turn's `sources`. A passage is a valid origin for a number only when it is **cited in the same sentence**; it never counts as a tool result.
  - **No index configured:** the Coach works with the brief only.

## ADR-09
**Firestore instead of Supabase/Postgres with RLS**
- **Context:** the previous version had a Supabase schema with Row Level Security.
- **Decision:** Firestore (decided 2026-10-10).
- **Alternative:** Supabase Cloud EU with RLS (authorization also in the database, reuses the schema).
- **Why:** everything inside GCP, no servers to maintain and no extra provider; Supabase's free plan pauses inactive projects.
- **Consequence:** authorization is enforced in the backend and the tool layer; there is no second barrier in the database. Compensated with attack tests.

## ADR-10
**No fine-tuning**
- **Why:** it is only justified when no available model already does what is needed. Current models classify and reason well with prompts and tools.
- **Evidence:** metrics of the prompt-based guardian. If insufficient, distilling the guardian stays on the roadmap.

## ADR-11
**Shopping list without a budget; no scraping**
- **Alternatives:** MAPA prices (official, by category), Open Prices (real, partial coverage), supermarket scraping, web search by an agent.
- **Why:** there is no reliable price API; scraping goes against terms of use and is fragile; an agent searching for prices cannot be verified (breaks Principle #1).
- **Consequence:** an indicative cost with MAPA data stays on the roadmap.

## ADR-12
**One container on Cloud Run, EU region**
- **Why:** free tier, serverless, simple deployment; `europe-west1` to comply with GDPR (data transfers).
- **Cons:** cold starts; mitigated with live events and, if needed, a minimum instance during the demo.
- **Pending:** frontend in the same container or on Firebase Hosting.
- **Future work:** deploy the same image as two services (`api` and `mcp`) to isolate the public MCP endpoint (own limits, scaling and IAM).

## ADR-13
**DeepEval + Langfuse + G-Eval as judge**
- **Why:** DeepEval runs inside pytest (quality gate in CI/CD); Langfuse stores datasets, experiments and scores next to the traces.
- **Judge** (2026-10-12): **G-Eval only** (DeepEval) with **Claude Sonnet 5.5** as the model and **evaluation steps fixed** by hand, in CI and in the full evaluation. A single rubric.
- **Discarded alternative:** a custom judge with Claude's Batch API. It halves the cost, but with tens of cases that is a few dollars, and it duplicates code and rubrics.
- **Note:** with Claude, G-Eval uses the direct score (no weighting by token probabilities, which Claude does not expose).
- **Judge revised** (2026-10-17): **GPT-OSS 120B on Groq's free tier** (`openai/gpt-oss-120b`), a different model family from the agents (Gemini). No Anthropic key was available, and OpenCode's Go plan is restricted to coding-agent traffic. It runs at temperature 0. On a rate limit it waits and retries the **same** model: switching judges in the middle of a run would make variants incomparable. Groq is hosted outside the EU, which is acceptable because the judge only sees **synthetic test cases**, never user data. Claude Sonnet stays the alternative if the tutor prefers it (a configuration change in `evals/judge.py`). A second judge from another family (Qwen 3.8 27B, same free tier) is used only to compare judges during calibration.
- **Evaluation runs as scripts** (`evals/run.py`), not inside pytest: DeepEval's pytest plugin is disabled for the unit tests (`-p no:deepeval`), and DeepEval lives in its own dependency group (`eval`), so it never reaches the production image.

## ADR-14
**Authorization in the tool layer**
- **Why:** a prompt ("NEVER ACT AS ANOTHER USER") is not a security control.
- **Decision:** `user_id` from the token, injected by the backend; tools do not accept identifiers from the LLM.

## ADR-15
**Mojo Picón as an A2A agent (and not the internal Planner)**
- **Decision:** expose the whole Coach over A2A so external agents can delegate queries to it.
- **Discarded alternative:** the internal Planner as an A2A service. Inside the app it is forced (a direct call does the same) and barely visible in the demo.
- **Why:** it shows in one demo the difference between MCP (tools) and A2A (agents); interoperability across frameworks (ADK → LangGraph); it uses what is specific to A2A (stateful tasks, requests for information, progress).
- **If there is no time:** it remains a documented design.

## ADR-16
**Name: Mojo Picón**
- **Decision:** «Mojo Picón · dale sabor a tu vida»; «Mojo» in the interface; technical id `mojo-picon`.
- **Discarded:** *NutriCoach* (too descriptive); *NutrIA* (an existing Chilean AI nutrition app with photo analysis, and *nutria* is a rodent in English); plain *Mojo* (existing "mojo – GLP-1 Weight Tracker" app and the Keto-Mojo brand); *Sabia*, *Pizca*, *Sazón*, *Platia*, *Kalia* (valid alternatives).
- **Why:** its own identity (Canary Islands), a double meaning (flavour and energy), and "Picón" sets it apart from existing apps and fixes the Spanish pronunciation.
- **Pending if released as a product:** check registered trademarks (OEPM, EUIPO) and domain.

## ADR-17
**Direct tools for the Coach; MCP as an adapter for external agents**
- **Context:** the initial design had the Coach call the MCP server in its own container.
- **Decision** (2026-10-11): the agents call the functions in `tools/` directly. The MCP server is a **thin layer** over those same functions, for external agents (ADK, MCP Inspector, any client).
- **Discarded alternative:** the Coach through MCP (`langchain-mcp-adapters`) against its own server: an HTTP call to itself, extra latency and an internal token to manage, with no interoperability gain.
- **Why:** consistent with ADR-07: MCP makes sense when **other** agents use it. A single tool codebase guarantees the same behaviour and the same authorization on both paths.
- **Evidence:** the same tool and attack tests run through the direct path and through MCP.

## ADR-18
**Conversation state in our own Firestore session (no LangGraph checkpointer)**
- **Decision** (2026-10-11): the backend explicitly stores in `users/{uid}/sessions/{id}` only what is needed: recent messages, a summary of older ones and the **action pending confirmation** (e.g. the meal detected in a photo). Each turn, the graph runs from that state.
- **Discarded alternative:** `interrupt()` with a checkpointer (a community Firestore package or our own): there is no official one and it persists **the whole** graph state, image included.
- **Why:** full control over what is stored (never the photo); Cloud Run keeps no state between requests; GDPR export and deletion are trivial.
- **Consequence:** the photo's human-in-the-loop is implemented as a **pending action**: if the user confirms, `log_meal` runs; if they change the subject or reject it, it expires without logging anything.

## ADR-19
**Numbers verified at the output (instead of placeholders)**
- **Context:** the principles (#1) proposed that the writer use placeholders filled by code, but the mechanism was not designed and models forget or break placeholders.
- **Decision** (2026-10-11): the **output guardian** extracts every number in the answer and checks that each matches (with rounding tolerance) a result of that turn's tools or the profile. If one has no origin, the answer is regenerated with the concrete error; if it fails again, the answer is given without the number.
- **Revision** (2026-10-12, because of ADR-23): the expert brief and retrieval bring reference figures ("1,2–2 g/kg") and users write their own ("10 km"). With the original rule, a correct answer citing the guidelines was flagged as invented. Now **the valid origin depends on the kind of number**:
  1. **Personal figures** (kcal, grams of food or nutrient for this user, expenditure, what remains): **only tools**, the profile or the user's own message. If the Coach wants to give "your protein", `per_kg_target` calculates it.
  2. **Reference values** (g/kg, ml, %, ranges from the guidelines): must appear in the **brief or a retrieved chunk cited in that same sentence**. Requiring the citation avoids chance matches with the hundreds of numbers in the brief.
  3. **The user's numbers** (distances, what they say they ate): accepted.
  4. **The rest** (times, dates, number of meals): not checked.

  Details in [guardrails.md](guardrails.md#numbers-with-origin).
- **Alternatives:** placeholders (`{{kcal_restantes}}`); both mechanisms (more work with no clear gain). In the revision: accept any number from the brief or retrieval without requiring a citation (simpler, but an invented number matches easily) or check only kcal and grams (lets invented recommendations such as "3 g/kg" through).
- **Evidence:** "0 unsourced numbers" in the tests (ADR-05); precision and recall of the checker on a labelled set; number of regenerations for this cause in Langfuse.

## ADR-20
**Code layers and single access points**
- **Decision** (2026-10-11):
  - `domain/` and `tools/` do not depend on LLMs, FastAPI or MCP: they are tested on their own and used by the agents and the MCP server.
  - **`UserContext`** (uid, roles, timezone) is created by the backend when it verifies the token and reaches the tools as an **injected argument** (`InjectedToolArg`), invisible to the model (ADR-14).
  - **`get_model(role)`** is the only access point to models. Today it returns Gemini; in milestone 3 it points to LiteLLM by changing only the configuration.
- **Why:** what is expensive to change later (authorization, model access) is done right from the start.

## ADR-21
**MCP only exposes deterministic tools; what reasons goes through A2A**
- **Context:** through MCP the external agent calls tools **without going through the Coach or the guardian**. The initial list included `plan_rest_of_day`, which uses the Planner (an LLM) inside.
- **Decision** (2026-10-11): the MCP server only publishes deterministic tools (log, query, calculate). `plan_rest_of_day` is removed from MCP; planning is requested through **A2A**, where the whole Coach and the guardian take part.
- **Discarded alternative:** keep `plan_rest_of_day` in MCP with its own guardian (rules before and after planning): it duplicates controls and blurs the line between tools and agents.
- **Why:** a clean separation that is easy to defend: **MCP = tools, A2A = agents**. Protections that must always apply (authorization, validation, limits) live in `tools/` and `store/`; MCP tools do not give health advice, so they need no guardian.
- **Consequence:** if A2A is not implemented in milestone 3, external agents cannot request plans; it remains a documented design.

## ADR-22
**Qdrant instead of Chroma for retrieval**
- **Decision** (2026-10-12): Qdrant Cloud (free plan, European GCP region).
- **Alternatives:** Chroma inside the image + in-memory `rank-bm25` with hand-made RRF fusion; Qdrant in local mode inside the image.
- **Why:** **native hybrid search** (dense + sparse with fusion in the engine), metadata filters, and the index lives outside the image: **guidelines can be updated without redeploying**.
- **Cons:** one more network call; the free plan is suspended after 1 week without use and deleted after 4. Mitigated with periodic queries from CI and an ingestion script that rebuilds the collection.

## ADR-23
**Expert brief in the context + supporting retrieval**
- **Context:** with retrieval alone, the Coach sees 3–5 loose chunks and may miss the general framework; it would also search for the same things again and again. With the full guidelines in the context, every call would carry hundreds of thousands of tokens.
- **Decision** (2026-10-12): an **expert brief** of 5–15 thousand tokens, distilled from the guidelines, with source tags, at the start of the Coach's prompt and **cached**. **Retrieval over the guidelines** is kept for specific or infrequent questions and literal quotes. Numbers, in tools.
- **Alternatives:** retrieval only (previous design); brief only (loses literal quotes and the check against the official document); full guidelines in the context (cost, latency and context rot); a recipe retrieval index (roadmap).
- **Evidence:** comparison of retrieval only / brief only / brief + retrieval on quality, cost and latency.

## ADR-24
**Python 3.12**
- **Decision** (2026-10-12): Python 3.12.
- **Why:** the version with the broadest and most stable support among the project's dependencies (LangGraph/LangChain, Presidio and spaCy, DeepEval, `qdrant-client`, `a2a-sdk`, Google ADK, Pillow and `pillow-heif`), with an official `python:3.12-slim` image. Newer versions may still hit packages without prebuilt wheels.

## ADR-25
**CIQUAL as the main source of the food table; BEDCA only for Spanish and Canary products**
- **Context:** BEDCA was the planned main source. Its conditions, besides limiting use to personal, educational or non-commercial purposes, state that reproduction in electronic format requires AESAN's express authorisation; a CSV in the repository (public later, as a portfolio) is such a reproduction.
- **Decision** (2026-10-12): CIQUAL 2020 (Etalab 2.0, open, commercial reuse allowed) is the main source. BEDCA is only used for Spanish and Canary products that CIQUAL lacks (gofio, mojo picón, queso majorero, vieja, chorizo, paella), after asking AESAN for authorisation. Until then, composite dishes are **recipes** of table rows (paella, mojo picón) and single products are **approximations** with the closest food (gofio: wholemeal wheat flour; queso majorero: dry goat cheese; vieja; chorizo), all marked in the table.
- **Alternatives:** keep BEDCA first assuming educational use (legal risk when the repository is published); use a third-party copy of BEDCA (unofficial, same licence problem); other open tables (UK CoFID, Canadian Nutrient File, Australian AFCD) as main source (less Mediterranean).
- **Revision** (2026-10-12): the authorisation request was sent to AESAN. Meanwhile BEDCA values are used for the six products **as educational use while the repository is private**; the fallbacks are kept, and any public release is built with `--no-bedca` until AESAN authorises it. BEDCA vs fallback: −23 % to +66 % in kcal, which justifies preferring analysed values.
- **Consequences:** some Spanish products are approximated with French equivalents (noted per row); 38 foods without energy in CIQUAL have it derived from macronutrients with the EU factors; a commercial future is not blocked by the data licence.
- **Evidence:** the build report lists every approximation and derived value; the cross-source comparison with BEDCA is done once authorised.
