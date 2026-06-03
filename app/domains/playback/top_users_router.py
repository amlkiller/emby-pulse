from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import get_user_map_local
from app.domains.playback.stats_queries import build_stats_base_filter
from app.domains.users import public_service as user_service
from app.infra.config.user_visibility_settings import get_hidden_users
from app.infra.db.playback_store import playback_store


router = APIRouter()

_user_service_provider = lambda: user_service
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_playback_store_provider = lambda: playback_store
_get_user_map_local_provider = lambda: get_user_map_local
_get_hidden_users_provider = lambda: get_hidden_users


def set_dependency_providers(
    *,
    user_service_provider=None,
    build_stats_base_filter_provider=None,
    playback_store_provider=None,
    get_user_map_local_provider=None,
    get_hidden_users_provider=None,
):
    global _user_service_provider
    global _build_stats_base_filter_provider
    global _playback_store_provider
    global _get_user_map_local_provider
    global _get_hidden_users_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if get_user_map_local_provider is not None:
        _get_user_map_local_provider = get_user_map_local_provider
    if get_hidden_users_provider is not None:
        _get_hidden_users_provider = get_hidden_users_provider


@router.get("/api/stats/top_users_list")
def api_top_users_list(request: Request, period: str = 'all'):
    # 🔒 安全检查：仅管理员可查看全站用户排名
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        where_base, params = _build_stats_base_filter_provider()('all')
        date_filter = ""

        # 🔥 使用统一的时间计算模块
        from app.shared.time import get_period_range
        start_date, end_date, where_sql, _ = get_period_range(period)

        # 如果有有效的 WHERE 条件，使用它
        if where_sql:
            # 将 WHERE 替换为 AND（因为已有 where_base）
            date_filter = where_sql.replace("WHERE", "AND")
        # 否则使用原有的 SQLite 方式（向后兼容）
        elif period == 'day':
            date_filter = " AND DateCreated >= date('now', 'localtime', 'start of day')"
        elif period == 'week':
            date_filter = " AND DateCreated >= date('now', 'localtime', '-7 days')"
        elif period == 'month':
            date_filter = " AND DateCreated >= date('now', 'localtime', 'start of month')"
        elif period == 'year':
            date_filter = " AND DateCreated >= date('now', 'localtime', 'start of year')"

        sql = f"SELECT UserId, COUNT(*) as Plays, SUM(PlayDuration) as TotalTime FROM PlaybackActivity {where_base} {date_filter} GROUP BY UserId ORDER BY TotalTime DESC LIMIT 10"
        res = _playback_store_provider().query(sql, params)
        if not res: return {"status": "success", "data": []}
        user_map = _get_user_map_local_provider()()
        hidden = _get_hidden_users_provider()()
        # 确保 hidden 中的值是字符串，以便比较
        hidden_str = [str(h) for h in hidden]
        data = []
        for row in res:
            # 统一转换为字符串比较
            if str(row['UserId']) in hidden_str:
                continue
            u = dict(row)
            u['UserName'] = user_map.get(u['UserId'], f"User {str(u['UserId'])[:5]}")
            data.append(u)
            if len(data) >= 5:
                break
        return {"status": "success", "data": data}
    except Exception as e:
        print(f"[Top Users List] Error: {e}")
        return {"status": "error", "data": []}
