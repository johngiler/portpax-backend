from decimal import Decimal

# Max allowed LOA overhang beyond position max (m) — minuta ~30 m.
MAX_OVERHANG_M = Decimal("30.00")

# Operational / planned occupancy (excludes Real and Cancelled).
ACTIVE_BOOKING_STATUSES = ("nr", "h", "co")

# Same-day position conflicts: include Real (berth was used that day).
OCCUPATION_CONFLICT_STATUSES = ("nr", "h", "co", "r")

# Minimum gap between non-overlapping windows on the same position (hours).
ETA_CLOSE_GAP_HOURS = 2
