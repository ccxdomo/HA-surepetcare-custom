# Spec 042 — Documentation for the HA-surepetcare-custom component

- **Status**: Done (documentation only)
- **Date**: 2026-09-26
- **Repo**: `HA-surepetcare-custom` (branch `main`)
- **Subject**: the deliverable of [spec 041](../041-indoor-only-switch/spec.md) — the
  custom `surepetcare` component with the per-pet **Indoor Only** switch.
- **Scope rule**: documentation only — `custom_components/**` and `tests/**` are not
  touched (byte-identical to the spec 041 commit); nothing is committed here either
  (the orchestrator commits).

## Deliverables

| File | Contents |
|---|---|
| `README.md` (repo root) | What this fork is, the upstream (core) feature set, the indoor-only switch + service, installation and domain-takeover semantics, write protection, verification, honest limitations (undocumented cloud API, live-probed semantics), troubleshooting summary, credits |
| `docs/README.md` | Documentation index |
| `docs/automations.md` | Ready-to-copy YAML: night curfew, dashboard button + scripts, presence-based automation, holiday scenario — all using the real `surepetcare.set_indoor_only` schema |
| `docs/entities-and-services.md` | Full entity list (id patterns, unique_id patterns, attributes) + every service with its fields and exact error messages |
| `docs/how-it-works.md` | Cloud-first state, read-after-write verification, write-protection rationale, API request shapes (headers, no credential values), tag/profile model, log lines |
| `docs/troubleshooting.md` | 401/X-Device-Id story (Authorization is the only auth boundary, sessions additive), what "verification failed" really means (propagation delay, write may have landed), the list-shaped `/device` read, how to check the real cloud state, where the audit lines come from |

## Facts policy

- Every claim is checked against the committed code (`switch.py`, `coordinator.py`,
  `api.py`, `assignments.py`, `services.py`, `services.yaml`, `const.py`,
  `translations/en.json`) and the spec 041 artifacts (`research.md`, `evidence.md`,
  `data-model.md`, `quickstart.md`).
- Upstream feature wording is based on the core integration's HA docs page and its
  `strings.json`/`services.yaml` — the core component has no upstream README.
- No credentials, tokens, or real account identifiers appear in any documentation file
  (no household id, no device serial, no MAC, no real pet names — examples use
  fictional pets such as "Felix" and "Luna").
- All documentation is in English, Markdown only.