from __future__ import annotations

from apps.notifications.models import Notification


ORIGIN_LABELS: dict[str, str] = {
    Notification.Artifact.MASS_IMPORT: "importación masiva",
    Notification.Artifact.LTA_GENERATE: "acuerdos LTA",
    Notification.Artifact.LTA_AGREEMENT: "acuerdos LTA",
    Notification.Artifact.MASS_UPDATE: "edición masiva",
    Notification.Artifact.BERTHING_IMPORT: "BERTHING PAPERS",
}


def single_booking_message(event: str, booking_code: str) -> str:
    code = booking_code or "—"
    if event == Notification.Event.CREATED:
        return f"Se creó la reserva {code}"
    if event == Notification.Event.DELETED:
        return f"Se eliminó la reserva {code}"
    if event == Notification.Event.CONFLICT_DETECTED:
        return f"La reserva {code} tiene conflictos operativos"
    if event == Notification.Event.CONFLICT_RESOLVED:
        return f"Se resolvieron los conflictos de la reserva {code}"
    if event == Notification.Event.CONFLICT_UPDATED:
        return f"Se actualizaron los conflictos de la reserva {code}"
    return f"Se modificó la reserva {code}"


def bulk_booking_message(
    event: str,
    count: int,
    artifact: str,
) -> str:
    origin = ORIGIN_LABELS.get(artifact, artifact)
    n = max(int(count), 1)
    if event == Notification.Event.CREATED:
        verb = "crearon" if n != 1 else "creó"
        noun = "reservas" if n != 1 else "reserva"
        return f"Se {verb} {n} {noun} · {origin}"
    if event == Notification.Event.DELETED:
        verb = "eliminaron" if n != 1 else "eliminó"
        noun = "reservas" if n != 1 else "reserva"
        return f"Se {verb} {n} {noun} · {origin}"
    verb = "modificaron" if n != 1 else "modificó"
    noun = "reservas" if n != 1 else "reserva"
    return f"Se {verb} {n} {noun} · {origin}"
