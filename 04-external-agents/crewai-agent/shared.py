"""Bridge to the hotel data and house style the platform-hosted agent uses.

Module 04's whole claim is that this is the *same* concierge running
somewhere else. Copying the room rates and the system prompt into this
folder would quietly make that untrue the first time either one changed,
so they are imported from ``agent/`` instead - two directories up, the
same files module 00 ran on a laptop and module 01 deployed.

The path is resolved from this file rather than the working directory, so
it does not matter where you start the process from.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLATFORM_AGENT = Path(__file__).resolve().parents[2] / "agent"

if not _PLATFORM_AGENT.is_dir():  # pragma: no cover - checked out on its own
    raise RuntimeError(
        f"Expected the platform-hosted agent's source at {_PLATFORM_AGENT}. "
        "Run this from a full checkout of the lab repository."
    )

# Appended, not inserted. Both agents have a module called ``tools``, and
# putting the platform-hosted agent's directory first would shadow this
# folder's CrewAI tools with its LangGraph ones.
sys.path.append(str(_PLATFORM_AGENT))

from hotel_data import (  # noqa: E402
    HOTEL_NAME,
    MENU,
    RECOMMENDATIONS,
    ROOMS,
)
from system_prompt import SYSTEM_PROMPT  # noqa: E402

__all__ = ["HOTEL_NAME", "MENU", "RECOMMENDATIONS", "ROOMS", "SYSTEM_PROMPT"]
