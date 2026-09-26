"""T11 + T12 (contracts §10): pet↔tag↔flap mapping and state rules.

Runs without Home Assistant (assignments.py is standalone by contract).
"""

from __future__ import annotations

import copy
from typing import Any


def assignment_for(assignments: list, pet_id: int) -> Any:
    return next(a for a in assignments if a.pet_id == pet_id)


def set_tag_profiles(entity_map: dict, tag_id: int, profile: int) -> None:
    """Set the profile of every (device, tag) assignment carrying tag_id."""
    for payload in entity_map.values():
        for tag in payload.get("tags") or []:
            if tag.get("id") == tag_id:
                tag["profile"] = profile


# ---------------------------------------------------------------------- T11


def test_t11_pet_tag_flap_mapping(assignments_module, entity_map):
    """Pets map to flap devices via pets[].tag_id ↔ devices[].tags[].id."""
    assignments = assignments_module.build_pet_assignments(entity_map)
    by_id = {a.pet_id: a for a in assignments}

    # Pinceau 701753 -> tag 2119787 -> cat flap 1307328 only (research §3).
    pinceau = by_id[701753]
    assert pinceau.pet_name == "Pinceau"
    assert pinceau.tag_id == 2119787
    assert [f.device_id for f in pinceau.flaps] == [1307328]
    assert pinceau.flaps[0].tag["profile"] == 2
    assert pinceau.flaps[0].tag["version"] == 13

    # Tibounet 584008 -> tag 1492590.
    tibounet = by_id[584008]
    assert tibounet.tag_id == 1492590
    assert [f.device_id for f in tibounet.flaps] == [1307328]

    # Moca 584007 -> tag 1492589 on TWO flaps (multi-flap pet).
    moca = by_id[584007]
    assert moca.tag_id == 1492589
    assert sorted(f.device_id for f in moca.flaps) == [1307328, 1307329]


def test_t11_flap_only_scoping_felaqua_ignored(assignments_module, entity_map):
    """Felaqua (product 8) and hub (product 1) never appear as flaps."""
    assignments = assignments_module.build_pet_assignments(entity_map)
    for assignment in assignments:
        assert all(f.device_id != 906099 for f in assignment.flaps)
        assert all(f.device_id != 1073725 for f in assignment.flaps)
    pinceau = assignment_for(assignments, 701753)
    # The Felaqua carries the same tag at version 1 but is excluded (D3).
    assert all(f.tag["version"] != 1 for f in pinceau.flaps)


def test_t11_unchipped_pet_skipped_no_flap_pet_kept(assignments_module, entity_map):
    """tag_id: None pet is skipped entirely; chipped pet without flaps is kept."""
    assignments = assignments_module.build_pet_assignments(entity_map)
    pet_ids = {a.pet_id for a in assignments}
    assert 999001 not in pet_ids  # Ghost (tag_id null) skipped
    assert 999002 in pet_ids  # NoFlap: chipped but no flap assignment
    noflap = assignment_for(assignments, 999002)
    assert noflap.flaps == []


def test_t11_trailing_space_names_stripped(assignments_module, entity_map):
    """Whitespace is stripped from device and pet names."""
    assignments = assignments_module.build_pet_assignments(entity_map)
    moca = assignment_for(assignments, 584007)
    assert moca.pet_name == "Moca"  # fixture carries "Moca "
    for assignment in assignments:
        for flap in assignment.flaps:
            assert flap.device_name == flap.device_name.strip()
    # Device fixture "la chatière " (trailing space).
    pinceau = assignment_for(assignments, 701753)
    assert pinceau.flaps[0].device_name == "la chatière"


def test_t11_accepts_surepy_style_entities(assignments_module, entity_map):
    """Values may also be objects exposing raw_data() (surepy entities)."""

    class FakeSurepyEntity:
        def __init__(self, payload):
            self._payload = payload

        def raw_data(self):
            return self._payload

    wrapped = {k: FakeSurepyEntity(v) for k, v in entity_map.items()}
    assignments = assignments_module.build_pet_assignments(wrapped)
    pinceau = assignment_for(assignments, 701753)
    assert pinceau.tag_id == 2119787
    assert [f.device_id for f in pinceau.flaps] == [1307328]


# ---------------------------------------------------------------------- T12


def test_t12_all_profile3_is_on(assignments_module, entity_map):
    set_tag_profiles(entity_map, 2119787, 3)
    assignments = assignments_module.build_pet_assignments(entity_map)
    pinceau = assignment_for(assignments, 701753)
    assert assignments_module.all_flaps_indoor_only(pinceau) is True
    assert assignments_module.indoor_only_state(pinceau) is True


def test_t12_any_profile2_is_off(assignments_module, entity_map):
    assignments = assignments_module.build_pet_assignments(entity_map)
    pinceau = assignment_for(assignments, 701753)  # fixture: profile 2
    assert assignments_module.all_flaps_indoor_only(pinceau) is False


def test_t12_mixed_state_is_off(assignments_module, entity_map):
    """Moca: profile 3 on pet door 1307329, profile 2 on cat flap 1307328."""
    assignments = assignments_module.build_pet_assignments(entity_map)
    moca = assignment_for(assignments, 584007)
    assert assignments_module.all_flaps_indoor_only(moca) is False
    profiles = {f.device_id: f.tag["profile"] for f in moca.flaps}
    assert profiles == {1307328: 2, 1307329: 3}


def test_t12_offline_flap_unavailable_and_refuses_write(
    assignments_module, entity_map
):
    """An offline flap makes the pet's switch unavailable (write refusal
    is asserted coordinator-side in test_coordinator_service.py)."""
    entity_map[1307328]["status"]["online"] = False
    assignments = assignments_module.build_pet_assignments(entity_map)
    pinceau = assignment_for(assignments, 701753)
    assert assignments_module.switch_available(pinceau) is False
    # State is still derived (last cloud read), but the entity reports
    # unavailable and the coordinator refuses writes for it.
    assert assignments_module.all_flaps_indoor_only(pinceau) is False


def test_t12_all_online_available(assignments_module, entity_map):
    assignments = assignments_module.build_pet_assignments(entity_map)
    pinceau = assignment_for(assignments, 701753)
    assert assignments_module.switch_available(pinceau) is True
    moca = assignment_for(assignments, 584007)
    assert assignments_module.switch_available(moca) is True


def test_t12_empty_flaps_not_indoor_only(assignments_module, entity_map):
    """A pet with no flap assignment is never 'on' (vacuous truth guarded)."""
    assignments = assignments_module.build_pet_assignments(entity_map)
    noflap = assignment_for(assignments, 999002)
    assert noflap.flaps == []
    assert assignments_module.all_flaps_indoor_only(noflap) is False
    assert assignments_module.switch_available(noflap) is False