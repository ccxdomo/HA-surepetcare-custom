"""Per-pet "Indoor Only" switches (spec 041, contracts §9.1).

State is ALWAYS derived from a cloud read — the regular coordinator poll or
the post-write verification read — never from a PUT response (invariants
V1/V2/V3). The entity itself is write-protected: toggling raises an error;
the only write path is the surepetcare.set_indoor_only service.
"""

from __future__ import annotations

import logging
from typing import Any, override

from surepy.entities import SurepyEntity

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import assignments
from .const import DOMAIN
from .coordinator import SurePetcareConfigEntry, SurePetcareDataCoordinator
from .entity import SurePetcareEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one write-protected indoor-only switch per pet with flap access."""
    coordinator = entry.runtime_data
    entities: list[PetIndoorOnlySwitch] = []
    unassigned: list[str] = []
    for assignment in assignments.build_pet_assignments(coordinator.data):
        if assignment.flaps:
            entities.append(PetIndoorOnlySwitch(assignment.pet_id, coordinator))
        else:
            unassigned.append(assignment.pet_name)
    if unassigned:
        # Contract §9.1: pets without flap assignments get no entity; log once.
        _LOGGER.info(
            "pet(s) without flap assignment, no indoor-only switch created: %s",
            ", ".join(sorted(unassigned)),
        )
    async_add_entities(entities)


class PetIndoorOnlySwitch(SurePetcareEntity, SwitchEntity):
    """Write-protected per-pet indoor-only switch, cloud state only."""

    def __init__(
        self, pet_id: int, coordinator: SurePetcareDataCoordinator
    ) -> None:
        """Initialize the switch for one pet."""
        # Set before super().__init__: the base constructor already calls
        # _update_attr() with the coordinator data.
        self._assignment: assignments.PetAssignment | None = None
        super().__init__(pet_id, coordinator)
        self._attr_name = f"{self._device_name.strip()} Indoor Only"
        self._attr_unique_id = f"{self._device_id}-indoor_only"

    @callback
    @override
    def _update_attr(self, surepy_entity: SurepyEntity | None) -> None:
        """Derive state from the pet's flap assignments (cloud read only)."""
        assignment = None
        for candidate in assignments.build_pet_assignments(self.coordinator.data):
            if candidate.pet_id == self._id:
                assignment = candidate
                break
        self._assignment = assignment
        if assignment is None:
            # Pet no longer in the cloud payload: no meaningful state.
            self._attr_is_on = None
            return
        indoor = assignments.all_flaps_indoor_only(assignment)
        self._attr_is_on = indoor
        self._attr_icon = "mdi:home-lock" if indoor else "mdi:home-lock-open"
        attributes: dict[str, Any] = {
            "pet_id": assignment.pet_id,
            "pet_name": assignment.pet_name,
            "tag_id": assignment.tag_id,
            "devices": [
                {
                    "device_id": flap.device_id,
                    "device_name": flap.device_name,
                    "profile": flap.tag.get("profile"),
                    "version": flap.tag.get("version"),
                }
                for flap in assignment.flaps
            ],
            "all_flaps_indoor_only": indoor,
        }
        last_write = self.coordinator.get_last_write(assignment.pet_id)
        if last_write is not None:
            attributes["last_write"] = last_write
        self._attr_extra_state_attributes = attributes

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Get the latest data and update the state (tolerates a missing pet)."""
        self._update_attr(self.coordinator.data.get(self._id))
        self.async_write_ha_state()

    @property
    @override
    def available(self) -> bool:
        """Available iff the coordinator update succeeded and all flaps are online."""
        if not self.coordinator.last_update_success:
            return False
        if self._assignment is None:
            return False
        return assignments.switch_available(self._assignment)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Refuse direct writes: use the protected service (contracts §9.1)."""
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="switch_write_protected"
        )

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Refuse direct writes: use the protected service (contracts §9.1)."""
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="switch_write_protected"
        )