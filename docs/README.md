# Sure Petcare custom component — documentation

User-facing guides for the custom `surepetcare` component (a fork of the Home Assistant
core integration with the per-pet **Indoor Only** switch). Start with the
[main README](../README.md) for an overview and installation.

## Pages

| Page | Contents |
|---|---|
| [Automations](automations.md) | Ready-to-copy YAML automations and scripts: night curfew, dashboard button, presence-based lock-in, holiday mode. |
| [Entities & services](entities-and-services.md) | The complete list of entities the component creates (id patterns, attributes) and every service with its fields. |
| [How it works](how-it-works.md) | Short technical page: cloud-first state, read-after-write verification, why the switch is write-protected, the API request shapes, and the tag/profile model. |
| [Troubleshooting](troubleshooting.md) | Common failures and what to check — auth/401, offline flaps, verification failures, log lines, cloud propagation. |

## Quick reference

- Switch per pet: `switch.<pet>_indoor_only` — `on` = indoor only on all the pet's flaps.
- The only way to change it:

  ```yaml
  action: surepetcare.set_indoor_only
  target:
    entity_id: switch.felix_indoor_only
  data:
    indoor_only: true
    confirm: true
  ```

- The switch state always comes from the Sure Petcare cloud: within one poll
  (~3 minutes) after an app-side change, or immediately after a verified service write.