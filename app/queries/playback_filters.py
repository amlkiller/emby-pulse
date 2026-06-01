from app.infra.config.user_visibility_settings import get_hidden_users


def get_base_filter(user_id_filter):
    where = "WHERE 1=1"
    params = []

    if user_id_filter and user_id_filter != "all":
        where += " AND UserId = ?"
        params.append(user_id_filter)

    hidden = get_hidden_users()
    if (not user_id_filter or user_id_filter == "all") and hidden and len(hidden) > 0:
        placeholders = ",".join(["?"] * len(hidden))
        where += f" AND UserId NOT IN ({placeholders})"
        params.extend(hidden)

    return where, params
