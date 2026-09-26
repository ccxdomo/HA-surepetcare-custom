# Spec 041 — Per-pet "Indoor Only" switch for Sure Petcare (Home Assistant custom component)

- **Status**: Approved for implementation (interview decisions are requirements, not options)
- **Date**: 2026-09-26
- **Author**: Architect (spec phase)
- **Repo**: `ccxdomo/HA-surepetcare-custom` (branch `main`)
- **Related**: research.md (evidence) · contracts/ha-component.md (BINDING) · data-model.md · plan.md · quickstart.md

## 1. Summary

This project delivers a Home Assistant **custom component** that is a fork of the HA core
`surepetcare` integration, extended with **one "Indoor Only" switch per pet**. The switch
shows, for each pet, whether the pet is currently restricted to the house
("indoor only", Sure Petcare tag profile `3`) or has normal access (profile `2`).

The switch is **read-driven**: its state always comes from the Sure Petcare cloud. Changing
it is only possible through a **protected write service** (`surepetcare.set_indoor_only`)
that requires an explicit `confirm: true` field, performs the change on the cloud, then
**reads the cloud state back and verifies it** (including the tag `version` increment)
before the switch state is allowed to move. There is **no optimistic state, ever**.

The component keeps the domain `surepetcare` so that dropping the folder into
`custom_components/` **replaces the core integration** in place: existing config entries,
devices and entities keep working, and the new switches appear next to them.

## 2. Background

- The household runs Sure Petcare hardware (hub + cat flap + Felaqua) with three pets
  (Moca, Tibounet, Pinceau). One of them (Pinceau) is periodically kept indoors using the
  app's per-pet "indoor only" setting.
- The HA core `surepetcare` integration (which polls via the `surepy` 0.9.0 library)
  exposes connectivity, battery, presence and lock entities — but has **no indoor-only
  entity, service or sensor**.
- The Sure Petcare API stores the indoor-only setting as the `profile` field of a
  **(device, tag) pair**: `PUT /api/device/{device_id}/tag/{tag_id}` with
  `{"profile": 2|3}`. Tags are per-pet microchips; the pet↔tag association is exposed by
  the API itself (see research.md §3 — this was unproven at interview time and is now
  **pinned with live evidence**).

## 3. Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | **One switch per pet** named "<Pet> Indoor Only". NOT per device — a per-device toggle "does not make any sense" (owner, explicit). | Interview |
| R2 | Switch state is **read from the cloud** and follows the coordinator poll (≈ every 3 min). No optimistic or locally computed state. | Interview |
| R3 | The switch **cannot be changed by toggling it** (UI toggle raises a clear error). The only write path is the protected service. | Interview |
| R4 | Protected service `surepetcare.set_indoor_only`: targets one or more pet switches, takes `indoor_only` (bool) and **`confirm` (must be true)**; UI-level confirmation dialog as well. | Interview |
| R5 | Every service call is **audit-logged**: who (user), when, what (pet, device(s), tag, profiles and versions before/after). | Interview |
| R6 | **Read-after-write verification is mandatory**: after the PUT, the cloud state is read back and verified (profile matches AND tag `version` incremented) before any state change is shown. If verification fails, the switch keeps the last cloud-verified state. | Owner's hard condition |
| R7 | Drop-in custom component: same domain (`surepetcare`), custom component overrides the core integration; existing entities are **not duplicated** (identical `unique_id`s to core). | Interview |
| R8 | Live write tests use only Pinceau's tag (300003) and **must end with a verified return to profile 3**. Credentials are never read from the repo, printed, logged or committed. | Interview (env contract) |

## 4. Non-goals

- No per-device toggles (explicitly rejected by the owner).
- No optimistic UI; no "assume write worked" shortcuts.
- No changes to the existing entities (binary sensors, sensors, locks) beyond what is
  needed to complete the fork (see plan.md Phase 0 — the seeded component is a partial
  subset of core and must be completed to even import).
- No re-implementation of the read backbone: `surepy` 0.9.0 keeps feeding the existing
  coordinator (decision in research.md §5).
- No config UI for pet↔tag mapping (the API provides the mapping; nothing to configure).
- No HACS listing, no PyPI package, no publish of a `surepy` fork.
- No curfew management, no multi-household support beyond correct behavior.

## 5. Acceptance criteria

1. With the folder dropped into `custom_components/` and HA restarted, the integration
   loads as the **custom** one (integration info shows manifest version; startup log shows
   the custom-integration notice) and all pre-existing entities keep their entity_ids and
   states.
2. One new switch per pet that has a tag assigned to at least one flap device. Pets whose
   tag is not on any flap get no switch (logged at setup).
3. Switch state equals the cloud truth within one coordinator poll after any external
   change (e.g. made from the official app).
4. Toggling the switch in the UI produces an error and **does not** change cloud state.
5. Calling `surepetcare.set_indoor_only` without `confirm: true` is rejected
   (`ServiceValidationError`) and produces no API write.
6. A successful service call flips the cloud profile, and the switch shows the new state
   **only after** the read-back verification (profile match + `version` increment) passed;
   the log line records user, pet, device, tag, old→new profile and old→new version.
7. If the API refuses the write, or verification cannot confirm it after the retry budget,
   the call raises, the log explains it, and the switch re-syncs from the next cloud read.
8. A flap that is offline refuses writes (error, no API call issued).
9. Live round-trip test on tag 300003 ends with profile 3 verified (version incremented
   from the starting value), and no credentials appear anywhere in logs, output or the
   repository.

## 6. Constraints

- HA target: current HA (2026.9 line; `requires-python >= 3.14.2`). The fork contains
  PEP 758 `except` syntax in untouched core files (valid on Python ≥ 3.14 only).
- Custom component manifest **must** carry a `version` key (core manifests do not) — see
  contracts §3.
- The seeded repo only contains 7 of the 13 files of the core component; the fork must be
  completed with the missing verbatim core files before any feature work (plan.md Phase 0).
- Architect ran **read-only** probes only. The profile semantics (2 = normal access,
  3 = indoor only) and the write shape are taken from the interview's controlled
  round-trip; the Coder's live test re-proves them.

## 7. Key decisions (summary — full evidence in research.md)

| # | Decision | Evidence anchor |
|---|---|---|
| D1 | Keep `surepy` 0.9.0 for the read backbone (existing coordinator, `/me/start`); add a small self-contained aiohttp client (`api.py`) inside the component for login + write + read-after-write verification. Do **not** extend or fork surepy. | research.md §5 — surepy has no profile write, swallows HTTP errors, retries PUTs as GETs on 401, and rejects current 492-char tokens by its stale length cap. `/me/start` (surepy's poll) already carries everything the switch needs to read. |
| D2 | Pet→tag association = `pets[].tag_id` (top level, present on `/me/start` and `/pet`), cross-validated by `pet.tag.id`, `pet.status.activity.tag_id`, and `pet.position.tag_id`. | research.md §3 — live probes, three independent sources agree. |
| D3 | Switch state derives from **flap devices only** (product_id 3, 6) carrying the pet's tag; feeders/Felaqua are ignored for state and writes. | research.md §6 — Felaqua tag `version` = 1 (never written) while flap tags show version 3/9/13: the app writes flaps only. |
| D4 | Post-write state sync: patch the verified (device, tag) values into the coordinator's cached raw payload, push via `async_set_updated_data`; the next poll reconciles. | research.md §7 — `/device` read-back proven fresh; `/me/start` freshness unverified, hence verify must use `/device`. |
| D5 | In-memory session for the write client (uuid4 device-id + token, lazy login, one re-login on 401). No persistence. | research.md §4 — sessions are additive, tokens are not fenced, logins are cheap. |

## 8. Deliverable surface (what the owner gets)

- Entities: `switch.<pet>_indoor_only` (e.g. `switch.pinceau_indoor_only`) — one per pet
  with flap access. State `on` = indoor only in force on all the pet's flaps.
- Service: `surepetcare.set_indoor_only` (target: switch entity; fields: `indoor_only`
  bool, `confirm` bool) with a UI confirmation dialog and full audit logging.
- All existing core surepetcare entities, unchanged.

## 9. Risks

| Risk | Mitigation |
|---|---|
| The core integration evolves upstream; the fork must be rebased manually | Documented fork base pin (plan.md Phase 0); keep diff minimal (feature isolated in new files + small extensions). |
| `/me/start` could lag behind a write (freshness unproven) | Verification always reads `/device` (proven fresh). The switch never depends on `/me/start` freshness for write confirmation. |
| The API changes (token shape, headers) | Small, isolated client; all live facts pinned in research.md for fast re-probing. |
| Concurrent writer (the app) changes profile mid-round-trip | Version delta check detects it (warn + strict profile match); next poll self-heals. |
| Pet with tag on multiple flaps in mixed states | Defined semantics: `on` only if **all** flaps are profile 3; write targets all flaps carrying the tag. (Owner has one flap; rule is documented.) |
| Live test leaves wrong resting state | Hard rule: test sequence ends at verified profile 3 on tag 300003 (contracts §10). |