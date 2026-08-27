"""Async LTA booking association jobs."""

from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from apps.audit.services.record import record_lta_audit
from apps.bookings.models import LongTermAgreement
from apps.bookings.services.lta.link_bookings import (
    link_matching_bookings,
    resync_agreement_bookings,
    unlink_agreement_bookings,
)
from apps.bookings.services.lta.lta_audit import snapshot_lta

logger = logging.getLogger(__name__)
User = get_user_model()


def _actor(user_id: int | None):
    if user_id is None:
        return None
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None


def _load_agreement(agreement_id: int) -> LongTermAgreement | None:
    try:
        return (
            LongTermAgreement.objects.select_related("port", "shipping_line")
            .prefetch_related("vessels", "positions")
            .get(pk=agreement_id)
        )
    except LongTermAgreement.DoesNotExist:
        return None


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    name="bookings.lta_link_matching",
)
def lta_link_matching(self, agreement_id: int, user_id: int | None = None):
    """Link unmatched bookings that match this agreement (create / link-bookings)."""
    task_id = self.request.id or ""
    actor = _actor(user_id)
    agreement = _load_agreement(agreement_id)
    if agreement is None:
        record_lta_audit(
            action="link_bookings",
            summary="Vinculación LTA fallida: acuerdo no encontrado",
            agreement=None,
            agreement_code="",
            changes={
                "job_status": "failed",
                "job_kind": "link",
                "task_id": task_id,
                "error": f"Acuerdo id={agreement_id} no existe.",
            },
            actor=actor,
        )
        return {"ok": False, "error": "missing_agreement"}

    try:
        result = link_matching_bookings(agreement, user=actor)
        linked = int(result.get("linked") or 0)
        skipped = int(result.get("skipped") or 0)
        record_lta_audit(
            action="link_bookings",
            summary=(
                f"Vinculación LTA completada ({agreement.code}): "
                f"{linked} vinculadas, {skipped} omitidas"
            ),
            agreement=agreement,
            changes={
                "job_status": "success",
                "job_kind": "link",
                "task_id": task_id,
                "linked": linked,
                "skipped": skipped,
                "agreement_code": agreement.code,
            },
            actor=actor,
            entity=snapshot_lta(agreement),
        )
        return {"ok": True, "linked": linked, "skipped": skipped}
    except Exception as exc:
        logger.exception("lta_link_matching failed agreement_id=%s", agreement_id)
        record_lta_audit(
            action="link_bookings",
            summary=f"Vinculación LTA fallida ({agreement.code})",
            agreement=agreement,
            changes={
                "job_status": "failed",
                "job_kind": "link",
                "task_id": task_id,
                "error": str(exc)[:500],
                "agreement_code": agreement.code,
            },
            actor=actor,
            entity=snapshot_lta(agreement),
        )
        raise


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    name="bookings.lta_resync_agreement",
)
def lta_resync_agreement(self, agreement_id: int, user_id: int | None = None):
    """Set-diff rematch after agreement update."""
    task_id = self.request.id or ""
    actor = _actor(user_id)
    agreement = _load_agreement(agreement_id)
    if agreement is None:
        record_lta_audit(
            action="link_bookings",
            summary="Re-sincronización LTA fallida: acuerdo no encontrado",
            agreement=None,
            changes={
                "job_status": "failed",
                "job_kind": "resync",
                "task_id": task_id,
                "error": f"Acuerdo id={agreement_id} no existe.",
            },
            actor=actor,
        )
        return {"ok": False, "error": "missing_agreement"}

    try:
        result = resync_agreement_bookings(agreement, user=actor)
        linked = int(result.get("linked") or 0)
        unlinked = int(result.get("unlinked") or 0)
        skipped = int(result.get("skipped") or 0)
        kept = int(result.get("kept") or 0)
        record_lta_audit(
            action="link_bookings",
            summary=(
                f"Re-sincronización LTA completada ({agreement.code}): "
                f"+{linked} / −{unlinked} / ={kept}"
            ),
            agreement=agreement,
            changes={
                "job_status": "success",
                "job_kind": "resync",
                "task_id": task_id,
                "linked": linked,
                "unlinked_bookings": unlinked,
                "skipped": skipped,
                "kept": kept,
                "agreement_code": agreement.code,
            },
            actor=actor,
            entity=snapshot_lta(agreement),
        )
        return {
            "ok": True,
            "linked": linked,
            "unlinked": unlinked,
            "kept": kept,
        }
    except Exception as exc:
        logger.exception("lta_resync_agreement failed agreement_id=%s", agreement_id)
        record_lta_audit(
            action="link_bookings",
            summary=f"Re-sincronización LTA fallida ({agreement.code})",
            agreement=agreement,
            changes={
                "job_status": "failed",
                "job_kind": "resync",
                "task_id": task_id,
                "error": str(exc)[:500],
                "agreement_code": agreement.code,
            },
            actor=actor,
            entity=snapshot_lta(agreement),
        )
        raise


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    name="bookings.lta_destroy_agreement",
)
def lta_destroy_agreement(self, agreement_id: int, user_id: int | None = None):
    """Unlink all bookings then delete the agreement."""
    task_id = self.request.id or ""
    actor = _actor(user_id)
    agreement = _load_agreement(agreement_id)
    if agreement is None:
        record_lta_audit(
            action="deleted",
            summary="Eliminación LTA fallida: acuerdo no encontrado",
            agreement=None,
            changes={
                "job_status": "failed",
                "job_kind": "destroy",
                "task_id": task_id,
                "error": f"Acuerdo id={agreement_id} no existe.",
            },
            actor=actor,
        )
        return {"ok": False, "error": "missing_agreement"}

    snap = snapshot_lta(agreement)
    code = snap.get("code") or agreement.code
    try:
        unlink = unlink_agreement_bookings(agreement, user=actor)
        unlinked = int(unlink.get("unlinked") or 0)
        agreement.delete()
        record_lta_audit(
            action="deleted",
            summary=f"Eliminó el acuerdo {code} (−{unlinked} vínculos)",
            agreement=None,
            agreement_code=code,
            agreement_name=snap.get("name") or "",
            port_id=snap.get("port_id"),
            port_code=snap.get("port_code") or "",
            shipping_line_code=snap.get("shipping_line_code") or "",
            changes={
                "job_status": "success",
                "job_kind": "destroy",
                "task_id": task_id,
                "deleted": snap,
                "unlinked_bookings": unlinked,
            },
            actor=actor,
            entity=snap,
        )
        return {"ok": True, "unlinked": unlinked}
    except Exception as exc:
        logger.exception("lta_destroy_agreement failed agreement_id=%s", agreement_id)
        record_lta_audit(
            action="deleted",
            summary=f"Eliminación LTA fallida ({code})",
            agreement=agreement if LongTermAgreement.objects.filter(pk=agreement_id).exists() else None,
            agreement_code=code,
            agreement_name=snap.get("name") or "",
            port_id=snap.get("port_id"),
            port_code=snap.get("port_code") or "",
            shipping_line_code=snap.get("shipping_line_code") or "",
            changes={
                "job_status": "failed",
                "job_kind": "destroy",
                "task_id": task_id,
                "error": str(exc)[:500],
                "deleted": snap,
            },
            actor=actor,
            entity=snap,
        )
        raise
