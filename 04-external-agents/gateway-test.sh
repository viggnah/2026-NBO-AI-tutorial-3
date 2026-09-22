#!/usr/bin/env bash
#
# Talk to the LLM gateway directly, with no agent in the way.
#
#   ./gateway-test.sh            run every check
#   ./gateway-test.sh pii        just the masking one
#   ./gateway-test.sh block      just the guardrail one
#   ./gateway-test.sh ping       just a health call
#
# Reads OPENAI_BASE_URL and LLM_GATEWAY_API_KEY from crewai-agent/.env.
# Use it when the agent says it cannot reach its systems: the agent only ever
# reports that something went wrong, while the gateway says what and why.
#
set -uo pipefail
cd "$(dirname "$0")"
[ -f crewai-agent/.env ] || { echo "No crewai-agent/.env here." >&2; exit 1; }
set -a; . crewai-agent/.env; set +a

: "${OPENAI_BASE_URL:?OPENAI_BASE_URL is not set - are you in gateway mode?}"
: "${LLM_GATEWAY_API_KEY:?LLM_GATEWAY_API_KEY is not set - are you in gateway mode?}"
MODEL="${OPENAI_MODEL:-gpt-4o}"

# ---- presentation --------------------------------------------------------
# Colour only when writing to a terminal, so piping to a file stays clean.
if [ -t 1 ] && [ "${NO_COLOR:-}" = "" ]; then
  r=$'\033[0m'; b=$'\033[1m'; d=$'\033[2m'
  gold=$'\033[38;5;178m'; grn=$'\033[38;5;71m'; red=$'\033[38;5;167m'; slate=$'\033[38;5;103m'
else
  r=''; b=''; d=''; gold=''; grn=''; red=''; slate=''
fi

W=$(tput cols 2>/dev/null || echo 92); [ "$W" -gt 96 ] && W=96; [ "$W" -lt 60 ] && W=60
rule() { local i out=''; for ((i=0; i<$1; i++)); do out+="$2"; done; printf '%s' "$out"; }
plain() { printf '%s' "$1" | sed $'s/\033\\[[0-9;]*m//g'; }

top() {  # top <colour> <title>
  local t="$1" title=" $2 " len; len=${#title}
  printf '%s╭─%s%s%s%s╮%s\n' "$t" "$b" "$title" "$r$t" "$(rule $((W-3-len)) ─)" "$r"
}
bot() { printf '%s╰%s╯%s\n' "$1" "$(rule $((W-2)) ─)" "$r"; }
row() {  # row <frame-colour> <text>
  local t="$1" s="$2" v; v=$(plain "$s")
  if [ ${#v} -gt $((W-4)) ]; then printf '%s│%s %s\n' "$t" "$r" "$s"
  else printf '%s│%s %s%*s%s│%s\n' "$t" "$r" "$s" $((W-3-${#v})) '' "$t" "$r"; fi
}
gap() { row "$1" ""; }

# ---- the gateway ---------------------------------------------------------
post() {  # post <content> -> sets CODE, SECS, BODY
  local body out meta
  body=$(jq -nc --arg m "$MODEL" --arg c "$1" '{model:$m, messages:[{role:"user", content:$c}]}')
  out=$(curl -s --max-time 60 -w '\n%{http_code} %{time_total}' \
        -X POST "${OPENAI_BASE_URL%/}/chat/completions" \
        -H "API-Key: $LLM_GATEWAY_API_KEY" -H 'Content-Type: application/json' -d "$body")
  meta=$(printf '%s' "$out" | tail -1); BODY=$(printf '%s' "$out" | sed '$d')
  CODE=${meta%% *}; SECS=${meta##* }
}

ping_() {
  top "$slate" "1. Baseline"
  row "$slate" "${d}Does the gateway answer at all?${r}"
  gap "$slate"
  post "Reply with exactly: OK"
  if [ "$CODE" = "200" ]; then
    row "$slate" "  ${grn}ok${r} HTTP $CODE ${d}in ${SECS}s${r}   $(printf '%s' "$BODY" | jq -r '.choices[0].message.content')"
  else
    row "$slate" "  ${red}!!${r} HTTP $CODE ${d}in ${SECS}s${r}   $(printf '%s' "$BODY" | head -c 60)"
  fi
  bot "$slate"
}

pii() {
  local record='guest=A. Osei; contact=guest@example.com; card=4111 1111 1111 1111; room=Junior Suite; rate=380; nights=3; total=1140; arrival=2026-06-05'
  local instruction='Reformat this reservation record as a markdown bullet list. Copy every value exactly as written; do not alter, summarise or omit anything.'

  top "$gold" "2. PII masking"
  row "$gold" "${d}The gateway rewrites the request on its way out. Only the model sees${r}"
  row "$gold" "${d}the substitution, so ask the model what it received.${r}"
  gap "$gold"
  row "$gold" "${b}-> going to${r}"
  row "$gold" "  ${slate}POST ${OPENAI_BASE_URL%/}/chat/completions${r}"
  row "$gold" "  ${slate}API-Key: ${LLM_GATEWAY_API_KEY:0:14}...${r}"
  row "$gold" "  ${d}the gateway holds the provider key; this agent has none${r}"
  gap "$gold"
  row "$gold" "${b}-> what this machine sends${r}  ${d}both PII fields in the clear${r}"
  printf '%s│%s   %s\n' "$gold" "$r" "$record"
  gap "$gold"

  post "$instruction
$record"
  if [ "$CODE" != "200" ]; then
    row "$gold" "${red}!! HTTP $CODE${r}  $(printf '%s' "$BODY" | head -c 60)"
    bot "$gold"; return
  fi
  local reply; reply=$(printf '%s' "$BODY" | jq -r '.choices[0].message.content')
  row "$gold" "${b}<- what the model answered${r}  ${d}HTTP $CODE in ${SECS}s${r}"
  while IFS= read -r l; do
    case "$l" in
      *'*****'*) row "$gold" "  ${red}${l}${r}" ;;
      *)         row "$gold" "  ${l}" ;;
    esac
  done <<< "$reply"
  gap "$gold"

  if printf '%s' "$reply" | grep -q '\*\*\*\*\*'; then
    row "$gold" "${b}-> so${r}"
    row "$gold" "  ${red}contact=guest@example.com${r}   never left the gateway"
    row "$gold" "  ${red}card=4111 1111 1111 1111${r}    never left the gateway"
    row "$gold" "  ${grn}room, rate, nights, total, arrival${r}  ${d}arrived untouched${r}"
  else
    row "$gold" "  ${red}Nothing was masked.${r} Check the policy is attached, scoped to"
    row "$gold" "  POST /chat/completions, and that the regex was typed raw."
  fi
  bot "$gold"
}

block() {
  top "$red" "3. Regex guardrail"
  row "$red" "${d}A phrase the hotel cannot use. The gateway should refuse it.${r}"
  gap "$red"
  post "Reply with exactly this sentence: We will issue a full refund immediately."
  if [ "$CODE" = "200" ]; then
    row "$red" "  ${grn}allowed${r} ${d}HTTP $CODE${r}  $(printf '%s' "$BODY" | jq -r '.choices[0].message.content' | head -c 50)"
    row "$red" "  ${d}no guardrail fired - is one attached to this agent?${r}"
  else
    row "$red" "  ${red}!! blocked${r}  ${d}HTTP $CODE in ${SECS}s${r}"
    gap "$red"
    printf '%s' "$BODY" | jq -r '.message | "guardrail : \(.interveningGuardrail // "-")","direction : \(.direction // "-")","reason    : \(.actionReason // "-")"' 2>/dev/null \
      | while IFS= read -r l; do row "$red" "  $l"; done
  fi
  bot "$red"
}

printf '\n'
case "${1:-all}" in
  ping)  ping_ ;;
  pii)   pii ;;
  block) block ;;
  all)   ping_; printf '\n'; pii; printf '\n'; block ;;
  *)     echo "usage: ./gateway-test.sh [all|ping|pii|block]" >&2; exit 2 ;;
esac
printf '\n'
