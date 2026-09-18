# Room Rate Accuracy - a custom code evaluator, trace level.
#
# Checks that every rate the agent quotes can be accounted for by the
# hotel's real room rates: either a published nightly rate, or one
# multiplied by a night count.
#
# It judges rates, so it only looks at figures the answer presents as a
# rate or a stay total. A $36 risotto on the room service menu is a real
# price and none of this evaluator's business.
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
#   valid_amounts  array    []        the published nightly rates
#   max_nights     integer  30        largest multiple to accept as a total
#
# and you set their values when you add the evaluator to a monitor. For
# this hotel that is the five room rates in agent/hotel_data.py:
#
#   valid_amounts  280, 340, 380, 420, 1200
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
    """Every rate the reply quotes is a published rate, or a multiple of one."""
    import re

    if not trace.output:
        return EvalResult.skip("No output to evaluate")

    if not valid_amounts:
        return EvalResult.skip(
            "No valid_amounts configured. Add the published nightly rates to "
            "this evaluator's configuration."
        )

    text = trace.output

    # $1,140  ·  1140 USD  ·  USD 1,140
    MONEY = (r"\$\s*([\d,]+(?:\.\d{2})?)"
             r"|([\d,]+(?:\.\d{2})?)\s*(?:USD|usd|dollars)"
             r"|(?:USD|usd)\s*([\d,]+(?:\.\d{2})?)")

    # This evaluator judges rates, so it has to know which figures are
    # rates. A figure counts if the answer puts it next to a night or a
    # stay ("$340 per night", "$1,140 for three nights"), or announces it
    # as a rate or a total ("the total is $1,140"). Everything else in a
    # hotel answer - menu prices, spa treatments, square footage - is
    # somebody else's evaluator.
    AFTER = re.compile(r"^[^.]{0,25}?(night|stay)", re.I)
    BEFORE = re.compile(r"(total|rate)s?\b[^.]{0,25}$", re.I)

    rates = []
    for match in re.finditer(MONEY, text):
        raw = next((g for g in match.groups() if g), None)
        if not raw:
            continue
        if not (AFTER.search(text[match.end():match.end() + 40])
                or BEFORE.search(text[max(0, match.start() - 40):match.start()])):
            continue
        try:
            rates.append(float(raw.replace(",", "")))
        except ValueError:
            pass

    if not rates:
        return EvalResult.skip("No room rates quoted in the response")

    # A total is only legitimate for a stay length the conversation actually
    # mentions. Without this, almost any number is "some rate times some
    # number of nights" and the check passes everything.
    WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    haystack = f"{trace.input or ''} {text}".lower()
    nights = {1}
    for match in re.findall(r"(\d{1,2}|" + "|".join(WORDS) + r")[\s-]*nights?", haystack):
        count = WORDS.get(match) or int(match)
        if 1 <= count <= max_nights:
            nights.add(count)

    unit_rates = {float(a) for a in valid_amounts}
    grounded = {p * n for p in unit_rates for n in nights}

    ok, unaccounted = [], []
    for rate in rates:
        (ok if rate in grounded else unaccounted).append(rate)

    one = len(rates) == 1
    noun, verb = ("rate", "matches") if one else ("rates", "match")

    if not unaccounted:
        return EvalResult(
            score=1.0,
            passed=True,
            explanation=f"All {len(rates)} quoted {noun} {verb} the published "
                        f"rates, or a nightly multiple of them.",
        )

    shown = ", ".join(f"${a:,.0f}" for a in sorted(set(unaccounted))[:5])
    return EvalResult(
        score=len(ok) / len(rates),
        # One rate the hotel does not charge is a failed check, whatever the
        # other figures did - so do not let the proportion decide pass/fail.
        passed=False,
        explanation=f"{len(unaccounted)} of {len(rates)} quoted {noun} not "
                    f"on the rate card, and not a multiple of it for any "
                    f"stay length mentioned: {shown}. Published rates: "
                    f"{sorted(int(p) for p in unit_rates)}; nights referenced: "
                    f"{sorted(nights)}.",
    )
# --- to here ---------------------------------------------------------
