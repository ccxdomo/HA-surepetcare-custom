# Spec 041 — Data model

- **Date**: 2026-09-26
- **Sources**: live probes (research.md §1), surepy 0.9.0 source, interview ground truth.
- All ids in examples are the household's real fixtures (household 100241).

## 1. Object graph

```
Household (id 100241)
├── Device  Hub            (product_id 1, id 200002, tags: [])
├── Device  Cat Flap       (product_id 6, id 200001 "la chatière")
│     ├── TagAssignment {tag 300001, index 1, profile 2, version 3}
│     ├── TagAssignment {tag 300002, index 2, profile 2, version 9}
│     └── TagAssignment {tag 300003, index 3, profile 2, version 13}
├── Device  Felaqua        (product_id 8, id 200003)
│     ├── TagAssignment {tag 300001, index 1, profile 2, version 1}
│     ├── TagAssignment {tag 300002, index 2, profile 2, version 1}
│     └── TagAssignment {tag 300003, index 3, profile 2, version 1}
├── Pet  Moca     (id 400001, tag_id 300001)
├── Pet  Tibounet (id 400002, tag_id 300002)
└── Pet  Pinceau  (id 400003, tag_id 300003)
```

Key relation: **pet → tag** (`pets[].tag_id`, the physical microchip tag of the pet) and
**tag → device** (`devices[].tags[]`, one *assignment* per (device, tag) pair). The
indoor-only setting lives **only** on the assignment: `devices[].tags[].profile`.

## 2. Endpoints & payload shapes (all verified live)

### 2.1 `POST /api/auth/login`

Request body: `{"email_address": "<email>", "password": "<password>", "device_id": "<uuid>"}`
Response `200`: `{"data": {"token": "<492 chars>", "user": {...}}}`
(never log any of these; the `user` object is irrelevant to the component and must be
discarded).

### 2.2 `GET /api/me/start` — surepy's poll endpoint (every 3 min)

`data` keys: `devices`, `pets`, `households`, `photos`, `segments`, `tags`, `user`.

- `data.devices[]` — device objects:

| Field | Type | Notes / observed values (flap 200001) |
|---|---|---|
| `id` | int | device id (fixture flap: 200001) |
| `product_id` | int | 1 hub · 3 pet door connect · 4 feeder · 6 cat flap connect · 8 felaqua (surepy `EntityType`) |
| `name` | str | e.g. `"la chatière "` (may carry a trailing space — entity naming must use `.strip()`/core's capitalize convention) |
| `household_id` | int | 100241 |
| `parent_device_id` | int | hub id for flaps |
| `serial_number`, `mac_address`, `index`, `pairing_at`, `last_new_event_at`, `updated_at`, `version` | misc | registry/diagnostic |
| `status` | obj | `online` (bool) · `battery` (float, total for 4 batteries — e.g. 5.825) · `locking.mode` (0 unlocked … 3 locked all) · `signal.device_rssi` · `learn_mode` · `version.device.{hardware, firmware}` |
| `control` | obj | flap: `locking`, `curfew[] {enabled, lock_time, unlock_time}`, `fail_safe`, `fast_polling` (observed: curfew 18:00–06:00 enabled) |
| `tags` | list | **per-(device,tag) assignments** (below) — present on `/me/start` and `/device`, even bare |

- `devices[].tags[]` — tag assignment:

| Field | Type | Notes |
|---|---|---|
| `id` | int | tag id (e.g. 300003) |
| `device_id` | int | parent device id (mirrors the enclosing device) |
| `index` | int | slot index on the device (1–3 observed) |
| `profile` | int | **the indoor-only setting**: 2 = normal access, 3 = indoor only (GIVEN, interview differential) |
| `version` | int | **increments on every accepted profile change** — persistence proof (GIVEN, interview round-trip) |
| `created_at`, `updated_at` | ISO8601 | `updated_at` moves with writes (observed 2026-09-26T07:09:15Z after this morning's round-trip) |

- `data.pets[]` — pet objects:

| Field | Type | Notes (Pinceau 400003) |
|---|---|---|
| `id` | int | pet id |
| `name` | str | `"Pinceau"` |
| `household_id` | int | 100241 |
| `tag_id` | int | **pet → tag link** (300003) |
| `tag` | obj | tag object (below), `id == tag_id` |
| `status.activity` | obj | `{pet_id, tag_id, device_id, where, since}` — last movement; `where`: 1 inside / 2 outside |
| `status.drinking` | obj | `{tag_id, device_id, change[], at}` — Felaqua drinks |
| `position` | obj | `{pet_id, tag_id, device_id, where, since}` — last flap position |
| `gender`, `date_of_birth`, `weight`, `breed_id`, `food_type_id`, `species_id`, `spayed`, `photo_id`, `photo`, `conditions`, `version`, `created_at`, `updated_at` | misc | core entities use some of these; irrelevant to this feature |

- `data.tags[]` — **tag objects** (not assignments): `{id, tag <serial string>, supported_product_ids: [3,4,6,8,10,32], incompatible_product_ids, version: 0, created_at}`. No `profile`, no `device_id` — useless for indoor-only state, listed for completeness.
- `data.households[]` — household metadata incl. `timezone` (used by surepy for curfew logic); `users` — **must never be logged**.

### 2.3 `GET /api/device?with[]=children&with[]=tags&with[]=control&with[]=status`

Same device objects as `/me/start` `devices[]` (verified field-for-field equal for the
flap, including tags). This endpoint is the **read-after-write verification read**
(proven to reflect an accepted write immediately). Bare `GET /api/device` also returns
tags; keep the `with[]` params for parity with surepy's resource.

### 2.4 `GET /api/pet?with[]=photo&with[]=breed&with[]=conditions&with[]=tag&with[]=food_type&with[]=species&with[]=position&with[]=status`

Same pet objects as `/me/start` `pets[]` (bare `/pet` also carries `tag_id`). Not needed
at runtime (mapping already available from the coordinator poll); listed because it
proves the mapping independently of `/me/start`.

### 2.5 `PUT /api/device/{device_id}/tag/{tag_id}`

Request body: `{"profile": 2 | 3}` → accepted (GIVEN, interview round-trip). The
response body is **not trusted**; acceptance is proven only by the follow-up
`GET /device` (profile matches + `version` incremented).

### 2.6 Not needed / rejected endpoints

- `GET /api/tag`, `GET /api/tag/{id}` — tag objects only, no profile.
- `/api/report/household/{id}`, `/api/timeline/...` — surepy internals for feeding/
  drinking enrichment; untouched.

## 3. Mapping & state derivation (normative for the Coder)

Inputs: the coordinator's `dict[int, SurepyEntity]` (from `/me/start` via surepy).

1. **Pets**: entities with `type == EntityType.PET` having a non-null `tag_id`
   (`SurepyPet.tag_id`).
2. **Flaps**: entities with `type in (EntityType.CAT_FLAP, EntityType.PET_FLAP)`
   (product_id 6 / 3).
3. **Assignment**: pet P with `tag_id` T is assigned to flap F iff
   `F.raw_data()["tags"]` contains `{"id": T}`. Feeders/Felaqua/Hub are ignored (research §6).
4. **Switch state**: for pet P with flap assignments A = {(F₁,T), …, (Fₙ,T)}:
   - `is_on` (indoor only active) ⟺ **all** assignments have `profile == 3`.
   - `off` (normal access) otherwise — including the mixed case (any profile-2 flap lets
     the pet out; attributes expose per-device profiles so mixed states are visible).
   - Switch exists only when n ≥ 1. n = 0 (tag on no flap, or no tag) → no entity, one
     INFO log at platform setup.
5. **Availability**: last coordinator update succeeded **and** every assigned flap's
   `status.online == true`. An offline flap has stale cloud state and refuses writes.

## 4. Fixtures (for tests and examples)

| Entity | Id | Notes |
|---|---|---|
| Household | 100241 | single household |
| Hub "Hub Chatière" | 200002 | product 1, parent of the flap |
| Cat flap "la chatière" | 200001 | product 6 — **the only write target** |
| Felaqua | 200003 | product 8 — ignored for indoor-only |
| Pet Moca | 400001 | tag 300001 |
| Pet Tibounet | 400002 | tag 300002 |
| Pet Pinceau | 400003 | tag **300003** — the only tag allowed in live write tests |
| Tag assignments on flap | 300001/300002/300003 | profile 2 at probe time, versions 3/9/13 |

**Live-state note (probe time 2026-09-26 ≈ 09:30 CEST):** Pinceau's tag rests at
**profile 2 (normal access), version 13** — the interview's expectation of a resting
profile 3 is not the current cloud state (research.md §1). The Coder's live test must
still **end at verified profile 3** (contracts §10).

## 5. Switch state model (HA surface)

| Concept | Value |
|---|---|
| Entity | `switch.<pet>_indoor_only` (e.g. `switch.pinceau_indoor_only`) |
| `unique_id` | `{household_id}-{pet_id}-indoor_only` (e.g. `100241-400003-indoor_only`) |
| Device | the pet's HA device, identifiers `("surepetcare", "{household_id}-{pet_id}")` — same device as the presence binary sensor |
| State `on` | all assigned flaps at profile 3 → "indoor only" |
| State `off` | at least one assigned flap at profile 2 → normal access |
| Attributes | `pet_id`, `pet_name`, `tag_id`, `devices[]` (per flap: `device_id`, `device_name`, `profile`, `version`), `all_flaps_indoor_only` (bool), `last_write` (audit info of the last verified write, or omitted) |
| Icon | `mdi:home-lock` when on · `mdi:home-lock-open` when off |
| Writes | **none via the entity** — `turn_on`/`turn_off` raise a protected-use error; only the service can change the cloud state |

See contracts/ha-component.md for the binding versions of these rules.