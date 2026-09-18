# Running Agents Like Production Software

**WSO2Con 2026 Africa - Agent Manager lab, session 1**

Your agent runs locally and it works. This lab is about everything that
happens after that: getting it built, deployed, instrumented, and
measured - using [WSO2 Agent Manager](https://wso2.com/agent-platform/agent-manager/).

## Tutorial plan

```
00 - Starting Point  A working agent, running locally.
01 - Build & Deploy  From a Git repository to a running service.
02 - Observability   Seeing inside a single request.
03 - Evaluation      Measuring something that answers differently every time.
04 - External Agents Agents the platform doesn't run, governed all the same.
```

Each module has its own `README.md` with the steps. They are written to be
followed in order - later modules assume the agent registered in 01.

## The use case

A concierge agent for *The Grand Meridian*, a fictional luxury hotel.
LangGraph + FastAPI + OpenAI, roughly 300 lines. One endpoint:

```
POST /chat   { "message": str, "session_id": str, "context": {} }
         →   { "response": str }
```

Three tools, backed by static hotel data:

- `check_room_availability(room_type, check_in, nights)`
- `get_room_service_menu(vegetarian_only)`
- `get_local_recommendations(category)`

The agent lives in [`agent/`](agent/) and is **shared by every module** -
one copy, never edited as you go. That is the point of the lab: the
architecture around the agent changes at every step while the agent
itself stays exactly as it was written.

## Prerequisites

- **Python 3.11 or 3.12.** Avoid 3.13 / 3.14 - the LangGraph pins used
  here do not support them yet. macOS: `brew install python@3.11`.
- **An OpenAI API key** (`sk-...`).
- **An Agent Manager instance** you can register an agent in. Module 00
  runs without one; modules 01–04 need it. There are two ways to get one:

  - **Run it yourself.** The
    [quick start](https://wso2.github.io/agent-manager/docs/latest/get-started/quick-start/)
    brings up a complete install in a dev container and puts the console
    on `http://console.amp.localhost:8080` (`admin` / `admin`). This lab
    is written and verified against a self-managed install, and it is the
    setup to choose if you want the CLI and MCP steps as well as the
    console ones.
  - **Use the hosted version** at
    [console.agent-manager.cloud.wso2.com](https://console.agent-manager.cloud.wso2.com)
    - nothing to install. Every module's main path is a console path, so
    this carries the whole lab. `amctl` and the MCP servers connect to a
    self-managed instance today; hosted support for them is on the way,
    and the steps here will work unchanged when it lands.

- **`amctl`**, the Agent Manager CLI, if you are following the terminal
  steps. Install it and log in before module 01:

  ```bash
  curl -fsSL https://wso2.github.io/agent-manager/install.sh | sh
  amctl version

  amctl login --url http://api.amp.localhost:8080
  ```

  The URL is your instance's **API** base, not the console's. `login`
  opens a browser to sign in; `amctl project list` afterwards confirms it
  took.

## Quick start

```bash
git clone https://github.com/wso2con/2026-NBO-AI-tutorial-3.git
cd 2026-NBO-AI-tutorial-3/agent

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env - paste your OPENAI_API_KEY
set -a; source .env; set +a

python main.py
# → listening on http://localhost:8000
```

Then open [`00-starting-point/README.md`](00-starting-point/README.md).

## A note on versions

This lab targets Agent Manager **1.0.0**, generally available since
September 2026.

Command flags and console screens do move between releases. Where this
repo and your installation disagree, believe your installation -
`amctl <command> --help` is always the authority on flag shape.

## Licence

Apache 2.0.
