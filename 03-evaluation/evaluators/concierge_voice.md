# Concierge Voice - a custom LLM-judge evaluator, trace level

An LLM-judge evaluator is a prompt, not code. You write the criteria and
the rubric; the platform appends the instructions that make the model
return a structured score and explanation - so do not write output-format
instructions yourself.

Access trace data with `{expression}`, Python f-string style. Expressions
are allowed (`{len(trace.spans)}`, comprehensions); statements are not.
The prompt below uses the three fields a trace-level judge almost always
wants - `trace.input`, `trace.output`, and `trace.format_evidence()`,
which renders the tool results and retrieved documents the agent actually
had in front of it.

## Why a judge and not a rule

`room_rate_accuracy.py` next door is a rule, and it catches an invented
rate cleanly. It also misses this: an answer offering *"$420 per night, or
$760 for two nights"*. That total is wrong for a $420 room - but it is
exactly two nights of the $380 junior suite, so a rule holding a price
list cannot fault it.

Catching that needs something that can read *which room was being
discussed*. So does every other rule in `agent/system_prompt.py` worth
enforcing: lead with the answer, stay in character, never invent a room
type, never surface a tool error to a guest. None of those are
expressible as a regex.

That is the division of labour. Rules for what you can count. Judges for
what you would otherwise have to read.

## The prompt

```text
You are an expert evaluator. Your sole criterion is CONCIERGE STANDARD: does this response meet the service standards of The Grand Meridian, a luxury hotel? Judge the concierge, never the guest.

Guest Query: {trace.input}
Concierge Response: {trace.output}

Evidence Available to the Concierge:
{trace.format_evidence()}

Evaluation Steps:
1. GROUNDED. Check every price, room name, room size, menu item and recommendation in the response against the evidence above. A figure that is a stated nightly rate multiplied by a stay length the guest asked about is correct; a figure attributable to a different room than the one under discussion is not, however plausible the arithmetic looks.
2. ANSWER FIRST. Check that the response opens with what the guest asked for, rather than with pleasantries, an apology, or a restatement of the question.
3. IN CHARACTER. Warm, concise, slightly formal - a concierge, not a chatbot and not a brochure. At most one follow-up offer, and only where it genuinely serves the guest.
4. NO LEAKED PLUMBING. No error text, tool names, JSON, stack traces or internal identifiers. Where a tool failed, the response apologises briefly and offers the nearest alternative without narrating the machinery.
5. HONEST LIMITS. Where the evidence does not cover the request, the response says so and offers a handover, rather than filling the gap with something invented or generic.

Weigh grounding above the other four: a beautifully written answer carrying a rate the hotel does not charge is worse than a plain one.

Scoring Rubric:
  0.0  = States something the evidence contradicts - an invented rate, room type or amenity
  0.25 = Grounded, but badly off standard: leaked plumbing, or the answer buried under pleasantries
  0.5  = Accurate and usable, with two or more standards clearly missed
  0.75 = Meets the standards with one minor lapse
  1.0  = All five standards met - grounded, answer-first, in character, clean, and honest about its limits
```

## Configuration

Pick **LLM-Judge** as the type and **trace** as the level, and the Config
Params section arrives with the four parameters every judge takes already
in it. Only the first has no default:

| Parameter | Set to | Why |
|---|---|---|
| `model` | `gpt-4o` | Required, and just the model name - the provider already names the vendor. Step 1 needs arithmetic and cross-referencing against tool output; a smaller judge scores tone well and grounding poorly. |
| `temperature` | `0` (the default) | You want the same trace to score the same way twice. |
| `max_tokens` | `1024` (the default) | Enough for a score and a two-sentence explanation. |
| `max_retries` | `2` (the default) | Retries when the model returns something unparseable. |

The *provider* those calls go through is not set here - you choose it once
per monitor, and every judge in that monitor shares it.

The run's **Logs** tab is where a judge accounts for itself: how many
evaluations it scored, how many it declined, and the reason for each one
it declined.

## Making it reusable

Add your own config parameter and this evaluator stops being about one
hotel. In **Config Params**, add:

| Key | Type | Default |
|---|---|---|
| `property_name` | string | `The Grand Meridian` |

Then replace the hotel's name in the first line with `{property_name}`.
The same evaluator now serves every property in the group, configured per
monitor - the same reuse-with-a-contract idea as an Agent Kind, applied to
quality standards instead of to agents.
