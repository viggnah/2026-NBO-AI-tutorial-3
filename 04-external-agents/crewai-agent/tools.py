"""Hotel concierge tools, bound to CrewAI.

The hotel data is not copied. It is imported from ``agent/hotel_data.py``
- the same module the platform-hosted agent reads - so the two agents are
answering from one source of truth and any difference between them is the
framework, not the data.

Each tool validates input defensively and returns JSON. Tools never raise
into the agent loop.

Each is also wrapped in `traced_tool`, which emits the `execute_tool` span
CrewAI's auto-instrumentation does not - see `instrumentation.py`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from crewai.tools import tool

from instrumentation import traced_tool
from shared import MENU, RECOMMENDATIONS, ROOMS

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


@tool("check_room_availability")
@traced_tool
def check_room_availability(
    room_type: str,
    check_in: str | None = None,
    nights: int | None = None,
) -> str:
    """Check availability and price for hotel rooms.

    Args:
        room_type: One of: honeymoon, deluxe, standard, junior, presidential.
        check_in: Check-in date (YYYY-MM-DD). Optional.
        nights: Number of nights. Optional, defaults to 1.
    """
    if not isinstance(room_type, str) or room_type not in ROOMS:
        return _json({"error": f"Unknown room type. Available: {', '.join(ROOMS)}."})
    if check_in is not None and not _ISO_DATE.match(check_in):
        return _json({"error": "Check-in date must be in YYYY-MM-DD format."})
    n = 1 if nights is None else nights
    if not isinstance(n, int) or n < 1 or n > 30:
        return _json({"error": "Nights must be an integer between 1 and 30."})

    room = ROOMS[room_type]
    return _json(
        {
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
    )


@tool("get_room_service_menu")
@traced_tool
def get_room_service_menu(vegetarian_only: bool | None = None) -> str:
    """Return the room service menu.

    Args:
        vegetarian_only: Filter to vegetarian items only. Optional.
    """
    veg = bool(vegetarian_only)
    items = [m for m in MENU if (not veg) or m["vegetarian"]]
    return _json(
        {
            "items": items,
            "filtered": "vegetarian_only" if veg else "none",
            "count": len(items),
        }
    )


# The category list is derived from the data it describes rather than typed
# out by hand, so it cannot drift from RECOMMENDATIONS. Module 02 shows what
# the hand-maintained version costs when it does.
_CATEGORIES = ", ".join(RECOMMENDATIONS)


def get_local_recommendations(category: str) -> str:
    # The description below is what the model actually reads. It is assigned
    # rather than written as a literal docstring so that the category list is
    # generated from RECOMMENDATIONS and cannot drift from it.
    if not isinstance(category, str) or category not in RECOMMENDATIONS:
        return _json({"error": f"Unknown category. Available: {_CATEGORIES}."})
    return _json(
        {
            "category": category,
            "recommendations": RECOMMENDATIONS[category],
            "count": len(RECOMMENDATIONS[category]),
        }
    )


get_local_recommendations.__doc__ = f"""Return curated recommendations near the hotel by category.

    Args:
        category: One of: {_CATEGORIES}.
    """

get_local_recommendations = tool("get_local_recommendations")(
    traced_tool(get_local_recommendations)
)


CREW_TOOLS = [
    check_room_availability,
    get_room_service_menu,
    get_local_recommendations,
]
