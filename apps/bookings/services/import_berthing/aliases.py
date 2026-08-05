"""Static maps for BERTHING Excel → PortPax catalogs."""

from __future__ import annotations

# Excel file stem / port_key → Port.code
PORT_BY_KEY: dict[str, str] = {
    "pop": "puerto_plata",
    "rtb": "roatan",
    "cbr": "cabo_rojo",
    "paz": "la_paz",
    "sam": "samana",
    "mel": "melilla",
}

# BERTHING PAPERS «BERTH ASSIG» → Position short suffix (catalog uses {port}-{suffix}).
# Papers use legacy P1/P2/P3 labels; PortPax layouts use port-specific codes (E1/N1/…).
BERTH_ALIAS_BY_PORT_CODE: dict[str, dict[str, str]] = {
    "puerto_plata": {"P1": "E1", "P2": "E2", "P3": "W3"},
    "cabo_rojo": {"P1": "N1", "P2": "S2"},
    "samana": {"P1": "S1", "P2": "N2"},
    "melilla": {"N3": "NE3", "P1": "NE2"},
    "la_paz": {"P1": "P1", "P2": "P2"},
    "roatan": {"P1": "P1", "P2": "P2", "A1": "A1", "A2": "A2"},
}

# (filename substring upper, sheet name, port_key, c_means_confirmed)
FILE_SPECS: list[tuple[str, str, str, bool]] = [
    ("BERTHING POP", "TB BOOKING", "pop", False),
    ("BERTHING ROATAN", "RT BOOKING", "rtb", False),
    ("BERTHING CABO ROJO", "CBR BOOKING", "cbr", True),
    ("BERTHING LA PAZ", "PZ BOOKING", "paz", False),
    ("BERTHING SAMANA", "SM BOOKING", "sam", False),
    ("BERTHING MELILLA", "MEL BOOKING", "mel", True),
]

# Brand / corp codes from Excel → ShippingLine.code (catalog)
BRAND_TO_LINE_CODE: dict[str, str] = {
    "RCCL": "royal_caribbean_international",
    "RCI": "royal_caribbean_international",
    "NCL": "norwegian_cruise_line",
    "CEL": "celebrity_cruises",
    "MSC": "msc_cruises",
    "HAL": "holland_america_line",
    "VV": "virgin_voyages",
    "COS": "costa_cruises",
    "CCL": "carnival_cruise_line",
    "AIDA": "aida_cruises",
    "REG": "regent_seven_seas_cruises",
    "OC": "oceania_cruises",
    "EXP": "explora_journeys",
    "DIS": "disney_cruise_line",
    "TUI": "tui_cruises",
    "RITZ": "ritz-carlton_yacht_collection",
    "MARG": "margaritaville_at_sea",
    "PCL": "princess_cruises",
    "PON": "ponant",
    "SS": "silversea_cruises",
    "CRY": "crystal_cruises",
    "VIK": "viking_ocean_cruises",
    "AZA": "azamara",
    "PH": "phoenix_reisen",
    "FO": "fred_olsen",
    "ATLAS": "atlas_ocean_voyages",
    "SAG": "saga_cruises",
    "MAR": "marella_cruises",
    "SB": "seabourn",
    "HLY": "hapag-lloyd_cruises",
    "WS": "windstar_cruises",
    "CUN": "cunard",
}

STATUS_MAP: dict[str, str] = {
    "R": "r",
    "CO": "co",
    "CL": "cl",
    "LTA": "lta",
    "LTD": "ltd",
    "H": "h",
    "NR": "nr",
    "C": "c",  # overridden per file when c_means_confirmed
}
