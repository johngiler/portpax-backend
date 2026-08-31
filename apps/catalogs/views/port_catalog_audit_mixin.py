from __future__ import annotations

from apps.catalogs.services.port_catalog_audit.record import record_port_child_audit


class PortCatalogAuditMixin:
    """Record port-scoped catalog CRUD in PortAuditEntry."""

    port_audit_resource: str = ""
    port_audit_label: str = ""

    def resolve_audit_port(self, instance):
        return instance.port

    def get_port_audit_snapshot(self, instance) -> dict:
        raise NotImplementedError

    def get_port_audit_diff(self, before: dict, after: dict) -> dict:
        raise NotImplementedError

    def get_port_audit_entity(self, snap: dict) -> dict:
        raise NotImplementedError

    def get_port_audit_identifier(self, snap: dict) -> str:
        return (
            snap.get("short_code")
            or snap.get("name")
            or snap.get("code")
            or snap.get("caption")
            or str(snap.get("id", ""))
        )

    def _port_audit_action(self, verb: str) -> str:
        return f"{self.port_audit_resource}_{verb}"

    def _port_audit_port_label(self, snap: dict) -> str:
        name = (snap.get("port_name") or "").strip()
        code = (snap.get("port_code") or "").strip()
        return name or code

    def _port_audit_summary(self, verb: str, snap: dict) -> str:
        identifier = self.get_port_audit_identifier(snap)
        labels = {
            "created": "Creó",
            "updated": "Modificó",
            "deleted": "Eliminó",
        }
        prefix = labels.get(verb, verb)
        base = f"{prefix} {self.port_audit_label} {identifier}"
        port_label = self._port_audit_port_label(snap)
        if port_label:
            return f"{base} en {port_label}"
        return base

    def perform_create(self, serializer):
        instance = serializer.save()
        snap = self.get_port_audit_snapshot(instance)
        port = self.resolve_audit_port(instance)
        record_port_child_audit(
            action=self._port_audit_action("created"),
            summary=self._port_audit_summary("created", snap),
            port=port,
            changes={"created": snap},
            entity=self.get_port_audit_entity(snap),
            actor=self.request.user,
            request=self.request,
        )

    def perform_update(self, serializer):
        before = self.get_port_audit_snapshot(serializer.instance)
        instance = serializer.save()
        after = self.get_port_audit_snapshot(instance)
        changes = self.get_port_audit_diff(before, after)
        if changes:
            port = self.resolve_audit_port(instance)
            record_port_child_audit(
                action=self._port_audit_action("updated"),
                summary=self._port_audit_summary("updated", after),
                port=port,
                changes=changes,
                entity=self.get_port_audit_entity(after),
                actor=self.request.user,
                request=self.request,
            )

    def perform_destroy(self, instance):
        port = self.resolve_audit_port(instance)
        snap = self.get_port_audit_snapshot(instance)
        record_port_child_audit(
            action=self._port_audit_action("deleted"),
            summary=self._port_audit_summary("deleted", snap),
            port=port,
            changes={"deleted": snap},
            entity=self.get_port_audit_entity(snap),
            actor=self.request.user,
            request=self.request,
        )
        instance.delete()
