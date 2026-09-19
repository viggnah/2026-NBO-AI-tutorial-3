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
PIDFILE=".run.pid"
VENV_PY="${VENV_PY:-.venv/bin/python}"
AMP="${AMP:-.venv/bin/amp-instrument}"

# Load .env early so PORT is known to every subcommand, not just start.
[ -f .env ] && { set -a; . ./.env; set +a; }
PORT="${PORT:-8000}"

port_pids() { lsof -ti "tcp:$PORT" 2>/dev/null || true; }

stop() {
  # `amp-instrument python main.py` is two processes: the wrapper and the
  # python child that actually binds the port. Kill the recorded wrapper and
  # its children, then sweep anything still holding the port - the child's
  # command line is relative (".venv/bin/python main.py"), so pattern-matching
  # on an absolute path silently matches nothing and leaves the old agent
  # running while the new one dies on "address already in use".
  if [ -f "$PIDFILE" ]; then
    local pid; pid=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi

  local pids; pids=$(port_pids)
  [ -n "$pids" ] && kill $pids 2>/dev/null || true

  for _ in $(seq 1 20); do
    [ -z "$(port_pids)" ] && return 0
    sleep 0.5
  done

  pids=$(port_pids)
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  sleep 1
  [ -z "$(port_pids)" ] || { echo "! port $PORT is still held by: $(port_pids)" >&2; return 1; }
}

case "${1:-restart}" in
  stop)
    stop; echo "stopped." ;;

  status)
    if curl -sf --max-time 5 "http://localhost:$PORT/health" > /dev/null 2>&1; then
      curl -s "http://localhost:$PORT/health" | (jq . 2>/dev/null || cat)
    else
      echo "not running (no answer on http://localhost:$PORT/health)"; exit 1
    fi ;;

  logs)
    tail -f "$LOG" ;;

  restart|start)
    [ -f .env ] || { echo "No .env here. Copy .env.example and fill it in." >&2; exit 1; }
    [ -x "$AMP" ] || { echo "No venv yet. Run: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }
    # There are two valid ways to be configured, and gateway mode is the one
    # where OPENAI_API_KEY is *meant* to be absent - step 9 tells you to
    # comment it out, because the platform holds the provider credential.
    if [ -n "${LLM_GATEWAY_API_KEY:-}" ]; then
      [ -n "${OPENAI_BASE_URL:-}" ] || {
        echo "LLM_GATEWAY_API_KEY is set but OPENAI_BASE_URL is not." >&2
        echo "Both come from the console: Configure -> Add LLM Configuration -> Connect to LLM Provider." >&2
        exit 1; }
      if [ -n "${OPENAI_API_KEY:-}" ]; then
        echo "! OPENAI_API_KEY is still set while routing through the gateway. The agent"
        echo "  ignores it, but it does not need to be there - see step 9.2."
      fi
    else
      [ -n "${OPENAI_API_KEY:-}" ] || {
        echo "Neither OPENAI_API_KEY nor LLM_GATEWAY_API_KEY is set in .env." >&2
        echo "Set OPENAI_API_KEY to call the provider directly, or set OPENAI_BASE_URL" >&2
        echo "and LLM_GATEWAY_API_KEY to route through Agent Manager (step 9)." >&2
        exit 1; }
    fi

    stop || exit 1

    if [ -z "${AMP_OTEL_ENDPOINT:-}" ] || [ -z "${AMP_AGENT_API_KEY:-}" ]; then
      echo "! AMP_OTEL_ENDPOINT / AMP_AGENT_API_KEY not set - the agent will run untraced."
    fi

    nohup "$AMP" "$VENV_PY" main.py > "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    echo "starting (pid $(cat $PIDFILE), log: $LOG)"

    for _ in $(seq 1 30); do
      # A bind failure is fatal and immediate; catch it rather than waiting
      # out the timeout.
      if grep -aq "address already in use" "$LOG"; then
        echo "! port $PORT is already in use - the old agent is still running." >&2; exit 1
      fi
      if curl -sf --max-time 2 "http://localhost:$PORT/health" > /dev/null 2>&1; then
        echo; curl -s "http://localhost:$PORT/health" | (jq . 2>/dev/null || cat); echo
        # The exporter line is the only proof traces are going anywhere -
        # amp-instrument fails open, so the agent answers health checks
        # perfectly well while exporting nothing.
        for _ in $(seq 1 10); do
          grep -a -m1 -i "exporting traces" "$LOG" && exit 0
          if grep -a -m1 -iE "Failed to initialize .*instrumentation" "$LOG"; then
            echo "! instrumentation did not start - running UNTRACED." >&2; exit 0
          fi
          sleep 1
        done
        echo "! no exporter line after 10s - may be running untraced. Check $LOG" >&2
        exit 0
      fi
      sleep 1
    done

    echo "! did not come up in 30s. Last lines of $LOG:" >&2
    tail -20 "$LOG" >&2; exit 1 ;;

  *)
    echo "usage: ./run.sh [restart|stop|status|logs]" >&2; exit 2 ;;
esac
