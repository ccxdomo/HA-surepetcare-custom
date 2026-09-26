"""T14 (contracts §10): the write-protected per-pet switch.

Requires homeassistant installed (skipped otherwise). No HA harness: the
entity is instantiated via object.__new__ with a coordinator double.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from custom_components.surepetcare import assignments  # noqa: E402
from custom_components.surepetcare.switch import PetIndoorOnlySwitch  # noqa: E402


def make_switch(pet_id: int, entity_map: dict, last_write: Any = None):
    switch = object.__new__(PetIndoorOnlySwitch)
    switch._id = pet_id
    switch._assignment = None
    switch.coordinator = SimpleNamespace(
        data=entity_map,
        last_update_success=True,
        get_last_write=lambda _pet_id: last_write,
    )
    return switch


# ---------------------------------------------------------------------- T14


async def test_t14_turn_on_refused():
    """Direct toggle raises the write-protected error — never writes."""
    switch = make_switch(701753, {})
    with pytest.raises(HomeAssistantError) as excinfo:
        await switch.async_turn_on()
    assert excinfo.value.translation_key == "switch_write_protected"


async def test_t14_turn_off_refused():
    switch = make_switch(701753, {})
    with pytest.raises(HomeAssistantError) as excinfo:
        await switch.async_turn_off()
    assert excinfo.value.translation_key == "switch_write_protected"


def test_t14_state_and_attributes_from_coordinator_fixture(entity_map):
    switch = make_switch(701753, entity_map)
    switch._update_attr(None)
    assert switch._attr_is_on is False  # fixture: Pinceau at profile 2
    attributes = switch._attr_extra_state_attributes
    assert attributes["pet_id"] == 701753
    assert attributes["pet_name"] == "Pinceau"
    assert attributes["tag_id"] == 2119787
    assert attributes["devices"] == [
        {
            "device_id": 1307328,
            "device_name": "la chatière",
            "profile": 2,
            "version": 13,
        }
    ]
    assert attributes["all_flaps_indoor_only"] is False
    assert "last_write" not in attributes
    assert switch.available is True
    assert switch._attr_icon == "mdi:home-lock-open"


def test_t14_indoor_only_state_and_icon(entity_map):
    for tag in entity_map[1307328]["tags"]:
        if tag["id"] == 2119787:
            tag["profile"] = 3
    switch = make_switch(701753, entity_map)
    switch._update_attr(None)
    assert switch._attr_is_on is True
    assert switch._attr_extra_state_attributes["all_flaps_indoor_only"] is True
    assert switch._attr_icon == "mdi:home-lock"


def test_t14_mixed_multi_flap_is_off(entity_map):
    """Moca: profile 3 on one flap, profile 2 on the other → off."""
    switch = make_switch(584007, entity_map)
    switch._update_attr(None)
    assert switch._attr_is_on is False
    devices = switch._attr_extra_state_attributes["devices"]
    assert sorted(d["device_id"] for d in devices) == [1307328, 1307329]
    assert switch.available is True


def test_t14_offline_flap_unavailable(entity_map):
    entity_map[1307328]["status"]["online"] = False
    switch = make_switch(701753, entity_map)
    switch._update_attr(None)
    assert switch.available is False


def test_t14_coordinator_failure_unavailable(entity_map):
    switch = make_switch(701753, entity_map)
    switch.coordinator.last_update_success = False
    switch._update_attr(None)
    assert switch.available is False


def test_t14_missing_pet_tolerated(entity_map):
    """A pet vanished from the payload: no state, unavailable — no crash."""
    switch = make_switch(424242, entity_map)
    switch._update_attr(None)
    assert switch._assignment is None
    assert switch._attr_is_on is None
    assert switch.available is False


def test_t14_last_write_attribute(entity_map):
    last_write = {
        "at": "2026-09-26T10:00:00+02:00",
        "user_id": "user-041",
        "requested": True,
        "verified": [
            {"device_id": 1307328, "tag_id": 2119787, "profile": 3, "version": 14}
        ],
    }
    switch = make_switch(701753, entity_map, last_write=last_write)
    switch._update_attr(None)
    assert switch._attr_extra_state_attributes["last_write"] == last_write


def test_t14_assignment_lookup_matches_module_rules(entity_map):
    """The switch's state matches assignments.all_flaps_indoor_only."""
    switch = make_switch(701753, entity_map)
    switch._update_attr(None)
    found = next(
        a
        for a in assignments.build_pet_assignments(entity_map)
        if a.pet_id == 701753
    )
    assert switch._attr_is_on == assignments.all_flaps_indoor_only(found)