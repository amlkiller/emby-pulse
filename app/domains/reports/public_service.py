"""Public reports facade for cross-domain callers."""

from app.domains.reports import report_queries
from app.domains.reports import report_service


def count_report_plays(where_sql: str, params):
    return report_queries.count_report_plays(where_sql, params)


def sum_report_duration(where_sql: str, params):
    return report_queries.sum_report_duration(where_sql, params)


def count_report_distinct_users(where_sql: str, params):
    return report_queries.count_report_distinct_users(where_sql, params)


def list_report_top_users(where_sql: str, params, limit: int):
    return report_queries.list_report_top_users(where_sql, params, limit)


def list_report_content_items(where_sql: str, params, limit: int):
    return report_queries.list_report_content_items(where_sql, params, limit)


def has_pillow_support() -> bool:
    return report_service.HAS_PIL


def generate_daily_poster(period, tv_list, movie_list, theme="cinema"):
    return report_service.report_gen.generate_daily_poster(period, tv_list, movie_list, theme)
