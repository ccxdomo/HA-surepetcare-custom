# Spec 041 — Implementation evidence (Coder run, 2026-09-26)

- **Repo**: `HA-surepetcare-custom` (branch `main`, nothing committed — the orchestrator commits)
- **Binding contract**: `contracts/ha-component.md` · plan.md phases 0-4
- **QA host**: this gateway (Raspberry Pi 5, aarch64, Linux 6.18). Local throwaway HA only;
  the owner's production HA and network were never touched.
- **Credentials**: read from `.secrets/surepetcare.env` (outside the repo, mode 600) by scripts
  only; never printed, echoed, logged or stored in the repo. Outputs below contain ids,
  profiles and versions only.

## 0. Environment & exact commands

```bash
# Python 3.14 (HA 2026.9 requires >= 3.14.2; the host python is 3.13.5)
~/.local/bin/uv python install 3.14
~/.local/bin/uv venv /home/emc/ha041/venv --python 3.14
/home/emc/.local/bin/uv pip install --python /home/emc/ha041/venv/bin/python \
    "homeassistant==2026.9.3" "surepy==0.9.0" pytest pytest-asyncio
# HA-free test venv (proves the standalone modules import without HA)
python3 -m venv /home/emc/ha041/testvenv313
/home/emc/ha041/testvenv313/bin/pip install aiohttp pytest pytest-asyncio
# Local throwaway HA (config OUTSIDE the repo; deleted after QA)
cp -r custom_components/surepetcare /home/emc/ha041/config/custom_components/
/home/emc/ha041/venv/bin/python -m homeassistant -c /home/emc/ha041/config   # port 8124
# Unit tests (both venvs)
/home/emc/ha041/venv/bin/python -m pytest tests/ -q          # HA venv, Python 3.14.5
/home/emc/ha041/testvenv313/bin/python -m pytest tests/ -q   # HA-free subset, Python 3.13.5
# Live probes (read-only unless gated)
/home/emc/ha041/venv/bin/python tests/live/l1_read.py
/home/emc/ha041/venv/bin/python tests/live/l2_round_trip.py        # aborts without the gate
/home/emc/ha041/venv/bin/python tests/live/l3_post_read.py
# QA driver (onboard → config flow → verify → refusal → roundtrip → finish)
/home/emc/ha041/venv/bin/python /home/emc/ha041/qa/driver.py <phase>
```

**Unit test counts**: HA venv **60 passed** (1 unrelated deprecation warning);
HA-free 3.13 venv **37 passed, 2 skipped** (the two HA-gated modules
`test_coordinator_service.py`, `test_switch.py` skip without `homeassistant` —
proving api.py/assignments.py import and pass without HA, gate G1).
Test matrix coverage: T1-T15 all implemented and green.

## 1. Phase 0 — fork completion (gate G0)

Fetch (verbatim from core dev @ 2026-09-26):

```bash
BASE=https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/surepetcare
for f in __init__.py binary_sensor.py config_flow.py const.py coordinator.py \
         entity.py icons.json lock.py manifest.json sensor.py services.py \
         services.yaml strings.json; do curl -fsSL "$BASE/$f" -o "/tmp/041-core/$f"; done
```

Byte sizes — all 13 match research.md §8 exactly:
`binary_sensor.py 5035 · config_flow.py 3886 · const.py 528 · coordinator.py 3477 ·
entity.py 1854 · icons.json 142 · __init__.py 1825 · lock.py 3221 · manifest.json 335 ·
sensor.py 6154 · services.py 3026 · services.yaml 578 · strings.json 1825` (total 31886).

Seeded 7 files **byte-identical** to core dev (diff): `OK __init__.py · binary_sensor.py ·
const.py · coordinator.py · manifest.json · sensor.py · services.py`.
The 6 missing CORE files were copied in verbatim (sizes verified).

**Import gate** (HA venv, Python 3.14.5): all 12 modules import cleanly
(`custom_components.surepetcare.{__init__,api,assignments,binary_sensor,config_flow,const,coordinator,entity,lock,sensor,services,switch}`),
manifest.json/strings.json/icons.json/translations/en.json valid JSON,
services.yaml valid YAML (`set_indoor_only, set_lock_state, set_pet_location`),
manifest: `surepetcare 0.1.0 https://github.com/ccxdomo/HA-surepetcare-custom
['@ccxdomo', '@benleb', '@danielhiversen']`.

## 2. Local HA — loads, config flow, entities (gate G0 full)

Throwaway HA 2026.9.3 on port 8124. Startup log:

```
WARNING (SyncWorker_0) [homeassistant.loader] We found a custom integration surepetcare
which has not been tested by Home Assistant. ...
INFO [homeassistant.setup] Setting up surepetcare
INFO [homeassistant.setup] Setup of domain surepetcare took 0.00 seconds
```

Zero `Setup failed`/`ImportError` lines for surepetcare across all runs.

**Config flow** (REST, with the test credentials; sanitized output):

```
flow created: step=user flow_id=01M3EBGV41SJ08MWTSSW8ERKZZ
config flow OK: create_entry title='Sure Petcare' domain=surepetcare
                entry_id=01M3EBHEDKGTYK7Z6AEFR2AA07
```

**Manifest proof (the custom component is the loaded one)** — WebSocket `manifest/get`:

```
manifest/get: domain=surepetcare version=0.1.0
  documentation=https://github.com/ccxdomo/HA-surepetcare-custom
  codeowners=['@ccxdomo', '@benleb', '@danielhiversen']
```

**One switch per pet (3 pets)** with states read from the cloud
(captured after the final write; states match the cloud exactly):

```
switch.moca_indoor_only:    state=off pet_id=584007 tag_id=1492589 [device=1307328 profile=2 version=3]  all_flaps_indoor_only=False
switch.pinceau_indoor_only: state=on  pet_id=701753 tag_id=2119787 [device=1307328 profile=3 version=16] all_flaps_indoor_only=True
switch.tibounet_indoor_only:state=off pet_id=584008 tag_id=1492590 [device=1307328 profile=2 version=9]  all_flaps_indoor_only=False
```

**Unique_id stability** (entity registry; core entities not duplicated —
identical unique_id convention as core, new switches collision-free):

```
switch.pinceau_indoor_only  -> 267941-701753-indoor_only
switch.moca_indoor_only     -> 267941-584007-indoor_only
switch.tibounet_indoor_only -> 267941-584008-indoor_only
```

Full surepetcare entity registry (21 entities, all core platforms intact):
6 binary sensors (incl. hub, connectivity, pet presence), 3 locks,
9 sensors (batteries, Felaqua, 6 `*_last_seen_*`), 3 switches. The same
entity_ids/unique_ids persisted across every restart (no duplicates).

## 3. Switch refusal + confirm gate (write protection proof)

Via WebSocket (`call_service`) — the channel the HA UI uses. Note: in HA
2026.9.3 the **REST** API maps service `HomeAssistantError`s to a generic
HTTP 500 (only `vol.Invalid`/`ServiceNotFound` map to 400), so the intended
messages are proven on the WS channel (the UI shows exactly these):

```
direct toggle ON via WS:
  {"error": {"code": "home_assistant_error",
             "message": "The indoor-only switch is write-protected by design and cannot be
                         toggled directly. Use the surepetcare.set_indoor_only service with
                         confirm: true instead",
             "translation_domain": "surepetcare",
             "translation_key": "switch_write_protected"}, "success": false}
direct toggle OFF via WS: same error.

confirm=false call via WS:
  {"error": {"code": "service_validation_error",
             "message": "Validation error: The confirm field must be true to change indoor-only
                         access. Call surepetcare.set_indoor_only again with confirm: true",
             "translation_key": "confirm_required"}, "success": false}

cloud state before/after refused call: (2, 13) / (2, 13)   <- zero writes
```

HA log lines (same messages, from the WebSocket error logger):

```
Error during service call to switch.turn_on: The indoor-only switch is write-protected
  by design and cannot be toggled directly. Use the surepetcare.set_indoor_only service
  with confirm: true instead
The confirm field must be true to change indoor-only access. Call
  surepetcare.set_indoor_only again with confirm: true
```

## 4. The write round-trip (tag 2119787 — Pinceau — ends at verified profile 3)

Write ledger (every state-changing write on tag 2119787; no other tag ever written):

| # | Time (CEST) | Write | Result | Cloud state after |
|---|---|---|---|---|
| 1 | 09:59:22 | establishing 2→3 (service call, attempt 1) | PUT accepted; verification budget (3×2 s, then-contract values) expired ~5 s before the write became visible → call raised `verification_failed`, **the write landed anyway** | profile 3, version 14 (updated_at 09:59:33) |
| 2 | 10:01:02 | diagnostic PUT profile 3 (raw response capture) | no-op (already at 3): version stayed 14, updated_at unchanged | profile 3, version 14 |
| 3 | 10:07:12 | outbound leg 3→2 (service call) | write verified + cache patched; call then crashed on a coordinator bug (see §6) → HTTP 500, audit INFO line skipped | profile 2, version 15 (updated_at 10:07:08) |
| 4 | 10:09:16 | return leg 2→3 (service call) | **verified, HTTP 200, full audit** | profile 3, version 16 (updated_at 10:09:24) |

**Pre-state** (captured 09:57-10:06, multiple independent sources):
HA switch `state=on [device=1307328 profile=3 version=14]`; cloud read:
`profile=3 version=14 updated_at=2026-09-26T07:59:33Z` (N = 14).

**After-write-2** (outbound leg, profile 2 = normal access):
- Independent cloud reads after the write: `profile=2 version=15
  updated_at=2026-09-26T08:07:08Z` (L1 script).
- HA state after restart (coordinator poll — cloud truth): `switch.pinceau_indoor_only:
  state=off [device=1307328 profile=2 version=15]`.
- The component **verified** this write before the crash (execution reached step 6 —
  past `set_tag_profile` and `_patch_cached_tag`): the TypeError traceback in the log
  (see §6) proves the verified path ran. Profile moved 3→2, version 14→15 (N+1).

**After-write-3** (return leg, profile 3 = indoor only — final resting state):

```
service call (indoor_only=True -> profile 3): HTTP 200 body=[]
HA after-write-3: state=on pet=Pinceau [device=1307328 profile=3 version=16]
  last_write={"at": "2026-09-26T10:09:16.974314+02:00", "requested": true,
              "user_id": "4a0c77ff06fe4c4aa3501a025458f845",
              "verified": [{"device_id": 1307328, "profile": 3,
                            "tag_id": 2119787, "version": 16}]}
cloud after-write-3: profile=3 version=16
```

**HA audit log line** (contract §9.2 — one INFO line, all fields; log line 261):

```
2026-09-26 10:09:27.940 INFO (MainThread) [custom_components.surepetcare.coordinator]
indoor-only write verified | user=QA041 | user_id=4a0c77ff06fe4c4aa3501a025458f845 |
at=2026-09-26T10:09:16.974314+02:00 | entity_id(s)=switch.pinceau_indoor_only |
pet=Pinceau tag_id=2119787 device=la chatière (1307328) | profile 2->3 | version 15->16
```

**Failure-path evidence** (attempt 1, run 1 log; the component refused to report
success when the cloud did not confirm — contract V3, acceptance #7; the log
rotation kept only one backup, this line is preserved from the captured run):

```
2026-09-26 09:59:28.212 ERROR (MainThread) [custom_components.surepetcare.coordinator]
indoor-only write FAILED | user=QA041 | user_id=4a0c77ff06fe4c4aa3501a025458f845 |
at=2026-09-26T09:59:21.560070+02:00 | entity_id(s)=switch.pinceau_indoor_only |
pet=Pinceau tag_id=2119787 device=la chatière (1307328) |
reason=verification failed: Could not verify the indoor-only change for tag 2119787 on
device 1307328 after 3 attempts: expected profile 3 with version greater than 13;
last observed profile=2 version=13
```

The switch kept showing the last cloud-verified state and resynced on the next poll.

## 5. Live scripts (tests/live/, run on the local host only)

```
L1 OK | device=1307328 name='la chatière' online=True tag=2119787
       profile=3 version=16 updated_at=2026-09-26T08:09:24+00:00

L3 final | device=1307328 name='la chatière' online=True tag=2119787
          profile=3 version=16 updated_at=2026-09-26T08:09:24+00:00
L3 OK | resting state verified at profile 3

L2 gate demo (SUREPETCARE_LIVE_WRITE unset):
L2 ABORT: SUREPETCARE_LIVE_WRITE != 1 — refusing to run (no changes made)   (exit code 1)
```

L1 asserts the flap exists, the tag is present with profile in {2, 3} and prints
profile+version; L3 re-reads `/device` after the round-trip and asserts profile 3
(Reviewer proof artifact); L2 aborts before any network call unless
`SUREPETCARE_LIVE_WRITE=1` **and** the configured tag is 2119787 (spec R8).
The L2 write path itself (api.set_tag_profile) was exercised live through the
protected service (§4) rather than by running L2 — see deviation D3.

## 6. Bugs found and fixed during live QA (with live evidence)

1. **Verification budget too tight** (contract §4 pinned 3 attempts × 2 s on
   research §7's "immediate reflection" assumption). Live evidence: attempt 1's
   PUT (09:59:22) was accepted but became visible in `/device` only at 09:59:33
   (~10 s propagation); the 6 s budget expired first and the component correctly
   raised `verification_failed` on a write that landed. Fixed to **15 attempts ×
   5 s (~70 s window)** in const.py + api.py with the evidence documented in the
   code comment; unit tests updated to the module constant. The fixed budget
   verified both subsequent writes on the first-attempt-4 window (~10-15 s).
2. **`await async_set_updated_data(...)`** (contract §7.2 step 6 says "await").
   In HA 2026.9 `async_set_updated_data` is a `@callback` (sync); the `await`
   crashed the service call with `TypeError: 'NoneType' object can't be awaited`
   AFTER the write was verified and the cache patched (log.1: the traceback
   follows `set_tag_profile` → `_patch_cached_tag` → line 360). Fixed to a plain
   call; the unit-test double was corrected from an async stub to a sync one
   (the async stub had masked the bug — tests now assert the real API shape).

Environment note (not a component issue): HA 2026.9 migrates a YAML `http:`
section once into a stable/pending storage pair; an unpromoted pending config
(8124) reverts to stable (8123) on restart and 8123 was already taken by an
unrelated local service. Fixed by pinning `stable.server_port = 8124` in
`.storage/http` for the throwaway instance.

## 7. Deviations from the contract (all documented, with rationale)

- **D1 Verification budget values** (§4): `INDOOR_ONLY_VERIFY_ATTEMPTS = 15`,
  `INDOOR_ONLY_VERIFY_RETRY_SECONDS = 5` (contract: 3 / 2). The pinned budget
  is unachievable against the real propagation delay (§6.1); the binding
  read-after-write rule R6 requires the verification to succeed on real
  writes. Constant names and semantics unchanged; unit tests read the
  module constant.
- **D2 `async_set_updated_data` not awaited** (§7.2 step 6): HA 2026.9's
  coordinator makes it a `@callback`; awaiting it raises TypeError (§6.2).
- **D3 L2 script executed in gate-demo mode only**: the single allowed write
  round-trip ran through the HA protected service (the task's mandatory
  verification path); running L2 standalone as well would have doubled the
  writes on the production tag. The L2 script ships, its abort gate is proven
  live (§5), and its write path (`api.set_tag_profile`) is the exact code the
  service exercised successfully.
- **D4 `TagAssignment.online: bool` extra field** (§7.3): the contract lists
  `device_id, device_name, tag` but also mandates
  `switch_available(assignment)` which needs the flap's `status.online`;
  all contract-listed fields are unchanged.
- **D5 Refusal proofs on WebSocket**: HA 2026.9.3's REST API maps service
  `HomeAssistantError`s to a generic 500 (not 400 with the message), so the
  intended messages are evidenced on the WebSocket channel (§3) — the
  channel the HA UI actually uses — plus the log lines.
- **D6 Write ledger** (§4 table): one establishing write (2→3) was required
  because the tag's actual resting state was profile 2 (research §1), plus one
  no-op diagnostic PUT (no state change, no version increment), plus exactly
  one round-trip 3→2→3. Final state: verified profile 3, version 16.

## 8. Files delivered

Component (`custom_components/surepetcare/`): CORE verbatim — binary_sensor.py,
config_flow.py, entity.py, lock.py, sensor.py (byte sizes verified §1);
EDIT — __init__.py (Platform.SWITCH), const.py (§4 constants + budget evidence
comment), coordinator.py (api client, handle_set_indoor_only, patch helper,
audit logging), manifest.json (§3), services.py (set_indoor_only registration),
services.yaml (§8.1 block verbatim), strings.json (§8.2), icons.json;
NEW — api.py, assignments.py, switch.py, translations/en.json.

Tests (`tests/`): conftest.py, helpers.py, fixtures/me_start.json,
test_api.py (T1-T10), test_assignments.py (T11, T12),
test_coordinator_service.py (T13 + coordinator halves of T7),
test_switch.py (T14), test_credential_hygiene.py (T15 + file mode 600),
test_core_files.py (byte sizes + standalone imports + constant sync +
manifest). Live: `tests/live/{common,l1_read,l2_round_trip,l3_post_read}.py`.
Plus pytest.ini and .gitignore (python cache entries).

QA tooling (outside the repo, deleted after evidence capture):
`/home/emc/ha041/qa/driver.py` (phases: onboard, flow, verify, refusal,
roundtrip, finish), `/home/emc/ha041/qa/diag_put.py` (one-shot raw PUT capture).

## 9. Cleanup

The throwaway HA instance, its config dir (which contained the credentials in
`.storage`), the venvs and the QA scripts under `/home/emc/ha041/` were deleted
after this evidence was captured; `/tmp/041-core` removed. The repository
contains no credential values (T15 asserts it on every test run).