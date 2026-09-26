# Spec 041 — BINDING contract: HA custom component `surepetcare` (indoor-only fork)

- **Date**: 2026-09-26
- **Audience**: Coder (implementer) and Reviewer (gate). This document is **binding**.
  Where it conflicts with any other spec file, **this file wins**. Where implementation
  judgment is needed and this file is silent, the Coder must ask the Architect — not
  guess.
- Fork base pin: home-assistant/core `dev` @ 2026-09-26 (see research.md §8).

## 1. Scope

A drop-in Home Assistant custom component at `custom_components/surepetcare/` that:

1. reproduces the HA core `surepetcare` integration (same domain, same `unique_id`s), and
2. adds one read-driven **"Indoor Only" switch per pet** plus the protected write service
   `surepetcare.set_indoor_only` with read-after-write verification.

No source code is included in this contract — it defines names, shapes, sequences and
invariants. Pseudocode marked NORMATIVE describes required behavior, not implementation.

## 2. File layout

```
custom_components/surepetcare/
├── __init__.py            EDIT   add Platform.SWITCH to PLATFORMS; register nothing else new
├── api.py                 NEW    SurePetcareApiClient (login / read devices / write+verify)
├── assignments.py         NEW    pure pet↔tag↔flap mapping + state helpers (no HA imports)
├── binary_sensor.py       CORE   verbatim (untouched)
├── config_flow.py         NEW    verbatim from core (completes the fork)
├── const.py               EDIT   add constants in §4.2
├── coordinator.py         EDIT   api client attribute + handle_set_indoor_only + patch helper
├── entity.py              NEW    verbatim from core (completes the fork)
├── icons.json             NEW    core content + set_indoor_only icon
├── lock.py                NEW    verbatim from core (completes the fork)
├── manifest.json          EDIT   per §3 (version, documentation, codeowners)
├── sensor.py              CORE   verbatim (untouched, incl. PEP 758 except clause)
├── services.py            EDIT   register set_indoor_only (pattern: existing services)
├── services.yaml          NEW    core content + set_indoor_only block (§8.1)
├── strings.json           NEW    core content + set_indoor_only + new exceptions (§8.2)
├── switch.py              NEW    PetIndoorOnlySwitch platform (§7)
└── translations/en.json   NEW    resolved strings (core strings.json translated, §8.3)
```

Rules:

- **CORE** files are copied verbatim from core dev @ 2026-09-26 and never modified
  (sizes in research.md §8 allow byte verification). **EDIT** files change only what this
  contract states. **NEW** files are authored fresh.
- New/edited files use `except (A, B):` (parenthesized) so they stay importable on
  Python 3.13+ for tests; PEP 758 lines in untouched CORE files are left alone.
- Tests live at repo root `tests/` (not inside `custom_components/`).

## 3. `manifest.json` (NORMATIVE)

- Keep: `domain: "surepetcare"`, `name: "Sure Petcare"`, `config_flow: true`,
  `integration_type: "hub"`, `iot_class: "cloud_polling"`,
  `loggers: ["rich", "surepy"]`, `requirements: ["surepy==0.9.0"]`.
- Add: `"version": "0.1.0"` (mandatory for custom components; bump per release).
- Change: `"documentation": "https://github.com/ccxdomo/HA-surepetcare-custom"`.
- Change: `"codeowners": ["@ccxdomo", "@benleb", "@danielhiversen"]`.

## 4. Constants (added to `const.py`)

```text
SERVICE_SET_INDOOR_ONLY = "set_indoor_only"
ATTR_INDOOR_ONLY = "indoor_only"
ATTR_CONFIRM = "confirm"
ATTR_ENTITY_ID = "entity_id"
PROFILE_NORMAL_ACCESS = 2      # pet can pass both ways
PROFILE_INDOOR_ONLY = 3       # pet kept inside
INDOOR_ONLY_VERIFY_ATTEMPTS = 3
INDOOR_ONLY_VERIFY_RETRY_SECONDS = 2
```

Flap device types: reuse `surepy.enums.EntityType` `CAT_FLAP` / `PET_FLAP` — do not
hardcode product ids outside `assignments.py`.

## 5. `api.py` — SurePetcareApiClient (NEW, NORMATIVE)

A single class, **no `homeassistant` imports** (aiohttp only; the session is injected by
the coordinator). State: `email`, `password`, `session`, `timeout` (use existing
`SURE_API_TIMEOUT`), `device_id = str(uuid.uuid4())` (in-memory, per HA start),
`_token: str | None` (lazy login; NO upper-bound length heuristic — accept any
non-empty, printable ASCII token of length ≥ 300; live tokens are 492 chars, research §1).

Base URL `https://app.api.surehub.io/api`. Headers on **every** request (research §2):

```
Content-Type: application/json         (requests with a body)
Accept: application/json, text/plain, */*
Origin: https://surepetcare.io
Referer: https://surepetcare.io/
Accept-Language: en-US,en-GB;q=0.9
X-Requested-With: com.sureflap.surepetcare
User-Agent: <surepy-style UA>
Authorization: Bearer <token>          (all calls except login)
X-Device-Id: <self.device_id>          (all calls; not an auth boundary, but always sent)
```

No `OPTIONS` preflight. No `Accept-Encoding` manipulation (session default).

### 5.1 Operations

| Operation | HTTP | Path | Body | Returns |
|---|---|---|---|---|
| `async login()` | POST | `/auth/login` | `{"email_address": email, "password": password, "device_id": self.device_id}` | stores `data.token`; raises `SurePetcareApiAuthError` on non-200 |
| `async get_devices()` | GET | `/device?with[]=children&with[]=tags&with[]=control&with[]=status` | — | `response["data"]` (LIST of device objects) |
| `async set_tag_profile(device_id, tag_id, profile)` | PUT then GETs | `/device/{device_id}/tag/{tag_id}` | `{"profile": profile}` | the **verified** tag assignment dict from `/device` after the §6 rule passes |

Internal `_request()` handles: lazy login; 401 → clear token, `login()` once, retry the
failed call exactly once; network/timeout → `SurePetcareApiConnectionError`;
non-2xx (400/403/422/5xx) → raise with status code and a short redacted body excerpt
(no headers, no auth material in exceptions or logs).

Exception taxonomy (module-level, no HA imports):
`SurePetcareApiError` (base) → `SurePetcareApiAuthError`, `SurePetcareApiConnectionError`,
`SurePetcareVerificationError`.

### 5.2 Forbidden behaviors (NORMATIVE MUST NOT)

- MUST NOT log, return or expose the token, email or password anywhere (including
  exception messages and `repr`/`vars` dumps).
- MUST NOT trust or parse the PUT response body as state.
- MUST NOT silently swallow non-2xx statuses (no surepy-style `return None`).
- MUST NOT retry a failed PUT more than once (the single retry is only after a
  successful re-login).
- MUST NOT impose the surepy `len < 448` cap.

## 6. Read-after-write verification rule (BINDING — the owner's hard condition)

`set_tag_profile(device_id, tag_id, profile, *, expected_prior_version)`:

1. Record `expected_prior_version` (from the coordinator cache, §7.2).
2. PUT `{"profile": profile}`. Non-2xx → raise (no state change anywhere).
3. **Verify loop** — up to `INDOOR_ONLY_VERIFY_ATTEMPTS` times, sleeping
   `INDOOR_ONLY_VERIFY_RETRY_SECONDS` between attempts:
   a. `get_devices()` (the read proven fresh; research §7). A 401 during verification
      follows the single-re-login rule, then continues the loop.
   b. Locate the device by id and its tag by id. Missing device/tag → keep retrying
      until attempts exhausted → `SurepetcareVerificationError`.
   c. **Pass conditions**: `tag["profile"] == profile` AND
      `tag["version"] > expected_prior_version`.
      - `profile` mismatch → retry.
      - `version <= expected_prior_version` → retry (no increment = not persisted).
      - `version > expected_prior_version + 1` → PASS, but log a WARNING
        (concurrent writer detected, e.g. the mobile app).
4. All attempts exhausted → `SurepetcareVerificationError` (the caller MUST then trigger
   a coordinator refresh and MUST NOT patch any cache).
5. Return the verified tag dict (the single source for the post-write cache patch).

**Invariant V1 (MUST)**: the switch state may only ever be derived from a successful
cloud read — the regular coordinator poll, or the verification GET. **Invariant V2
(MUST NOT)**: no code path may set, patch or display state based solely on the PUT
having returned 2xx. **Invariant V3**: on any write/verification failure the displayed
state remains the last verified cloud state, and a coordinator refresh is scheduled.

## 7. Coordinator & service flow (`coordinator.py` EDIT + `services.py` EDIT)

### 7.1 Construction

`SurePetcareDataCoordinator.__init__` gains exactly: `self.api = SurePetcareApiClient(
email=entry.data[CONF_USERNAME], password=entry.data[CONF_PASSWORD],
session=async_get_clientsession(hass), timeout=SURE_API_TIMEOUT)`. No eager login.
Polling (`_async_update_data`) is NOT modified — `/me/start` via surepy already
provides pet `tag_id` + device `tags[].profile/version` (research §5.5).

### 7.2 `handle_set_indoor_only(call)` — NORMATIVE sequence

Inputs: resolved entity ids (switch platform of this domain), `indoor_only` bool,
`confirm` bool, calling `context`.

1. If `confirm is not True` → `ServiceValidationError`
   (`translation_key="confirm_required"`). No API traffic.
2. Build assignments via `assignments.build_pet_assignments(self.data)`. Resolve each
   entity_id to a pet assignment; unknown/mismatched entity →
   `ServiceValidationError("invalid_entity")`.
3. For each targeted pet, for each assigned flap: if the flap's raw
   `status.online` is not true → `HomeAssistantError` mapped to
   `"device_offline"` naming the device; **no PUT is issued for any pet** once any
   target flap is offline (fail fast, write nothing).
4. For each targeted pet (sequential): for each assigned flap (sequential):
   `tag = await self.api.set_tag_profile(device_id, tag_id,
   profile=3 if indoor_only else 2, expected_prior_version=tag["version"])`.
5. After each verified tag: patch the coordinator's cached raw device payload —
   the matching entry of `coordinator.data[device_id].raw_data()["tags"]` gets the
   verified `profile` and `version` (and `updated_at` if present). **Patch only the
   values returned by §6.5.**
6. After all targets verified and patched: `await self.async_set_updated_data(self.data)`
   (switches re-read the patched cache), then audit-log (§9.3).
7. On any exception mid-sequence: let it propagate as `HomeAssistantError` (auth →
   `"api_auth_failed"`, connection → `"api_connection_failed"`, verification →
   `"verification_failed"`); first `await self.async_request_refresh()` so the UI shows
   cloud truth alongside the error. Already-verified-and-patched targets stay patched
   (they are cloud-verified facts); the log MUST name the failed device.

### 7.3 `assignments.py` (NEW, NORMATIVE)

Pure module, **no HA or surepy imports beyond type-free dict access** (accepts a
`Mapping[int, Any]` of raw entity payloads; testable without HA). Exposes:

- `TagAssignment` dataclass: `device_id: int`, `device_name: str`, `tag: dict`
  (the raw assignment incl. `profile`, `version`).
- `PetAssignment` dataclass: `pet_id: int`, `pet_name: str`, `tag_id: int`,
  `flaps: list[TagAssignment]`.
- `build_pet_assignments(entities) -> list[PetAssignment]` — data-model.md §3 rules:
  pets (`EntityType.PET` / payload without `product_id` or with `product_id` 0) with
  non-null `tag_id`, matched against flap devices (`product_id` in {3, 6}) via
  `tags[].id`. Tag name normalization: strip whitespace from device/pet names.
- `indoor_only_state(assignment) -> bool` — True iff **all** `flaps` have
  `profile == 3`.
- `all_flaps_indoor_only(assignment) -> bool` (alias of the above, kept for attribute
  clarity), and `switch_available(assignment) -> bool` — True iff every flap's
  `status.online` is true.

## 8. Service & i18n surface

### 8.1 `services.yaml` — added block (verbatim shape; NORMATIVE)

```yaml
set_indoor_only:
  name: Set indoor only
  description: >-
    Sets the indoor-only access profile of one or more pets on their flaps.
    The cloud state is read back and verified before the switch updates.
  target:
    entity:
      integration: surepetcare
      domain: switch
  fields:
    indoor_only:
      required: true
      name: Indoor only
      description: "true keeps the pet(s) inside (indoor only); false restores normal access."
      selector:
        boolean: {}
    confirm:
      required: true
      name: Confirm
      description: "Must be true — protects against accidental flips."
      selector:
        boolean: {}
  confirmation:
    text: >-
      This changes the pet's flap access on the Sure Petcare cloud. Continue?
```

Keep the two existing core services unchanged. `icons.json`: add
`set_indoor_only: {service: "mdi:home-lock"}`.

### 8.2 `strings.json` / `translations/en.json`

- `strings.json`: core content (config flow + existing services + existing exceptions)
  verbatim, plus: `services.set_indoor_only` (name/description/field names from §8.1),
  and `exceptions`: `confirm_required`, `invalid_entity`, `device_offline`,
  `api_auth_failed`, `api_connection_failed`, `verification_failed`,
  `switch_write_protected`, `no_flap_assignment` (setup log message uses plain text).
  Message texts must state the recovery action (e.g. "Flap offline — cannot verify a
  change; refusing to write. Check the flap's power/hub connectivity.").
- `translations/en.json`: the resolved equivalent (custom components must ship it;
  core uses `[%key:...]%` references that resolve to the common strings — replace with
  the resolved literals: e.g. `invalid_auth` → "Invalid authentication",
  `cannot_connect` → "Failed to connect", `unknown` → "Unexpected error",
  `password` → "Password", `username` → "Username", `reauth` → "Re-authenticate").

### 8.3 Registration pattern (`services.py` EDIT)

Follow the seeded pattern exactly: register in `async_setup_services`, resolve the
config entry with `service.async_get_config_entry(hass, DOMAIN, None)`, build the
schema with `probatio` mirroring the existing services — `entity_id` (required,
`cv.entity_ids`-equivalent), `indoor_only` (required, boolean), `confirm` (required,
boolean). The handler validates `confirm is True` (ServiceValidationError), resolves
target entities to this platform's pet switches, and delegates to
`coordinator.handle_set_indoor_only`. The Coder must verify exact `probatio`
validator composition against the installed version; the intent (target entity ids +
two required booleans) is binding, the spelling is not.

## 9. Switch platform (`switch.py` NEW) & audit log

### 9.1 Entity contract

- One `PetIndoorOnlySwitch(SurePetcareEntity, SwitchEntity)` per `PetAssignment`
  with `len(flaps) >= 1`; pets without flap assignments get **no entity** and one setup
  INFO log naming the pet.
- `_attr_name = f"{pet_name} Indoor Only"` (pet name capitalized/stripped per the
  entity.py convention) → e.g. `switch.pinceau_indoor_only`.
- `_attr_unique_id = f"{household_id}-{pet_id}-indoor_only"`.
- Device info: attach to the **pet's** existing device (same identifiers as the
  presence binary sensor: `(DOMAIN, f"{household_id}-{pet_id}")`). MUST NOT create a
  second device.
- `_update_attr`: `is_on = all_flaps_indoor_only(...)`; icon
  `mdi:home-lock` / `mdi:home-lock-open`; extra attributes:
  `pet_id`, `pet_name`, `tag_id`,
  `devices`: `[{"device_id", "device_name", "profile", "version"}, ...]` (per assigned
  flap), `all_flaps_indoor_only` (bool), `last_write` (audit summary dict, present
  after the first verified service write: `at` ISO-8601, `user_id`, `requested`,
  `verified`: per-device `{device_id, tag_id, profile, version}`).
- `available`: coordinator last update OK **and** `switch_available(assignment)`.
- `async_turn_on` / `async_turn_off`: MUST raise `HomeAssistantError` with the
  `switch_write_protected` message (use the service instead). This is the
  protected-toggle requirement R3 — the UI toggle shows an error and never writes.
- No `assumed_state` (read-driven entity).

### 9.2 Audit logging (BINDING, requirement R5)

Every successful `set_indoor_only` call logs one INFO line:
`user=<resolved name or user_id, else "unknown">`, `user_id=<context.user_id>`,
`at=<ISO-8601 local>`, `entity_id(s)`, per pet: `pet`, `tag_id`, per device:
`device`, `device_id`, `profile old→new`, `version old→new`. Verification retries log
WARNING; failures log ERROR with the same identifiers. NEVER log token, email,
password, or HTTP headers.

## 10. Test matrix (BINDING)

**Mandatory** (pytest, no HA harness needed; `api.py` and `assignments.py` are
importable without HA):

| # | Test |
|---|---|
| T1 | Client login: success stores token; headers on every request include the §5 set + `X-Device-Id`; login body shape exact. |
| T2 | Login failure (401/timeout) → `SurePetcareApiAuthError`/`ConnectionError`; **captured logs/asserts contain no password, email or token**. |
| T3 | 492-char token accepted (no upper-bound rejection) — regression vs surepy's stale cap. |
| T4 | `get_devices` parses the LIST under `data` (multiple devices; hub with `tags: []`). |
| T5 | `set_tag_profile` happy path: PUT body exactly `{"profile": N}`; verify GET returns profile N with version prior+1 → returns verified dict. |
| T6 | Verify retry: first GET stale (old version) → retry passes (2 attempts). |
| T7 | Verify exhaustion (3 stale GETs) → `SurepetcareVerificationError`; no cache patch happens (coordinator mock asserts zero patches). |
| T8 | PUT 401 → re-login once → PUT retried once → verify. Re-login failure → auth error. |
| T9 | Verify-GET 401 → re-login once → verify continues. |
| T10 | PUT 400/422/500 → raised error naming status; no retry, no verification, no patch. |
| T11 | `assignments`: mapping from raw `/me/start` fixture (fixture payloads embedded as JSON test data): pets↔tags, flap-only scoping, felaqua ignored, multi-flap pet, `tag_id: None` pet skipped, trailing-space names stripped. |
| T12 | State rules: all-3 → on; any-2 → off; mixed → off + `all_flaps_indoor_only: false`; offline flap → unavailable + write refusal. |
| T13 | Service schema: missing/False `confirm` → `ServiceValidationError`, zero HTTP calls; unknown entity → `invalid_entity`. |
| T14 | Switch: `turn_on`/`turn_off` raise `switch_write_protected`; state/attributes populated from coordinator fixture. |
| T15 | Credential hygiene: repo-wide grep test asserting no test or source file contains the literal secrets from `.secrets/surepetcare.env` (values fetched at runtime, compared by hash). |

**Optional but recommended**: HA-harness tests (pytest-homeassistant-custom-component)
for platform setup on a fixture config entry.

**Live tests** (`tests/live/`, run manually by the Coder on the local host ONLY, never
in CI — CI has no secrets):

| # | Test |
|---|---|
| L1 | Live read: login from env; `get_devices`; assert fixture flap 1307328 exists, tag 2119787 present with profile in {2, 3}; print profile+version. |
| L2 | **Controlled write round-trip** (requires `SUREPETCARE_LIVE_WRITE=1` AND tag == `SUREPETCARE_TAG_ID_PINCEAU` == 2119787, else abort before any write): capture profile P₀/version V₀ → PUT opposite profile → verify (profile flipped, version V₀+1) → PUT back to **3** → verify → final assert profile == 3. **MUST end at verified profile 3** (spec R8). |
| L3 | Post-round-trip: re-read `/device` and print final tag assignment (proof artifact for the Reviewer). |

## 11. Credential handling (NORMATIVE, requirement R8)

- The only source is `.secrets/surepetcare.env` (600, outside the repo, gitignored).
- Tests read it via environment only; the repo holds no credential values, and no file
  (test, log, doc) may echo, print or embed them. Live outputs show ids, profiles and
  versions — never secrets.
- CI (GitHub Actions) must not have access to these secrets; live tests detect CI
  absence and skip.
- Write probes outside tag 2119787 are forbidden; the Architect ran **zero** write probes,
  and the Coder's only write is the L2 round-trip (plus any write performed by the
  component under live manual QA by the owner).

## 12. Compatibility notes

- Requires HA with Python ≥ 3.14 (PEP 758 in untouched CORE files; HA 2026.9 line
  requires 3.14.2). State this in quickstart.md.
- The custom component shadows the core integration by domain precedence
  (research §9); after install + restart, the integration info page must show
  version 0.1.0 as proof the fork is the loaded one.
- `surepy==0.9.0` remains pinned — it is the read backbone; the new client is
  additive and does not change the requirements list.