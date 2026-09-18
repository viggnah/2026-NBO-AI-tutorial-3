#!/usr/bin/env python3
"""Run a custom code evaluator locally, before pasting it into the console.

    ./harness.py room_rate_accuracy.py

Custom evaluators are written and saved in the AMP Console. That is a slow
loop to debug in: save, open a monitor, wait for a run, read the score.
This runs the same function against sample traces on your machine, in
about a second.

In the console you write only the body of the evaluator: the imports, the
function name and the typed parameters above it are generated and
read-only. So this harness does the same thing the console does — it takes
the body between the `paste from here` / `to here` markers, puts the same
generated header in front of it, and calls the result with `CONFIG` as the
config parameters. `EvalResult` and a trace-level `Trace` with the surface
the real ones expose are stood in below.

It is a development aid, not a reimplementation of the evaluation engine.
The score you see here is the score that function will produce; the
plumbing around it is AMP's.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field


@dataclass
class EvalResult:
    """Mirrors amp_evaluation.EvalResult, including its constraints."""
    score: float = 0.0
    explanation: str = ""
    passed: bool | None = None
    skipped: bool = False

    def __post_init__(self) -> None:
        if not self.skipped and not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be between 0.0 and 1.0, got {self.score}")
        if self.passed is None:
            self.passed = self.score >= 0.5

    @classmethod
    def skip(cls, reason: str) -> "EvalResult":
        return cls(score=0.0, explanation=reason, skipped=True)

    def render(self) -> str:
        if self.skipped:
            return f"SKIP    —     {self.explanation}"
        mark = "pass" if self.passed else "FAIL"
        return f"{self.score:>5.0%} {mark}  {self.explanation}"


@dataclass
class ToolSpan:
    name: str = ""
    arguments: dict = field(default_factory=dict)
    result: object = None


@dataclass
class Trace:
    """The object a trace-level evaluator receives."""
    input: str = ""
    output: str = ""
    spans: list = field(default_factory=list)

    def get_tool_calls(self) -> list:
        return [s for s in self.spans if isinstance(s, ToolSpan)]

    def format_evidence(self) -> str:
        return "\n".join(
            f"{s.name}({s.arguments}) -> {s.result}" for s in self.get_tool_calls()
        )


# The framework injects these; a pasted evaluator imports them by name, so
# stand them up as a module before exec'ing one.
_amp = types.ModuleType("amp_evaluation")
_amp.EvalResult = EvalResult
_amp.Param = lambda **kwargs: kwargs.get("default")
_models = types.ModuleType("amp_evaluation.trace.models")
_models.Trace, _models.ToolSpan = Trace, ToolSpan
sys.modules["amp_evaluation"] = _amp
sys.modules["amp_evaluation.trace"] = types.ModuleType("amp_evaluation.trace")
sys.modules["amp_evaluation.trace.models"] = _models


# Real answers from the deployed concierge, plus two that never happened —
# the point of the evaluator is to tell them apart.
CASES = [
    ("real · one room",
     Trace(input="What does a deluxe room cost?",
           output="A deluxe room costs $340 per night. It features a separate "
                  "sitting area, a soaking tub, and a full harbor view.")),

    ("real · a 3-night total",
     Trace(input="Compare a junior suite and the presidential suite for a 3-night stay.",
           output="The Junior Suite covers 540 square feet. For a 3-night stay, "
                  "the total is $1,140. The Presidential Suite is $3,600 for "
                  "the same three nights.")),

    ("real · no prices at all",
     Trace(input="What are the pool hours?",
           output="The pool is open 7am-10pm daily.")),

    ("caught · a rate we do not charge",
     Trace(input="What does the garden suite cost?",
           output="The Garden Suite is $295 per night, with a private patio "
                  "and courtyard view.")),

    ("missed · plausible arithmetic, wrong room",
     Trace(input="Any deal on the honeymoon suite for two nights?",
           output="I can offer the Honeymoon Suite at $420 per night, or $760 "
                  "for two nights as a seasonal rate.")),
]

# The Config Params you would set on the evaluator in the console.
# valid_amounts matches agent/hotel_data.py.
CONFIG = {"valid_amounts": [280, 340, 380, 420, 1200], "max_nights": 30}


def load(path: str, config: dict):
    """Wrap the pasted body in the header the console generates, and return it."""
    src = open(path).read()
    try:
        body = src.split("# --- paste from here")[1].split("# --- to here")[0]
    except IndexError:
        sys.exit(f"{path}: expected '# --- paste from here' and '# --- to here' markers.")
    body = body.split("\n", 1)[1]

    # The console builds this from the level and the Config Params section;
    # the function is always called my_evaluator and the first parameter is
    # always named for the level (trace / agent_trace / llm_span).
    header = [
        "from amp_evaluation import EvalResult, Param",
        "from amp_evaluation.trace.models import Trace",
        "",
        "",
        "def my_evaluator(",
        "    trace: Trace,",
        *(f"    {key}=None," for key in config),
        ") -> EvalResult:",
    ]
    module = "\n".join(header) + "\n" + body
    scope: dict = {}
    try:
        exec(compile(module, path, "exec"), scope)
    except SyntaxError as exc:
        sys.exit(f"{path}: {exc.msg} (body line {(exc.lineno or 0) - len(header)})")
    return scope["my_evaluator"]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "room_rate_accuracy.py"
    evaluate = load(path, CONFIG)
    print(f"{path}   ·   {len(CASES)} sample traces\n")
    for label, trace in CASES:
        try:
            result = evaluate(trace, **CONFIG)
        except Exception as exc:                      # noqa: BLE001
            print(f"{label:<38} ERROR   {type(exc).__name__}: {exc}")
            continue
        print(f"{label:<38} {result.render()}")
    print()
    print("The first three are real answers from the deployed agent and score")
    print("as they should. The fourth invents a rate and is caught.")
    print()
    print("The fifth is the interesting one. $760 for two nights of a $420")
    print("room is wrong — but it is exactly two nights of the $380 junior")
    print("suite, so a rule that only knows the price list cannot fault it.")
    print("Catching that needs a judge that can read which room was being")
    print("discussed. That is what concierge_voice.md and the built-in")
    print("Groundedness evaluator are for.")


if __name__ == "__main__":
    main()
