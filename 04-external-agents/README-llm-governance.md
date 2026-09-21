# Module 04b - LLM Governance: controlling the model call

**Duration:** 12 min

> Continues from [Module 04](README.md). That module ends with an agent the
> platform observes and scores but does not run. This one puts the platform
> in the path of its model calls.

Look at what the agent has been doing for the whole of module 04. It holds a
live `sk-...` in a file on your laptop and calls the provider directly. There
is no spend cap on it, no content policy over it, and no way to revoke it that
does not involve rotating the key for everyone else using it.

That is not a flaw in the lab. It is the ordinary state of most agents in an
organisation, and it is the part of "governance" that observability and
evaluation do not touch: both of those *watch*. Neither is in a position to
*stop* anything, because neither is in the request path - which was the point
of module 03's opening, and is a limitation as much as a feature.

Module 04's step 8 showed the platform cannot help on the way **in** to this
agent. On the way **out**, to the model, it can.

## Step 1 - Register a provider and attach it

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

## Step 2 - Point the agent at it

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

## Step 3 - Shrink the door before you police it

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

## Step 4 - Two levels, two kinds of rule

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

**Agent level - block the words the hotel cannot say.** The agent's LLM
configuration -> **Add Guardrail** -> **Regex Guardrail**, **Request** phase:

| Field | Value |
|---|---|
| regex | `(?i)(guarantee\|refund\|free upgrade)` |
| jsonPath | `$.messages[-1].content` |
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

> **Guardrails fail closed, so a misconfigured one is an outage.** Point a
> rule at a JSONPath the payload does not have and extraction errors, the
> policy refuses, and every call fails:
>
> ```
> "actionReason":"Error extracting value from JSONPath","direction":"REQUEST"
> ```
>
> The agent reports only that it cannot reach its systems, because from where
> it sits that is all it knows. Check a rule against real traffic - including
> a question that uses a tool - before you rely on it.

This rule sits on the **request** phase, so it reads the guest's message.
`$.messages[-1].content` is the last thing the guest said.

## Step 5 - Watch them work

The regex guardrail is visible from the chat. Ask for something the hotel
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
    "direction": "REQUEST",
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

**PII masking usually will not show up in the chat**, and the reason is about
this agent rather than about the gateway. The substitution happens on the
request, on its way to the model, so the model is the only party that sees
asterisks. Whether *you* see them depends on whether the model repeats the
masked text back - and this concierge is told to lead with the answer and not
restate the guest's input, so it does not. Ask it to confirm a card back and
it declines outright:

> *"I'm unable to confirm or repeat masked payment details."*

Note the word **masked**: the model is describing what it received. The
mechanism worked; the reply just never carries it.

So prove it against the model directly, where no persona is in the way.
[`gateway-test.sh`](crewai-agent/gateway-test.sh) does this and two other
checks; `./gateway-test.sh pii` runs just this one. The trick is to give the
model a formatting job rather than a question about personal data - asked the
second way it gets protective and substitutes its own placeholder, which
proves nothing:

```bash
curl -s -X POST "$OPENAI_BASE_URL/chat/completions" \
  -H "API-Key: $LLM_GATEWAY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"'"$OPENAI_MODEL"'","messages":[{"role":"user","content":
  "Reformat this reservation record as a markdown bullet list. Copy every value exactly as written; do not alter, summarise or omit anything.\nguest=A. Osei; contact=guest@example.com; card=4111 1111 1111 1111; room=Junior Suite; rate=380; nights=3; total=1140; arrival=2026-06-05"}]}' \
  | jq -r '.choices[0].message.content'
```

```
- guest=A. Osei
- *****
- card=*****
- room=Junior Suite
- rate=380
- nights=3
- total=1140
- arrival=2026-06-05
```

That is the whole claim in one block. The card and the email never reached
OpenAI - and the six fields beside them arrived untouched, which is the part
worth pointing at. This is not the model refusing to repeat something
sensitive; it is the model faithfully copying what it was given, having been
given asterisks.

> **If you do want it in the chat**, the decorator from step 6 is the lever:
> tell the agent to confirm the guest's details back and the masked values
> travel out with the reply. Worth knowing that it is the agent's instructions
> deciding this, not the policy.

> **Give the gateway a moment after any policy change.** The proxy
> redeploys, and the first call after an edit returns `504 upstream request
> timeout` for ten to twenty seconds. It is not a failure; it is why a live
> before-and-after needs a sentence of narration rather than silence.

## Step 6 - Change behaviour without touching the agent

Blocking is the obvious use of a gateway and the least interesting. The
**Prompt Decorator** injects instructions into every request before the model
sees them - so you can change what an agent *does*, not just what it is
allowed to return.

Add it at agent level with:

```json
{ "promptDecoratorConfig": { "messages": [
    { "role": "system",
      "content": "Never promise a refund, upgrade or guarantee. Never quote a price that did not come from a tool result." } ] },
  "append": false }
```

> Provide **exactly one** of `messages` or `text` - the schema is a `oneOf`.
> Setting both saves without complaint and the gateway then answers every
> request with `500`.

`append: false` prepends. `messages` mode targets `$.messages` by default;
`text` mode decorates a single string at `$.messages[-1].content` instead.

Then ask the agent for its *"very best nightly rate"* on a suite and compare
the answer with and without the decorator attached.

Nothing was rebuilt, redeployed or restarted, and nobody opened the agent's
repository - which for an agent another team owns is the difference between a
policy you can state and a policy you can apply. It also pairs with the
guardrail above: the decorator is **prevention**, the regex is
**enforcement**, and you want both, because a model told not to say something
still sometimes says it.

## Step 7 - A page to demo it from

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

## What the gateway can apply

The policy catalogue is reported by the gateway, not fixed by Agent Manager,
so this is the current shape of it rather than a permanent list - **expect it
to grow**, and check your own instance with the Console's policy picker.

<details>
<summary><b>The current catalogue</b> (click to expand)</summary>

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

</details>

Two rows deserve a second look even if you do not demo them. **Provider
translation** means moving an agent from OpenAI to Bedrock is gateway
configuration rather than an agent change. And **rate and cost** only exists
at provider level for the moment, so you cannot give one agent a tighter token budget through
a guardrail - that needs a second provider.

---

Previous: [Module 04 - External Agents](README.md)
