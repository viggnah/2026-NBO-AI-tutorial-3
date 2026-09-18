# Room Rate Accuracy - a custom code evaluator, trace level.
#
# Checks that every money figure in the agent's answer can be accounted
# for by the hotel's real price list: either a published price, or a
# published price multiplied by a night count.
#
# This is the check no built-in evaluator can do for you, because only you
# know what your rooms cost. It is also the failure that worries people
# most - a confident, well-written, fast, cheap answer quoting a rate the
# hotel does not charge.
#
# HOW THE CONSOLE EDITOR WORKS. You do not write the whole file. The top of
# the editor is generated and read-only - the imports, the function name,
# the typed first parameter that sets the evaluation level, and one line
# per config parameter you declare in the Config Params section beneath it.
# You write the body. Declare these two parameters first, in the Config
# Params section, each with a default:
#
#   Key            Type     Default
#   valid_amounts  array    []        the published prices
#   max_nights     integer  30        largest multiple to accept as a total
#
# and you set their values when you add the evaluator to a monitor. For
# this hotel that is every price in agent/hotel_data.py - the five room
# rates and the six menu prices, because the agent quotes both and this
# evaluator reads every money figure in the answer:
#
#   valid_amounts  18, 22, 32, 36, 48, 62, 280, 340, 380, 420, 1200
#   max_nights     30
#
# and the editor's fixed header becomes exactly this:
#
#   from amp_evaluation import EvalResult, Param
#   from amp_evaluation.trace.models import Trace
#
#
#   def my_evaluator(
#       trace: Trace,
#       # Configurable parameters - defined in the Config Params section below.
#       valid_amounts: list = Param(default=[], description="Published nightly prices"),
#       max_nights: int = Param(default=30, description="Largest multiple to accept as a total"),
#   ) -> EvalResult:
#
# So `trace`, `valid_amounts` and `max_nights` are already in scope, under
# those names - they are function arguments, not attributes, so it is
# `valid_amounts` and never `self.valid_amounts`. The function is always
# called `my_evaluator`, and anything you need to import is imported inside
# the body, since the header is not yours to edit - which is why
# `import re` is the first line below.
#
# Everything between the two markers is the body. Select the editor's
# existing body and paste over it.

# --- paste from here -------------------------------------------------
    """Every money figure in the reply is a published price, or a multiple of one."""
    import re

    if not trace.output:
        return EvalResult.skip("No output to evaluate")

    if not valid_amounts:
        return EvalResult.skip(
            "No valid_amounts configured. Add the published prices to this "
            "evaluator's configuration."
        )

    text = trace.output

    # $1,140  ·  1140 USD  ·  USD 1,140
    money = re.findall(
        r"\$\s*([\d,]+(?:\.\d{2})?)"
        r"|([\d,]+(?:\.\d{2})?)\s*(?:USD|usd|dollars)"
        r"|(?:USD|usd)\s*([\d,]+(?:\.\d{2})?)",
        text,
    )
    amounts = []
    for groups in money:
        raw = next((g for g in groups if g), None)
        if raw:
            try:
                amounts.append(float(raw.replace(",", "")))
            except ValueError:
                pass

    if not amounts:
        return EvalResult.skip("No money figures in the response")

    # A total is only legitimate for a stay length the conversation actually
    # mentions. Without this, almost any number is "some price times some
    # number of nights" and the check passes everything.
    WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    haystack = f"{trace.input or ''} {text}".lower()
    nights = {1}
    for match in re.findall(r"(\d{1,2}|" + "|".join(WORDS) + r")[\s-]*nights?", haystack):
        count = WORDS.get(match) or int(match)
        if 1 <= count <= max_nights:
            nights.add(count)

    unit_prices = {float(a) for a in valid_amounts}
    grounded = {p * n for p in unit_prices for n in nights}

    ok, unaccounted = [], []
    for amount in amounts:
        (ok if amount in grounded else unaccounted).append(amount)

    one = len(amounts) == 1
    noun, verb = ("figure", "matches") if one else ("figures", "match")

    if not unaccounted:
        return EvalResult(
            score=1.0,
            passed=True,
            explanation=f"All {len(amounts)} money {noun} {verb} the published "
                        f"price list, or a nightly multiple of it.",
        )

    shown = ", ".join(f"${a:,.0f}" for a in sorted(set(unaccounted))[:5])
    return EvalResult(
        score=len(ok) / len(amounts),
        # One rate the hotel does not charge is a failed check, whatever the
        # other figures did - so do not let the proportion decide pass/fail.
        passed=False,
        explanation=f"{len(unaccounted)} of {len(amounts)} money {noun} not "
                    f"on the price list, and not a multiple of it for any "
                    f"stay length mentioned: {shown}. Published prices: "
                    f"{sorted(int(p) for p in unit_prices)}; nights referenced: "
                    f"{sorted(nights)}.",
    )
# --- to here ---------------------------------------------------------
