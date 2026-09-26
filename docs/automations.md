# Automations and scripts

Ready-to-copy YAML for the `surepetcare.set_indoor_only` service. All examples are
valid for Home Assistant 2026.9+ and use the real service schema:

- `target.entity_id` — one or more `switch.<pet>_indoor_only` entities
- `data.indoor_only` — `true` (keep the pet(s) inside) or `false` (normal access)
- `data.confirm` — must be `true`; without it the call is rejected before any API traffic

The examples use two fictional pets, **Felix** and **Luna**. Replace them with your
own entity ids: the switch entity id is derived from the pet's name,
`switch.<pet>_indoor_only` (e.g. pet "Felix" → `switch.felix_indoor_only`; a pet named
"Big Felix" → `switch.big_felix_indoor_only`).

Before copying an automation, check the entity ids under **Developer Tools → States**
(`switch.` domain).

## 1. Night curfew for one pet

Keep Felix inside from 21:00, restore normal access at 06:30.

```yaml
automation:
  - alias: "Felix night curfew"
    description: "Keep Felix inside overnight; normal access in the morning."
    triggers:
      - trigger: time
        at: "21:00:00"
        id: curfew_on
      - trigger: time
        at: "06:30:00"
        id: curfew_off
    actions:
      - choose:
          - conditions:
              - condition: trigger
                id: curfew_on
            sequence:
              - action: surepetcare.set_indoor_only
                target:
                  entity_id: switch.felix_indoor_only
                data:
                  indoor_only: true
                  confirm: true
          - conditions:
              - condition: trigger
                id: curfew_off
            sequence:
              - action: surepetcare.set_indoor_only
                target:
                  entity_id: switch.felix_indoor_only
                data:
                  indoor_only: false
                  confirm: true
```

## 2. Dashboard button and script

Because the switch itself is write-protected, put a **script** in front of it and a
**button card** on the dashboard.

The script (Settings → Automations & Scenes → Scripts, or YAML):

```yaml
script:
  keep_felix_inside:
    alias: "Keep Felix inside"
    icon: mdi:home-lock
    sequence:
      - action: surepetcare.set_indoor_only
        target:
          entity_id: switch.felix_indoor_only
        data:
          indoor_only: true
          confirm: true
  let_felix_out:
    alias: "Let Felix out"
    icon: mdi:home-lock-open
    sequence:
      - action: surepetcare.set_indoor_only
        target:
          entity_id: switch.felix_indoor_only
        data:
          indoor_only: false
          confirm: true
```

A button card that calls the service directly (the button shows the switch's current
state — `home-lock` when indoor-only is in force):

```yaml
type: button
name: "Keep Felix inside"
entity: switch.felix_indoor_only
icon: mdi:home-lock
tap_action:
  action: perform-action
  perform_action: surepetcare.set_indoor_only
  target:
    entity_id: switch.felix_indoor_only
  data:
    indoor_only: true
    confirm: true
```

The service declares a confirmation text, so the UI asks *"This changes the pet's flap
access on the Sure Petcare cloud. Continue?"* before it runs. That dialog is a UI
feature only: calls from automations and scripts never prompt, they just run — which
is why the `confirm: true` field is still enforced everywhere.

## 3. Presence-based automation: lock the pet in when it comes home late

If Felix comes back inside late at night, keep him in until morning. The pet's
presence binary sensor is `on` when the pet is inside.

```yaml
automation:
  - alias: "Late arrival: keep Felix in"
    description: "If Felix gets home after curfew, keep him inside until 06:30."
    triggers:
      - trigger: state
        entity_id: binary_sensor.felix
        to: "on"
    conditions:
      - condition: time
        after: "21:00:00"
        before: "06:30:00"
    actions:
      - action: surepetcare.set_indoor_only
        target:
          entity_id: switch.felix_indoor_only
        data:
          indoor_only: true
          confirm: true
```

## 4. Holiday scenario: all pets stay inside while you are away

A helper switch drives it: turn it on when you leave, off when you return. Multiple
pets are targeted in a single call — each one is written and verified independently.

```yaml
input_boolean:
  holiday_mode:
    name: "Holiday (pets stay inside)"
    icon: mdi:beach

automation:
  - alias: "Holiday on: all pets indoor"
    triggers:
      - trigger: state
        entity_id: input_boolean.holiday_mode
        to: "on"
    actions:
      - action: surepetcare.set_indoor_only
        target:
          entity_id:
            - switch.felix_indoor_only
            - switch.luna_indoor_only
        data:
          indoor_only: true
          confirm: true

  - alias: "Holiday off: normal access"
    triggers:
      - trigger: state
        entity_id: input_boolean.holiday_mode
        to: "off"
    actions:
      - action: surepetcare.set_indoor_only
        target:
          entity_id:
            - switch.felix_indoor_only
            - switch.luna_indoor_only
        data:
          indoor_only: false
          confirm: true
```

The same works with a `person` entity (e.g. `trigger: state, entity_id: person.you,
to: "not_home"`) or the `binary_sensor.workday` style helpers — only the triggers
change; the action block always calls the service with `confirm: true`.

## Things to know when automating

- **A refused call is an error, not a silent skip.** If any target flap is offline the
  whole call fails fast and *nothing is written*; the error appears in the
  automation/script trace and the Home Assistant log. Consider adding a
  `notify` action to be told about failures:

  ```yaml
  - action: surepetcare.set_indoor_only
    target:
      entity_id: switch.felix_indoor_only
    data:
      indoor_only: true
      confirm: true
  - action: notify.persistent_notification
    data:
      title: "Felix is locked in"
      message: "Indoor-only verified by the Sure Petcare cloud."
  ```

- **The switch state is cloud truth.** After a successful call the switch updates
  immediately (the verified state is pushed as soon as the cloud confirms it); after a
  change made in the mobile app it updates within the next poll (~3 minutes). Do not
  add "wait a few minutes" steps — they are not needed.
- **Multi-flap pets are written atomically.** If a pet's chip is on several flaps, all
  of them are written; the switch reads `on` only when every flap is at the indoor-only
  profile.
- Every successful call is audit-logged with user, time, pet, flap, and the profile and
  version numbers before → after (see [troubleshooting.md](troubleshooting.md) for
  where to find those lines).