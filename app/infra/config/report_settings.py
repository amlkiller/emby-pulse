from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_REPORT_TOP_QUERY_LIMIT_DEFAULT = 300


def get_report_top_query_limit() -> int:
    return coerce_positive_int(
        cfg.get("report_top_query_limit", _REPORT_TOP_QUERY_LIMIT_DEFAULT),
        _REPORT_TOP_QUERY_LIMIT_DEFAULT,
    )
