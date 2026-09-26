# Spec 041 — Owner quickstart: install and verify the Sure Petcare "Indoor Only" switch

- **What you get**: your existing Sure Petcare entities, unchanged, plus **one switch per
  pet** ("Pinceau Indoor Only", …) showing whether each pet is kept inside, and the
  protected service `surepetcare.set_indoor_only` to change it. The switch always shows
  the **cloud truth** — it never guesses, and after every write the change is read back
  and verified before the switch moves.
- **Requirements**: Home Assistant 2026.9 line or newer (Python ≥ 3.14). Nothing else to
  install.

## 1. Install

1. Copy the component into your HA configuration directory (only the
   `surepetcare` folder):

   ```
   <config>/custom_components/surepetcare/
   ```

   If the core `surepetcare` integration is currently in use, that is expected — the
   custom folder **takes precedence** over the built-in one because it uses the same
   domain.

2. Restart Home Assistant.

3. Confirm the **custom** one is loaded (two checks):
   - Settings → Devices & Services → Sure Petcare → the integration info shows
     **Version 0.1.0** (the built-in integration has no version there).
   - The startup log contains the notice that a custom integration for `surepetcare`
     is in use.

   Your existing entities keep their names, ids and history — the fork reuses the exact
   same internal identifiers as the core integration.

## 2. First look

- Each pet with a chip registered on a flap gets a new switch, e.g.
  `switch.pinceau_indoor_only`, attached to that pet's device card.
  - **On** = indoor only (kept inside) on all the pet's flaps.
  - **Off** = normal access.
- The switch attributes show the details: `pet_id`, `tag_id`, and per flap `device_id`,
  `profile`, `version`.
- State follows the cloud: if you change "indoor only" in the Sure Petcare **app**, the
  switch catches up within the next poll (about 3 minutes). An offline flap makes the
  switch `unavailable` rather than show a possibly stale value.

## 3. Changing a pet's indoor-only state (the only way)

The toggle in the UI is **deliberately locked**: tapping it raises an error and never
writes. The only write path is the service, and it is protected twice (a `confirm`
field that must be `true`, plus a confirmation dialog in the UI).

**From the UI**: Developer Tools → Actions → `Sure Petcare: Set indoor only` →
pick the pet's switch under Targets → set `Indoor only` on/off → tick `Confirm` →
confirm the dialog.

**From YAML**:

```yaml
service: surepetcare.set_indoor_only
target:
  entity_id: switch.pinceau_indoor_only
data:
  indoor_only: true   # true = keep inside, false = normal access
  confirm: true       # required, or the call is rejected with no API write
```

You can target several pets at once (e.g. all cats) — each one is written and verified
independently.

## 4. Verifying the change really happened in the cloud

The component never assumes a write worked — it reads the cloud back and checks the
tag `version` incremented. To convince yourself:

1. **Before**: Developer Tools → States → `switch.pinceau_indoor_only` → note
   `devices[0].version` (e.g. `13`) and `profile` (e.g. `2`).
2. Call the service as above.
3. **After**: the state flipped **and** the attributes show the new `profile` (e.g. `3`)
   and the **version bumped by one** (e.g. `14`). The log (Settings → System → Logs)
   contains one audit line like:

   ```
   surepetcare: indoor-only verified | user=… | pet=Pinceau tag=2119787 | device=la chatière (1307328) | profile 2→3 | version 13→14
   ```

   (format indicative — the fields are contractual, the wording may differ slightly).
4. **Cross-check in the Sure Petcare app**: the pet now shows "Indoor only".

If the write could not be verified after the retry budget, the call raises, the log
explains it, and the switch re-syncs to whatever the cloud actually says — it will
**never** show a value that was not read back from the cloud.

## 5. Troubleshooting

| Symptom | Meaning / action |
|---|---|
| Tapping the toggle shows an error | By design — use the service (§3). |
| Service rejected with "confirm required" | You must pass `confirm: true` — accidental runs (old automations, typos) are blocked on purpose. |
| "Flap offline" error | The flap (or hub) is not reachable; the component refuses to write because it could not guarantee verification. Restore connectivity and retry. |
| Switch `unavailable` | One of the pet's flaps is offline — state cannot be trusted, writes are refused until it returns. |
| 401 / "authentication failed" | Re-authenticate the integration: Settings → Devices & Services → Sure Petcare → Reauthenticate. |
| Switch state lags behind the app | The poll runs about every 3 minutes; the next poll corrects it. (A service write updates immediately after verification.) |
| Version jumped by more than 1 in the log | Someone else (likely the app) wrote between your read and write — the component detects and logs it; the state stays cloud-true. |

## 6. Notes and limits

- Only **flaps** are considered for indoor-only (cat flap / pet door). Felaqua and feeder
  chip profiles are shown for transparency but never used for state or written.
- A pet with no chip on any flap gets no switch (a setup log line explains which pets and
  why).
- Keeping this fork up to date is manual: when HA ships a new core `surepetcare` version,
  the fork does not change — rebase deliberately (see plan.md).
- Live test scripts (`tests/live/`) exist for development only; they use the local
  `.secrets/surepetcare.env`, never run in CI, and their controlled write test only ever
  touches Pinceau's chip, always returning it to "indoor only" (profile 3) at the end.