#!/usr/bin/env bash
#
# Create a Past-Traces monitor over the agent's recent traffic, with three
# rule-based evaluators configured properly.
#
# The console is the normal way to do this, and it is what module 03 walks
# through - it handles LLM-as-Judge credentials for you. This script exists
# for the other case: when you want the same monitor, identically, every
# time. Put it in CI after a deploy and every release gets evaluated the
# same way.
#
# It uses rule-based evaluators so that it needs no LLM credentials and can
# run anywhere without a secret to inject. That is a property of this
# script, not a rule about where judges belong - add judges and their
# provider configuration whenever you want them, in either monitor type.
#
# To add one, put the provider alongside the evaluators in the body:
#
#   llmProvider: { providerName: "<your llm provider>" },
#   evaluators: [ ..., pick("Completeness"; { model: "gpt-4o", temperature: 0 }) ]
#
# The model name goes in bare. The provider already says which vendor it
# is, and the runner prefixes the template itself.
#
# Usage:
#   ./create-monitor.sh [agent-name] [hours-back]
#
set -euo pipefail

AGENT="${1:-grand-meridian-concierge}"
HOURS="${2:-6}"
PROJECT="${PROJECT:-default}"
ENVIRONMENT="${ENVIRONMENT:-default}"
NAME="${NAME:-lab-quality-check}"

command -v jq >/dev/null || { echo "jq is required"; exit 1; }

# The window must be entirely in the past - traceEnd in the future is rejected.
if date -u -v-1H >/dev/null 2>&1; then          # BSD date (macOS)
  START=$(date -u -v-"${HOURS}"H +%Y-%m-%dT%H:%M:%SZ)
  END=$(date -u -v-2M +%Y-%m-%dT%H:%M:%SZ)
else                                            # GNU date (Linux)
  START=$(date -u -d "${HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)
  END=$(date -u -d "2 minutes ago" +%Y-%m-%dT%H:%M:%SZ)
fi

echo "Evaluating traces from $START to $END"

# Evaluators are referenced by the id and identifier the platform assigns,
# so read them from the org rather than hardcoding them.
CATALOG=$(amctl api --project "$PROJECT" '/orgs/{org}/evaluators')

BODY=$(jq -n \
  --argjson catalog "$CATALOG" \
  --arg env "$ENVIRONMENT" --arg name "$NAME" \
  --arg start "$START" --arg end "$END" '
  def pick($display; $config):
    ($catalog.evaluators[] | select(.displayName == $display)) as $e
    | { evaluatorId: $e.id, identifier: $e.identifier, displayName: $e.displayName,
        type: $e.type, level: $e.level, version: $e.version, config: $config };

  { environmentName: $env,
    name: $name,
    displayName: "Lab Quality Check",
    description: "Rule-based quality baseline over recent traffic.",
    type: "past",
    traceStart: $start,
    traceEnd: $end,
    evaluators: [
      pick("Length Compliance";   { min_length: 20, max_length: 2000 }),
      pick("Latency Performance"; { max_latency_ms: 5000 }),

      # Content Safety skips unless it has something to look for. Give it
      # real values at creation time - an evaluator that skips every trace
      # contributes nothing to the score and is easy to mistake for a pass.
      pick("Content Safety"; {
        case_sensitive: false,
        prohibited_strings: ["guarantee", "guaranteed", "refund", "free upgrade"],
        prohibited_patterns: ["\\b\\d{13,16}\\b", "\\b[\\w.+-]+@[\\w-]+\\.[\\w.]+\\b"]
      })
    ] }')

echo "$BODY" | amctl api --project "$PROJECT" \
  "/orgs/{org}/projects/{project}/agents/$AGENT/monitors" --input - \
  | jq -r '"Created monitor \(.name) - run \(.latestRun.status // "queued")"'

cat <<NEXT

Watch it, then read the scores:

  amctl api --project $PROJECT \\
    '/orgs/{org}/projects/{project}/agents/$AGENT/monitors/$NAME/runs' \\
    | jq -r '.runs[0] | "\\(.status)  \\(.completedAt // "")"'

  amctl api --project $PROJECT \\
    '/orgs/{org}/projects/{project}/agents/$AGENT/monitors/$NAME/scores' \\
    -X GET -f startTime="$START" -f endTime="$END" \\
    | jq -r '.evaluators[] | "\\(.evaluatorName)  mean=\\(.aggregations.mean)  n=\\(.count)  skipped=\\(.skippedCount)"'

NEXT
