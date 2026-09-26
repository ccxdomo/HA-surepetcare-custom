# Spec 041 — Implementation plan (for the Coder)

- **Date**: 2026-09-26
- **Binding reference**: contracts/ha-component.md (names, shapes, sequences, test matrix).
  This file sequences the work only.
- **Fork base pin**: home-assistant/core `dev` @ 2026-09-26 (research.md §8).

## Phase 0 — Complete the fork baseline (make the seed importable)

The seeded component is a **partial subset** of core: it is missing `entity.py`
(imported by `sensor.py`/`binary_sensor.py`), `lock.py` (platform forwarded by
`__init__.py`), `config_flow.py` (manifest declares `config_flow: true`), and the
i18n/service-description files. As seeded, the component cannot even import.

1. Fetch the missing CORE files verbatim from core dev @ 2026-09-26:
   `config_flow.py`, `entity.py`, `lock.py`, `services.yaml`, `strings.json`,
   `icons.json`. Verify byte sizes against research.md §8.
2. Add `translations/en.json` (resolved strings; contracts §8.2).
3. Edit `manifest.json` per contracts §3 (`version: 0.1.0`, documentation, codeowners).
4. **Verification gate G0**: with the folder in a HA 2026.9 dev/custom environment, the
   integration loads, the existing entities come up, and the integration info shows
   version 0.1.0. No feature code yet.
5. Do NOT touch the PEP 758 `except KeyError, TypeError:` lines in CORE files.

## Phase 1 — Pure feature core (HA-free, fully unit-testable)

1. `assignments.py` (contracts §7.3): dataclasses + `build_pet_assignments` +
   state/availability helpers.
2. `api.py` (contracts §5): `SurePetcareApiClient` — login, `get_devices`,
   `set_tag_profile` with the §6 verification loop; exception taxonomy; in-memory
   session; single-relogin rule.
3. Unit tests T1–T4, T10–T12 (contracts §10) with embedded JSON fixtures derived from
   the real payload shapes (data-model.md §2; use the sanitized fixture values —
   household 100241, flap 200001, tags 300001/300002/300003).
4. **Gate G1**: all mandatory unit tests green on Python 3.13+ (parenthesized excepts
   keep the new modules importable there); no HA import needed for this phase.

## Phase 2 — HA integration layer

1. `coordinator.py` EDIT (contracts §7.1–§7.2): `self.api` construction, no changes to
   `_async_update_data`; `handle_set_indoor_only` NORMATIVE sequence incl. offline
   fail-fast, sequential verified writes, cache patch, `async_set_updated_data`, and
   refresh-on-error.
2. `switch.py` NEW (contracts §9.1): `PetIndoorOnlySwitch` platform.
3. `services.py` EDIT (contracts §8.3): register `set_indoor_only`; `const.py` EDIT
   (contracts §4); `__init__.py` EDIT: add `Platform.SWITCH`.
4. i18n: `services.yaml`, `strings.json`, `translations/en.json`, `icons.json`
   (contracts §8.1–§8.2).
5. Unit tests T5–T9, T13–T15 (mocked HTTP via aioresponses or equivalent; coordinator
   doubles for patch assertions).
6. **Gate G2**: test matrix T1–T15 green; a fixture-driven HA-harness test (optional)
   proves platform setup and protected toggles.

## Phase 3 — Live verification (local host only, env-gated)

1. `tests/live/` scripts (contracts §10 L1–L3). They read `.secrets/surepetcare.env`
   via environment only; L2 aborts unless `SUREPETCARE_LIVE_WRITE=1` and the tag equals
   `SUREPETCARE_TAG_ID_PINCEAU` (300003).
2. Run L1 (read-only). Record profile/version observed (expected now: profile 2,
   version 13 — research.md §1).
3. Run L2 **once**: flip → verify (version +1) → back to 3 → verify. **The test must end
   at verified profile 3** (spec R8). Save the printed before/after evidence for the
   Reviewer.
4. **Gate G3**: L2/L3 outputs show the version increment as persistence proof and the
   final state profile 3; no secrets appear in any output.

## Phase 4 — Handoff to Reviewer

Deliver: component folder + tests + live evidence + this spec set. Reviewer checklist
(acceptance = spec.md §5, all items): no optimistic state anywhere (grep for
`_attr_is_on` writes outside verified paths); V1/V2/V3 invariants hold (contracts §6);
switch toggle raises; service refuses `confirm != true`; audit log fields complete;
CORE files byte-identical to core pin; manifest versioned; unique_ids match core
(no duplicate entities after swap); live test ended at profile 3.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Fetching CORE files from a drifted upstream | Byte-size check against research.md §8; diff against the seeded 7 files must be empty |
| probatio API spelling differs from the schema intent | contracts §8.3: intent binding, spelling follows installed version; ask Architect if unclear |
| `/me/start` lag vs verified patch | By design (contracts §6, research §7): display uses verified `/device` values; poll reconciles |
| Live L2 fails mid-round-trip leaving wrong profile | L2 must always attempt the return-to-3 leg even if verification of the first leg failed mid-flight; abort-with-error before any PUT if tag ≠ 300003 |
| Entity duplication scare after swap | unique_ids are core-identical (research §8); quickstart explains the two version checks |

## Out of scope (do not build)

Per-device toggles; optimistic UI; surepy changes; HACS; multi-household UI;
curfew management; README beyond a short pointer to specs/041-indoor-only-switch/quickstart.md
(optional, English only).