"""Constants for the Sure Petcare component."""

DOMAIN = "surepetcare"

CONF_FEEDERS = "feeders"
CONF_FLAPS = "flaps"
CONF_PETS = "pets"

# sure petcare api
SURE_API_TIMEOUT = 60

# flap
SURE_BATT_VOLTAGE_FULL = 1.6  # voltage
SURE_BATT_VOLTAGE_LOW = 1.25  # voltage
SURE_BATT_VOLTAGE_DIFF = SURE_BATT_VOLTAGE_FULL - SURE_BATT_VOLTAGE_LOW

# state service
SERVICE_SET_LOCK_STATE = "set_lock_state"
SERVICE_SET_PET_LOCATION = "set_pet_location"
ATTR_FLAP_ID = "flap_id"
ATTR_LOCK_STATE = "lock_state"
ATTR_PET_NAME = "pet_name"

# indoor-only switch (spec 041, contracts/ha-component.md §4)
SERVICE_SET_INDOOR_ONLY = "set_indoor_only"
ATTR_INDOOR_ONLY = "indoor_only"
ATTR_CONFIRM = "confirm"
ATTR_ENTITY_ID = "entity_id"
PROFILE_NORMAL_ACCESS = 2  # pet can pass both ways
PROFILE_INDOOR_ONLY = 3  # pet kept inside
# Read-after-write verification budget. The contract pinned 3 attempts / 2 s
# on research.md §7's then-unverified assumption that /device reflects a
# PUT immediately. Live evidence (2026-09-26 09:59 CEST, spec 041 QA): a
# 2xx-accepted PUT became readable in /device only ~10 s later (tag
# updated_at 09:59:33 vs PUT ~09:59:22), so the 3x2 s budget raised
# verification_failed on a write that actually landed. 15 attempts spaced
# 5 s apart (~70 s window) keeps the binding verification rule (R6)
# achievable with margin. Deviation documented in
# specs/041-indoor-only-switch/evidence.md.
INDOOR_ONLY_VERIFY_ATTEMPTS = 15
INDOOR_ONLY_VERIFY_RETRY_SECONDS = 5
