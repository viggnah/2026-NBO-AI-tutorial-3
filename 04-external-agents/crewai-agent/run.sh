#!/usr/bin/env bash
#
# Start, restart and stop the agent, instrumented.
#
#   ./run.sh            restart it (the one you want between config changes)
#   ./run.sh stop       stop it
#   ./run.sh status     is it up, and what is it pointed at
#   ./run.sh logs       follow the log
#
# Reads .env from this directory every time, so editing .env and running
# ./run.sh is the whole loop.
#
set -euo pipefail
cd "$(dirname "$0")"

LOG="${LOG:-/tmp/concierge-crew.log}"
VENV_PY="${VENV_PY:-.venv/bin/python}"
AMP="${AMP:-.venv/bin/amp-instrument}"

stop() {
  # Match on this directory's main.py so we never kill somebody else's agent.
  pkill -f "$PWD/main.py" 2>/dev/null || true
  pkill -f "amp_instrumentation.*$PWD" 2>/dev/null || true
  sleep 1
}

case "${1:-restart}" in
  stop)
    stop; echo "stopped." ;;

  status)
    if curl -sf --max-time 5 "http://localhost:${PORT:-8000}/health" > /dev/null 2>&1; then
      curl -s "http://localhost:${PORT:-8000}/health" | (jq . 2>/dev/null || cat)
    else
      echo "not running (no answer on http://localhost:${PORT:-8000}/health)"
      exit 1
    fi ;;

  logs)
    tail -f "$LOG" ;;

  restart|start)
    [ -f .env ] || { echo "No .env here. Copy .env.example and fill it in." >&2; exit 1; }
    [ -x "$AMP" ] || { echo "No venv yet. Run: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

    stop
    set -a; . ./.env; set +a

    : "${OPENAI_API_KEY:?OPENAI_API_KEY is not set in .env}"
    if [ -z "${AMP_OTEL_ENDPOINT:-}" ] || [ -z "${AMP_AGENT_API_KEY:-}" ]; then
      echo "! AMP_OTEL_ENDPOINT / AMP_AGENT_API_KEY not set - the agent will run untraced."
    fi

    nohup "$AMP" "$VENV_PY" main.py > "$LOG" 2>&1 &
    echo "starting (log: $LOG)"

    for _ in $(seq 1 30); do
      if curl -sf --max-time 2 "http://localhost:${PORT:-8000}/health" > /dev/null 2>&1; then
        echo
        curl -s "http://localhost:${PORT:-8000}/health" | (jq . 2>/dev/null || cat)
        echo
        # The exporter line is the only proof traces are actually going
        # somewhere - amp-instrument fails open, so the agent answers health
        # checks perfectly well while exporting nothing. Traceloop prints it
        # slightly after the port opens, so give it a few seconds rather than
        # crying wolf.
        for _ in $(seq 1 10); do
          if grep -a -m1 -i "exporting traces" "$LOG"; then exit 0; fi
          if grep -a -m1 -iE "Failed to initialize .*instrumentation" "$LOG"; then
            echo "! instrumentation did not start - the agent is running UNTRACED." >&2
            exit 0
          fi
          sleep 1
        done
        echo "! no exporter line after 10s - the agent may be running untraced. Check $LOG" >&2
        exit 0
      fi
      sleep 1
    done

    echo "! did not come up in 30s. Last lines of $LOG:" >&2
    tail -20 "$LOG" >&2
    exit 1 ;;

  *)
    echo "usage: ./run.sh [restart|stop|status|logs]" >&2; exit 2 ;;
esac
