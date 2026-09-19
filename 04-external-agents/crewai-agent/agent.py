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

# Set this and the agent routes its model calls through Agent Manager's LLM
# gateway instead of calling a provider directly: rate limits, access control
# and guardrails are then applied centrally, and the provider's real
# credential never reaches this process. Both values come from the console -
# Configure -> Add LLM Configuration -> Connect to LLM Provider - where
# OPENAI_BASE_URL is the Endpoint URL it shows and this is the API Key.
#
# The header is the one thing the OpenAI client cannot infer. It sends the
# key as `Authorization: Bearer`, and the gateway reads `API-Key`, so the
# key has to be attached explicitly below.
LLM_GATEWAY_KEY = os.environ.get("LLM_GATEWAY_API_KEY") or None
LLM_GATEWAY_HEADER = os.environ.get("LLM_GATEWAY_HEADER", "API-Key")

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
        extra: dict[str, Any] = {}
        if LLM_GATEWAY_KEY:
            extra["extra_headers"] = {LLM_GATEWAY_HEADER: LLM_GATEWAY_KEY}
            # Deliberately NOT the provider key. The gateway authenticates on
            # its own header and holds the real credential itself, so sending
            # ours upstream would be pointless and would leak it.
            #
            # This is a suppression, not a fallback, and it has to be: CrewAI
            # calls dotenv's load_dotenv() when it is imported, so a stale
            # OPENAI_API_KEY left in .env is back in the environment before
            # this line runs. Reading the variable here would quietly put the
            # real key in an Authorization header on every gateway call, and
            # the only place you would see it is the gateway's access log.
            # The OpenAI client will not build without something, hence the
            # placeholder.
            api_key = "amp-gateway"
        else:
            api_key = os.environ.get("OPENAI_API_KEY")

        _llm = LLM(
            model=LLM_MODEL,
            api_key=api_key,
            base_url=OPENAI_BASE_URL,
            temperature=0,
            additional_params=extra,
        )
    return _llm


# The crew is two members, and the split has to be a real one. An earlier
# version gave both the whole system prompt and asked the second to "polish"
# the first's draft; measured over five prompts its output was byte-identical
# every time, for a third of the latency and a third of the tokens. Two agents
# doing one job is not a multi-agent system, it is an expensive one.
#
# So the responsibilities are divided rather than duplicated. The concierge
# owns *what is true*: it holds the tools and produces an internal brief of
# facts, and nothing it writes is shown to anyone. The writer owns *what the
# guest reads*: it has no tools and cannot look anything up, so it can only
# phrase what the brief already contains.
#
# Each member produces its own `agent` span, so a trace shows which one spent
# the time, and the two task outputs are visibly different things - which is
# how you can tell the second one is earning its keep.


def _concierge() -> Agent:
    """Owns the facts. Holds the tools; writes for a colleague, not a guest."""
    return Agent(
        role=f"Concierge at {HOTEL_NAME}",
        goal="Establish the facts that answer the guest, using the tools.",
        backstory=(
            f"You are the concierge desk at {HOTEL_NAME}. You look things up "
            "and you are the authority on what is true.\n\n"
            f"{SYSTEM_PROMPT}\n\n"
            "On this crew you do not write to the guest. You hand a colleague "
            "an internal brief: the figures, names and details that answer the "
            "question, each one taken from a tool result or from the fixed "
            "answers above. Terse notes, not prose, and no greeting or "
            "sign-off. If a tool refuses or the data does not cover it, say so "
            "plainly in the brief so the reply can be honest."
        ),
        tools=CREW_TOOLS,
        llm=_get_llm(),
        allow_delegation=False,
        verbose=bool(os.environ.get("CREW_VERBOSE")),
    )


def _writer() -> Agent:
    """Owns the voice. No tools, so it cannot introduce a fact of its own."""
    return Agent(
        role="Guest Relations Writer",
        goal="Turn the concierge's brief into the reply the guest receives.",
        backstory=(
            f"You write to guests on behalf of {HOTEL_NAME}. The house "
            "standards are these:\n\n"
            f"{SYSTEM_PROMPT}\n\n"
            "You have no tools and no way to look anything up, which is "
            "deliberate: everything you are allowed to say is in the brief in "
            "front of you. Do not add a fact, drop one, or round a price. If "
            "the brief says something could not be found, be honest about it "
            "and offer the nearest thing that was."
        ),
        tools=[],
        llm=_get_llm(),
        allow_delegation=False,
        verbose=bool(os.environ.get("CREW_VERBOSE")),
    )


def _guardrail_refusal(exc: BaseException) -> dict[str, Any] | None:
    """Return the gateway's guardrail verdict if this exception is one.

    A blocked call does not arrive as a clean HTTP error. The gateway answers
    with the guardrail payload instead of a completion, and the OpenAI client
    raises APIResponseValidationError reporting **status 200** - so keying off
    a 422 finds nothing. The reliable signal is the body.
    """
    for err in (exc, getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
        body = getattr(err, "body", None)
        if not isinstance(body, dict):
            continue
        detail = body.get("message")
        if isinstance(detail, dict) and detail.get("action") == "GUARDRAIL_INTERVENED":
            return {
                "action": detail.get("action"),
                "guardrail": detail.get("interveningGuardrail"),
                "direction": detail.get("direction"),
                "reason": detail.get("actionReason"),
                "assessment": detail.get("assessments"),
                "type": body.get("type"),
            }
    return None


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
    # Present only when the gateway refused the call on policy grounds. The
    # chat UI renders it; a plain client can ignore it.
    policy: dict[str, Any] | None = None


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
        "llm_via_gateway": bool(LLM_GATEWAY_KEY),
        "instrumented": bool(os.environ.get("AMP_OTEL_ENDPOINT")),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        return ChatResponse(response="How can I help you today?")

    sid = req.session_id or "_anonymous_"
    history = SESSIONS.get(sid, [])

    concierge, writer = _concierge(), _writer()

    brief = Task(
        description=_task_description(history, req.message),
        expected_output=(
            "An internal brief: the facts needed to answer, as short notes. "
            "Every figure and name taken from a tool result. No greeting, no "
            "sign-off, not addressed to the guest."
        ),
        agent=concierge,
    )
    reply = Task(
        description=(
            "Write the reply the guest receives, using only the concierge's "
            "brief."
        ),
        expected_output=(
            "The final reply: prose, in character, leading with the answer. "
            "No JSON, no preamble, no restating the question."
        ),
        agent=writer,
        context=[brief],
    )

    crew = Crew(
        agents=[concierge, writer],
        tasks=[brief, reply],
        process=Process.sequential,
        verbose=bool(os.environ.get("CREW_VERBOSE")),
    )

    try:
        result = crew.kickoff()
        reply = (result.raw or "").strip() or "I'm not sure how to help with that."
    except Exception as e:
        refusal = _guardrail_refusal(e)
        if refusal is not None:
            # A policy stopped this, not an outage. Saying "our systems are
            # down" would be a lie, and it would hide the one event an
            # operator most wants to see.
            log.warning(
                "session=%s blocked by %s on the %s: %s",
                sid, refusal["guardrail"], refusal["direction"], refusal["assessment"],
            )
            return ChatResponse(
                response=(
                    "I am not able to put that in writing. Let me connect you "
                    "with our duty manager, who can help."
                ),
                policy=refusal,
            )
        log.exception("session=%s error: %s", sid, e)
        return ChatResponse(
            response="I'm having trouble reaching our systems. Please try again in a moment."
        )

    SESSIONS[sid] = (history + [(req.message, reply)])[-MAX_TURNS:]
    return ChatResponse(response=reply)
