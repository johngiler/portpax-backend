"""Vessel catalog helpers."""

from __future__ import annotations

import re

from apps.catalogs.models import Vessel

# LTA placeholders often use class names (e.g. "ICON CLASS", "VY CLASS").
_CLASS_PLACEHOLDER = re.compile(r"(?i)\bCLASS\b")


def vessel_is_provisional(vessel: Vessel | None) -> bool:
    """
    Heuristic for LTA ghost / class placeholders (no dedicated flag in catalog).
    True when the name is a class slot, or the vessel sheet lacks class + pax.
    """
    if vessel is None:
        return False
    name = (vessel.name or "").strip()
    if not name:
        return False
    if _CLASS_PLACEHOLDER.search(name):
        return True
    has_class = bool((vessel.vessel_class or "").strip())
    if not has_class and vessel.pax_capacity is None:
        return True
    return False
