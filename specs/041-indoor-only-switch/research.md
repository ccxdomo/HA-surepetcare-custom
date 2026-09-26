# Spec 041 — Research: verified API facts, probes, and decisions

- **Date**: 2026-09-26 (all live probes run between 09:30 and 09:45 Europe/Paris)
- **Method**: read-only probes from the local host against the production API, using the
  provisioned credentials in `.secrets/surepetcare.env` (outside the repo, mode 600).
  Credentials and tokens were **never** printed, echoed, logged or stored in any repo
  file; probe output below is sanitized (identities appear only as the already-known
  fixture ids). Three probe scripts (Python stdlib `urllib`) were used: `probe1` (payload
  shapes), `probe2` (auth/401 isolation, session fencing), `probe3` (login response shape,
  `/me/start` aux arrays).
- **Legend**: **PROVEN** (live evidence in this session) · **GIVEN** (established by the
  interview's controlled probes this morning, accepted as ground truth) · **DISPROVEN**
  (live evidence contradicts an interview assumption) · **UNVERIFIED** (no evidence either
  way).

## 1. Facts table

| Fact | Status | Evidence |
|---|---|---|
| Base URL `https://app.api.surehub.io/api` (`api.surepetcare.io` does not resolve) | PROVEN | All probes used this host; 200s everywhere. |
| Login: `POST /auth/login` with `{"email_address", "password", "device_id": "<uuid>"}` → `200 {"data": {"token": ..., "user": ...}}` | PROVEN | probe1/probe3. Response `data` keys: `token`, `user`. |
| Tokens are long: measured **492 chars** (surepy asserts `320 < len < 448` — its cap is **stale**) | PROVEN | probe1: `token_len=492`; probe2: A/B/C all 492. |
| Header set accepted (see §2) incl. `Authorization: Bearer <token>` | PROVEN | All calls 200 with exactly these headers. |
| **401s are caused by missing/invalid `Authorization`**, not by `X-Device-Id` mismatch | **DISPROVEN** (interview claim) | probe2: valid token + *wrong* `X-Device-Id` → **200**; valid token + *missing* `X-Device-Id` → **200**; garbage/missing Bearer → **401**. |
| Sessions are **additive** (no fencing) | PROVEN | probe2: re-login with same device-id keeps old token valid (200); separate device-id logins do not invalidate each other. `tokenA != tokenB != tokenC` (each login mints a fresh token). |
| `GET /api/me/start` returns `{"data": {"devices", "pets", "households", "photos", "segments", "tags", "user"}}` — this is **surepy's poll endpoint** | PROVEN | probe1. |
| `/me/start` pets carry top-level **`tag_id`** (int) + `tag` object | PROVEN | probe1: Pinceau 400003 → `tag_id=300003`; Moca 400001 → 300001; Tibounet 400002 → 300002. |
| `/me/start` **devices carry `tags[]`** with `id, device_id, index, profile, version, created_at, updated_at` | PROVEN | probe1 + inspect: flap 200001 tags = [{300001, v3}, {300002, v9}, {300003, v13}], all profile 2; hub 200002 has `tags: []`; Felaqua 200003 carries the same three tag ids at version 1. |
| `/device` returns the same device payloads with tags (`with[]=tags` belt-and-braces; **bare `/device` also includes tags**) | PROVEN | probe1: bare `/device` and `?with[]=children&with[]=tags&with[]=control&with[]=status` → identical tags arrays (byte-equal fields compared for flap 200001). |
| `/me/start` top-level `tags[]` = **tag objects** (`id, tag <serial>, supported_product_ids, incompatible_product_ids, version, created_at`), NOT device assignments | PROVEN | probe3. `supported_product_ids: [3, 4, 6, 8, 10, 32]`. |
| `GET /api/tag` and `GET /api/tag/{id}` exist; no `profile`/`device_id` there | PROVEN | probe1: 200, tag objects only. The (device,tag) `profile` exists **only** under `/device` and `/me/start` devices. |
| Pet payload cross-links: `status.activity.tag_id`, `position.tag_id`, `status.drinking.tag_id` all agree with the pet's `tag_id` | PROVEN | probe1/inspect: Pinceau activity = {tag_id: 300003, device_id: 200001, where: 2, since: 2026-09-26T06:08:31Z}. |
| Flap device payload contains `status` (online, battery, locking.mode, signal), `control` (curfew 18:00–06:00 enabled), `version`, `serial_number`, `parent_device_id` | PROVEN | inspect of saved payloads. |
| profile semantics: **2 = normal access, 3 = indoor only** | GIVEN | Established by the interview's three-dump differential + controlled round-trip. Not re-provable read-only (writes are forbidden for the Architect); the Coder's live test re-confirms. |
| Write: `PUT /api/device/{device_id}/tag/{tag_id}` with `{"profile": 2|3}`; accepted change increments the tag `version` | GIVEN | Interview round-trip; `version` increment is the persistence proof. |
| **Pinceau's tag currently rests at profile 2, not 3** | **DISPROVEN** (interview expectation) | probe1: tag 300003 on flap 200001 = profile **2**, version **13**, `updated_at` 2026-09-26T07:09:15Z (this morning, after the interview's round-trip); Pinceau exited via the flap at 06:08Z (`position.where=2`). The Coder's live test therefore starts from profile 2 and MUST end at profile 3 (its final write). |
| App behavior: indoor-only writes go to **flaps only**, never to Felaqua/feeder | PROVEN (inference from version counters) | Felaqua tags: all `version: 1` (never written) while the same tags on the flap show versions 3/9/13 — the app never touched them despite frequent profile toggling. |

## 2. Working header set (evidence-backed)

Used on every probe call, all returned 200:

```
Content-Type: application/json        (on requests with a body)
Accept: application/json, text/plain, */*
Origin: https://surepetcare.io
Referer: https://surepetcare.io/       (trailing slash used by probes; surepy sends no slash — both accepted)
Accept-Language: en-US,en-GB;q=0.9
X-Requested-With: com.sureflap.surepetcare
User-Agent: surepy 0.9.0 - https://github.com/benleb/surepy
Authorization: Bearer <token>          (required on all non-login calls — 401 without it)
X-Device-Id: <uuid>                    (sent always; NOT an auth boundary — see §1)
```

`Accept-Encoding` was not sent (identity), and no `OPTIONS` preflight was sent; both are
unnecessary (surepy sends both; the API does not require them).

## 3. Pet → tag association (interview open question — now SOLVED)

The API exposes the mapping directly and redundantly:

1. `GET /pet` (bare, or with `with[]=tag`): each pet object has top-level **`tag_id`**
   (int) and a nested **`tag`** object whose `id` matches. surepy 0.9.0 already models
   this (`surepy/entities/pet.py`: `Pet.tag_id` property reads `data["tag_id"]`).
2. `GET /me/start` (surepy's poll endpoint): `data.pets[].tag_id` — same values.
3. Cross-validation: `pet.status.activity.tag_id` and `pet.position.tag_id` agree with the
   pet's `tag_id`.

The (device, tag) side comes from `devices[].tags[]` on `/me/start` or `/device` — each
tag entry carries `device_id`, `profile`, `version`. So the per-pet mapping rule is:

> For each pet with `tag_id` T: the pet's controllable devices are the **flap** devices
> (product_id 3 = pet door connect, 6 = cat flap connect) whose `tags[]` contains
> `{id: T}`.

Fixtures (household 100241): Moca 400001 → tag 300001; Tibounet 400002 → tag 300002;
Pinceau 400003 → tag 300003 — all three tags sit on flap "la chatière" (200001) *and*
Felaqua 200003 (ignored for indoor-only, see §6).

No fallback is needed; the API carries the association natively. (The interview's
"unknown pet→tag mapping" was a gap in the morning probes, which only looked at
`/device` — where tag objects indeed carry no pet id. The link is on the **pet** side.)

## 4. Auth & session model (live evidence)

- Login mints a fresh 492-char Bearer token per call; tokens are long-lived (no expiry
  observed within the session; surepy treats them as long-lived too).
- **Additive sessions**: multiple concurrent tokens (app + HA surepy + our write client)
  coexist; re-login with the same `X-Device-Id` does not invalidate the previous token.
- 401 occurs only when `Authorization` is missing/invalid.
- The morning session's 401 ("token bound to device_id") is explained by a missing or
  stale Bearer token, not by device-id binding. We still **send `X-Device-Id` on every
  call** (matches the app convention, costs nothing, and hedges against the server ever
  tightening enforcement) — but the component must not *rely* on it for auth.
- Consequence for design: an in-memory session (uuid4 generated at startup, lazy login,
  one re-login on 401) is sufficient. No token persistence, no config-entry mutation.

## 5. Library vs. direct client — decision (a)

**Verdict: keep `surepy` 0.9.0 as the read backbone; add a small self-contained aiohttp
client (`api.py`) inside the custom component for the write + verification path. Do not
extend, subclass, vendor or fork surepy.**

Evidence from the surepy 0.9.0 wheel (source inspected line-by-line):

1. **No indoor-only support**: `grep -rn profile` finds `Tag.profile` (a read property,
   and — a surepy bug — declared without `@property`) on the `Feeder` entity only; the
   client has `_add_tag_to_device` (empty-body PUT = assign tag) and
   `_remove_tag_from_device` (DELETE). No method writes `{"profile": N}`.
2. **`SureAPIClient.call()` swallows errors**: any non-OK/401 status (400, 422, 500…)
   just logs `logger.info` and returns `None`. A rejected write would look like
   "no data". For a protected write, silent failure is unacceptable.
3. **401 retry bug**: on 401 the client re-logins and retries with
   `method="GET"` — even for a PUT. A write retried as a GET would silently do a read
   instead of the write.
4. **Stale token validation**: `token_seems_valid()` requires
   `320 < len(token) < 448`. Live tokens are 492 chars → the config entry's stored
   token (CONF_TOKEN) is always rejected; the error raised in `__init__` is constructed
   but **not raised** (another surepy bug — dead expression), and every HA start falls
   back to a fresh email/password login on the first poll. Building on this session
   handling would inherit its bugs.
5. **Read backbone works**: `Surepy.get_entities()` → `GET /api/me/start`, which
   (proven) already contains `pets[].tag_id` and `devices[].tags[].profile` — everything
   the switch needs to *read* state, at zero extra API cost. The coordinator, entity
   model and all existing platforms stay untouched.

Alternatives considered:

| Option | Assessment |
|---|---|
| Extend surepy upstream | Cannot publish a fork to PyPI easily; upstream has no profile support; PR round-trip is out of the project's scope/timebox. Rejected. |
| Vendor a surepy fork inside the component | ~1.5k lines of inherited bugs (above), plus a second `surepy` on the path conflicting with the core requirement pin. Rejected. |
| Subclass `SureAPIClient`, add `set_tag_profile` | Inherits error-swallowing `call()` and the GET-retry bug; no control over verification semantics; the class is built for reads. Rejected. |
| Self-contained client for the feature | ~1 module, 3 operations (login, GET devices, PUT+verify). Full control over error taxonomy, verification, retries, logging. No new dependencies. **Chosen.** |
| Replace surepy entirely (own client for reads too) | Would require reimplementing `/me/start` entity model, report/timeline calls, battery math, etc. High regression risk for zero functional gain — `/me/start` already gives us state for free. Rejected. |

The chosen client must **not** import `homeassistant` (aiohttp only, session injected) so
it is unit-testable without HA fixtures (contracts §9).

## 6. Flap-only scoping (decision D3)

`profile` exists on every (device, tag) pair — including the Felaqua. But indoor-only is
a flap concept, and the observed app behavior writes flaps only (Felaqua tags of a
frequently-toggled pet are still at `version: 1`). Therefore:

- State: only tags on **product_id 3/6** devices count.
- Writes: only flap (3/6) devices carrying the pet's tag are written.
- Feeders/Felaqua tag profiles are exposed in switch attributes for transparency but are
  never read for state or written.

## 7. Read-after-write freshness (decision D4)

- The interview's round-trip proved `/device` reflects an accepted write immediately
  (profile + `version` increment readable right after the PUT).
- `/me/start` freshness after a write is **UNVERIFIED** (no write probes allowed for the
  Architect; no observation available). It is the app bootstrap endpoint, so freshness is
  expected but not assumed.
- Consequence (normative in contracts §6): verification reads **`/device`**; the switch's
  post-write display uses the values verified on `/device` (patched into the coordinator
  cache), and the next regular `/me/start` poll reconciles. At no point may the switch
  display a value that was not read back from the cloud.

## 8. HA core component findings (fork baseline)

- Fork base: **home-assistant/core `dev` as of 2026-09-26**. The 7 seeded files are
  **byte-identical** to core dev HEAD (verified by diff; core file list & sizes below).
  HA stable line 2026.9.3; HA requires Python ≥ 3.14.2 (`pyproject.toml`).
- Core component has 13 files; the seed is missing 6: `config_flow.py`, `entity.py`,
  `icons.json`, `lock.py`, `services.yaml`, `strings.json` (+ a `translations/en.json`
  that core does not carry but custom components must ship). The seeded component
  **cannot even import as-is** (`sensor.py`/`binary_sensor.py` import `.entity`, and
  `__init__.py` forwards to `Platform.LOCK`).
- Seeded files contain **PEP 758** syntax (`except KeyError, TypeError:` — valid Python
  ≥ 3.14, syntax error on the host's 3.13). Untouched in the fork; new files use
  parenthesized `except (A, B):`.
- The core manifest has no `version` key (core injects it); a custom component **must**
  add one.
- Entity/unique_id conventions (must be preserved for continuity):
  device id = `{household_id}-{surepy_id}`; pet binary sensor `unique_id = {hh}-{pet_id}`;
  battery `…-battery`; connectivity `…-connectivity`; locks `…-locked_in|locked_out|locked_all`;
  last-seen sensors `…-last_seen_flap_device|…-last_seen_user`. Our switch uses
  `{hh}-{pet_id}-indoor_only` — collision-free.
- Services are registered via the new **`probatio`** schema library (see seeded
  `services.py`), in `async_setup`, resolved to the config entry via
  `service.async_get_config_entry(hass, DOMAIN, None)`. The new service must follow the
  same pattern.
- Config flow stores `username`, `password`, `token` (CONF_TOKEN — effectively dead
  weight given surepy's stale length cap; harmless). Our client uses username/password
  only.
- Core component file inventory (dev @ 2026-09-26, bytes):
  `__init__.py` 1825 · `binary_sensor.py` 5035 · `config_flow.py` 3886 · `const.py` 528 ·
  `coordinator.py` 3477 · `entity.py` 1854 · `icons.json` 142 · `lock.py` 3221 ·
  `manifest.json` 335 · `sensor.py` 6154 · `services.py` 3026 · `services.yaml` 578 ·
  `strings.json` 1825.

## 9. Custom-vs-core domain collision behavior

- HA's integration loader checks `custom_components/` **before** built-ins: a custom
  component with the same domain takes precedence and the core one is not loaded while the
  custom folder exists. This is the mechanism the owner relies on ("drop-in replaces
  core").
- Config entries, device-registry and entity-registry records are keyed by domain +
  `unique_id`s, not by install path — with identical `unique_id`s the existing entities
  attach to the custom integration seamlessly after a restart.
- Caveats (documented in quickstart.md): HA upgrades do not update the fork (manual
  rebase); HA logs the "custom integration not tested by Home Assistant" notice; the
  integration info page shows the manifest `version` (proof the custom one is loaded).