# Module 00 - Starting Point: a working agent, running locally

**Duration:** 5 min

A concierge agent for *The Grand Meridian*, built on LangGraph and
OpenAI's tool-calling API. One endpoint:

```
POST /chat   { "message": str, "session_id": str, "context": {} }
         →   { "response": str }
```

Three tools - `check_room_availability`, `get_room_service_menu`,
`get_local_recommendations` - and a unit-test suite covering each tool's
pure logic.

Nothing here is wrong. This is what a working agent looks like on the day
you finish writing it. The rest of the lab is about what is missing.

## Run it

```bash
cd agent
python3.11 -m venv .venv && source .venv/bin/activate   # 3.11 or 3.12; avoid 3.13/3.14
pip install -r requirements.txt

cp .env.example .env
# Edit .env - paste your OPENAI_API_KEY
set -a; source .env; set +a

python main.py
# → listening on http://localhost:8000
```

## The tests pass

```bash
python -m pytest tests/ -q
# → 8 passed
```

Worth pausing on what those eight tests actually assert. They check that
`check_room_availability("honeymoon", "2026-06-05", 2)` returns a total of
`840`, and that a bad date is rejected. They say nothing about whether the
*agent* answers a guest correctly, stays in character, invents a room type
that does not exist, or takes nine seconds to do it.

They pass whether the system prompt is good or catastrophic. Module 03 is
about that gap.

## Smoke test

Open the chat widget:

```bash
open web/index.html         # macOS; Linux: xdg-open web/index.html
```

The Grand Meridian landing page loads. Click the launcher in the
bottom-right, then pick a chip - *Check availability*, *Room service*,
*Things to do nearby* - or type your own question. The agent replies in
the panel.

<details>
<summary>Or via curl</summary>

```bash
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Is the honeymoon suite available the first weekend in June?",
       "session_id": "smoke-1", "context": {}}' | jq
```

</details>

## The crack

In the widget, ask something that needs more than one tool call:

> *"Compare a junior suite and the presidential suite for a 3-night stay."*

You get a good answer. Now look at the terminal running the agent:

```
INFO:     127.0.0.1:52118 - "POST /chat HTTP/1.1" 200 OK
```

One line. One request in, one response out.

In between, the model was called at least twice, decided on its own to
invoke `check_room_availability` twice with arguments it chose, and spent
tokens you are paying for. None of that is visible. If the answer had been
wrong, there is nothing here to tell you *where* it went wrong - only that
a 200 was returned.

That is the gap module 02 closes. But first the agent has to live
somewhere other than your own machine.

<details>
<summary>Or via curl</summary>

```bash
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Compare a junior suite and the presidential suite for a 3-night stay",
       "session_id": "crack-1", "context": {}}' | jq
```

</details>

## What is missing

Five things, and the next four modules take them in order:

| Missing | Module |
|---|---|
| Anywhere to run but this machine | 01 - Build & Deploy |
| Any view of what happened inside a request | 02 - Observability |
| Any measure of whether the answers are good | 03 - Evaluation |
| Any of the above for agents you did not build | 04 - External Agents |

---

Next: [Module 01 - Build & Deploy](../01-build-deploy/README.md)
