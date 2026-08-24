from decimal import Decimal

# Max allowed LOA overhang beyond position max (m) — minuta ~30 m.
MAX_OVERHANG_M = Decimal("30.00")

# Operational / planned occupancy (excludes Real and Cancelled).
ACTIVE_BOOKING_STATUSES = ("nr", "h", "co", "cl", "lta", "ltd")

# Same-day position conflicts: include Real (berth was used that day).
OCCUPATION_CONFLICT_STATUSES = ("nr", "h", "co", "cl", "lta", "ltd", "r")

# LTA horizon / covered-window without agreement: soft-fail when creating Hold.
LTA_SOFT_FAIL_CODES = frozenset(
    {"lta_beyond_horizon", "lta_horizon_denied", "lta_policy_denied"}
)

# Minimum gap between non-overlapping windows on the same position (hours).
ETA_CLOSE_GAP_HOURS = 2

# Search window (±days) when comparing multi-port itineraries (geo proximity).
MAX_GEO_PROXIMITY_WINDOW_DAYS = 3
