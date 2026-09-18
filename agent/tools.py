"""Hotel concierge tools.

Each tool validates input defensively and returns either a result dict or
{"error": "<reason>"}. Tools never raise into the agent loop.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.tools import tool

from hotel_data import MENU, RECOMMENDATIONS, ROOMS

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_room_availability(
    room_type: str,
    check_in: str | None = None,
    nights: int | None = None,
) -> dict[str, Any]:
    """Check availability and price for hotel rooms.

    Args:
        room_type: One of: honeymoon, deluxe, standard, junior, presidential.
        check_in: Check-in date (YYYY-MM-DD). Optional.
        nights: Number of nights. Optional, defaults to 1.
    """
    if not isinstance(room_type, str) or room_type not in ROOMS:
        return {"error": f"Unknown room type. Available: {', '.join(ROOMS.keys())}."}
    if check_in is not None and not _ISO_DATE.match(check_in):
        return {"error": "Check-in date must be in YYYY-MM-DD format."}
    n = 1 if nights is None else nights
    if not isinstance(n, int) or n < 1 or n > 30:
        return {"error": "Nights must be an integer between 1 and 30."}

    room = ROOMS[room_type]
    return {
        "room_type": room_type,
        "name": room["name"],
        "price_per_night_usd": room["price_per_night_usd"],
        "nights": n,
        "total_usd": room["price_per_night_usd"] * n,
        "size_sqft": room["size_sqft"],
        "description": room["description"],
        "available": True,
        "check_in": check_in,
    }


def get_room_service_menu(vegetarian_only: bool | None = None) -> dict[str, Any]:
    """Return the room service menu.

    Args:
        vegetarian_only: Filter to vegetarian items only. Optional.
    """
    veg = bool(vegetarian_only)
    items = [m for m in MENU if (not veg) or m["vegetarian"]]
    return {
        "items": items,
        "filtered": "vegetarian_only" if veg else "none",
        "count": len(items),
    }


def get_local_recommendations(category: str) -> dict[str, Any]:
    """Return curated recommendations near the hotel by category.

    The description the model actually reads is built below, from
    RECOMMENDATION_CATEGORY_DOC. The text of the error this returns is
    controlled by TOOL_ERRORS - see the notes on both.
    """
    if not isinstance(category, str) or category not in RECOMMENDATIONS:
        return {"error": _category_error()}
    return {
        "category": category,
        "recommendations": RECOMMENDATIONS[category],
        "count": len(RECOMMENDATIONS[category]),
    }


# A tool's description is the only thing telling the model what the tool will
# accept, so how you maintain it matters. TOOL_DOCS picks between the two ways
# this one can be maintained, and it is read at startup - so switching is a
# configuration change, with no rebuild:
#
#   handwritten (the default)
#       The category list is typed out by hand, below. It has drifted from the
#       keys in hotel_data.RECOMMENDATIONS, and the agent misbehaves in a way
#       that only a trace explains. That drift is deliberate: it is the fault
#       module 02 diagnoses. See 02-observability/README.md, step 6.
#
#   generated
#       The same list is derived from the data it describes, so it cannot drift.
#
# If you are reusing this file, run with TOOL_DOCS=generated.
_HANDWRITTEN_CATEGORIES = "dining, family, nightlife, outdoors"


def _category_list() -> str:
    if os.environ.get("TOOL_DOCS", "handwritten").strip().lower() == "generated":
        return ", ".join(RECOMMENDATIONS)
    return _HANDWRITTEN_CATEGORIES


# What a tool says when it refuses is part of the same interface. TOOL_ERRORS
# picks how much this one says, and it decides whether the agent can recover
# from a bad argument on its own:
#
#   terse (the default)
#       "Unknown category." The model is told no and given nothing to work
#       with, so a wrong argument becomes a failed answer.
#
#   helpful
#       The refusal names the categories that do exist, which is usually
#       enough for the model to correct itself and retry - at the cost of an
#       extra round trip it should not have needed.
#
# Compare check_room_availability above, which always names its valid values.
def _category_error() -> str:
    if os.environ.get("TOOL_ERRORS", "terse").strip().lower() == "helpful":
        return f"Unknown category. Available: {', '.join(RECOMMENDATIONS)}."
    return "Unknown category."


RECOMMENDATION_CATEGORY_DOC = f"""Return curated recommendations near the hotel by category.

    Args:
        category: One of: {_category_list()}.
    """

# Wrap with tool() rather than @tool decorator so the underlying functions
# remain directly callable from tests.
LANGCHAIN_TOOLS = [
    tool(check_room_availability),
    tool(get_room_service_menu),
    tool(get_local_recommendations, description=RECOMMENDATION_CATEGORY_DOC),
]
