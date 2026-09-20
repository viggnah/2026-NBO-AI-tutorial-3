#!/usr/bin/env bash
#
# Talk to the LLM gateway directly, with no agent in the way.
#
#   ./gateway-test.sh            run every check
#   ./gateway-test.sh pii        just the masking one
#   ./gateway-test.sh block      just the guardrail one
#   ./gateway-test.sh ping       just a health call
#
# Reads OPENAI_BASE_URL and LLM_GATEWAY_API_KEY from .env in this directory.
# Use it when the agent says it cannot reach its systems: the agent only ever
# reports that something went wrong, while the gateway says what and why.
#
set -uo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "No .env here." >&2; exit 1; }
set -a; . ./.env; set +a

: "${OPENAI_BASE_URL:?OPENAI_BASE_URL is not set - are you in gateway mode?}"
: "${LLM_GATEWAY_API_KEY:?LLM_GATEWAY_API_KEY is not set - are you in gateway mode?}"
MODEL="${OPENAI_MODEL:-gpt-4o}"

b=$(printf '\033[1m'); d=$(printf '\033[2m'); r=$(printf '\033[0m')

call() {  # call <json-content> -> prints status, time, and the reply or the refusal
  local body; body=$(jq -nc --arg m "$MODEL" --arg c "$1" \
        '{model:$m, messages:[{role:"user", content:$c}]}')
  local out; out=$(curl -s --max-time 60 -w '\n%{http_code} %{time_total}' \
        -X POST "${OPENAI_BASE_URL%/}/chat/completions" \
        -H "API-Key: $LLM_GATEWAY_API_KEY" -H 'Content-Type: application/json' \
        -d "$body")
  local meta; meta=$(printf '%s' "$out" | tail -1)
  local payload; payload=$(printf '%s' "$out" | sed '$d')
  local code=${meta%% *} secs=${meta##* }
  printf '  %sHTTP %s%s in %ss\n' "$d" "$code" "$r" "$secs"
  if [ "$code" = "200" ]; then
    printf '%s' "$payload" | jq -r '.choices[0].message.content' 2>/dev/null | sed 's/^/  /'
  else
    # A policy refusal carries the guardrail that fired and its assessment.
    printf '%s' "$payload" \
      | jq -r '.message | "  guardrail : \(.interveningGuardrail // "-")\n  direction : \(.direction // "-")\n  reason    : \(.actionReason // "-")\n  assessment: \(.assessments // "-")"' 2>/dev/null \
      || printf '%s\n' "$payload" | head -c 400 | sed 's/^/  /'
  fi
}

ping_() {
  printf '\n%s1. Baseline%s  - does the gateway answer at all?\n' "$b" "$r"
  call "Reply with exactly: OK"
}

pii() {
  printf '\n%s2. PII masking%s  - the gateway rewrites the request on its way out.\n' "$b" "$r"
  printf '   %sWatch which fields come back as asterisks and which survive.%s\n' "$d" "$r"
  call 'Reformat this reservation record as a markdown bullet list. Copy every value exactly as written; do not alter, summarise or omit anything.
guest=A. Osei; contact=guest@example.com; card=4111 1111 1111 1111; room=Junior Suite; rate=380; nights=3; total=1140; arrival=2026-06-05'
}

block() {
  printf '\n%s3. Regex guardrail%s  - a phrase the hotel cannot use.\n' "$b" "$r"
  call "Reply with exactly this sentence: We will issue a full refund immediately."
}

case "${1:-all}" in
  ping)  ping_ ;;
  pii)   pii ;;
  block) block ;;
  all)   ping_; pii; block ;;
  *)     echo "usage: ./gateway-test.sh [all|ping|pii|block]" >&2; exit 2 ;;
esac
printf '\n'
