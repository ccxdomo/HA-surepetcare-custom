# Entities and services

The complete surface of the custom `surepetcare` component: every entity it creates,
with id patterns and attributes, and every service with its fields. All entities exist
under a single integration; each Sure Petcare device (hub, flap, feeder, Felaqua) and
each pet gets its own device card under **Settings → Devices & Services → Sure Petcare**.

Entity ids are derived from the names of your devices and pets (as set in the Sure
Petcare app), lower-cased with spaces turned into underscores: a flap named "Front
door" becomes `front_door`, a pet named "Felix" becomes `felix`. The examples below use
fictional names — a hub, a flap "Front door", a Felaqua "Water fountain" and two pets
Felix and Luna.

## Entities from the base (core) integration

### Hub

| Entity | Entity id pattern | Notes |
|---|---|---|
| Connectivity binary sensor | `binary_sensor.<hub>` | Diagnostic. `on` = hub online. Attributes: `led_mode` (int), `pairing_mode` (bool). Unavailable (not just `off`) when the hub is offline. |

### Pet / cat flaps

| Entity | Entity id pattern | Notes |
|---|---|---|
| Connectivity binary sensor | `binary_sensor.<flap>_connectivity` | Diagnostic. `on` = online. Attributes: `device_rssi`, `hub_rssi` (formatted strings; `device_rssi` is "Unknown" when absent). |
| Locks (3 per flap) | `lock.<flap>_locked_in` · `lock.<flap>_locked_out` · `lock.<flap>_locked_all` | `locked_in` = entry only; `locked_out` = exit only; `locked_all` = locked both ways. Each entity reads `locked` when the flap's mode matches it (when the flap is fully unlocked, all three read `unlocked`). |
| Battery level sensor | `sensor.<flap>_battery_level` | Diagnostic. Percentage derived from the battery voltage. Attributes: `voltage` (total), `voltage_per_battery`. |

Example: flap "Front door" → `binary_sensor.front_door_connectivity`,
`lock.front_door_locked_in`, `lock.front_door_locked_out`, `lock.front_door_locked_all`,
`sensor.front_door_battery_level`.

### Feeders

| Entity | Entity id pattern | Notes |
|---|---|---|
| Connectivity binary sensor | `binary_sensor.<feeder>_connectivity` | Diagnostic, as above. |
| Battery level sensor | `sensor.<feeder>_battery_level` | Diagnostic, as above. |

### Felaqua (water fountain)

| Entity | Entity id pattern | Notes |
|---|---|---|
| Connectivity binary sensor | `binary_sensor.<felaqua>_connectivity` | Diagnostic, as above. |
| Water remaining sensor | `sensor.<felaqua>` | Device class volume, milliliters. |
| Battery level sensor | `sensor.<felaqua>_battery_level` | Diagnostic, as above. |

Example: Felaqua "Water fountain" → `binary_sensor.water_fountain_connectivity`,
`sensor.water_fountain`, `sensor.water_fountain_battery_level`.

### Pets

| Entity | Entity id pattern | Notes |
|---|---|---|
| Presence binary sensor | `binary_sensor.<pet>` | `on` = pet is inside. Attributes: `since` (timestamp of last movement), `where` (1 = inside, 2 = outside). |
| Last seen flap device id | `sensor.<pet>_last_seen_flap_device_id` | Diagnostic, **disabled by default**. The Sure Petcare device id of the last flap the pet used; `unknown` if the last update was not from a flap. |
| Last seen user id | `sensor.<pet>_last_seen_user_id` | Diagnostic, **disabled by default**. The user id that last changed the pet's location manually; `unknown` if the last update was not manual. |

Unique id patterns (stable across restarts and identical to the core integration —
this is why existing entities are never duplicated):

| Entity | unique_id pattern |
|---|---|
| Hub connectivity · Felaqua water · pet presence | `{household_id}-{device_or_pet_id}` |
| Connectivity | `{household_id}-{id}-connectivity` |
| Battery level | `{household_id}-{id}-battery` |
| Locks | `{household_id}-{id}-locked_in` / `-locked_out` / `-locked_all` |
| Last seen flap device id | `{household_id}-{pet_id}-last_seen_flap_device` |
| Last seen user id | `{household_id}-{pet_id}-last_seen_user` |

## The new entity: Indoor Only switch (this fork)

One per pet whose chip is assigned to at least one flap. Pets without any flap
assignment get no switch (a setup log line names them).

| Property | Value |
|---|---|
| Entity id pattern | `switch.<pet>_indoor_only` (e.g. pet "Felix" → `switch.felix_indoor_only`, "Big Felix" → `switch.big_felix_indoor_only`) |
| Name | `<Pet> Indoor Only` |
| unique_id | `{household_id}-{pet_id}-indoor_only` |
| Device | the pet's device card, next to the presence binary sensor |
| `on` | indoor only is in force: **every** flap carrying the pet's chip is at the indoor-only profile (profile 3) |
| `off` | normal access (at least one flap at profile 2) |
| Icon | `mdi:home-lock` when on · `mdi:home-lock-open` when off |
| Available | only when the last cloud poll succeeded **and** all of the pet's flaps are online; otherwise `unavailable` |
| Toggling | **write-protected**: raises an error, never writes (see below) |

Attributes:

| Attribute | Meaning |
|---|---|
| `pet_id` | Sure Petcare id of the pet |
| `pet_name` | Pet name |
| `tag_id` | Sure Petcare id of the pet's chip |
| `devices` | List with one entry per flap assigned to the chip: `{device_id, device_name, profile, version}`. `profile`: 2 = normal access, 3 = indoor only. `version`: increments on every accepted change (see [how-it-works.md](how-it-works.md)) |
| `all_flaps_indoor_only` | Whether every flap is at the indoor-only profile (mirrors the state; useful in templates) |
| `last_write` | Present after the first verified service write for this pet: `{at (ISO-8601), user_id, requested (true/false), verified: [{device_id, tag_id, profile, version}, …]}` |

Toggling the switch in the UI produces exactly this error:

> The indoor-only switch is write-protected by design and cannot be toggled directly.
> Use the surepetcare.set_indoor_only service with confirm: true instead.

## Services

### `surepetcare.set_lock_state` *(core)*

Sets the locking state of a flap. The numeric `flap_id` is the Sure Petcare device id of
the flap.

```yaml
action: surepetcare.set_lock_state
data:
  flap_id: 123456
  lock_state: locked_all
```

| Field | Required | Selector | Notes |
|---|---|---|---|
| `flap_id` | yes | positive integer | The flap's Sure Petcare device id |
| `lock_state` | yes | select | `unlocked` · `locked_in` · `locked_out` · `locked_all` |

Unknown flap ids are rejected with *"Unknown Sure Petcare flap ID: {flap_id}"*.

### `surepetcare.set_pet_location` *(core)*

Manually sets a pet's location to `Inside` or `Outside`.

```yaml
action: surepetcare.set_pet_location
data:
  pet_name: Felix
  location: Inside
```

| Field | Required | Selector | Notes |
|---|---|---|---|
| `pet_name` | yes | text | The pet's name **exactly** as in the app/HA (the match is exact: `felix` will not match "Felix") |
| `location` | yes | select | `Inside` · `Outside` |

Unknown pet names are rejected with *"Unknown Sure Petcare pet: {pet_name}"*.

### `surepetcare.set_indoor_only` *(this fork — the only way to change the switch)*

Sets the indoor-only access profile of one or more pets on their flaps. The cloud state
is read back and verified before the switch updates.

```yaml
action: surepetcare.set_indoor_only
target:
  entity_id: switch.felix_indoor_only
data:
  indoor_only: true
  confirm: true
```

Full schema (verbatim from `services.yaml`):

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

| Field | Required | Type | Notes |
|---|---|---|---|
| `entity_id` (target) | yes | one or more switch entities of this integration | Must be `switch.<pet>_indoor_only` entities; anything else is rejected |
| `indoor_only` | yes | boolean | `true` = indoor only, `false` = normal access |
| `confirm` | yes | boolean | Must be `true` |

Behaviour and failure modes (exact messages from the integration's translations):

| Situation | Result |
|---|---|
| `confirm` missing or `false` | Rejected with *"The confirm field must be true to change indoor-only access. Call surepetcare.set_indoor_only again with confirm: true."* — no API call is made |
| Target is not an indoor-only switch of this integration | Rejected with *"{entity_id} is not a Sure Petcare indoor-only switch. Target a switch.<pet>_indoor_only entity of this integration."* |
| Pet's chip is not on any flap | Rejected with *"Pet {pet_name} has no chip assignment on any flap, so indoor-only cannot be set."* |
| Any target flap offline | Rejected with *"Flap {device_name} ({device_id}) is offline — cannot verify a change; refusing to write. Check the flap's power and hub connectivity, then retry."* — nothing is written for **any** target (fail fast) |
| Cloud authentication failed | *"Authentication with the Sure Petcare cloud failed. Re-authenticate the integration (Settings → Devices & Services → Sure Petcare → three-dot menu → Reauthenticate), then retry."* |
| Cloud unreachable | *"Could not reach the Sure Petcare cloud. Check your network connection and retry once it is restored."* |
| Write not verifiable in time | *"The indoor-only change could not be verified against the Sure Petcare cloud after the retry budget, so no state was updated. The switch re-syncs from the next cloud read; retry the service call if needed."* |
| Success | The cloud profile is written, read back and verified (profile matches **and** the tag `version` incremented), the switch updates immediately, one audit line is logged |

You can target several pets in one call — each pet is written and verified independently.
See [automations.md](automations.md) for ready-to-copy examples and
[how-it-works.md](how-it-works.md) for the verification sequence.