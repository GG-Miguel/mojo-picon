#!/usr/bin/env bash
# Simulated attacker (evals/red_team.py) with the local .env (GROQ_API_KEY for the evaluator) and Qdrant's key.
#   evals/red_team.sh --per-type 2
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
. ./.env
set +a
export QDRANT_URL="${QDRANT_URL:-https://84d5ceea-c6e9-48b7-a73c-c5a8e9379ac8.europe-west3-0.gcp.cloud.qdrant.io}"
export QDRANT_API_KEY="${QDRANT_API_KEY:-$(gcloud secrets versions access latest --secret qdrant-api-key --project mojo-picon)}"
export DEEPEVAL_TELEMETRY_OPT_OUT=YES DEEPTEAM_TELEMETRY_OPT_OUT=YES
exec uv run --group eval python -m evals.red_team "$@"
