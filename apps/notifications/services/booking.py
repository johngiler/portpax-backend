from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.accounts.services.user_audit import user_display_name
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services.messages import (
    bulk_booking_message,
    single_booking_message,
)
from apps.notifications.services.recipients import notification_recipients


def _actor_label(user) -> str:
    if user is None:
        return "Sistema"
    label = user_display_name(user).strip()
    return label or user.get_username()


def _history_filter_for_artifact(event: str, artifact: str) -> str:
    if artifact == Notification.Artifact.MASS_IMPORT:
        return "create:mass_import"
    if artifact == Notification.Artifact.LTA_GENERATE:
        return "create:lta_generate"
    if artifact == Notification.Artifact.BERTHING_IMPORT:
        return "create:berthing_import"
    if artifact == Notification.Artifact.MASS_UPDATE:
        return "update:mass_update"
    if artifact == Notification.Artifact.LTA_AGREEMENT:
        return "update:lta_agreement"
    if event in (
        Notification.Event.CREATED,
        Notification.Event.UPDATED,
        Notification.Event.DELETED,
    ):
        return event
    return ""


def _push_notification(notification: Notification) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    payload = NotificationSerializer(notification).data
    async_to_sync(channel_layer.group_send)(
        f"notifications_{notification.recipient_id}",
        {"type": "notification.message", "payload": payload},
    )


def deliver_notification(
    *,
    recipient,
    event: str,
    target: str,
    message: str,
    actor_display: str = "",
    artifact: str = "",
    booking_id: int | None = None,
    booking_code: str = "",
    port_id: int | None = None,
    batch_id: int | None = None,
    affected_count: int = 1,
    history_type_filter: str = "",
) -> Notification:
    notification = Notification.objects.create(
        recipient=recipient,
        event=event,
        artifact=artifact,
        target=target,
        message=message,
        actor_display=actor_display,
        booking_id=booking_id,
        booking_code=booking_code or "",
        port_id=port_id,
        batch_id=batch_id,
        affected_count=max(int(affected_count), 1),
        history_type_filter=history_type_filter,
    )
    _push_notification(notification)
    return notification


def broadcast_to_recipients(
    *,
    recipients,
    event: str,
    target: str,
    message: str,
    actor=None,
    artifact: str = "",
    booking_id: int | None = None,
    booking_code: str = "",
    port_id: int | None = None,
    port_ids: set[int] | None = None,
    batch_id: int | None = None,
    affected_count: int = 1,
    history_type_filter: str = "",
) -> list[Notification]:
    actor_display = _actor_label(actor)
    if not history_type_filter and artifact:
        history_type_filter = _history_filter_for_artifact(event, artifact)

    created: list[Notification] = []
    for recipient in recipients:
        effective_port = port_id
        if effective_port is None and port_ids and len(port_ids) == 1:
            effective_port = next(iter(port_ids))
        created.append(
            deliver_notification(
                recipient=recipient,
                event=event,
                target=target,
                message=message,
                actor_display=actor_display,
                artifact=artifact,
                booking_id=booking_id,
                booking_code=booking_code,
                port_id=effective_port,
                batch_id=batch_id,
                affected_count=affected_count,
                history_type_filter=history_type_filter,
            )
        )
    return created


def notify_booking_created_wizard(booking, *, actor=None) -> None:
    code = booking.booking_code or str(booking.pk)
    recipients = notification_recipients(port_id=booking.port_id)
    broadcast_to_recipients(
        recipients=recipients,
        event=Notification.Event.CREATED,
        artifact=Notification.Artifact.WIZARD,
        target=Notification.Target.BOOKING_DETAIL,
        message=single_booking_message(Notification.Event.CREATED, code),
        actor=actor,
        booking_id=booking.id,
        booking_code=code,
        port_id=booking.port_id,
    )


def notify_booking_updated_detail(booking, *, actor=None) -> None:
    code = booking.booking_code or str(booking.pk)
    recipients = notification_recipients(
        port_id=booking.port_id,
        exclude_user_id=getattr(actor, "pk", None),
    )
    broadcast_to_recipients(
        recipients=recipients,
        event=Notification.Event.UPDATED,
        artifact=Notification.Artifact.WIZARD,
        target=Notification.Target.BOOKING_DETAIL,
        message=single_booking_message(Notification.Event.UPDATED, code),
        actor=actor,
        booking_id=booking.id,
        booking_code=code,
        port_id=booking.port_id,
    )


def notify_booking_deleted(
    *,
    booking_code: str,
    booking_id: int | None,
    port_id: int | None,
    actor=None,
) -> None:
    recipients = notification_recipients(port_id=port_id)
    broadcast_to_recipients(
        recipients=recipients,
        event=Notification.Event.DELETED,
        artifact=Notification.Artifact.WIZARD,
        target=Notification.Target.BOOKING_DETAIL,
        message=single_booking_message(Notification.Event.DELETED, booking_code),
        actor=actor,
        booking_id=booking_id,
        booking_code=booking_code,
        port_id=port_id,
    )


def notify_bookings_bulk_created(
    *,
    count: int,
    port_id: int | None = None,
    port_ids: set[int] | None = None,
    batch_id: int | None,
    artifact: str,
    actor=None,
) -> None:
    if count <= 0:
        return
    recipients = notification_recipients(
        port_id=port_id,
        port_ids=port_ids,
    )
    broadcast_to_recipients(
        recipients=recipients,
        event=Notification.Event.CREATED,
        artifact=artifact,
        target=Notification.Target.BOOKINGS_HISTORY,
        message=bulk_booking_message(Notification.Event.CREATED, count, artifact),
        actor=actor,
        port_id=port_id,
        port_ids=port_ids,
        batch_id=batch_id,
        affected_count=count,
    )


def notify_bookings_bulk_updated(
    *,
    count: int,
    port_id: int | None = None,
    port_ids: set[int] | None = None,
    artifact: str,
    actor=None,
) -> None:
    if count <= 0:
        return
    recipients = notification_recipients(
        port_id=port_id,
        port_ids=port_ids,
    )
    broadcast_to_recipients(
        recipients=recipients,
        event=Notification.Event.UPDATED,
        artifact=artifact,
        target=Notification.Target.BOOKINGS_HISTORY,
        message=bulk_booking_message(Notification.Event.UPDATED, count, artifact),
        actor=actor,
        port_id=port_id,
        port_ids=port_ids,
        affected_count=count,
    )


def notify_booking_conflict(
    booking,
    *,
    event: str,
    actor=None,
) -> None:
    code = booking.booking_code or str(booking.pk)
    recipients = notification_recipients(port_id=booking.port_id)
    broadcast_to_recipients(
        recipients=recipients,
        event=event,
        artifact=Notification.Artifact.CONFLICT,
        target=Notification.Target.BOOKING_DETAIL,
        message=single_booking_message(event, code),
        actor=actor,
        booking_id=booking.id,
        booking_code=code,
        port_id=booking.port_id,
    )


def notify_lta_job(
    *,
    port_id: int | None,
    event: str,
    count: int,
    artifact: str,
    actor=None,
) -> None:
    if count <= 0:
        return
    if event == Notification.Event.CREATED:
        notify_bookings_bulk_created(
            count=count,
            port_id=port_id,
            batch_id=None,
            artifact=artifact,
            actor=actor,
        )
        return
    notify_bookings_bulk_updated(
        count=count,
        port_id=port_id,
        artifact=artifact,
        actor=actor,
    )


def mark_notification_read(notification: Notification) -> Notification:
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification
