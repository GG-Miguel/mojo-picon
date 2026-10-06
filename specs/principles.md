# Principles (constitution)

Rules that are **never broken** during development. If a task conflicts with a principle, the principle wins. First step of Spec-Driven Development.

## Correctness
1. **The LLM decides, the code calculates.** No number (kcal, macronutrients, energy expenditure, quantities) reaches the user unless it comes from a tool. The output guardrail checks the origin of every number: personal figures must come from a tool of the turn; reference values from a cited source ([guardrails.md](guardrails.md#numbers-with-origin), ADR-19).
2. **No recommendation without a source.** What comes from the guidelines is cited; if retrieval finds nothing, the agent says so.
3. **Explicit uncertainty.** Estimates (photos) are given as a **range** and confirmed by the user before they are saved.

## Security
4. **Authorization never depends on the prompt.** The `user_id` comes from the authentication token; tools do not accept a `user_id` written by the LLM.
5. **External content is not trusted.** Photos, Open Food Facts data, documents and responses from third-party MCP servers are treated as data, never as instructions.
6. **Least privilege.** Each agent only has the tools it needs; no tool can touch another user's data.
7. **Risky cases go to a professional.** When there are clinical signals, the system does not improvise: it applies the [guardrail policy](guardrails.md#three-level-policy).

## Privacy
8. **Data only in the EU**, and minimised. Personal data is masked before it reaches the LLM and the traces.
9. **Users own their data:** they can export and delete it (memory and traces included).

## Quality and operations
*Concrete rules for Git and GitLab are in [CONTRIBUTING.md](../CONTRIBUTING.md).*

10. **Every change passes the evaluation** before reaching production.
11. **Every loop has a limit** on steps, tokens and cost. Stops are logged.
12. **Everything is traceable:** each answer has its trace in Langfuse.
13. **No decision without justification:** design choices are recorded in [decisions.md](decisions.md) with their evidence.
14. **Honesty:** limitations are measured and documented, not hidden.
