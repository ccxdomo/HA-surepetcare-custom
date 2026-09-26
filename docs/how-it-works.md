# How it works

A short technical page: where the switch state comes from, what happens on a write,
why the switch is write-protected, the API requests the component makes, and the
tag/profile model behind indoor-only.

## Cloud-first state (no optimistic state, ever)

The read backbone is the [surepy](https://github.com/benleb/surepy) library (0.9.0),
exactly as in the core integration. It polls the Sure Petcare bootstrap endpoint

```
GET https://app.api.surehub.io/api/me/start
```

about **every 3 minutes** (the coordinator's poll interval). That single response
already contains everything the switch needs: each pet's chip id (`tag_id`) and each
flap device's list of `(tag, profile, version)` assignments. No extra read traffic is
added for polling.

The indoor-only switch derives its state only from **flap** devices (pet door / cat
flap) that carry the pet's chip:

- `on` ⟺ **every** flap carrying the chip is at the indoor-only profile
- `off` otherwise (per-flap profiles are visible in the `devices` attribute)
- `unavailable` when a poll failed or any of the pet's flaps is offline

Three invariants hold everywhere in the code:

1. The switch state may only ever come from a **successful cloud read** — the regular
   poll, or the verification read after a write.
2. No code path sets or displays state based solely on a write request having been
   accepted.
3. On any write or verification failure, the displayed state stays the last
   cloud-verified state and a coordinator refresh is scheduled.

## What happens on a `set_indoor_only` call

1. **Confirm gate** — `confirm` must be `true`; anything else is rejected before any
   network traffic.
2. **Entity resolution** — each targeted entity id must resolve (via the entity
   registry) to one of this integration's `switch.<pet>_indoor_only` entities.
3. **Offline fail-fast** — if **any** target flap is offline, the whole call fails and
   **nothing is written** (an offline flap has stale cloud state and could not be
   verified).
4. **Verified writes** — for each targeted pet, for each flap carrying its chip (in
   sequence):
   1. `PUT /device/{device_id}/tag/{tag_id}` with body `{"profile": 2|3}`.
   2. **Read-after-write verification**: the component reads the device list back and
      accepts the write **only** when the assignment shows the requested profile
      **and** a `version` strictly greater than before the write (see below). The PUT
      response body is never trusted or parsed.
   3. Verification retries up to **15 attempts spaced 5 seconds apart** (~70 s
      window). This budget was raised during development after live testing showed
      the cloud needs ~10 seconds to reflect an accepted write — the first budget
      (3 × 2 s) was too tight and produced a false failure on a write that landed.
   4. Once verified, the new `profile`/`version` are patched into the coordinator's
      cached payload, so the switch updates **immediately** (no waiting for the next
      poll). The next regular poll then reconciles naturally.
5. **Audit log** — one line per successful call: user, user_id, time, entity id(s),
   pet, chip id, flap name/id, profile before → after, version before → after.

If anything fails mid-sequence, a coordinator refresh is triggered first (so the UI
shows cloud truth), then the error surfaces with a specific message (see
[entities-and-services.md](entities-and-services.md#surepetcareset_indoor_only-this-fork--the-only-way-to-change-the-switch)).

A `version` jump of more than +1 is accepted but logged as a **warning**: it means
someone else (typically the mobile app) wrote between the component's read and write.

## Why the switch is write-protected

The switch drives a **physical door for a living animal**. A stray UI tap, a dashboard
bug or an automation typo could let a pet out at night — or lock it outside. So the
entity refuses to be toggled (the toggle raises an error and issues no API call), and
the only write path is a service that:

- requires an explicit `confirm: true` field (rejected before any API traffic otherwise),
- shows a confirmation dialog in the UI,
- refuses when a flap is offline (it could not verify the result),
- verifies the change against the cloud before displaying it,
- audit-logs who changed what, when, and the before → after values.

This is deliberately more friction than a normal switch. It is the difference between
"toggle a boolean" and "control a pet's access to the outside".

## The write client

The write + verification path is a small self-contained `aiohttp` client
(`api.py`) inside the component — surepy is **not** used for writes, for three
evidence-backed reasons: surepy 0.9.0 silently swallows non-2xx responses (a rejected
write would look like "no data"), it retries a failed PUT as a GET after a 401, and it
rejects current 492-character session tokens with a stale length cap. surepy remains
untouched as the read backbone.

Session model (all in memory, per Home Assistant start):

- a random `device_id` (UUID) is generated at startup and sent as `X-Device-Id`,
- login is **lazy** (the first write triggers it) and re-done **once** if a request
  returns 401, then the failed call is retried exactly once,
- the session token is never written to disk, logs or exceptions.

## API request shapes

Base URL: `https://app.api.surehub.io/api`. The Sure Petcare cloud API is
**undocumented**; these shapes were established by live probing during development
and can change without notice.

Headers sent on every request (credential values are never logged or stored):

```text
Accept: application/json, text/plain, */*
Origin: https://surepetcare.io
Referer: https://surepetcare.io/
Accept-Language: en-US,en-GB;q=0.9
X-Requested-With: com.sureflap.surepetcare
User-Agent: surepy 0.9.0 - https://github.com/benleb/surepy
X-Device-Id: <uuid generated per HA start>
Content-Type: application/json        # requests with a body
Authorization: Bearer <session token> # all calls except login
```

**Login**

```text
POST /auth/login
{"email_address": "<account email>", "password": "<password>", "device_id": "<same uuid as X-Device-Id>"}

200 -> {"data": {"token": "<long-lived bearer token>", ...}}
```

Observed tokens are ~492 chars; the client accepts any printable-ASCII token of at
least 300 chars (no upper bound — see the surepy caveat above).

**Fresh device read (the verification read)**

```text
GET /device?with[]=children&with[]=tags&with[]=control&with[]=status

200 -> {"data": [ <device object>, <device object>, ... ]}
```

Note that `data` is a **list** of device objects, not a mapping — the component scans
it for the device id, then for the chip id inside `device.tags[]`.

**Profile write**

```text
PUT /device/{device_id}/tag/{tag_id}
{"profile": 2 | 3}

2xx -> accepted (response body ignored; acceptance is proven by the verification read)
```

## The tag / profile model

Indoor-only is not a property of the pet or of the flap alone — it lives on the
**(flap, chip) assignment**:

```
Household
├── Hub                 (no profiles)
├── Flap "Front door"
│     ├── assignment {chip A, profile 2|3, version N}
│     └── assignment {chip B, profile 2|3, version M}
├── Felaqua             (chips may appear here too — ignored for indoor-only)
└── Pet "Felix"         (tag_id -> chip A)
```

- `profile 2` = normal access, `profile 3` = indoor only.
- `version` increments on **every accepted change** — it is the persistence proof the
  verification relies on (a write that was not persisted does not bump the version).
- Each pet's chip maps to the pet via `pets[].tag_id` (the API carries the
  association natively; nothing is configured by hand).
- Only flap devices count for state and writes. The observed app behaviour writes
  flaps only (fountain/feeder assignments stay untouched, their `version` never
  moves), and this component mirrors that.

## Where the log lines come from

All audit lines come from the component's coordinator logger
(`custom_components.surepetcare.coordinator`), visible in **Settings → System → Logs**:

- success (INFO): `indoor-only write verified | user=… | user_id=… | at=… |
  entity_id(s)=… | pet=… tag_id=… device=… (id) | profile a->b | version x->y`
- failure (ERROR): `indoor-only write FAILED | … | reason=…`
- refused write (ERROR): `refusing indoor-only write: flap … for pet … is offline`
- setup (INFO): names of pets that got no switch because their chip is on no flap

Never logged: passwords, emails, tokens, or HTTP headers.