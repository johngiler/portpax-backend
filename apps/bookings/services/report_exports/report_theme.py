"""Shared visual theme for ReportsView exports (Excel + PDF).

Single source of truth for palette and typography sizes so every report
keeps the same visual harmony.
"""

from __future__ import annotations

# PortPax / ITM report palette (Excel hex without #; PDF adds #).
NAVY = "1B3A5C"
NAVY_MID = "2E5A8A"
SKY = "D6E8F7"
SKY_LIGHT = "EBF4FC"
WHITE = "FFFFFF"
GROWTH_POS = "15803D"
GROWTH_NEG = "DC2626"
MUTED = "64748B"
TEXT = "1E293B"
GRID = "CBD5E1"

# Typography (pt) — Calibri in Excel; Helvetica family in PDF.
FONT_FAMILY_XLSX = "Calibri"
TITLE_SIZE = 14
SUBTITLE_SIZE = 11
SECTION_SIZE = 11
HEADER_SIZE = 10
BODY_SIZE = 10
NOTE_SIZE = 9
PDF_TABLE_SIZE = 7
