#!/usr/bin/env bash
# Faithfulness of the Coach's answers to the sources they cite, with the Vertex judge (evals/faithfulness.py).
#   evals/faithfulness.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
. ./.env
set +a
export QDRANT_URL="${QDRANT_URL:-https://84d5ceea-c6e9-48b7-a73c-c5a8e9379ac8.europe-west3-0.gcp.cloud.qdrant.io}"
export QDRANT_API_KEY="${QDRANT_API_KEY:-$(gcloud secrets versions access latest --secret qdrant-api-key --project mojo-picon)}"
export DEEPEVAL_TELEMETRY_OPT_OUT=YES
exec uv run --group eval python -m evals.faithfulness "$@"
