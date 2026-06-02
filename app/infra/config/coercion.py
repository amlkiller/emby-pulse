def coerce_positive_int(
    value,
    default: int,
    *,
    minimum: int = 1,
    maximum: int = None,
    allow_bool: bool = False,
) -> int:
    if isinstance(value, bool) and not allow_bool:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    normalized = max(minimum, normalized)
    if maximum is not None:
        normalized = min(normalized, maximum)
    return normalized
