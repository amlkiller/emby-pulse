import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login, get_clean_name, resolve_poster_ids
from app.domains.playback.stats_queries import build_stats_base_filter
from app.infra.db.playback_store import playback_store


logger = logging.getLogger("uvicorn")
router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_playback_store_provider = lambda: playback_store
_get_clean_name_provider = lambda: get_clean_name
_resolve_poster_ids_provider = lambda: resolve_poster_ids
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    playback_store_provider=None,
    get_clean_name_provider=None,
    resolve_poster_ids_provider=None,
    logger_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _playback_store_provider
    global _get_clean_name_provider
    global _resolve_poster_ids_provider
    global _logger_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if get_clean_name_provider is not None:
        _get_clean_name_provider = get_clean_name_provider
    if resolve_poster_ids_provider is not None:
        _resolve_poster_ids_provider = resolve_poster_ids_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


@router.get("/api/stats/top_movies")
def api_top_movies(request: Request = None, user_id: Optional[str] = None, category: str = 'all', sort_by: str = 'count', exclude_types: Optional[str] = None, period: str = 'all'):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    if request:
        admin_user = request.session.get("user", {})
        req_user = request.session.get("req_user", {})
        is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

        if not is_admin:
            if req_user:
                user_id = req_user.get("Id")
            elif admin_user:
                user_id = admin_user.get("id")

    """
    获取播放排行

    Args:
        user_id: 用户ID，'all' 表示全服
        category: 类型过滤，'all'/'Movie'/'Episode'
        sort_by: 排序方式，'count' 按播放量，'time' 按时长
        exclude_types: 排除的媒体类型，逗号分隔，如 'Audio,MusicVideo'
        period: 时间维度，'today'/'week'/'month'/'quarter'/'year'/'all'
    """
    try:
        where, params = _build_stats_base_filter_provider()(user_id)

        # 🔥 时间维度筛选 - 使用 SQLite 原生日期函数确保时区一致
        if period == 'today':
            where += " AND DateCreated >= date('now', 'localtime', 'start of day')"
        elif period == 'week':
            where += " AND DateCreated >= date('now', 'localtime', '-7 days')"
        elif period == 'month':
            where += " AND DateCreated >= date('now', 'localtime', 'start of month')"
        elif period == 'quarter':
            # SQLite 没有季度函数，使用 Python 计算
            now = datetime.datetime.now()
            quarter_month = ((now.month - 1) // 3) * 3 + 1
            quarter_start = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            where += " AND DateCreated >= ?"
            params.append(quarter_start.strftime('%Y-%m-%d'))
        elif period == 'year':
            where += " AND DateCreated >= date('now', 'localtime', 'start of year')"

        if category == 'Movie': where += " AND ItemType = 'Movie'"
        elif category == 'Episode': where += " AND ItemType = 'Episode'"

        # 排除指定媒体类型
        if exclude_types:
            excluded = [t.strip() for t in exclude_types.split(',') if t.strip()]
            if excluded:
                placeholders = ','.join(['?' for _ in excluded])
                where += f" AND ItemType NOT IN ({placeholders})"
                params.extend(excluded)  # params 是列表，用 extend

        sql = f"SELECT ItemName, ItemId, ItemType, PlayDuration FROM PlaybackActivity {where} LIMIT 5000"
        _logger_provider().debug(f"[api_top_movies] SQL: {sql}, params: {params}")
        rows = _playback_store_provider().query(sql, params)
        _logger_provider().debug(f"[api_top_movies] 查询结果数量: {len(rows) if rows else 0}")

        aggregated = {}
        if rows:
            for row in rows:
                row_dict = dict(row)
                clean = _get_clean_name_provider()(row_dict.get('ItemName'), row_dict.get('ItemType', ''))
                if clean not in aggregated: aggregated[clean] = {'ItemName': clean, 'ItemId': row_dict['ItemId'], 'PlayCount': 0, 'TotalTime': 0}
                aggregated[clean]['PlayCount'] += 1; aggregated[clean]['TotalTime'] += (row_dict['PlayDuration'] or 0)

        _logger_provider().debug(f"[api_top_movies] 聚合后数量: {len(aggregated)}")

        res = list(aggregated.values())
        res.sort(key=lambda x: x['TotalTime'] if sort_by == 'time' else x['PlayCount'], reverse=True)
        top_50 = res[:50]

        # 🔥 打印 resolve_poster_ids 调用前的 ItemIds
        _logger_provider().debug(f"[api_top_movies] resolve_poster_ids 调用前 ItemIds: {[x['ItemId'] for x in top_50[:5]]}")
        _resolve_poster_ids_provider()(top_50)
        _logger_provider().debug(f"[api_top_movies] resolve_poster_ids 调用后 ItemIds: {[x['ItemId'] for x in top_50[:5]]}")

        _logger_provider().debug(f"[api_top_movies] 最终返回: {len(top_50)} 条")
        return {"status": "success", "data": top_50}
    except Exception as e:
        _logger_provider().error(f"[api_top_movies] 异常: {e}")
        return {"status": "error", "data": []}
