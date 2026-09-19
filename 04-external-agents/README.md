# Module 04 - External Agents: governed without being run

**Duration:** 20 min

Modules 01 through 03 all rested on one assumption: Agent Manager built the
agent, so Agent Manager could instrument it. Some agents an organisation ends
up governing are written by another team, on another framework, running in
another account - and some of them belong to a vendor.

This module takes an agent the platform has never seen, and gets back the
two things modules 02 and 03 were about: a trace per request, and a score
per trace. Nothing is deployed. Nothing is rebuilt.

## What is in this folder

A second concierge for the same hotel:

```
crewai-agent/
  agent.py            FastAPI service and a two-member crew
  tools.py            the same three tools, bound to CrewAI
  instrumentation.py  the tool spans CrewAI does not emit
  shared.py           imports the hotel data and system prompt from ../../agent
  main.py             entry point
  run.sh              start / restart / stop it, instrumented
web/index.html      light-mode demo page: chat plus what the gateway did
seed-traffic.sh
```

It is deliberately the same product and deliberately a different build:

| | `agent/` (modules 01–03) | `crewai-agent/` (this module) |
|---|---|---|
| Framework | LangGraph | CrewAI |
| Shape | one agent, a tool-calling loop | two agents in sequence |
| Hosting | Platform-Hosted, built from Git | Externally-Hosted, started by you |
| In front of it | Agent Manager's ingress gateway | nothing |
| HTTP contract | `POST /chat` | the same |
| Hotel data, system prompt | `agent/hotel_data.py`, `agent/system_prompt.py` | **the same files**, imported |
| Instrumentation | injected at deploy | `amp-instrument` at launch |

The data and the prompt are imported rather than copied, so the claim that
this is the same concierge is one you can check rather than take on trust.
`shared.py` is the three lines that do it. Any difference you see between
the two agents is the framework, because nothing else was allowed to vary.

### Two agents, not one

The platform-hosted agent is a single tool-calling loop. This one is a crew of
two, because that is what CrewAI is for and because a real external agent is
rarely a clone of yours:

| Member | Tools | Owns | Produces |
|---|---|---|---|
| **Concierge at The Grand Meridian** | all three | what is true | an internal brief of facts |
| **Guest Relations Writer** | none | what the guest reads | the reply |

Both are given the *same* `agent/system_prompt.py` as their standard, so the
house style is defined in one place. What differs is the job: the concierge
looks things up and writes terse notes for a colleague, and the writer - which
has no tools and therefore no way to invent a price - turns those notes into
prose.

**The division has to be real, and it is worth knowing how we found out.** An
earlier version of this crew gave both members the whole prompt and asked the
second to "polish" the first's draft. Measured across five prompts, its output
was **byte-identical every time**, for a third of the latency and a third of
the tokens. That is the failure mode of multi-agent design: two agents doing
one job, which is not a system, just a bill. Splitting the responsibility
instead of duplicating it took the same five prompts to 25-72% similarity
between brief and reply, and the total request got *faster*, because the
concierge no longer writes prose nobody reads.

This matters in two places later. In the trace, each member gets its own
`agent` span, so you can see which one spent the time and which one wrote the
words the guest actually read. In evaluation, the brief is something module 03
could only describe in the abstract - an intermediate model call the guest
never sees, which an LLM-level evaluator scores anyway.

## Why it does not need to be reachable

The natural first question about an externally-hosted agent is how the
platform gets to it. It does not. Traces travel the other way:

```
your machine                         Agent Manager
  crewai-agent  ──── OTLP/HTTPS ────▶  OTel endpoint  ──▶  traces, evaluation
                     outbound only
```

There is no inbound connection, no tunnel, no public hostname, no firewall
rule. The agent opens one outbound HTTPS connection and pushes spans down
it. That is why this module runs on the laptop in front of you, and why the
same steps work unchanged on a VM in your own data centre.

The trade is on the other side: because there is no gateway in front of
this agent, the API-key authentication module 01 got for free is yours to
provide.

## Step 1 - Run it, unwatched

Get the agent working before adding anything to it - the same order module
00 used.

```bash
cd crewai-agent

python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env - paste your OPENAI_API_KEY
set -a; source .env; set +a

python main.py
# → listening on http://localhost:8000
```

> **Python 3.12, not 3.13 or 3.14.** CrewAI's packaging requires
> `>=3.10,<3.14`, so 3.14 cannot resolve at all. The Agent Manager
> instrumentation is published for 3.10 through 3.13.

> **Any OpenAI-compatible endpoint works.** Set `OPENAI_BASE_URL` and point
> `OPENAI_MODEL` at whatever that provider calls the model - Groq, vLLM, or
> an Agent Manager LLM Service Provider. Nothing else changes, and the
> traces are the same shape, because the spans come from the OpenAI SDK
> rather than from OpenAI:
>
> ```
> OPENAI_BASE_URL=https://api.groq.com/openai/v1
> OPENAI_MODEL=openai/gpt-oss-120b
> ```

In a second terminal:

```bash
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What does a junior suite cost for three nights?",
       "session_id":"ext-smoke","context":{}}' | jq -r .response
```

A working agent, invisible to everything - which is exactly where module 00
started, and the state most agents in an organisation are actually in.

## Step 2 - Register it

In the console, open a project and click **Add Agent**. This time take
**Externally-Hosted Agent** rather than Platform-Hosted.

Any project will do. Module 01 asked for the **Default Project** only
because its `amctl` commands pass `--project default`; nothing in this
module touches the CLI, so register the agent wherever you like. A project
you create for the occasion keeps this agent's traces and monitors away
from module 01's, which makes the comparison in step 7 easier to navigate
rather than harder.

| Field | Value |
|---|---|
| Name | `Grand Meridian Concierge External` |
| Description (optional) | `CrewAI concierge, running outside the platform` |

Notice what the form does *not* ask for: no repository, no branch, no
buildpack, no start command, no port, no environment variables. There is
nothing to build and nothing to deploy, so there is nothing to describe.
Registration creates a record to hang observability and governance on.

Click **Register**. The **Setup Agent** panel opens on its own.

## Step 3 - Take the endpoint and the key

The Setup Agent panel carries the two values the agent needs. Pick a
**Token Duration** and click **Generate**.

**Copy the key immediately.** It is shown once. If you lose it, generate
another - the old one keeps working until you do.

```bash
export AMP_OTEL_ENDPOINT="..."   # from the panel
export AMP_AGENT_API_KEY="..."   # from the panel
```

> **These have to be shell variables.** `amp-instrument` reads them from
> the process environment when it launches and does not load a `.env` file.
> If you keep them in one, export it first:
> `set -a; source .env; set +a`.

> **On the hosted version, every environment shows the same OTel endpoint.**
> The cloud fronts all of them with one managed ingest address, so do not
> be surprised that the value does not change per environment. On a
> self-managed install it is that environment's gateway.

The endpoint works with or without a trailing `/v1/traces` - the signal
path is appended only when it is missing.

## Step 4 - Run it instrumented

The package is already in `requirements.txt`, so it is installed. All that
changes is how the process starts:

```bash
amp-instrument python main.py
```

[`run.sh`](crewai-agent/run.sh) wraps that for the rest of the module -
`./run.sh` re-reads `.env` and restarts, `./run.sh status` says what the agent
is pointed at, `./run.sh stop` ends it. You will change `.env` several times
from here on, and restarting is the only way those changes take.

That is the entire integration. No import, no decorator, no initialisation
call, no SDK in the code - `agent.py` has no idea any of this is happening.
Look for this line in the output:

```
Traceloop exporting traces to https://...  authenticating with custom headers
```

> **This is not the init container from module 02.** Module 02's agent got
> its instrumentation from an init container AMP injects into the pod at
> deploy time - which needs a pod, so it exists only on the platform-hosted
> path. Here there is no pod, so you install the same thing yourself:
>
> | | Platform-hosted (02) | Externally-hosted (04) |
> |---|---|---|
> | Delivery | init container injected at deploy | `pip install amp-instrumentation` |
> | Started by | the platform | `amp-instrument <your command>` |
> | Traceloop SDK version | pinned by the instrumentation version you pick | pinned by the package version you install |
>
> Two delivery mechanisms, one payload. The PyPI package and the
> init-container image share a single version number, so
> `amp-instrumentation==0.4.1` here and instrumentation version `0.4.1`
> there install the same pinned Traceloop SDK - which is why the spans come
> out the same shape whichever way the agent is run.

> **Instrumentation fails open, and that is the trap in this step.** If the
> two variables are unset you get `ERROR: Failed to initialize WSO2 AMP
> instrumentation` - and then the agent starts anyway and serves perfectly
> well, untraced. If the key is wrong you get `Failed to export span batch
> code: 401, reason: Unauthorized`, and again the agent keeps answering.
> Both go to stderr and neither is fatal. An agent that looks healthy is
> not evidence that traces are landing; read the startup output.

> **On a conference network, raise the export timeout.** The OTLP exporter
> gives a batch ten seconds and then drops it with
> `Failed to export span batch code: None, reason: ... Read timed out`. The
> agent does not notice, and the trace simply never appears.
> `OTEL_EXPORTER_OTLP_TIMEOUT=30` - standard OpenTelemetry, seconds - is in
> `.env.example` for that reason.

## Step 5 - Send traffic

```bash
./seed-traffic.sh
```

Seven requests across six sessions - **the same seven prompts module 02
sent to the platform-hosted agent.** They are identical on purpose. Two
agents, two frameworks, two places to run, one set of questions makes step
7 a comparison rather than an anecdote.

No `AGENT_KEY` this time. There is no gateway in front of this agent, so
you are calling it directly.

## Step 6 - Read the trace, and find what is not a span

Console → the agent → **OBSERVABILITY → Traces**. The same view module 02
used, for an agent the platform never built.

> If the list is empty, check the time range first - as in module 02, the
> picker opens on a short window. Spans are batched, so allow a few seconds.

Open the comparison request. A crew is not a graph, so the tree is shaped
differently from module 02's - and both crew members are visible in it:

```
crewai.workflow                                              2942ms
  The guest says: "Compare a junior suite and the pres...    1821ms
    Concierge at The Grand Meridian.agent                    1820ms
      openai.chat                                             996ms
      openai.chat                                             810ms
      execute_tool check_room_availability                       0ms
      execute_tool check_room_availability                       0ms
  Write the reply the guest receives, using only the...      1100ms
    Guest Relations Writer.agent                             1099ms
      openai.chat                                            1091ms
```

Ten spans from **three** sources, which is worth pausing on:

| Span | Emitted by | Carries |
|---|---|---|
| `crewai.workflow` | CrewAI instrumentation | the root - crew config, result, token usage |
| `<task description>` | CrewAI instrumentation | description, expected output, output |
| `<agent role>.agent` | CrewAI instrumentation | role, goal, backstory, tool list |
| `openai.chat` | **OpenAI SDK** instrumentation | messages, tokens, finish reason, tool definitions |
| `execute_tool <name>` | **this repository** | arguments, result, status - see below |

**Read the per-agent split first.** The concierge took 1.82s and the writer
1.10s of a 2.94s request: roughly two thirds of the time establishing the
facts, one third turning them into prose. Nobody instrumented that division -
it falls out of the crew having two members, and it is the first question to
ask of any multi-agent system that feels slow.

It is also how you audit whether a member is worth its place. Open the two
task spans and read `traceloop.entity.output` on each: one is a brief of
notes, the other is the guest's reply. When those two are the *same text*, the
second agent is costing you a third of every request to retype the first
one's answer - which is exactly what an earlier version of this crew was
doing, and exactly what the trace made obvious.

Tool spans at 0ms are not a bug either. These tools are dictionary lookups in
the same process, so they finish inside a millisecond. That is module 02's
point about where agent latency actually goes, shown rather than asserted:
three model calls account for 4.0 of the 4.1 seconds.

**What did it cost** is the same story module 02 told. Read the tokens across
the model calls of one request and the input grows each time - nothing about
the guest's question changed, but each tool result was appended before the
model was asked again, and then the whole draft was handed to a second agent.
A two-member crew buys you a better-written answer and pays for it in tokens,
which is a trade worth being able to see before you make it in production.


### The tool spans, and where they came from

Four of those ten spans are `execute_tool`, sitting under the concierge. They
are **not** from auto-instrumentation. Zero-code patches a fixed catalogue of
libraries, and what it patches for CrewAI is `Crew.kickoff`,
`Agent.execute_task`, `Task.execute_sync` and `LLM.call`. Tools are not on that
list, and on a stock CrewAI agent there is no tool span at all.

Before writing any, it is worth seeing what you already had. Open an
`openai.chat` span and read `gen_ai.input.messages`:

```
role=system      text
role=user        text
role=assistant   tool_call            check_room_availability {"nights":3,"room_type":"junior"}
role=tool        tool_call_response   {"total_usd": 1140, ...}
role=assistant   tool_call            check_room_availability {"nights":3,"room_type":"presidential"}
role=tool        tool_call_response   {"total_usd": 3600, ...}
```

The arguments the model chose were never missing. Module 02's third question -
**why did it say that** - was answerable from the conversation the model saw.
What was missing is a span: something carrying a tool's name, duration and
status, that the platform can filter, badge and score.

That distinction is the whole reason to write the spans by hand:

| | Without tool spans | With them |
|---|---|---|
| Arguments and results recorded | ✅ inside the LLM messages | ✅ |
| Per-tool duration | ❌ | ✅ |
| Error badge when a tool refuses | ❌ | ✅ |
| Found by `--condition tool_call_fails` | ❌ | ✅ |
| Readable without opening a message array | ❌ | ✅ |

[`instrumentation.py`](crewai-agent/instrumentation.py) is what closes it, and
it is one decorator. Agent Manager publishes the contract its own
instrumentation writes to, so a span emitted against that contract renders
identically to an auto-instrumented one:

```python
with tracer.start_as_current_span(f"execute_tool {name}") as span:
    span.set_attribute("gen_ai.operation.name", "execute_tool")   # the kind
    span.set_attribute("gen_ai.tool.name", name)                  # the header
    span.set_attribute("traceloop.entity.input", json.dumps(arguments))
    result = fn(**arguments)
    span.set_attribute("traceloop.entity.output", result)
```

Applied to each tool, inside CrewAI's own decorator so the description the
model reads is untouched:

```python
@tool("check_room_availability")
@traced_tool
def check_room_availability(...)
```

There is no exporter setup in that file and no `init_otel()` call. Under
`amp-instrument` a tracer provider is already installed, so these spans travel
out with the rest; run the agent bare and `get_tracer` returns a no-op that
drops them harmlessly. `init_otel()` is for an agent with *no* auto
instrumentation - calling it here would point a second exporter at spans that
already have one.

### The refusal that is now visible

One detail in `instrumentation.py` is worth more than the rest of it. These
tools never raise; they return `{"error": ...}`. A span that only fails when
an exception escapes would be **green** for every one of those:

```python
if isinstance(parsed, dict) and "error" in parsed:
    span.set_status(Status(StatusCode.ERROR, parsed["error"]))
    span.set_attribute("error.type", "ToolRefused")
```

Ask this agent for a room type that does not exist and the tool refuses; the
span now carries an error badge and turns up under
`--condition tool_call_fails`. That is exactly the shape of module 02's
planted fault - a tool that says no, a `200 OK`, and a polite apology - except
that here it raises its hand instead of waiting to be found.

The lesson generalises past this lab. **Check the instrumentation catalogue
against your own framework before assuming coverage**, because the failure
mode is not an empty trace. It is a trace that looks complete until you go
looking for the one span you wanted to filter on. And when you find the gap,
the contract is published: closing it is a decorator, not a project.

> **The task span is named after the task description**, which contains the
> guest's message - so guest utterances appear as span names in the trace
> list. Convenient here, worth a thought before pointing this at real
> traffic.


## Step 7 - Score it with module 03's standards

Evaluation reads stored traces. It never touched the agent in module 03,
and it does not know or care that this one runs somewhere else. So the
monitor you already know how to build works here unchanged.

1. Open this agent and click the **Evaluation** tab.
2. **Add Monitor**, **Past Traces**, window covering step 5.
3. Add the evaluators from module 03 - `Length Compliance`,
   `Latency Performance`, `Content Safety`, `Completeness`, `Tone` - with
   the same settings. Judges need their LLM credentials configured on this
   monitor.
4. **Create Monitor.**

Then open module 03's monitor on the platform-hosted agent beside this one.
Same prompts, same evaluators, same scale - one radar chart per framework.

That comparison is the point of the module. The agent nobody here built,
that nobody here deployed, that runs on a laptop, is being held to the
written house style in `agent/system_prompt.py` by the same evaluator, on
the same dashboard, as the agent the platform operates.

> **Read the skipped count before reading the scores.** Evaluators need
> particular attributes, and they report **skipped** rather than guessing
> when those are absent - the honest result, and easy to mistake for a good
> one. The count is on the **Evaluation Summary**.
>
> For this agent the two levels are not equally well served, and step 6's
> span table says why:
>
> | Level | Needs | On a CrewAI trace |
> |---|---|---|
> | LLM | `gen_ai.input.messages` / `gen_ai.output.messages` per model call | present on all three `openai.chat` spans |
> | Trace | input and output on the root span | the root is `crewai.workflow`, which carries `crewai.crew.result` but no `gen_ai.*` messages |
>
> So expect `Tone` to have plenty to work with, and check whether the
> trace-level evaluators found their input before treating their average as
> a verdict. This is the same point as step 6 in a different costume: the
> data exists, but an evaluator can only read the attributes it was written
> to read.

## Step 8 - What you give up
| | Platform-Hosted | Externally-Hosted |
|---|---|---|
| Build from source | ✅ | you own it |
| Deploy, promote, roll back, suspend | ✅ | you own it |
| **Inbound** gateway, API keys, rate limits | ✅ | you own it |
| **Outbound** LLM gateway, guardrails, token limits | ✅ | ✅ - you wire it |
| Restart when it dies | ✅ | you own it |
| Traces, spans, token accounting | ✅ | ✅ |
| Evaluation, monitors, custom evaluators | ✅ | ✅ |
| AgentID credentials per environment | injected | generated, wired by you |
| `amctl agent logs` / `metrics` | ✅ | not available |
| `amctl agent traces` / `trace` / `traces export` | ✅ | ✅ |

The two gateway rows are the ones worth reading carefully, because they point
in opposite directions.

**Inbound**, the platform cannot help. An environment's ingress gateway
fronts workloads the platform runs, and registering an external agent tells
it a name and a description - not a hostname. There is nowhere for the
platform to send traffic, so authenticating and rate-limiting callers stays
your problem. Put your own gateway in front of it, as you would for any
service you host.

**Outbound**, it can, and this is the row most people miss. Attach an
org-level **LLM Service Provider** to this agent under **Configure → Add LLM
Configuration**, and the console hands back a gateway **Endpoint URL**, a
header name (`API-Key`) and a key. Point the agent's LLM client at that URL
instead of the provider's and every model call routes through the platform:
rate limits, access control and **guardrails** apply centrally, and the real
provider credential never reaches your agent. Guardrails attach at the
provider *and* at this agent's binding to it, and the two compose.

For this agent that is configuration, not a rewrite, because it already reads
`OPENAI_BASE_URL`. The only code it needs is the custom header, since the
OpenAI SDK sends `Authorization: Bearer` and the gateway wants `API-Key`:

```python
LLM(model=LLM_MODEL, base_url=OPENAI_BASE_URL, api_key=...,
    additional_params={"extra_headers": {"API-Key": LLM_GATEWAY_KEY}})
```

`logs` and `metrics` are not available for externally-hosted agents:

```bash
amctl agent logs external-grand-meridian-c --project session-1 --env gvisor --json
```
```
VALIDATION: agent "external-grand-meridian-c" is externally provisioned
  Runtime logs and metrics are only available for internally-provisioned agents.
```

That is the right answer - there is no pod here, so there is no pod log and no
pod metric. But read the message closely: it names **logs and metrics**, and
nothing else. Traces are not runtime state read out of a workload; they are
records the agent pushed, and the CLI serves them the same for both kinds of
agent:

```bash
amctl agent traces external-grand-meridian-c --project session-1 --env gvisor --since 12h --json \
  | jq -r '.data.traces[] | "\(.traceId[0:8])  \(.spanCount) spans"'
```
```
4e47f485  9 spans
b993548a  10 spans
```

`amctl agent trace <id>` and `traces export` work too. Run the same command
against both agents side by side and the boundary explains itself: the
platform can only tell you about a process it is running, but it can tell you
about work any agent did.

## Step 9 - Govern the model calls, not just the agent

Look at what this agent has been doing for the whole module. It holds a live
`sk-...` in a file on your laptop and calls the provider directly. There is no
spend cap on it, no content policy over it, and no way to revoke it that does
not involve rotating the key for everyone else using it.

That is not a flaw in the lab. It is the ordinary state of most agents in an
organisation, and it is the part of "governance" that observability and
evaluation do not touch: both of those *watch*. Neither is in a position to
*stop* anything, because neither is in the request path - which was the point
of module 03's opening, and is a limitation as much as a feature.

Step 8 showed the platform cannot help on the way **in** to this agent. On the
way **out**, to the model, it can.

### Step 9.1 - Register a provider and attach it

1. At the organization level, register an **LLM Service Provider** for OpenAI
   with your real key. This is the only place the provider credential now
   lives.
2. Open this agent, click **Configure**, then **+ Add LLM Configuration**.
3. Select the provider. Optionally add **Guardrails** here - these apply to
   this agent's use of the provider, on top of any on the provider itself.
4. **Save.** The **Connect to LLM Provider** panel opens with three things:

   | Field | Goes into |
   |---|---|
   | **Endpoint URL** | `OPENAI_BASE_URL` |
   | **API Key** (shown once) | `LLM_GATEWAY_API_KEY` |
   | **Header Name** (`API-Key`) | the default, nothing to set |

### Step 9.2 - Point the agent at it

```bash
# in crewai-agent/.env
OPENAI_BASE_URL=<Endpoint URL from the panel>
LLM_GATEWAY_API_KEY=<API Key from the panel>
# OPENAI_API_KEY=sk-...        <- comment it out
```

```bash
./run.sh
curl -s localhost:8000/health | jq
# → "llm_via_gateway": true
```

Ask it anything. **The answers are identical and the agent's own key is gone.**
Same crew, same tools, same traces - and every model call now passes a policy
you administer centrally, with the provider credential held by the platform
rather than by this process.

That is the whole demonstration, and it is a two-line configuration change,
because `agent.py` already reads a base URL. The only code the gateway needed
was the header, since the OpenAI client sends `Authorization: Bearer` and the
gateway reads `API-Key`:

```python
extra["extra_headers"] = {LLM_GATEWAY_HEADER: LLM_GATEWAY_KEY}
```

> **One trap, and it is a quiet one.** CrewAI calls `load_dotenv()` when it is
> imported. So a stale `OPENAI_API_KEY` left in `.env` is back in the
> environment before any of your code runs, and the OpenAI client will happily
> put it in an `Authorization` header on every call *through the gateway* -
> where the only place you would ever see it is the gateway's access log.
>
> `agent.py` therefore **suppresses** the provider key in gateway mode rather
> than falling back to it, and sends a placeholder the gateway ignores. Worth
> knowing generally: "the agent no longer has the credential" is a claim about
> what the process sends, not about what you deleted from a file.

### Step 9.3 - Shrink the door before you police it

Before adding a single policy, look at what the agent can reach. The `openai`
provider template is built from OpenAI's full OpenAPI spec:

```
paths 63    operations 95
/organization 14   /threads 11   /vector_stores 8   /fine_tuning 5
/uploads 4   /images 3   /audio 3   /files 3   /batches 3   ...   /chat 1
```

A provider registered with `allow_all` exposes every one of those to any agent
holding its key - including fourteen account-administration operations. The
concierge needs exactly one.

On the provider's **Access Control**, set **deny_all** and add one exception:
`POST /chat/completions`. That is 95 operations down to 1, and it is a
provider setting rather than a policy, so it costs nothing at runtime.

> **Check it by timing, not by reading the error.** A denied call and an
> allowed one come back with different-looking bodies but the same shape of
> failure once a guardrail is also in play. A locally denied request returns
> in about the same time as one with a deliberately wrong API key (~0.65s from
> a laptop here); a call that really reached OpenAI takes roughly twice that.
> If a "blocked" endpoint is as slow as a real completion, it is not blocked.

### Step 9.4 - Two levels, two kinds of rule

Attach these in the console. The level is the point: one is a floor for the
whole organization, the other is this agent's own rule.

**Provider level - PII masking.** `OpenAI for Agents` -> **Guardrails**,
scoped to `POST /chat/completions`:

| Field | Value |
|---|---|
| email | `true` |
| customPIIEntities | `CREDIT_CARD` / `\b(?:\d[ -]*?){13,16}\b` |
| jsonPath | `$.messages[-1].content` |
| redactPII | `true` |

> **Type the raw regex.** The form escapes what you paste, so pasting a
> JSON-escaped pattern (`\\b`) stores a literal backslash and the rule matches
> nothing. There is no built-in card detector - `email`, `phone` and `ssn` are
> the only built-ins, so a card needs a custom entity.

**Agent level - block promises the hotel cannot make.** The agent's LLM
configuration -> **Add Guardrail** -> **Regex Guardrail**, **Response** phase:

| Field | Value |
|---|---|
| regex | `(?i)(guarantee\|refund\|free upgrade)` |
| jsonPath | `$.choices[0].message.content` |
| invert | `true` |
| showAssessment | `true` |

Those are the same three strings module 03's **Content Safety** evaluator
scores. Same concern, two instruments: one scores it afterwards, one refuses
it in the path.

> **`invert` is backwards from what most people expect.** The default,
> `false`, means *pass when the regex matches* - an allow-list. To block a
> phrase you need `invert: true`. Get it wrong and you block everything the
> pattern does **not** match, which on a first test looks like the guardrail
> working.

> **Guardrails fail closed, so a misconfigured one is an outage.** Putting
> that response rule on the **request** phase leaves its JSONPath pointing at
> `$.choices[...]`, which does not exist in a request. Extraction errors, the
> policy refuses, and every call fails:
>
> ```
> "actionReason":"Error extracting value from JSONPath","direction":"REQUEST"
> ```
>
> The agent reports only that it cannot reach its systems. Scope the rule to
> `/chat/completions` too, so it never sees a response it cannot parse.

### Step 9.5 - Watch them work

The response guardrail is visible from the chat. Ask for something the hotel
cannot promise:

```bash
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"I am unhappy with my stay. Promise me a refund in writing.",
       "session_id":"gr-1","context":{}}' | jq
```

```json
{
  "response": "I am not able to put that in writing. Let me connect you with our duty manager, who can help.",
  "policy": {
    "guardrail": "regex-guardrail",
    "direction": "RESPONSE",
    "assessment": "Violated regular expression: (?i)(guarantee|refund|free upgrade)"
  }
}
```

That `policy` field exists because `agent.py` looks for it. A blocked call
does **not** arrive as a clean HTTP error: the gateway answers with the
guardrail payload instead of a completion, and the OpenAI client raises
`APIResponseValidationError` reporting **status 200**. Keying off a 422 finds
nothing; `_guardrail_refusal()` reads the body instead. Without that, a policy
refusal is indistinguishable from the network being down, and the guest is
told the hotel's systems are broken when they are working exactly as
configured.

**PII masking cannot be shown from the chat**, and the reason is worth saying
out loud rather than working around. The gateway rewrites the request on its
way *to* the model; the agent sent the original and never sees the
substitution. Nothing comes back for it to report. Ask the model directly
instead:

```bash
curl -s -X POST "$OPENAI_BASE_URL/chat/completions" -H "API-Key: $LLM_GATEWAY_API_KEY" \
  -H 'Content-Type: application/json' -d '{"model":"...","messages":[{"role":"user",
  "content":"Booking ref 4111 1111 1111 1111. Quote the exact characters between ref and the end."}]}' \
  | jq -r '.choices[0].message.content'
```

```
*****
```

The card never reached OpenAI. That is the whole claim, and it is one line of
output.

> **Give the gateway a moment after any policy change.** The proxy
> redeploys, and the first call after an edit returns `504 upstream request
> timeout` for ten to twenty seconds. It is not a failure; it is why a live
> before-and-after needs a sentence of narration rather than silence.

### Step 9.6 - Change behaviour without touching the agent

Blocking is the obvious use of a gateway and the least interesting. The
**Prompt Decorator** injects instructions into every request before the model
sees them - so you can change what an agent *does*, not just what it is
allowed to return.

Add it at agent level with:

```json
{ "promptDecoratorConfig": { "messages": [
    { "role": "system",
      "content": "Never promise a refund, upgrade or guarantee. Never quote a price that did not come from a tool result. If asked about payment details, state that the hotel does not store card numbers." } ] },
  "append": false }
```

`append: false` prepends. `messages` mode targets `$.messages` by default;
`text` mode decorates a single string at `$.messages[-1].content` instead.

Then ask the agent *"Do you store my card details anywhere?"* and compare the
answer with and without the decorator attached.

Nothing was rebuilt, redeployed or restarted, and nobody opened the agent's
repository - which for an agent another team owns is the difference between a
policy you can state and a policy you can apply. It also pairs with the
guardrail above: the decorator is **prevention**, the regex is
**enforcement**, and you want both, because a model told not to say something
still sometimes says it.

### Step 9.7 - A page to demo it from

[`web/index.html`](web/index.html) is a small light-mode page in the hotel's
own palette: the concierge chat on the left, and on the right a rail showing
what the gateway did to each request - allowed, or blocked with the policy
that intervened and its assessment.

```bash
cd web && python3 -m http.server 8090
# then open http://localhost:8090
```

The scenario chips send the four requests worth showing. There is a
**Compare** toggle that puts a second endpoint beside the first, if you have
built one, though the more direct demonstration is to leave one chat open,
detach the guardrail in the console, and ask the same question again. Same
agent, same process, no restart - and that, rather than two panes disagreeing,
is what this module has been about.

### What the gateway can apply

The policy catalogue is reported by the gateway, not fixed by Agent Manager,
so this is the current shape of it rather than a permanent list - **expect it
to grow**, and check your own instance with the Console's policy picker.

| Category | Policies | Notes |
|---|---|---|
| **Block / allow** | `regex`, `url`, `json-schema`, `content-length`, `word-count`, `sentence-count` | fail **closed** |
| **Transform in flight** | `pii-masking-regex`, `prompt-decorator`, `prompt-template`, `prompt-compressor` | change the payload, do not block |
| **ML-backed safety** | AWS Bedrock, Azure Content Safety, Granite Guardian prompt-injection, NeMo Guard, semantic prompt guard, semantic tool filtering | each needs its capability enabled on the install |
| **Rate and cost** | `basic-` / `advanced-` / `token-based-` / `llm-cost-based-ratelimit`, `llm-cost` | provider settings, not agent-level |
| **Model routing** | intelligent, semantic, cost-based, time-based, round-robin, weighted, header router | choose a model at the gateway |
| **Provider translation** | OpenAI to Anthropic / Azure / Bedrock / Gemini / Mistral | the agent speaks OpenAI; the gateway translates |
| **Performance** | `semantic-cache` | serves a similar earlier answer without calling upstream |
| **Auth and transport** | api-key, JWT, basic, opaque token, OAuth2 generator, AWS SigV4, CORS | inbound and upstream auth |

Two rows deserve a second look even if you do not demo them. **Provider
translation** means moving an agent from OpenAI to Bedrock is gateway
configuration rather than an agent change. And **rate and cost** only exists
at provider level for the moment, so you cannot give one agent a tighter token budget through
a guardrail - that needs a second provider.


## Step 10 - The platform, from an agent's side of the desk

One more thing, and it is about the platform rather than about the agent.
Everything in this lab has been a person driving a console or a CLI. The
same lifecycle is meant to be drivable by an AI assistant, and Agent
Manager ships the instructions for that:

```bash
amctl skills list
# → manage-agent (not installed)  Use when an agent needs to drive the full
#   agent-manager lifecycle through `amctl` ...

amctl skills install
```

This works with **no instance and no login** - the bundle is fetched from
[`wso2/agent-skills`](https://github.com/wso2/agent-skills), extracted to
`~/.agents/skills/`, and linked into whichever assistants are installed
locally (Claude Code, Cursor, Windsurf). Nothing about it depends on
whether you are on the hosted version or your own install.

What arrives is written guidance, not a plugin: the verb map, the rules
that stop calls failing silently, a `troubleshooting.md` of the CLI's sharp
edges and a `triage.md` that walks build → logs → metrics → traces in
order. Module 01 installed it; module 02 used it. It is worth naming what
that means - the platform treats a coding assistant as a first-class
operator of itself, which is the same claim this module has been making
about agents, pointed inward.

## Hosted or self-managed

This lab is written to work on both, and module 04 is where the two paths
differ most:

| | Hosted (`console.agent-manager.cloud.wso2.com`) | Self-managed |
|---|---|---|
| Register an external agent | console | console or `amctl agent create --provisioning external` |
| Generate the agent API key | console | console or CLI |
| Traces and evaluation | ✅ | ✅ |
| `amctl skills install` | ✅ (no login needed) | ✅ |
| `amctl login` | **not yet** | ✅ |

Hosted CLI support is on the way; until it lands, treat
every hosted step as a console step.

## Where the lab leaves you

| Module | What it added | Needed the platform to run the agent? |
|---|---|---|
| 00 | A working agent | - |
| 01 | Somewhere to run it | yes |
| 02 | A record of what happened inside a request | no - traces are pushed by the agent |
| 03 | A score for whether it was any good | no - it reads traces |
| 04 | The same two, plus a governed path to the model, for an agent run elsewhere | **no** |

The through-line is in the last column. Build and deploy are a service the
platform offers. Observability, evaluation and control of the model call are
the governance it applies - and those follow the agent, not the hosting.

Which leaves three instruments doing three different jobs, and it is worth
being able to say which is which:

| | Answers | When | Can it stop anything? |
|---|---|---|---|
| **Traces** | what the agent did | after | no |
| **Evaluation** | whether it was any good | after | no |
| **Guardrails** | what the model may be asked and may reply | during | yes |

An agent the platform never built, never deployed and does not run gets all
three.

## Going further

- [Internal and External Agents](https://wso2.github.io/agent-manager/docs/) - what the type fixes at registration, and why it cannot be changed afterwards
- [AMP Instrumentation](https://wso2.github.io/agent-manager/docs/) - the `amp-instrument` wrapper, the framework catalogue with its tested versions and known limitations, and the **manual instrumentation contract**: the OTLP endpoint, the `x-amp-api-key` header, and the `gen_ai.*` attribute table a hand-written tool span needs. This is the contract `instrumentation.py` is written against.
- [Retrieve AgentID Credentials for an Externally-Hosted Agent](https://wso2.github.io/agent-manager/docs/) - per-environment `client_id`/`client_secret` for an agent the platform cannot inject into. Provisioning starts at registration rather than at deploy, since there is no deploy.
- [Sample agents](https://github.com/wso2/agent-manager/tree/main/samples) - seven runnable agents across LangGraph, CrewAI, LangChain, Strands, .NET and plain Python. `manual-instrumentation-agent` is the executable reference for the contract above; `dotnet-agent` is the external path in a language the platform does not auto-instrument at all.

---

Previous: [Module 03 - Evaluation](../03-evaluation/README.md)
