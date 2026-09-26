"""Coordinator for the surepetcare integration."""

from datetime import timedelta
import logging
from typing import Any, override

from surepy import Surepy, SurepyEntity
from surepy.enums import EntityType, Location, LockState
from surepy.exceptions import SurePetcareAuthenticationError, SurePetcareError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_LOCATION,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SurePetcareApiClient,
    SurePetcareApiAuthError,
    SurePetcareApiConnectionError,
    SurepetcareVerificationError,
)
from .assignments import PetAssignment, build_pet_assignments
from .const import (
    ATTR_CONFIRM,
    ATTR_ENTITY_ID,
    ATTR_FLAP_ID,
    ATTR_INDOOR_ONLY,
    ATTR_LOCK_STATE,
    ATTR_PET_NAME,
    DOMAIN,
    PROFILE_INDOOR_ONLY,
    PROFILE_NORMAL_ACCESS,
    SURE_API_TIMEOUT,
)

# Suffix of the switch unique_id "{household_id}-{pet_id}-indoor_only"
# (contracts §9.1); also the parse anchor for service entity resolution.
UNIQUE_ID_INDOOR_ONLY_SUFFIX = "-indoor_only"

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=3)

type SurePetcareConfigEntry = ConfigEntry[SurePetcareDataCoordinator]


class SurePetcareDataCoordinator(DataUpdateCoordinator[dict[int, SurepyEntity]]):
    """Handle Surepetcare data."""

    config_entry: SurePetcareConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SurePetcareConfigEntry) -> None:
        """Initialize the data handler."""
        self.surepy = Surepy(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            auth_token=entry.data[CONF_TOKEN],
            api_timeout=SURE_API_TIMEOUT,
            session=async_get_clientsession(hass),
        )
        # Spec 041 (contracts §7.1): write + verify client. In-memory session
        # with lazy login — no eager login here; surepy stays the read backbone.
        self.api = SurePetcareApiClient(
            email=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            session=async_get_clientsession(hass),
            timeout=SURE_API_TIMEOUT,
        )
        # Last verified write audit per pet, shown as the switch last_write
        # attribute (contracts §9.1). Plain bookkeeping, no API wiring.
        self._last_write_by_pet: dict[int, dict[str, Any]] = {}
        self.lock_states_callbacks = {
            LockState.UNLOCKED.name.lower(): self.surepy.sac.unlock,
            LockState.LOCKED_IN.name.lower(): self.surepy.sac.lock_in,
            LockState.LOCKED_OUT.name.lower(): self.surepy.sac.lock_out,
            LockState.LOCKED_ALL.name.lower(): self.surepy.sac.lock,
        }
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    @override
    async def _async_update_data(self) -> dict[int, SurepyEntity]:
        """Get the latest data from Sure Petcare."""
        try:
            return await self.surepy.get_entities(refresh=True)
        except SurePetcareAuthenticationError as err:
            raise ConfigEntryAuthFailed("Invalid username/password") from err
        except SurePetcareError as err:
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

    async def handle_set_lock_state(self, call: ServiceCall) -> None:
        """Call when setting the lock state."""
        flap_id = call.data[ATTR_FLAP_ID]
        state = call.data[ATTR_LOCK_STATE]
        await self.lock_states_callbacks[state](flap_id)
        await self.async_request_refresh()

    def get_pets(self) -> dict[str, int]:
        """Get pets."""
        pets = {}
        for surepy_entity in self.data.values():
            if surepy_entity.type == EntityType.PET and surepy_entity.name:
                pets[surepy_entity.name] = surepy_entity.id
        return pets

    async def handle_set_pet_location(self, call: ServiceCall) -> None:
        """Call when setting the pet location."""
        pet_name = call.data[ATTR_PET_NAME]
        location = call.data[ATTR_LOCATION]
        device_id = self.get_pets()[pet_name]
        await self.surepy.sac.set_pet_location(device_id, Location[location.upper()])
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Spec 041: protected indoor-only write path (contracts §7.2).
    # ------------------------------------------------------------------

    def get_last_write(self, pet_id: int) -> dict[str, Any] | None:
        """Return the last verified indoor-only write audit for a pet."""
        return self._last_write_by_pet.get(pet_id)

    async def _resolve_user_name(self, user_id: str | None) -> str:
        """Resolve the calling user for the audit log (contracts §9.2)."""
        if user_id is None:
            return "unknown"
        auth = getattr(self.hass, "auth", None) if self.hass is not None else None
        if auth is None:
            return str(user_id)
        try:
            user = await auth.async_get_user(user_id)
        except Exception:  # noqa: BLE001 - the audit lookup must never break a write
            return str(user_id)
        if user is None:
            return str(user_id)
        return user.name or str(user_id)

    def _resolve_indoor_only_target(
        self,
        registry: er.EntityRegistry | None,
        entity_id: str,
        by_pet: dict[int, PetAssignment],
    ) -> PetAssignment:
        """Resolve a switch entity id to its pet assignment (§7.2 step 2)."""
        invalid = ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_entity",
            translation_placeholders={"entity_id": entity_id},
        )
        entry = registry.async_get(entity_id) if registry is not None else None
        if (
            entry is None
            or entry.platform != DOMAIN
            or entry.domain != Platform.SWITCH
        ):
            raise invalid
        unique_id = entry.unique_id or ""
        if not unique_id.endswith(UNIQUE_ID_INDOOR_ONLY_SUFFIX):
            raise invalid
        pet_key = unique_id[: -len(UNIQUE_ID_INDOOR_ONLY_SUFFIX)]
        try:
            pet_id = int(pet_key.rsplit("-", 1)[-1])
        except (IndexError, TypeError, ValueError) as error:
            raise invalid from error
        assignment = by_pet.get(pet_id)
        if assignment is None:
            raise invalid
        if not assignment.flaps:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="no_flap_assignment",
                translation_placeholders={"pet_name": assignment.pet_name},
            )
        return assignment

    def _patch_cached_tag(self, verified_tag: dict[str, Any]) -> None:
        """Patch verified profile/version into the cached raw device payload.

        surepy's ``raw_data()`` returns the live payload dict, so this updates
        exactly what the switches read from the coordinator cache. Only the
        values returned by the verification read are patched (contracts §6.5,
        §7.2 step 5).
        """
        device_id = int(verified_tag["device_id"])
        tag_id = int(verified_tag["id"])
        entity = self.data.get(device_id)
        raw = entity.raw_data() if hasattr(entity, "raw_data") else entity
        if not isinstance(raw, dict):
            _LOGGER.warning(
                "no cached payload for device %s; skipping cache patch", device_id
            )
            return
        for tag in raw.get("tags") or []:
            if tag.get("id") == tag_id:
                tag["profile"] = verified_tag["profile"]
                tag["version"] = verified_tag["version"]
                if "updated_at" in verified_tag:
                    tag["updated_at"] = verified_tag["updated_at"]
                return
        _LOGGER.warning(
            "verified tag %s not found in cached payload of device %s",
            tag_id,
            device_id,
        )

    def _log_indoor_only_failure(
        self,
        user_name: str,
        user_id: str | None,
        at: str,
        entity_ids: list[str],
        targets: list[PetAssignment],
        reason: str,
    ) -> None:
        """ERROR audit line carrying the same identifiers as success (§9.2)."""
        pets = "; ".join(
            f"pet={assignment.pet_name} tag_id={assignment.tag_id} "
            + " ".join(
                f"device={flap.device_name} ({flap.device_id})"
                for flap in assignment.flaps
            )
            for assignment in targets
        )
        _LOGGER.error(
            "indoor-only write FAILED | user=%s | user_id=%s | at=%s | "
            "entity_id(s)=%s | %s | reason=%s",
            user_name,
            user_id,
            at,
            ", ".join(entity_ids),
            pets,
            reason,
        )

    async def handle_set_indoor_only(self, call: ServiceCall) -> None:
        """Protected write: set indoor-only for the targeted pets (§7.2)."""
        # Step 1: refuse accidental runs before any API traffic.
        if call.data.get(ATTR_CONFIRM) is not True:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="confirm_required"
            )

        indoor_only = bool(call.data[ATTR_INDOOR_ONLY])
        entity_ids = call.data[ATTR_ENTITY_ID]
        if isinstance(entity_ids, str):
            entity_ids = [e.strip() for e in entity_ids.split(",") if e.strip()]

        # Step 2: resolve each entity id to a pet assignment.
        by_pet = {a.pet_id: a for a in build_pet_assignments(self.data)}
        registry = er.async_get(self.hass) if self.hass is not None else None
        targets = [
            self._resolve_indoor_only_target(registry, entity_id, by_pet)
            for entity_id in entity_ids
        ]

        # Step 3: fail fast if ANY target flap is offline — write nothing.
        for assignment in targets:
            for flap in assignment.flaps:
                if not flap.online:
                    _LOGGER.error(
                        "refusing indoor-only write: flap %s (%s) for pet %s is offline",
                        flap.device_id,
                        flap.device_name,
                        assignment.pet_name,
                    )
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="device_offline",
                        translation_placeholders={
                            "device_name": flap.device_name,
                            "device_id": str(flap.device_id),
                        },
                    )

        profile = PROFILE_INDOOR_ONLY if indoor_only else PROFILE_NORMAL_ACCESS
        context_user_id = getattr(call.context, "user_id", None)
        user_name = await self._resolve_user_name(context_user_id)
        at = dt_util.now().isoformat()
        # (assignment, flap, old_profile, old_version, verified_tag) tuples.
        audit_verified: list[
            tuple[PetAssignment, Any, Any, Any, dict[str, Any]]
        ] = []

        try:
            # Steps 4-5: sequential verified writes, patching the cache after
            # each verification read (never from the PUT response).
            for assignment in targets:
                pet_audit: dict[str, Any] = {
                    "at": at,
                    "user_id": context_user_id,
                    "requested": indoor_only,
                    "verified": [],
                }
                for flap in assignment.flaps:
                    old_profile = flap.tag.get("profile")
                    old_version = flap.tag.get("version")
                    verified = await self.api.set_tag_profile(
                        flap.device_id,
                        assignment.tag_id,
                        profile,
                        expected_prior_version=old_version,
                    )
                    self._patch_cached_tag(verified)
                    pet_audit["verified"].append(
                        {
                            "device_id": flap.device_id,
                            "tag_id": assignment.tag_id,
                            "profile": verified.get("profile"),
                            "version": verified.get("version"),
                        }
                    )
                    self._last_write_by_pet[assignment.pet_id] = pet_audit
                    audit_verified.append(
                        (assignment, flap, old_profile, old_version, verified)
                    )
        except SurePetcareApiAuthError as error:
            await self.async_request_refresh()
            self._log_indoor_only_failure(
                user_name, context_user_id, at, entity_ids, targets, f"authentication failed: {error}"
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="api_auth_failed"
            ) from error
        except SurePetcareApiConnectionError as error:
            await self.async_request_refresh()
            self._log_indoor_only_failure(
                user_name, context_user_id, at, entity_ids, targets, f"connection failed: {error}"
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="api_connection_failed"
            ) from error
        except SurepetcareVerificationError as error:
            await self.async_request_refresh()
            self._log_indoor_only_failure(
                user_name, context_user_id, at, entity_ids, targets, f"verification failed: {error}"
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="verification_failed"
            ) from error

        # Step 6: only now do switches re-read the patched cache.
        # Note: async_set_updated_data is a @callback in HA 2026.9 — do not await.
        self.async_set_updated_data(self.data)
        detail = "; ".join(
            f"pet={assignment.pet_name} tag_id={assignment.tag_id} "
            f"device={flap.device_name} ({flap.device_id}) "
            f"profile {old_profile}->{verified.get('profile')} "
            f"version {old_version}->{verified.get('version')}"
            for assignment, flap, old_profile, old_version, verified in audit_verified
        )
        _LOGGER.info(
            "indoor-only write verified | user=%s | user_id=%s | at=%s | "
            "entity_id(s)=%s | %s",
            user_name,
            context_user_id,
            at,
            ", ".join(entity_ids),
            detail,
        )
