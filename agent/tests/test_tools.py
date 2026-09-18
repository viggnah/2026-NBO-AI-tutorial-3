"""Unit tests for the three concierge tools.

These pass even when the system prompt is broken, the agent hallucinates,
or governance is misconfigured. They cover deterministic tool logic only -
which is exactly the gap module 03 (evaluation) addresses.
"""

from tools import (
    check_room_availability,
    get_local_recommendations,
    get_room_service_menu,
)


def test_check_room_availability_ok():
    out = check_room_availability("honeymoon", "2026-06-05", 2)
    assert out["available"] is True
    assert out["nights"] == 2
    assert out["total_usd"] == 420 * 2


def test_check_room_availability_bad_room():
    out = check_room_availability("penthouse")
    assert "error" in out


def test_check_room_availability_bad_date():
    out = check_room_availability("standard", check_in="June 5")
    assert "error" in out


def test_check_room_availability_bad_nights():
    assert "error" in check_room_availability("standard", nights=0)
    assert "error" in check_room_availability("standard", nights=99)


def test_room_service_menu_all():
    out = get_room_service_menu()
    assert out["count"] >= 4
    assert out["filtered"] == "none"


def test_room_service_menu_vegetarian():
    out = get_room_service_menu(vegetarian_only=True)
    assert out["filtered"] == "vegetarian_only"
    for item in out["items"]:
        assert item["vegetarian"] is True


def test_recommendations_ok():
    out = get_local_recommendations("restaurants")
    assert out["count"] >= 1
    assert "L'Ardoise" in {r["name"] for r in out["recommendations"]}


def test_recommendations_bad_category():
    out = get_local_recommendations("museums")
    assert "error" in out
