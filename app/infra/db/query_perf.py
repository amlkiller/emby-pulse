import datetime
import logging
from collections import deque

from app.infra.config.db_settings import get_slow_query_ms

logger = logging.getLogger("uvicorn")

_slow_queries = deque(maxlen=50)
_query_stats = {
    "total": 0,
    "select": 0,
    "slow": 0,
    "large_result": 0,
}

def record_query_perf(query: str, elapsed_ms: float, row_count: int = 0) -> None:
    _query_stats["total"] += 1
    if query.strip().upper().startswith("SELECT"):
        _query_stats["select"] += 1
    if row_count >= 1000:
        _query_stats["large_result"] += 1

    slow_ms = get_slow_query_ms()
    if elapsed_ms >= slow_ms:
        _query_stats["slow"] += 1
        normalized = " ".join(query.strip().split())
        _slow_queries.append(
            {
                "elapsed_ms": round(elapsed_ms, 1),
                "rows": row_count,
                "sql": normalized[:300],
                "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        logger.warning(f"[慢查询] {elapsed_ms:.1f}ms rows={row_count} sql={normalized[:180]}")


def get_query_perf_stats():
    return {
        **_query_stats,
        "slow_query_ms": get_slow_query_ms(),
        "recent_slow_queries": list(_slow_queries),
    }
