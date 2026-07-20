from apps.catalogs.utils.port_scope import filter_qs_for_user_ports


class UserPortScopedQuerysetMixin:
    """Filter list/detail querysets by the requesting user's port access.

    Set ``port_access_field`` to the ORM lookup that resolves to a Port PK
    (e.g. ``\"port_id\"``, ``\"id\"``, ``\"berth__port_id\"``).
    """

    port_access_field = "port_id"

    def get_queryset(self):
        qs = super().get_queryset()
        return filter_qs_for_user_ports(
            qs,
            self.request.user,
            self.port_access_field,
        )
