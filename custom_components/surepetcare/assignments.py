"""Pure pet↔tag↔flap mapping helpers (spec 041, contracts §7.3).

Standalone by design: no Home Assistant and no surepy imports. The module
accepts the coordinator's entity mapping — values may be surepy entities
exposing ``raw_data()`` or plain payload dicts — so it is unit-testable
without HA (data-model.md §3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Flap device product ids (surepy EntityType.PET_FLAP=3 / CAT_FLAP=6).
# Contract §4: the only place product ids may be hardcoded.
FLAP_PRODUCT_IDS = frozenset({3, 6})

# Mirror of const.py PROFILE_INDOOR_ONLY (kept local for standalone imports).
PROFILE_INDOOR_ONLY = 3


@dataclass
class TagAssignment:
    """A (flap device, tag) pair — the unit the indoor-only profile lives on.

    ``online`` carries the flap's ``status.online`` because the contract-mandated
    ``switch_available(assignment)`` needs it (all other fields per §7.3).
    """

    device_id: int
    device_name: str
    tag: dict[str, Any]
    online: bool = False


@dataclass
class PetAssignment:
    """A pet mapped to its tag and the flap assignments carrying that tag."""

    pet_id: int
    pet_name: str
    tag_id: int
    flaps: list[TagAssignment]


def _payload(entity: Any) -> Mapping[str, Any] | None:
    """Unwrap surepy entities to their raw payload, or pass dicts through."""
    raw = entity.raw_data() if hasattr(entity, "raw_data") else entity
    return raw if isinstance(raw, Mapping) else None


def build_pet_assignments(entities: Mapping[int, Any]) -> list[PetAssignment]:
    """Map every chipped pet to the flap devices carrying its tag.

    Rules (data-model.md §3, research §3/§6):
    - pets: payloads without ``product_id`` (or 0) with a non-null ``tag_id``;
    - flaps: payloads with ``product_id`` 3 or 6 only (feeders, Felaqua, hub
      and their tag profiles are ignored for indoor-only);
    - a pet is assigned to a flap iff the flap's ``tags[]`` contains its tag id.
    """
    flaps: list[Mapping[str, Any]] = []
    pets: list[Mapping[str, Any]] = []
    for entity in entities.values():
        raw = _payload(entity)
        if raw is None:
            continue
        product_id = raw.get("product_id")
        if product_id in FLAP_PRODUCT_IDS:
            flaps.append(raw)
        elif product_id in (None, 0) and "tag_id" in raw:
            pets.append(raw)

    assignments: list[PetAssignment] = []
    for pet in pets:
        tag_id = pet.get("tag_id")
        if tag_id is None:
            # Unchipped pet: no indoor-only surface at all.
            continue
        matched: list[TagAssignment] = []
        for flap in flaps:
            for tag in flap.get("tags") or []:
                if tag.get("id") == tag_id and flap.get("id") is not None:
                    matched.append(
                        TagAssignment(
                            device_id=int(flap["id"]),
                            # Names may carry trailing whitespace (research §1).
                            device_name=str(flap.get("name") or "").strip(),
                            tag=dict(tag),
                            online=bool((flap.get("status") or {}).get("online")),
                        )
                    )
        assignments.append(
            PetAssignment(
                pet_id=int(pet["id"]),
                pet_name=str(pet.get("name") or "").strip(),
                tag_id=int(tag_id),
                flaps=matched,
            )
        )
    return assignments


def all_flaps_indoor_only(assignment: PetAssignment) -> bool:
    """True iff the pet has flaps and every one is at the indoor-only profile."""
    return bool(assignment.flaps) and all(
        flap.tag.get("profile") == PROFILE_INDOOR_ONLY for flap in assignment.flaps
    )


def indoor_only_state(assignment: PetAssignment) -> bool:
    """Alias of all_flaps_indoor_only, kept for contract clarity (§7.3)."""
    return all_flaps_indoor_only(assignment)


def switch_available(assignment: PetAssignment) -> bool:
    """True iff every assigned flap is online (offline flaps refuse writes)."""
    return bool(assignment.flaps) and all(flap.online for flap in assignment.flaps)