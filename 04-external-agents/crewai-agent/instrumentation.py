"""Tool spans, emitted by hand against Agent Manager's published contract.

Why this file exists
--------------------
Zero-code instrumentation patches a fixed catalogue of libraries. For CrewAI
that catalogue covers `Crew.kickoff`, `Agent.execute_task`, `Task.execute_sync`
and `LLM.call` - and nothing that runs a tool. The arguments the model chose
still reach the trace, buried in the message array of the next LLM span, but
there is no span carrying a tool's name, duration or status. So a failing tool
raises no error badge, matches no `--condition tool_call_fails`, and is
invisible to any evaluator that reads tool spans.

This closes that gap. `traced_tool` wraps a plain function so every call emits
one `execute_tool` span with the attributes Agent Manager reads. Spans written
this way render exactly like auto-instrumented ones, because the contract is
the same one the managed instrumentation writes to.

The attributes, and what each one buys (see the AMP instrumentation guide):

    gen_ai.operation.name = "execute_tool"   the span's kind - which icon and
                                             card render, which evaluators apply
    gen_ai.tool.name                         the tool name header
    gen_ai.system / gen_ai.provider.name     the vendor chip. Both are set: the
                                             published table names the first,
                                             the SDK now emits the second
    traceloop.entity.input  (JSON)           the arguments the model chose
    traceloop.entity.output (JSON)           what came back
    span status Error                        the error badge and the trace
                                             list's error count

No exporter is configured here. Under `amp-instrument` a tracer provider is
already installed and these spans travel with the rest; run the agent bare and
`get_tracer` hands back a no-op that costs nothing and drops them. There is
deliberately no `init_otel()` call - that is for agents with no auto
instrumentation at all, and calling it here would configure a second exporter
for spans that already have one.
"""

from __future__ import annotations

import functools
import json
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_tracer = trace.get_tracer("grand-meridian-concierge.tools")

# Attribute values long enough to be truncated by a collector help nobody, and
# a tool that returns the whole menu gets close. Trim before export.
_MAX_ATTR_CHARS = 8192


def _truncate(text: str) -> str:
    if len(text) > _MAX_ATTR_CHARS:
        return text[:_MAX_ATTR_CHARS] + "...(truncated)"
    return text


def _encode(value: Any) -> str:
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return _truncate(text)


def traced_tool(fn: Callable[..., str]) -> Callable[..., str]:
    """Emit one `execute_tool` span per call of `fn`.

    Wraps a tool that returns a JSON string. The span is a child of whatever
    the agent is doing at the time, so it lands under the agent span rather
    than floating at the root.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        name = fn.__name__
        with _tracer.start_as_current_span(
            f"execute_tool {name}", kind=SpanKind.INTERNAL
        ) as span:
            span.set_attribute("gen_ai.operation.name", "execute_tool")
            span.set_attribute("gen_ai.tool.name", name)
            span.set_attribute("gen_ai.system", "crewai")
            span.set_attribute("gen_ai.provider.name", "crewai")

            # Positional arguments are recorded by index: CrewAI calls tools
            # with keywords, so this is a fallback rather than the normal path.
            arguments: dict[str, Any] = dict(kwargs)
            arguments.update({str(i): a for i, a in enumerate(args)})
            span.set_attribute("traceloop.entity.input", _encode(arguments))

            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                # These tools are written never to raise, so reaching here is
                # itself the finding. Record it rather than swallowing it.
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("error.type", type(exc).__name__)
                raise

            # These tools already return JSON, so pass the string through
            # rather than encoding it a second time - `_encode` is for values
            # that are not JSON yet, and double-encoding renders as an escaped
            # blob instead of a structured payload.
            try:
                parsed = json.loads(result)
            except (TypeError, ValueError):
                parsed = None
                span.set_attribute("traceloop.entity.output", _encode(result))
            else:
                span.set_attribute("traceloop.entity.output", _truncate(result))

            # A tool that answers `{"error": ...}` returned normally but did
            # not succeed. Without this the span is green and the failure is
            # only visible to somebody reading the payload.
            if isinstance(parsed, dict) and "error" in parsed:
                span.set_status(Status(StatusCode.ERROR, str(parsed["error"])))
                span.set_attribute("error.type", "ToolRefused")

            return result

    return wrapper
