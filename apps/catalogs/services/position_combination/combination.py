from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.catalogs.models import Position, PositionComponent, PositionType


def position_is_combined(position: Position) -> bool:
    if hasattr(position, "_prefetched_component_links"):
        return bool(position._prefetched_component_links)
    return position.component_links.exists()


def validate_component_ids(
    *,
    port_id: int,
    component_ids: list[int],
    combined_position_id: int | None = None,
) -> list[Position]:
    if len(component_ids) != 2:
        raise ValidationError("Una posición combinada requiere exactamente dos posiciones base.")

    if len(set(component_ids)) != 2:
        raise ValidationError("Las dos posiciones base deben ser distintas.")

    sources = list(
        Position.objects.filter(id__in=component_ids, port_id=port_id).select_related("port")
    )
    if len(sources) != 2:
        raise ValidationError("Las posiciones base deben existir y pertenecer al mismo puerto.")

    for source in sources:
        if source.id == combined_position_id:
            raise ValidationError("Una posición no puede combinarse consigo misma.")
        if source.position_type != PositionType.PIER:
            raise ValidationError(
                f"Solo posiciones de muelle pueden combinarse ({source.code} no es muelle)."
            )
        if position_is_combined(source):
            raise ValidationError(
                f"{source.code} ya es una posición combinada y no puede usarse como base."
            )

    return sorted(sources, key=lambda p: component_ids.index(p.id))


def derive_combined_defaults(first: Position, second: Position) -> dict:
    """Suggested catalog values when spanning two pier slots for one vessel."""

    def _sum_int(a: int | None, b: int | None) -> int | None:
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    def _sum_decimal(a: Decimal | None, b: Decimal | None) -> Decimal | None:
        if a is None and b is None:
            return None
        return (a or Decimal("0")) + (b or Decimal("0"))

    def _min_decimal(a: Decimal | None, b: Decimal | None) -> Decimal | None:
        values = [v for v in (a, b) if v is not None]
        return min(values) if values else None

    berth_ids = {first.berth_id, second.berth_id}
    berth_id = first.berth_id if first.berth_id == second.berth_id else None

    return {
        "code": f"{first.code}+{second.code}",
        "position_type": PositionType.PIER,
        "berth": berth_id,
        "max_loa_m": _sum_decimal(first.max_loa_m, second.max_loa_m),
        "min_draft_m": _min_decimal(first.min_draft_m, second.min_draft_m),
        "bollard_count": _sum_int(first.bollard_count, second.bollard_count),
        "fender_count": _sum_int(first.fender_count, second.fender_count),
        "notes": "",
        "_distinct_berths": len([b for b in berth_ids if b is not None]) > 1,
    }


def sync_position_components(
    combined_position: Position,
    sources: list[Position],
) -> None:
    PositionComponent.objects.filter(combined_position=combined_position).delete()
    PositionComponent.objects.bulk_create(
        [
            PositionComponent(
                combined_position=combined_position,
                source_position=source,
                sort_order=index,
            )
            for index, source in enumerate(sources, start=1)
        ]
    )


def clear_position_components(combined_position: Position) -> None:
    PositionComponent.objects.filter(combined_position=combined_position).delete()
