"""Date-only LTA exceptions (include / skip / reschedule) on top of the rule grid."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

KIND_INCLUDE = "include"
KIND_SKIP = "skip"
KIND_RESCHEDULE = "reschedule"
VALID_KINDS = frozenset({KIND_INCLUDE, KIND_SKIP, KIND_RESCHEDULE})


class DateExceptionError(ValueError):
    """Invalid exception payload."""


def _parse_iso(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise DateExceptionError(f"Fecha inválida: {value!r}.") from exc


def _iso(value: date) -> str:
    return value.isoformat()


@dataclass(frozen=True)
class DateExceptionSets:
    skipped: frozenset[date]
    extras: frozenset[date]
    reschedule_from: dict[date, date]


def normalize_date_exceptions(raw: Any) -> list[dict[str, str]]:
    """Validate and canonicalize the JSON list stored on the agreement."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise DateExceptionError("Las excepciones deben ser una lista.")

    skipped: set[date] = set()
    extras: set[date] = set()
    from_dates: set[date] = set()
    to_dates: set[date] = set()
    out: list[dict[str, str]] = []

    for item in raw:
        if not isinstance(item, dict):
            raise DateExceptionError("Cada excepción debe ser un objeto.")
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in VALID_KINDS:
            raise DateExceptionError(
                "Tipo de excepción no válido (include, skip o reschedule)."
            )
        if kind == KIND_RESCHEDULE:
            src = _parse_iso(item.get("from") or item.get("from_date"))
            dest = _parse_iso(item.get("to") or item.get("to_date") or item.get("date"))
            if src == dest:
                raise DateExceptionError(
                    "Reprogramar requiere una fecha distinta a la de la regla."
                )
            if src in from_dates or src in skipped:
                raise DateExceptionError(
                    f"La fecha {_iso(src)} ya tiene una excepción."
                )
            if dest in extras or dest in to_dates:
                raise DateExceptionError(
                    f"La fecha {_iso(dest)} ya está incluida o reprogramada."
                )
            from_dates.add(src)
            to_dates.add(dest)
            extras.add(dest)
            skipped.add(src)
            out.append({"kind": KIND_RESCHEDULE, "from": _iso(src), "to": _iso(dest)})
            continue

        day = _parse_iso(item.get("date"))
        if kind == KIND_SKIP:
            if day in skipped or day in from_dates:
                raise DateExceptionError(f"La fecha {_iso(day)} ya tiene una excepción.")
            skipped.add(day)
            out.append({"kind": KIND_SKIP, "date": _iso(day)})
        else:
            if day in extras or day in to_dates:
                raise DateExceptionError(
                    f"La fecha {_iso(day)} ya está incluida o reprogramada."
                )
            extras.add(day)
            out.append({"kind": KIND_INCLUDE, "date": _iso(day)})

    plain_skips = skipped - from_dates
    overlap = plain_skips & extras
    if overlap:
        day = min(overlap)
        raise DateExceptionError(
            f"La fecha {_iso(day)} no puede omitirse e incluirse a la vez."
        )

    out.sort(
        key=lambda row: (
            row["kind"],
            row.get("from") or row.get("date") or "",
            row.get("to") or "",
        )
    )
    return out


def exception_sets(agreement) -> DateExceptionSets:
    skipped: set[date] = set()
    extras: set[date] = set()
    reschedule_from: dict[date, date] = {}
    for item in agreement.date_exceptions or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        try:
            if kind == KIND_RESCHEDULE:
                src = _parse_iso(item.get("from"))
                dest = _parse_iso(item.get("to"))
                skipped.add(src)
                extras.add(dest)
                reschedule_from[src] = dest
            elif kind == KIND_SKIP:
                skipped.add(_parse_iso(item.get("date")))
            elif kind == KIND_INCLUDE:
                extras.add(_parse_iso(item.get("date")))
        except DateExceptionError:
            continue
    return DateExceptionSets(
        skipped=frozenset(skipped),
        extras=frozenset(extras),
        reschedule_from=reschedule_from,
    )


def agreement_covers_call_date(agreement, call_date: date) -> bool:
    """Weekday + cadence, with skip / include / reschedule overrides."""
    from apps.bookings.services.lta.matching import (
        agreement_covers_cadence,
        agreement_covers_weekday,
    )

    sets = exception_sets(agreement)
    if call_date in sets.skipped:
        return False
    if call_date in sets.extras:
        return True
    return agreement_covers_weekday(agreement, call_date) and agreement_covers_cadence(
        agreement, call_date
    )


def apply_date_exceptions(
    agreement,
    rule_dates: list[date],
    *,
    extra_ok,
) -> list[date]:
    """
    Rule dates minus skips/reschedule-from, plus includes/reschedule-to
    that pass `extra_ok` (validity / A1 zone).
    """
    sets = exception_sets(agreement)
    out = {d for d in rule_dates if d not in sets.skipped}
    for extra in sets.extras:
        if extra_ok(extra):
            out.add(extra)
    return sorted(out)


def build_date_preview(agreement, today: date | None = None) -> dict[str, Any]:
    """Operator preview: rule grid + how exceptions rewrite the effective set."""
    from apps.bookings.services.lta.generate_dates import (
        agreement_in_lta_zone_only,
        iter_agreement_candidate_dates,
    )
    from apps.bookings.services.lta.matching import agreement_covers_validity

    today = today or date.today()
    rule_dates = iter_agreement_candidate_dates(agreement, today)
    sets = exception_sets(agreement)

    def extra_ok(day: date) -> bool:
        return agreement_covers_validity(agreement, day) and agreement_in_lta_zone_only(
            agreement, day, today
        )

    rows: list[dict[str, Any]] = []
    consumed_extras: set[date] = set()

    for rule_date in rule_dates:
        if rule_date in sets.reschedule_from:
            dest = sets.reschedule_from[rule_date]
            consumed_extras.add(dest)
            rows.append(
                {
                    "iso": dest.isoformat(),
                    "from_iso": rule_date.isoformat(),
                    "source": KIND_RESCHEDULE,
                    "active": extra_ok(dest),
                    "in_zone": extra_ok(dest),
                }
            )
            continue
        if rule_date in sets.skipped:
            rows.append(
                {
                    "iso": rule_date.isoformat(),
                    "from_iso": None,
                    "source": KIND_SKIP,
                    "active": False,
                    "in_zone": True,
                }
            )
            continue
        rows.append(
            {
                "iso": rule_date.isoformat(),
                "from_iso": None,
                "source": "rule",
                "active": True,
                "in_zone": True,
            }
        )

    for extra in sorted(sets.extras - consumed_extras):
        rows.append(
            {
                "iso": extra.isoformat(),
                "from_iso": None,
                "source": KIND_INCLUDE,
                "active": extra_ok(extra),
                "in_zone": extra_ok(extra),
            }
        )

    rows.sort(key=lambda row: row["iso"])
    effective = [
        date.fromisoformat(row["iso"])
        for row in rows
        if row["active"]
    ]
    return {
        "rule_dates": [d.isoformat() for d in rule_dates],
        "effective_dates": [d.isoformat() for d in effective],
        "rule_count": len(rule_dates),
        "effective_count": len(effective),
        "exception_count": len(agreement.date_exceptions or []),
        "rows": rows,
        "date_exceptions": list(agreement.date_exceptions or []),
    }
