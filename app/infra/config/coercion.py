def coerce_positive_int(value, default: int, *, minimum: int = 1, allow_bool: bool = False) -> int:
    if isinstance(value, bool) and not allow_bool:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, normalized)
