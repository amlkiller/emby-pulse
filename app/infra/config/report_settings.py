from app.core.config import cfg


def get_report_top_query_limit() -> int:
    return int(cfg.get("report_top_query_limit") or 300)
