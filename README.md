# Sure Petcare for Home Assistant — custom fork with per-pet **Indoor Only**

This is a **drop-in custom component** for Home Assistant: a fork of the core
**Sure Petcare** integration that adds the one thing the core integration does not
expose — **one "Indoor Only" switch per pet**, backed by the Sure Petcare cloud and
protected by a verified write service.

Everything the core integration does is preserved (same entities, same unique ids,
same services). On top of it you get:

- `switch.<pet>_indoor_only` — one switch per chipped pet, e.g. `switch.felix_indoor_only`
- `surepetcare.set_indoor_only` — the only way to change it, with a mandatory
  `confirm: true` field and **read-after-write verification** against the cloud

The switch never guesses. Its state is always what the Sure Petcare cloud says — either
from the regular 3-minute poll, or from the verification read that follows a service
write. There is no optimistic state anywhere.

## User guide

| Page | Contents |
|---|---|
| [docs/README.md](docs/README.md) | Index of the documentation |
| [docs/automations.md](docs/automations.md) | Ready-to-copy YAML: night curfew, dashboard button, presence automation, holiday mode |
| [docs/entities-and-services.md](docs/entities-and-services.md) | Every entity and service the component creates |
| [docs/how-it-works.md](docs/how-it-works.md) | Technical page: cloud-first state, verification, API request shapes, tag/profile model |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common failures and what to check |

## What the core component already does

This fork reproduces the full Home Assistant core `surepetcare` integration. If you
have used that integration, everything below works exactly as before:

**Devices and entities**

| Device | Entities |
|---|---|
| Hub | Connectivity binary sensor (diagnostic; attributes: `led_mode`, `pairing_mode`) |
| Pet / cat flap | Connectivity binary sensor · **3 locks** (locked in / locked out / locked all) · Battery level sensor |
| Feeder | Connectivity binary sensor · Battery level sensor |
| Felaqua (water fountain) | Connectivity binary sensor · Water remaining sensor (ml) · Battery level sensor |
| Pet | Presence binary sensor (`on` = inside) · Last seen flap device id and Last seen user id sensors (diagnostic, disabled by default) |

**Services**

| Service | What it does |
|---|---|
| `surepetcare.set_lock_state` | Sets the locking state of a flap (`unlocked`, `locked_in`, `locked_out`, `locked_all`) |
| `surepetcare.set_pet_location` | Manually sets a pet's location to `Inside` or `Outside` |

The full entity list with id patterns and attributes is in
[docs/entities-and-services.md](docs/entities-and-services.md).

## The new feature: per-pet "Indoor Only" switch

The Sure Petcare app can keep an individual pet indoors (the "indoor only" per-pet
setting). The core integration exposes nothing for it. This fork adds:

- **One switch per pet** whose chip is assigned to at least one flap:
  `switch.<pet>_indoor_only` (e.g. `switch.felix_indoor_only`).
- **`on` = the pet is kept inside on *all* of its flaps** (Sure Petcare tag profile 3).
  **`off` = normal access** (profile 2). If a pet has several flaps and they disagree,
  the switch is `off` — the per-flap profiles are visible in its attributes.
- The switch is attached to the pet's existing device card, next to the presence sensor.

### How state flows

- The coordinator polls the cloud about **every 3 minutes**. A change made in the
  Sure Petcare **mobile app** appears in Home Assistant within that poll window.
- A change made **from Home Assistant** (the service) is written to the cloud, read
  back and **verified**, then pushed to the entities immediately — you do not wait for
  the next poll.
- If one of the pet's flaps is offline, the switch goes `unavailable` rather than
  show a possibly stale value, and writes for that pet are refused.

### Why the switch is write-protected — and how to write anyway

The switch controls a **physical door for a living animal**. A stray UI tap or a buggy
automation must not be able to silently let a pet out at night. So:

- **Toggling the switch in the UI raises an error and writes nothing.** The exact
  message: *"The indoor-only switch is write-protected by design and cannot be toggled
  directly. Use the surepetcare.set_indoor_only service with confirm: true instead."*
- The **only** write path is the `surepetcare.set_indoor_only` service, protected
  twice: the `confirm` field must be `true` (anything else is rejected before any API
  traffic), and the UI shows a confirmation dialog on top.

```yaml
action: surepetcare.set_indoor_only
target:
  entity_id: switch.felix_indoor_only
data:
  indoor_only: true   # true = keep inside, false = normal access
  confirm: true       # required, or the call is rejected with no API write
```

Full schema (copied verbatim from `services.yaml`):

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

You can target several pets at once — each one is written and verified independently.

Every successful call is **audit-logged** (who, when, which pet, which flap, profile
and version before → after), and the switch carries a `last_write` attribute with the
same information. Details: [docs/how-it-works.md](docs/how-it-works.md).

## Installation

**Requirements**: Home Assistant 2026.9 line or newer (the fork contains core files
that need Python ≥ 3.14). Nothing else to install — no HACS listing, no PyPI package.

1. Copy the component folder into your Home Assistant configuration directory:

   ```
   <config>/custom_components/surepetcare/
   ```

2. Restart Home Assistant.

3. If you already use the core Sure Petcare integration, your existing config entry,
   devices and entities keep working as-is — **nothing to re-add**. New users: add it
   via **Settings → Devices & Services → Add Integration → Sure Petcare** (username =
   your Sure Petcare account email, plus password).

4. Confirm the **custom** one is loaded (two checks):
   - Settings → Devices & Services → Sure Petcare: the integration info shows
     **Version 0.1.0** (the built-in integration shows no version there).
   - The startup log contains the notice that a **custom integration** for
     `surepetcare` is in use.

### What "takes over the domain" means

Home Assistant checks `custom_components/` **before** built-ins, so this folder
**replaces the core integration in place** — both use the domain `surepetcare`, and
only one can own it. You cannot run this fork *alongside* the core integration, and
you do not need to: it *is* the core integration, plus the switches.

Because it reuses the exact same internal identifiers (`unique_id`s) as the core
component, your **existing entities are not duplicated** — the same config entry
re-attaches to the custom component after the restart, with all entity ids, names and
history intact. If you ever delete the `custom_components/surepetcare/` folder and
restart, Home Assistant falls back to the built-in integration the same way.

Consequences to be aware of:

- **Home Assistant upgrades do not update this fork.** When the core integration
  changes upstream, this fork stays as-is until it is deliberately rebased.
- The startup log will always show the "custom integration … has not been tested by
  Home Assistant" notice. That is expected for any custom component.

## Honest limitations

- **The Sure Petcare cloud API is undocumented.** Nothing about it is published; it
  can change without notice and break this component (or the core one) at any time.
- The indoor-only facts this fork relies on were **established by live probing**
  during development, not by any official documentation:
  - the setting lives on the per-(flap, chip) assignment, as the `profile` field:
    **profile 2 = normal access, profile 3 = indoor only**;
  - the write is `PUT /device/{device_id}/tag/{tag_id}` with body `{"profile": 2|3}`;
  - every accepted change **increments the tag `version`** — the component uses that
    increment as its proof that a write actually persisted (it never trusts the
    PUT response body).
- A pet whose chip is not assigned to any flap gets no switch (a setup log line names
  the pets concerned).
- The switch can lag the mobile app by up to one poll (~3 minutes); it will never
  show a state that was not read back from the cloud.
- Feeders and the Felaqua fountain are ignored for indoor-only: only flaps are read
  for state and written (matching the app's behaviour).

## Troubleshooting

| Symptom | Meaning / action |
|---|---|
| Tapping the switch shows an error | By design — use the service (see above). |
| Service rejected with "confirm required" | Pass `confirm: true`; accidental runs are blocked on purpose. |
| "Flap … is offline — refusing to write" | The flap (or hub) is not reachable; restore power/connectivity and retry. |
| Switch `unavailable` | One of the pet's flaps is offline — state cannot be trusted, writes refused. |
| 401 / "authentication failed" | Re-authenticate: Settings → Devices & Services → Sure Petcare → ⋮ → Reauthenticate. |
| Switch lags behind the app | The poll runs about every 3 minutes; the next poll corrects it. |

More (including the 401 story, how to check the real cloud state, and where the audit
log lines come from): [docs/troubleshooting.md](docs/troubleshooting.md).

## Credits

- **Home Assistant core `surepetcare` integration** — this fork is built directly on
  it; all credit for the base feature set (flaps, locks, feeders, Felaqua, presence,
  sensors, services) belongs to the upstream Home Assistant project and its
  maintainers (code owners `@benleb`, `@danielhiversen`).
- **[surepy](https://github.com/benleb/surepy)** by `@benleb` — the library that
  feeds the read backbone (polling, entities) for this integration, unchanged here.
- The indoor-only switch, verified write service and documentation are the additions
  of this fork (`@ccxdomo`).

## Repository layout

```
custom_components/surepetcare/   the component (copy this into your config)
docs/                           user-facing guides (this documentation)
specs/                          design specs: 041 = the feature, 042 = this documentation
tests/                          unit tests + manual live test scripts (no secrets inside)
```