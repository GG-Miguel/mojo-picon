# Specifications

Spec-Driven Development: what the product must do and why, written before the code. If a task conflicts with a principle, the principle wins.

| Document | Content |
|---|---|
| [principles.md](principles.md) | Rules that are never broken (the "constitution") |
| [functional-spec.md](functional-spec.md) | Use cases with acceptance criteria and non-functional requirements |
| [guardrails.md](guardrails.md) | Input and output guardrails, the three-level risk policy and numbers with origin |
| [food-table.md](food-table.md) | Sources, licences and build method of the curated food table |
| [decisions.md](decisions.md) | Architecture Decision Records (ADR-01 … ADR-25) |

## How to keep them up to date

- These documents are the English, repository copy of the author's planning notes. Content was transferred on 2026-10-12 without changes, except where marked **(implementation note)**.
- If a merge request changes behaviour, it updates the affected spec in the same merge request ([CONTRIBUTING.md](../CONTRIBUTING.md)).
- New design decisions are recorded as a new ADR in [decisions.md](decisions.md), with context, decision, discarded alternatives and the evidence needed to defend it.
- Values marked **provisional** must be validated by the author before the milestone that depends on them.
