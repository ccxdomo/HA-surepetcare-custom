"""T13 (contracts §10) plus the coordinator side of T7 and the audit checks.

Requires homeassistant installed (skipped otherwise; the HA-free test run
covers api.py and assignments.py only). No HA test harness: the coordinator
is instantiated via object.__new__ with doubles, proving the service flow
without a running Home Assistant.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import (  # noqa: E402
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import entity_registry as er  # noqa: E402

from custom_components.surepetcare.api import (  # noqa: E402
    SurepetcareVerificationError,
)
from custom_components.surepetcare.const import (  # noqa: E402
    ATTR_CONFIRM,
    ATTR_ENTITY_ID,
    ATTR_INDOOR_ONLY,
)
from custom_components.surepetcare.coordinator import (  # noqa: E402
    SurePetcareDataCoordinator,
)

PINCEAU_ENTITY = "switch.pinceau_indoor_only"
MOCA_ENTITY = "switch.moca_indoor_only"
NOFLAP_ENTITY = "switch.noflap_indoor_only"

VERIFIED_TAG = {
    "id": 300003,
    "device_id": 200001,
    "index": 3,
    "profile": 3,
    "version": 14,
    "updated_at": "2026-09-26T10:00:00Z",
}


class FakeApi:
    """Coordinator api double: records calls, replays a result or error."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result
        self._error = error

    async def set_tag_profile(
        self, device_id, tag_id, profile, *, expected_prior_version
    ):
        self.calls.append(
            {
                "device_id": device_id,
                "tag_id": tag_id,
                "profile": profile,
                "expected_prior_version": expected_prior_version,
            }
        )
        if self._error is not None:
            raise self._error
        if isinstance(self._result, list):
            return self._result.pop(0)
        return self._result


class FakeRegistry:
    def __init__(self, entries):
        self._entries = entries

    def async_get(self, entity_id):
        return self._entries.get(entity_id)


class FakeHass:
    def __init__(self, registry):
        self.data = {er.DATA_REGISTRY: registry}
        self.auth = None


def registry_entry(unique_id, platform="surepetcare", domain="switch"):
    return SimpleNamespace(platform=platform, domain=domain, unique_id=unique_id)


def make_registry() -> dict:
    return {
        PINCEAU_ENTITY: registry_entry("100241-400003-indoor_only"),
        MOCA_ENTITY: registry_entry("100241-400001-indoor_only"),
        NOFLAP_ENTITY: registry_entry("100241-999002-indoor_only"),
    }


def make_coordinator(entity_map, api=None, registry_entries=None):
    coordinator = object.__new__(SurePetcareDataCoordinator)
    coordinator.data = entity_map
    coordinator.hass = FakeHass(FakeRegistry(registry_entries or {}))
    coordinator.api = api if api is not None else FakeApi()
    coordinator._last_write_by_pet = {}
    refreshed: list[bool] = []
    pushed: list[Any] = []

    async def async_request_refresh():
        refreshed.append(True)

    coordinator.async_request_refresh = async_request_refresh

    def async_set_updated_data(data):
        # @callback in HA 2026.9 (sync) — the double mirrors that.
        pushed.append(data)

    coordinator.async_set_updated_data = async_set_updated_data
    return coordinator, refreshed, pushed


def make_call(indoor_only, confirm, entity_ids, user_id="user-041"):
    return SimpleNamespace(
        data={
            ATTR_INDOOR_ONLY: indoor_only,
            ATTR_CONFIRM: confirm,
            ATTR_ENTITY_ID: entity_ids,
        },
        context=SimpleNamespace(user_id=user_id),
    )


# ---------------------------------------------------------------------- T13


async def test_t13_confirm_false_rejected_zero_http(entity_map):
    coordinator, refreshed, pushed = make_coordinator(entity_map)
    with pytest.raises(ServiceValidationError) as excinfo:
        await coordinator.handle_set_indoor_only(
            make_call(False, False, [PINCEAU_ENTITY])
        )
    assert excinfo.value.translation_key == "confirm_required"
    assert coordinator.api.calls == []  # zero HTTP calls
    assert refreshed == []  # no refresh either
    assert pushed == []


async def test_t13_confirm_missing_rejected(entity_map):
    coordinator, refreshed, pushed = make_coordinator(entity_map)
    call = make_call(True, True, [PINCEAU_ENTITY])
    call.data.pop(ATTR_CONFIRM)
    with pytest.raises(ServiceValidationError) as excinfo:
        await coordinator.handle_set_indoor_only(call)
    assert excinfo.value.translation_key == "confirm_required"
    assert coordinator.api.calls == []


async def test_t13_unknown_entity_rejected(entity_map):
    coordinator, refreshed, pushed = make_coordinator(
        entity_map, registry_entries=make_registry()
    )
    with pytest.raises(ServiceValidationError) as excinfo:
        await coordinator.handle_set_indoor_only(
            make_call(True, True, ["switch.not_a_pet_indoor_only"])
        )
    assert excinfo.value.translation_key == "invalid_entity"
    assert coordinator.api.calls == []


async def test_t13_entity_of_other_platform_rejected(entity_map):
    entries = {
        PINCEAU_ENTITY: registry_entry(
            "100241-400003-indoor_only", platform="other_integration"
        )
    }
    coordinator, _, _ = make_coordinator(entity_map, registry_entries=entries)
    with pytest.raises(ServiceValidationError) as excinfo:
        await coordinator.handle_set_indoor_only(
            make_call(True, True, [PINCEAU_ENTITY])
        )
    assert excinfo.value.translation_key == "invalid_entity"


async def test_t13_entity_without_suffix_rejected(entity_map):
    entries = {PINCEAU_ENTITY: registry_entry("100241-400003")}
    coordinator, _, _ = make_coordinator(entity_map, registry_entries=entries)
    with pytest.raises(ServiceValidationError) as excinfo:
        await coordinator.handle_set_indoor_only(
            make_call(True, True, [PINCEAU_ENTITY])
        )
    assert excinfo.value.translation_key == "invalid_entity"


async def test_t13_no_flap_assignment_rejected(entity_map):
    coordinator, _, _ = make_coordinator(
        entity_map, registry_entries=make_registry()
    )
    with pytest.raises(HomeAssistantError) as excinfo:
        await coordinator.handle_set_indoor_only(
            make_call(True, True, [NOFLAP_ENTITY])
        )
    assert excinfo.value.translation_key == "no_flap_assignment"
    assert coordinator.api.calls == []


async def test_t13_offline_flap_refused_before_any_write(entity_map):
    entity_map[200001]["status"]["online"] = False
    coordinator, refreshed, pushed = make_coordinator(
        entity_map, registry_entries=make_registry()
    )
    with pytest.raises(HomeAssistantError) as excinfo:
        await coordinator.handle_set_indoor_only(make_call(True, True, [PINCEAU_ENTITY]))
    assert excinfo.value.translation_key == "device_offline"
    assert coordinator.api.calls == []  # fail fast: nothing written


async def test_t13_offline_flap_on_any_target_blocks_all(entity_map):
    """One offline flap in the batch blocks writes for ALL targeted pets."""
    entity_map[1307329]["status"]["online"] = False  # Moca's second flap
    coordinator, _, _ = make_coordinator(entity_map, registry_entries=make_registry())
    with pytest.raises(HomeAssistantError) as excinfo:
        await coordinator.handle_set_indoor_only(
            make_call(True, True, [PINCEAU_ENTITY, MOCA_ENTITY])
        )
    assert excinfo.value.translation_key == "device_offline"
    assert coordinator.api.calls == []


# ------------------------------------------------------- happy path + audit


async def test_happy_path_writes_verifies_patches_and_audits(entity_map, caplog):
    api = FakeApi(result=dict(VERIFIED_TAG))
    coordinator, refreshed, pushed = make_coordinator(
        entity_map, api=api, registry_entries=make_registry()
    )
    with caplog.at_level("INFO"):
        await coordinator.handle_set_indoor_only(
            make_call(True, True, [PINCEAU_ENTITY])
        )

    # Write used the cached profile version as the prior-version baseline.
    assert api.calls == [
        {
            "device_id": 200001,
            "tag_id": 300003,
            "profile": 3,
            "expected_prior_version": 13,
        }
    ]
    # Cache patched in place with ONLY the verified values (V1/D4).
    tag = entity_map[200001]["tags"][2]
    assert tag["profile"] == 3
    assert tag["version"] == 14
    assert tag["updated_at"] == "2026-09-26T10:00:00Z"
    # Switches re-read the patched cache exactly once, no extra refresh.
    assert pushed == [entity_map]
    assert refreshed == []
    # last_write audit recorded for the pet.
    audit = coordinator.get_last_write(400003)
    assert audit["requested"] is True
    assert audit["user_id"] == "user-041"
    assert audit["at"]
    assert audit["verified"] == [
        {
            "device_id": 200001,
            "tag_id": 300003,
            "profile": 3,
            "version": 14,
        }
    ]
    # One INFO audit line with the contractual fields (§9.2).
    assert "indoor-only write verified" in caplog.text
    assert "pet=Pinceau" in caplog.text
    assert "tag_id=300003" in caplog.text
    assert "device=la chatière (200001)" in caplog.text
    assert "profile 2->3" in caplog.text
    assert "version 13->14" in caplog.text
    assert "user=user-041" in caplog.text


async def test_happy_path_indoor_only_false_writes_profile_2(entity_map):
    verified = dict(VERIFIED_TAG, profile=2, version=14)
    api = FakeApi(result=verified)
    coordinator, _, pushed = make_coordinator(
        entity_map, api=api, registry_entries=make_registry()
    )
    await coordinator.handle_set_indoor_only(make_call(False, True, [PINCEAU_ENTITY]))
    assert api.calls[0]["profile"] == 2
    assert entity_map[200001]["tags"][2]["profile"] == 2
    assert pushed == [entity_map]


async def test_happy_path_multi_pet_multi_flap_sequential(entity_map):
    verified_tag_pinceau = dict(VERIFIED_TAG)
    verified_moca_flap1 = {
        "id": 300001,
        "device_id": 200001,
        "index": 1,
        "profile": 3,
        "version": 4,
    }
    verified_moca_flap2 = {
        "id": 300001,
        "device_id": 1307329,
        "index": 1,
        "profile": 3,
        "version": 8,
    }
    api = FakeApi(
        result=[verified_moca_flap1, verified_moca_flap2, verified_tag_pinceau]
    )
    coordinator, _, pushed = make_coordinator(
        entity_map, api=api, registry_entries=make_registry()
    )
    await coordinator.handle_set_indoor_only(
        make_call(True, True, [MOCA_ENTITY, PINCEAU_ENTITY])
    )
    # Moca's two flaps written sequentially, then Pinceau's one.
    assert [(c["device_id"], c["tag_id"]) for c in api.calls] == [
        (200001, 300001),
        (1307329, 300001),
        (200001, 300003),
    ]
    assert entity_map[200001]["tags"][0]["version"] == 4
    assert entity_map[1307329]["tags"][0]["version"] == 8
    assert entity_map[200001]["tags"][2]["version"] == 14
    assert pushed == [entity_map]


# ------------------------------------------------- T7 coordinator half + §6.4


async def test_t7_verification_failure_no_patch_refresh_scheduled(entity_map, caplog):
    api = FakeApi(
        error=SurepetcareVerificationError(
            "Could not verify the indoor-only change for tag 300003 on device 200001"
        )
    )
    coordinator, refreshed, pushed = make_coordinator(
        entity_map, api=api, registry_entries=make_registry()
    )
    with caplog.at_level("INFO"):
        with pytest.raises(HomeAssistantError) as excinfo:
            await coordinator.handle_set_indoor_only(
                make_call(True, True, [PINCEAU_ENTITY])
            )
    assert excinfo.value.translation_key == "verification_failed"
    # No cache patch: the displayed state remains the last cloud state (V3).
    assert pushed == []
    assert entity_map[200001]["tags"][2]["profile"] == 2
    assert entity_map[200001]["tags"][2]["version"] == 13
    # A refresh is scheduled so the UI reconciles with cloud truth (§6.4).
    assert refreshed == [True]
    # The failure is ERROR-audited with the same identifiers (§9.2).
    assert "indoor-only write FAILED" in caplog.text
    assert "pet=Pinceau" in caplog.text
    assert "200001" in caplog.text


async def test_no_secrets_in_audit_logs(entity_map, caplog):
    """Audit lines never contain credentials (they never had any, but the
    contract's hygiene rule is asserted here for the coordinator flow)."""
    api = FakeApi(result=dict(VERIFIED_TAG))
    coordinator, _, _ = make_coordinator(
        entity_map, api=api, registry_entries=make_registry()
    )
    with caplog.at_level("DEBUG"):
        await coordinator.handle_set_indoor_only(
            make_call(True, True, [PINCEAU_ENTITY])
        )
    assert "password" not in caplog.text.lower()
    assert "token" not in caplog.text.lower()
    assert "bearer" not in caplog.text.lower()