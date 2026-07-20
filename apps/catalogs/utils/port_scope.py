from apps.accounts.permissions import user_port_ids


def filter_qs_for_user_ports(qs, user, port_field: str = "port_id"):
    """Limit a queryset to ports the user may access.

    Admin (user_port_ids → None) sees all rows. Other roles are restricted
    to their UserPortAccess set (empty set → no rows).
    """
    allowed = user_port_ids(user)
    if allowed is None:
        return qs
    return qs.filter(**{f"{port_field}__in": allowed})
