# Troubleshooting

Common failures and what to check. Everything below is drawn from what was actually
observed during development (live probing and on-hardware QA), not guesswork.

## Quick table

| Symptom | Meaning / action |
|---|---|
| Tapping the switch in the UI shows an error | By design — the switch is write-protected. Use the `surepetcare.set_indoor_only` service with `confirm: true`. |
| Service rejected with "The confirm field must be true…" | Pass `confirm: true`. Accidental runs (old automations, typos) are blocked on purpose, before any API traffic. |
| "Flap … is offline — cannot verify a change; refusing to write" | The flap or its hub is not reachable. The component refuses to write because it could not guarantee verification. Check power/batteries and hub connectivity, then retry. |
| Switch `unavailable` | One of the pet's flaps is offline (or the last poll failed). State cannot be trusted and writes are refused until it returns. |
| 401 / "Authentication with the Sure Petcare cloud failed" | Re-authenticate: **Settings → Devices & Services → Sure Petcare → ⋮ → Reauthenticate**, then retry. See the 401 section below. |
| "The indoor-only change could not be verified…" | The cloud did not confirm the change within the retry budget. **The write may still have landed** — check the app or the switch attributes (see below). |
| Switch lags behind the mobile app | Normal: the poll runs about every 3 minutes. The next poll corrects it. A service write, by contrast, updates immediately after verification. |
| Audit log shows a version jump of more than 1 | Someone else (usually the mobile app) wrote between your read and write. Logged as a warning; the switch stays cloud-true. |
| Startup log shows "custom integration … has not been tested by Home Assistant" | Expected for any custom component. Not an error. |

## Authentication failures and 401s — the real story

**What a 401 means.** The Sure Petcare API returns 401 only when the
`Authorization: Bearer …` header is missing or invalid. For the integration this
means the stored credentials are stale: re-authenticate
(**Settings → Devices & Services → Sure Petcare → ⋮ → Reauthenticate**) and retry.

**The X-Device-Id red herring.** During development, a 401 was initially misread as
"the token is bound to the device id that requested it" — the error looked like an
`X-Device-Id` mismatch. Controlled live probing showed the opposite:

- a **valid token with a wrong or missing `X-Device-Id`** still returns **200**;
- a **garbage or missing Bearer token** is what returns **401**;
- sessions are **additive**: logging in again (from the app, from Home Assistant, from
  anywhere) does **not** invalidate earlier tokens — tokens are not fenced to a
  device id.

The component still sends `X-Device-Id` on every call (matching the official app's
convention, and hedging against the server ever tightening enforcement), but it never
relies on it for authentication. If a call ever hits a 401 mid-write, the component
logs in once with your configured username/password and retries the failed call
exactly once. The write client's session token lives in memory only — it is never
written to disk, logs or exceptions.

## "Verification failed" — what it really means

The component never trusts the write request's response. After a write it re-reads the
cloud and accepts the change only when the flap shows the requested profile **and**
the chip's `version` counter incremented. If that is not confirmed within the retry
budget (15 attempts, 5 s apart, ~70 s window), the call raises and the switch keeps
the last cloud-verified state until the next poll.

Two things observed during live QA are worth knowing:

1. **The cloud has propagation delay.** An accepted write became readable in the
   device read only about **10 seconds later** — the original, tighter budget
   (3 attempts × 2 s) produced a false "verification failed" on a write that had
   actually landed. That is why the budget is now 15 × 5 s.
2. **"Verification failed" ≠ "the write did not happen."** In the live test the write
   *did* land and the call still raised — the component refused to claim success it
   could not prove. The switch re-synced to the true cloud state on the next poll.

So after a "could not be verified" error: check the app or the switch attributes
(see below). If the cloud state is what you wanted, the write landed; if not, simply
retry the call.

## The device read returns a **list** — why tag lookups can miss

The fresh device read (`GET /device?with[]=children&with[]=tags&with[]=control&with[]=status`)
returns its payload as a **list** of device objects under `data` — not a mapping
keyed by id. Anything that treats the response as a dict (e.g. "look up
`data[<device_id>]`") fails to find the device or its chip assignment even though it
exists — a "tag not found" that is really a shape assumption. The component scans the
list for the device id, then the chip id inside the device's `tags[]`, and treats a
genuinely missing chip as a retryable condition during verification (the assignment
can also appear briefly stale right after a write — the propagation delay above).

If a chip really was removed from a flap (or the pet was deleted), the pet's switch shows
`unknown` and becomes `unavailable`, and it is not re-added the next time the
integration sets up (restart/reload) — a setup log line names any pets without flap
assignments.

## How to check the real cloud state

The switch is cloud truth *as of its last read* — to check the cloud *now*:

1. **Developer Tools → States** → `switch.<pet>_indoor_only` → attributes: the
   `devices` list shows, per flap, the live `profile` (2 = normal access, 3 = indoor
   only) and `version` numbers the component last read. Note the `version` before
   making a change.
2. Make the change (service call), then re-check: the state flips **and** the
   attributes show the new `profile` with the `version` bumped (typically by 1).
3. **Cross-check in the Sure Petcare app**: the pet shows "Indoor only" (or not).
4. The `last_write` attribute on the switch carries the last verified write for that
   pet (time, user id, per-flap verified profile/version).

## Where the audit log lines come from

All indoor-only audit lines come from the component's coordinator logger —
`custom_components.surepetcare.coordinator` — visible in **Settings → System → Logs**
(or `home-assistant.log`):

```text
INFO  indoor-only write verified | user=… | user_id=… | at=… | entity_id(s)=… | pet=… tag_id=… device=… (id) | profile 2->3 | version 15->16
ERROR indoor-only write FAILED    | user=… | user_id=… | at=… | entity_id(s)=… | pet=… | reason=…
ERROR refusing indoor-only write: flap … (id) for pet … is offline
INFO  pet(s) without flap assignment, no indoor-only switch created: …
```

The success line is written only after the cloud confirmed the change (profile match +
version increment). Failures carry the same identifiers plus the reason. Credentials,
tokens, emails and HTTP headers are never logged.

## Installation and updates

| Concern | Answer |
|---|---|
| How do I know the custom fork is the loaded one? | **Settings → Devices & Services → Sure Petcare** shows **Version 0.1.0** (the built-in integration shows no version), and the startup log names a custom integration. |
| Will my entities be duplicated after installing? | No. The fork reuses the core integration's exact internal identifiers, so existing config entries, devices and entities re-attach as-is. |
| Does a Home Assistant upgrade update the fork? | **No.** A custom component is never touched by HA updates; the core integration's upstream changes are not picked up automatically. Compare/rebase deliberately if you need them. |
| The integration went away after I deleted the custom folder | Expected: with the folder gone, Home Assistant falls back to the built-in integration on the next restart (same unique ids, entities unchanged — but the indoor-only switches disappear). |
| Pet has a chip but no switch appeared | The chip must be assigned to at least one **flap** (pet door / cat flap). Chips only on a feeder or Felaqua produce no switch; the setup log names such pets. |

## If nothing here helps

The component's own code is the ground truth: `custom_components/surepetcare/`
(`switch.py`, `coordinator.py`, `api.py`, `assignments.py`, `services.py`), and the
design evidence lives in `specs/041-indoor-only-switch/` (the live-probe research and
QA evidence are documented there). The cloud API itself is undocumented and can change
without notice — a sudden breakage across the board (both app and core integration
behaving oddly) usually points at an API change, not at your configuration.