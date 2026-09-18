#!/usr/bin/env bash
#
# Send the same seven requests module 02 sent to the platform-hosted agent,
# this time to the CrewAI agent running on your own machine.
#
# The prompts are deliberately identical. Two agents, two frameworks, two
# places to run, one set of questions — which is what makes the evaluation
# step at the end of the module a fair comparison rather than an anecdote.
#
# Unlike module 02 there is no gateway and no API key: this agent is not
# behind Agent Manager's ingress, you are calling it directly.
#
# Usage:
#   ./seed-traffic.sh                    # defaults to http://localhost:8000
#   AGENT_URL=http://host:8000 ./seed-traffic.sh
#
set -euo pipefail

AGENT_URL="${AGENT_URL:-http://localhost:8000}"

if ! curl -sf --max-time 5 "${AGENT_URL%/}/health" > /dev/null; then
  echo "No agent answering on ${AGENT_URL%/}/health." >&2
  echo "Start it first:  cd crewai-agent && amp-instrument python main.py" >&2
  exit 1
fi

ask() {
  local label="$1" session="$2" message="$3"
  printf '\n\033[1m%s\033[0m\n  > %s\n' "$label" "$message"

  local body
  body=$(jq -nc --arg m "$message" --arg s "$session" \
          '{message: $m, session_id: $s, context: {}}')

  # Captured into variables rather than piped into `head`: a pipeline that
  # closes early sends SIGPIPE to jq, and with `set -o pipefail` that ends
  # the whole run three prompts in.
  local raw text
  raw=$(curl -s --max-time 180 -X POST "${AGENT_URL%/}/chat" \
          -H 'Content-Type: application/json' -d "$body") || raw=''
  text=$(printf '%s' "$raw" | jq -r '.response // .message // .' 2>/dev/null) \
    || text="$raw"
  printf '%s\n' "${text:0:240}"
}

ask "1/7  no tool call"        "ext-1" \
    "What are the pool hours?"

ask "2/7  one tool call"       "ext-2" \
    "Is the honeymoon suite available the first weekend in June?"

ask "3/7  same tool twice"     "ext-3" \
    "Compare a junior suite and the presidential suite for a 3-night stay."

ask "4/7  a different tool"    "ext-4" \
    "What is on the room service menu for vegetarians?"

ask "5/7  two different tools" "ext-5" \
    "We are staying in tonight — what can we order to the room, and what is worth doing nearby tomorrow outdoors?"

ask "6/7  multi-turn"          "ext-6" \
    "What does a deluxe room cost?"

ask "7/7  multi-turn"          "ext-6" \
    "And for four nights?"

printf '\n\033[1mDone.\033[0m Seven requests across six sessions.\n'
printf 'Traces are batched, so give them a few seconds, then open the agent\n'
printf 'in the console and look at OBSERVABILITY -> Traces.\n\n'
