"""Hotel concierge agent on CrewAI - FastAPI service exposing POST /chat.

Same hotel, same house style, same three tools, same HTTP contract as the
LangGraph agent in ``agent/``. Two things differ, and they are the point of
module 04:

- the framework is CrewAI rather than LangGraph, and
- nobody built or deployed this. It runs wherever you start it.

There is no Agent Manager SDK here, and no tracing code. Instrumentation is
applied at launch by ``amp-instrument`` - see this module's README.
"""

from __future__ import annotations

import logging
import os
from typing import Any

# CrewAI writes under $HOME when it is imported and again when a crew is
# constructed. On a laptop that is fine; inside a container with a read-only
# home it is a crash on import, so both paths are pinned somewhere writable
# before CrewAI loads. Keep this above the crewai imports if you move it.
os.environ.setdefault("CREWAI_STORAGE_DIR", os.path.join(os.sep, "tmp", "crewai"))
if not os.access(os.path.expanduser("~"), os.W_OK):
    os.environ["HOME"] = os.path.join(os.sep, "tmp")

# CrewAI exports its own anonymous telemetry to telemetry.crewai.com. Turn it
# off - it has nothing to do with Agent Manager. Do *not* reach for
# OTEL_SDK_DISABLED here: CrewAI honours it, but so does the exporter that
# sends traces to Agent Manager, and you would silently lose both.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

from crewai import LLM, Agent, Crew, Process, Task  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from shared import HOTEL_NAME, SYSTEM_PROMPT  # noqa: E402
from tools import CREW_TOOLS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("concierge")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")

# Optional. Set it to talk to anything that speaks the OpenAI API instead of
# OpenAI itself - Groq, vLLM, an Agent Manager LLM Service Provider. Leave it
# unset for OpenAI.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None

# CrewAI resolves the provider from the part of the model name before the
# first slash. Everything here speaks the OpenAI API, so the provider is
# always "openai" and the rest of the name is passed through untouched -
# which matters for a model whose own id contains a slash, as Groq's
# openai/gpt-oss-120b does. Set OPENAI_MODEL to the id the provider
# publishes and let this line qualify it.
LLM_MODEL = f"openai/{OPENAI_MODEL}"

# Conversation state, in memory, keyed by session_id - as in the
# platform-hosted agent. Stored as (guest, concierge) pairs.
SESSIONS: dict[str, list[tuple[str, str]]] = {}

MAX_TURNS = 8

_llm: LLM | None = None


def _get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM(
            model=LLM_MODEL,
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=OPENAI_BASE_URL,
            temperature=0,
        )
    return _llm


# The crew is two members, and the split is the reason this agent is built on
# CrewAI rather than being a second copy of the LangGraph one. The concierge
# gathers facts with the tools; the editor is handed the draft and holds it to
# the house voice, with no tools of its own and no authority to change a
# figure. Each member produces its own `agent` span, so a trace shows which
# one spent the time and which one wrote the words the guest actually read.


def _concierge() -> Agent:
    """Gathers the facts. Its backstory is the platform-hosted agent's system
    prompt, unedited, so both agents are held to identical instructions."""
    return Agent(
        role=f"Concierge at {HOTEL_NAME}",
        goal="Answer the guest's question accurately, grounded in tool data.",
        backstory=SYSTEM_PROMPT,
        tools=CREW_TOOLS,
        llm=_get_llm(),
        allow_delegation=False,
        verbose=bool(os.environ.get("CREW_VERBOSE")),
    )


def _editor() -> Agent:
    """Holds the draft to the house voice. No tools, and no licence to invent:
    everything it is allowed to say is already in front of it."""
    return Agent(
        role="Guest Relations Editor",
        goal="Make the reply sound like the house, without changing what it says.",
        backstory=(
            f"You edit outgoing guest correspondence for {HOTEL_NAME}.\n\n"
            "The standards you enforce are the concierge's own:\n\n"
            f"{SYSTEM_PROMPT}\n\n"
            "You are an editor, not a source. Every fact, figure, room name, "
            "menu item and recommendation in your version must already appear "
            "in the draft you were given. Do not add one, remove one, or round "
            "a price. If the draft is already right, return it unchanged."
        ),
        tools=[],
        llm=_get_llm(),
        allow_delegation=False,
        verbose=bool(os.environ.get("CREW_VERBOSE")),
    )


def _task_description(history: list[tuple[str, str]], message: str) -> str:
    if not history:
        return f'The guest says: "{message}"'
    transcript = "\n".join(
        f"Guest: {guest}\nConcierge: {reply}" for guest, reply in history
    )
    return (
        "Conversation so far:\n"
        f"{transcript}\n\n"
        f'The guest now says: "{message}"'
    )


app = FastAPI(title="Grand Meridian Concierge (CrewAI, externally hosted)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    response: str


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "Grand Meridian Concierge",
        "framework": "crewai",
        "hosting": "external",
        "tip": "POST /chat with {message, session_id, context}. GET /health for status.",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": LLM_MODEL,
        "base_url": OPENAI_BASE_URL or "https://api.openai.com/v1",
        "instrumented": bool(os.environ.get("AMP_OTEL_ENDPOINT")),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        return ChatResponse(response="How can I help you today?")

    sid = req.session_id or "_anonymous_"
    history = SESSIONS.get(sid, [])

    concierge, editor = _concierge(), _editor()

    answer = Task(
        description=_task_description(history, req.message),
        expected_output=(
            "A draft reply to the guest, grounded in tool data: every figure "
            "and name taken from a tool result, nothing invented."
        ),
        agent=concierge,
    )
    polish = Task(
        description=(
            "Edit the concierge's draft into the reply the guest receives. "
            "Keep every fact exactly as it stands."
        ),
        expected_output=(
            "The final reply: prose, in character, leading with the answer. "
            "No JSON, no preamble, no restating the question."
        ),
        agent=editor,
        context=[answer],
    )

    crew = Crew(
        agents=[concierge, editor],
        tasks=[answer, polish],
        process=Process.sequential,
        verbose=bool(os.environ.get("CREW_VERBOSE")),
    )

    try:
        result = crew.kickoff()
        reply = (result.raw or "").strip() or "I'm not sure how to help with that."
    except Exception as e:
        log.exception("session=%s error: %s", sid, e)
        reply = "I'm having trouble reaching our systems. Please try again in a moment."
        return ChatResponse(response=reply)

    SESSIONS[sid] = (history + [(req.message, reply)])[-MAX_TURNS:]
    return ChatResponse(response=reply)
