#!/usr/bin/env bash
#
# Send a spread of real requests to the deployed concierge so there is
# something worth looking at in the trace panel.
#
# The prompts are chosen to produce *different trace shapes*, not just
# volume:
#
#   1. answered from the system prompt  - no tool call at all     (8 spans)
#   2. one tool call                                               (16 spans)
#   3. the same tool twice, from one model turn                    (18 spans)
#   4. a different tool                                            (16 spans)
#   5. two *different* tools in one request                        (18 spans)
#   6. two turns in one session           - watch the input tokens grow
#
# Span counts are from a real run and are worth knowing: the count tells
# you what the agent decided to do. 8 means it answered without a tool.
#
# Usage:
#   export AGENT_URL=https://...        # from `amctl agent status`
#   export AGENT_KEY=...                # the gateway API key
#   ./seed-traffic.sh
#
set -euo pipefail

: "${AGENT_URL:?set AGENT_URL - see module 01, step 3}"
: "${AGENT_KEY:?set AGENT_KEY - see module 01, step 4}"

ask() {
  local label="$1" session="$2" message="$3"
  printf '\n\033[1m%s\033[0m\n  > %s\n' "$label" "$message"

  local body
  body=$(jq -nc --arg m "$message" --arg s "$session" \
          '{message: $m, session_id: $s, context: {}}')

  local reply
  reply=$(curl -s --max-time 120 -X POST "${AGENT_URL%/}/chat" \
            -H 'Content-Type: application/json' \
            -H "X-API-Key: $AGENT_KEY" \
            -d "$body")

  echo "$reply" | jq -r '.response // .message // .' | head -c 240
  printf '\n'
}

ask "1/6  no tool call"        "lab-obs-1" \
    "What are the pool hours?"

ask "2/6  one tool call"       "lab-obs-2" \
    "Is the honeymoon suite available the first weekend in June?"

ask "3/6  parallel tool calls" "lab-obs-3" \
    "Compare a junior suite and the presidential suite for a 3-night stay."

ask "4/6  a different tool"    "lab-obs-4" \
    "What is on the room service menu for vegetarians?"

ask "5/6  two different tools" "lab-obs-5" \
    "We are staying in tonight - what can we order to the room, and what is worth doing nearby tomorrow outdoors?"

ask "6/6a multi-turn"          "lab-obs-6" \
    "What does a deluxe room cost?"

ask "6/6b multi-turn"          "lab-obs-6" \
    "And for four nights?"

printf '\n\033[1mDone.\033[0m Seven requests sent across six sessions.\n'
printf 'Traces take a few seconds to land. Then:\n\n'
printf '  amctl agent traces grand-meridian-concierge \\\n'
printf '    --project default --env default --since 30m --json\n\n'
