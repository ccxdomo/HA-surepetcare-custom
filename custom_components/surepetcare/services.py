"""Support for Sure Petcare services."""

import logging

import probatio
from surepy.enums import Location

from homeassistant.const import ATTR_LOCATION, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er, service

from .const import (
    ATTR_CONFIRM,
    ATTR_ENTITY_ID,
    ATTR_FLAP_ID,
    ATTR_INDOOR_ONLY,
    ATTR_LOCK_STATE,
    ATTR_PET_NAME,
    DOMAIN,
    SERVICE_SET_INDOOR_ONLY,
    SERVICE_SET_LOCK_STATE,
    SERVICE_SET_PET_LOCATION,
)
from .coordinator import SurePetcareConfigEntry

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Sure Petcare services."""

    async def handle_set_lock_state(call: ServiceCall) -> None:
        """Set lock state for a flap."""
        entry: SurePetcareConfigEntry = service.async_get_config_entry(
            hass, DOMAIN, None
        )
        coordinator = entry.runtime_data
        if call.data[ATTR_FLAP_ID] not in coordinator.data:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_flap_id",
                translation_placeholders={"flap_id": call.data[ATTR_FLAP_ID]},
            )
        await coordinator.handle_set_lock_state(call)

    async def handle_set_pet_location(call: ServiceCall) -> None:
        """Set pet location."""
        entry: SurePetcareConfigEntry = service.async_get_config_entry(
            hass, DOMAIN, None
        )
        coordinator = entry.runtime_data
        if call.data[ATTR_PET_NAME] not in coordinator.get_pets():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_pet_name",
                translation_placeholders={"pet_name": call.data[ATTR_PET_NAME]},
            )
        await coordinator.handle_set_pet_location(call)

    async def handle_set_indoor_only(call: ServiceCall) -> None:
        """Set the indoor-only profile for one or more pet switches."""
        entry: SurePetcareConfigEntry = service.async_get_config_entry(
            hass, DOMAIN, None
        )
        coordinator = entry.runtime_data
        # First protection layer: confirm must be true, before any API traffic
        # (contracts §8.3; the coordinator re-checks — §7.2 step 1).
        if call.data.get(ATTR_CONFIRM) is not True:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="confirm_required",
            )
        # Resolve target entities to this platform's pet switches (§8.3).
        registry = er.async_get(hass)
        entity_ids = call.data[ATTR_ENTITY_ID]
        if isinstance(entity_ids, str):
            entity_ids = [e.strip() for e in entity_ids.split(",") if e.strip()]
        for entity_id in entity_ids:
            entity_entry = registry.async_get(entity_id)
            if (
                entity_entry is None
                or entity_entry.platform != DOMAIN
                or entity_entry.domain != Platform.SWITCH
            ):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_entity",
                    translation_placeholders={"entity_id": entity_id},
                )
        # Delegate to the verified write sequence (§7.2).
        await coordinator.handle_set_indoor_only(call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LOCK_STATE,
        handle_set_lock_state,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_FLAP_ID): cv.positive_int,
                probatio.Required(ATTR_LOCK_STATE): probatio.All(
                    cv.string,
                    probatio.Lower,
                    probatio.In(
                        [
                            "unlocked",
                            "locked_in",
                            "locked_out",
                            "locked_all",
                        ]
                    ),
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PET_LOCATION,
        handle_set_pet_location,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_PET_NAME): cv.string,
                probatio.Required(ATTR_LOCATION): probatio.In(
                    [
                        Location.INSIDE.name.title(),
                        Location.OUTSIDE.name.title(),
                    ]
                ),
            }
        ),
    )
    # Spec 041 (contracts §8.3): protected indoor-only write. Target entity ids
    # plus two required booleans; the handler enforces confirm is True.
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_INDOOR_ONLY,
        handle_set_indoor_only,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
                probatio.Required(ATTR_INDOOR_ONLY): cv.boolean,
                probatio.Required(ATTR_CONFIRM): cv.boolean,
            }
        ),
    )
