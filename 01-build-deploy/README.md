# Module 01 - Build & Deploy: source in, service out

**Duration:** 15 min

Register the agent as a **Platform-Hosted Agent**, built straight from
this Git repository. Agent Manager clones the repo, builds an image with
a buildpack, deploys it, and puts a gateway in front of it.

The agent code does not change. Nothing is added to it - no Dockerfile,
no manifest, no SDK.

> The terminal steps below use `amctl` - install it and log in first, as
> described in the [repo README](../README.md#prerequisites). On the
> hosted version, follow the console route in each step; `amctl` and the
> MCP servers talk to a self-managed install today.

## Step 1 - Register it in the console

1. Open a project and click **Add Agent**. Every command in this lab
   passes `--project default`, so the **Default Project** that ships with
   a new instance is the one to use - if you register the agent somewhere
   else, pass that project's identifier instead.
2. Pick **Platform-Hosted Agent**, then **Source Code**.
3. Under **Agent Details**:

   | Field | Value |
   |---|---|
   | Name | `Grand Meridian Concierge` |
   | Description (optional) | `Hotel concierge agent for the Agent Manager lab` |

   The **identifier** is derived from the name as you type, and validated
   while you watch - this name becomes `grand-meridian-concierge`. That
   identifier, not the display name, is what every later step and every
   `amctl` command addresses. Keep the name above, or substitute your own
   identifier everywhere the rest of this lab says
   `grand-meridian-concierge`.

4. For **Agent Type**, take **Chat Agent** - *"standard chat interface with
   `/chat` endpoint on port 8000"*, which is exactly what `agent/main.py`
   serves. (**Custom API Agent**, the other option, is for an agent with
   its own OpenAPI spec and port.)
5. Under **Repository Details**:

   | Field | Value |
   |---|---|
   | GitHub Repository | `https://github.com/wso2con/2026-NBO-AI-tutorial-3` |
   | Branch | `main` |
   | Project Path | `/agent` |

6. Under **Build Details**, pick **Python**, then:

   | Field | Value |
   |---|---|
   | Language Version | `3.11` |
   | Start Command | `python main.py` |

   The choice here is **Python · Ballerina · Docker**. Picking a language
   *is* picking the buildpack - only **Docker** asks you for a Dockerfile,
   and there isn't one in this repository. That is the whole point of the
   module.

7. Environment variables:

   | Key | Value | Secret |
   |---|---|---|
   | `OPENAI_API_KEY` | your key | ✅ |
   | `OPENAI_MODEL` | `gpt-4o` | |
   | `PORT` | `8000` | |

   **`PORT` is not optional.** It is the single most common reason a
   lab agent builds fine and never comes up.

8. Click **Create**. The build starts automatically.

## Step 2 - Watch the build

The first build takes **five to ten minutes** - the buildpack resolves
and compiles every dependency in `requirements.txt`, and LangGraph pulls
a lot of them. Subsequent deploys of the same image take seconds.

Watch it from the console's **Build** tab, or from the terminal:

```bash
amctl agent build list grand-meridian-concierge --project default --json \
  | jq -r '.data.builds[0] | "\(.buildName)  \(.status)  \(.percent // 0)%"'
# → grand-meridian-concierge-1789202170069  Running  50%
# → grand-meridian-concierge-1789202170069  Completed  0%
```

(`percent` comes back `null` once a build finishes, hence the `// 0` -
read `status`, not the number, to know when it is done.)

Builds are addressed by `buildName` - the long
`grand-meridian-concierge-1789202170069` form - not by the `buildId`
UUID sitting next to it. The UUID is accepted by nothing.

## Step 3 - Confirm it is actually running

When the build reports `Completed`, the agent is not necessarily up.
Those are two different claims, and only one of them has been made.

```bash
amctl agent status grand-meridian-concierge --project default --json \
  | jq '.data.environments[] | {name, status, url: .endpoints[0].url}'
```

Wait for `"status": "active"`. Note the endpoint URL - you need it next.
The console shows the same thing on the agent's overview: each
environment with its own status and endpoint.

## Step 4 - Call it

Deployed agents sit behind the gateway with API-key authentication on by
default. Without a key:

```bash
curl -s -X POST "$AGENT_URL/chat" -H 'Content-Type: application/json' \
  -d '{"message":"What are the pool hours?","session_id":"lab-1","context":{}}'
# → {"error":"Unauthorized","message":"Valid API key required"}
```

Create a key - in the console under the agent's environment settings, or:

```bash
amctl api --project default \
  '/orgs/{org}/projects/{project}/agents/grand-meridian-concierge/environments/default/api-keys' \
  -f name=lab-key
# → {"status":"success", "keyId":"lab-key", "apiKey":"75f738d2...", "gatewayConnected":true}
```

Then the same call, with the key:

```bash
curl -s -X POST "$AGENT_URL/chat" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_KEY" \
  -d '{"message":"What are the pool hours?","session_id":"lab-1","context":{}}'
# → {"response":"The pool is open 7am-10pm daily. ..."}
```

The same agent you ran locally in module 00, now behind a gateway
that will not talk to a stranger.

### The same call, without the plumbing

You do not have to leave the console to do that. **Try It** is in the
agent's left nav: open it, type into **Type your message...**, press
**Send**.

It handles everything the curl above spells out - it mints and holds its
own test API key, sets the header, and knows the endpoint, so there is no
key to create and nothing to paste. Two things to know before you read
anything into an answer: it talks to the **environment selected at the top
of the page**, and it needs the agent to be deployed (it says so plainly
if it is not). Responses stream, and **Stop** interrupts one mid-flight.

Use whichever suits the moment. The console wins for *is it alive, and does
it sound like a concierge* - it is two clicks and no shell. The curl is
what you keep: it goes into a script, a CI job, or a bug report, which is
why the rest of this lab uses it. [Module 02](../02-observability/README.md)
sends this same request a hundred times, and nobody wants to click that.

Either way the call goes through the same gateway to the same endpoint, so
either way it turns up in the traces you will read in module 02.

## Step 5 - The same thing, in one command

The console is for the first time. This is for every time after:

```bash
amctl agent create grand-meridian-concierge \
  --project default \
  --display-name "Grand Meridian Concierge" \
  --description "Hotel concierge agent for the Agent Manager lab" \
  --subtype chat-api \
  --build-type buildpack \
  --language python --language-version 3.11 \
  --run-command "python main.py" \
  --repo-url https://github.com/wso2con/2026-NBO-AI-tutorial-3 \
  --repo-branch main --repo-path /agent \
  --env OPENAI_MODEL=gpt-4o \
  --env PORT=8000 \
  --env-secret OPENAI_API_KEY=sk-... \
  --json
```

One call creates the agent, starts the build, and deploys it when the
build completes.

> **Secrets:** `--env-secret` stores the value as a secret at create
> time. `amctl agent deploy --env` does **not** - values passed there are
> stored as plain text. Set real secrets at create time or in the
> console.

There is also a declarative form, which is what you would actually commit:

```bash
amctl agent create --template > agent.yaml   # then edit
amctl agent create -f agent.yaml
```

## Step 6 - Hand the CLI to your assistant

Agent Manager publishes skills that teach an AI coding assistant how to
drive `amctl` properly:

```bash
amctl skills list
# → manage-agent (not installed)  Use when an agent needs to drive the full
#   agent-manager lifecycle through `amctl` ...

amctl skills install
```

It installs to `~/.agents/skills/` and links itself into the assistants
it finds. Claude Code picks it up in the same session - no restart.

What you just installed is not a wrapper or a plugin. It is written
guidance: the verb map, the rules that stop calls failing silently, a
`troubleshooting.md` of the CLI's sharp edges, and a `triage.md` for
exactly the "build completed but is it running?" question from step 3.

Now ask, in plain English:

> *"Is the Grand Meridian concierge actually serving traffic?"*

and the assistant runs the build → logs → metrics → traces sequence
rather than guessing.

## Going further

- [`amctl` reference](https://wso2.github.io/agent-manager/docs/) - and `amctl <command> --help`, which is always more current than any document
- [Cloud Native Buildpacks](https://buildpacks.io/)

---

Previous: [Module 00 - Starting Point](../00-starting-point/README.md) ·
Next: [Module 02 - Observability](../02-observability/README.md)
