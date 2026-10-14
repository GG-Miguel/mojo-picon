# Contributing

Rules for working in this repository, for people and for the AI coding assistant (whose instructions are in [`CLAUDE.md`](CLAUDE.md)).

## Branches

| Branch | Use | Protection |
|---|---|---|
| `main` | Production | Protected: merge requests only, with green CI |
| `develop` | Integration; deployed to staging | Protected: merge requests only |
| `feat/<task>` · `fix/<task>` · `docs/…` · `chore/…` | Day-to-day work | Short-lived (hours or a few days) |

## Commits

- **Conventional Commits:** `type(scope): description`. Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`, `security`.
- Small and atomic: one logical change per commit, tests included. Every commit leaves the project working.
- Reference the issue when there is one (`Refs #12`).
- Commits are authored by the project author, without a `Co-Authored-By` line. The use of the AI assistant is acknowledged in the master's report.
- **Backdated commits are allowed** to record when work was actually done: set both `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`. Never in the future, never earlier than the parent commit, and only on commits not yet pushed. Squash merges get the merge date.
- Language: English for commits, code, comments and technical docs; Spanish for the app's interface.

## Merge requests

- Every change to `develop` or `main` goes through a merge request, using the template.
- Requirements: green CI (lint, tests, secret detection; on `main`, also the evaluation), reviewed by the author if written by the assistant, specs and docs updated if behaviour changes.
- Squash when merging work branches.

## CI/CD changes

- Validate every change to `.gitlab-ci.yml` in GitLab's **Build → Pipeline editor** before pushing: it checks the file, included templates too, without running anything. Valid YAML can still be an invalid pipeline.
- Do not redefine jobs that come from GitLab templates (e.g. `secret_detection`) unless needed, and then with all their fields. The first pipeline failed with "yaml invalid" because of such a partial override.

## Secrets

- Never in the repository: API keys, tokens, passwords, `.env`, service-account credentials.
- `.env.example` lists variable names only. Real values: Secret Manager (Cloud Run) and protected, masked GitLab CI/CD variables.
- Three barriers: `.gitignore`, pre-commit with gitleaks, GitLab Secret Detection in CI.
- If a secret leaks: revoke and rotate it first, then clean the history.

## Before making the repository public

- [ ] AESAN has authorised the use of BEDCA data, **or** `data/foods.csv` has been rebuilt with `uv run --group data python data/build_foods.py --no-bedca` (no row with source BEDCA). Check the whole history too: earlier commits of `foods.csv` with BEDCA rows are also published.
- [ ] A licence has been chosen and added.
- [ ] Secret scan of the whole history.

## Local checks

```bash
uv run pre-commit install
uv run ruff check . && uv run ruff format --check .
uv run pytest
```
