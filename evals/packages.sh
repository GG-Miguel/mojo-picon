#!/usr/bin/env bash
# Read the real package photos with the vision extractor (evals/packages.py), with the local .env.
#   evals/packages.sh --repeat 2
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
. ./.env
set +a
exec uv run --group eval python -m evals.packages "$@"
