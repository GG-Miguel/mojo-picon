#!/usr/bin/env bash
# Models per role (ADR-04): the reference and each role on a cheaper model, 3 runs per case, then one table.
#   evals/models.sh            # everything (a few hours: the judge runs two conversations at a time)
#   REPEAT=1 evals/models.sh   # a quicker pass
# Each role is measured on the sets it changes; the other roles stay on GEMINI_MODEL.
set -uo pipefail
cd "$(dirname "$0")/.."
REPEAT="${REPEAT:-3}"
CANDIDATES="${CANDIDATES:-gemini-3.5-flash-lite gemini-3.1-flash-lite}"
LIST="evals/results/models-$(date +%Y%m%d-%H%M%S).txt"
mkdir -p evals/results

run() {  # run <env assignment or -> <evals/run.sh arguments...>
  local assignment="$1"
  shift
  local marker
  marker=$(mktemp)
  echo "== ${assignment} $*"
  if [ "$assignment" = "-" ]; then
    evals/run.sh "$@" --repeat "$REPEAT" >/dev/null
  else
    env "$assignment" evals/run.sh "$@" --repeat "$REPEAT" >/dev/null
  fi
  local status=$?
  local result
  result=$(find evals/results -maxdepth 1 -name '*.json' -newer "$marker" ! -name '*-models.json' | sort | tail -1)
  rm -f "$marker"
  if [ -n "$result" ]; then
    echo "$result" >>"$LIST"
    echo "   -> $result (exit $status)"
  else
    echo "   -> no result (exit $status)"
  fi
}

run - --sets safety,attacks,planner,conversations
for model in $CANDIDATES; do
  run "MODEL_GUARDIAN=$model" --sets safety,attacks --no-judge
  run "MODEL_PLANNER=$model" --sets planner --no-judge
  run "MODEL_COACH=$model" --sets attacks,conversations
done
# shellcheck disable=SC2046
uv run --group eval python -m evals.models $(cat "$LIST")
