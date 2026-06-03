from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login
from app.domains.playback.stats_queries import build_stats_base_filter, get_playback_column_name
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_get_playback_column_name_provider = lambda: get_playback_column_name
_playback_store_provider = lambda: playback_store


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    get_playback_column_name_provider=None,
    playback_store_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _get_playback_column_name_provider
    global _playback_store_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if get_playback_column_name_provider is not None:
        _get_playback_column_name_provider = get_playback_column_name_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider


@router.get("/api/stats/badges")
def api_badges(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where, params = _build_stats_base_filter_provider()(user_id)

        # 🚀 性能优化：一次查询获取所有需要的数据
        client_col = _get_playback_column_name_provider()()
        raw_data = _playback_store_provider().query(f"SELECT DateCreated, PlayDuration, COALESCE({client_col}, DeviceName) as Client, ItemId, ItemName, ItemType FROM PlaybackActivity {where}", params)
        if not raw_data: raw_data = []

        night_c, weekend_c, fish_c, morning_c = 0, 0, 0, 0
        dur_total = 0
        devices = set()
        items = {}
        movies, eps = 0, 0

        for row in raw_data:
            r = dict(row)
            dur = r.get('PlayDuration') or 0
            dur_total += dur

            client = r.get('Client')
            if client: devices.add(client)

            item_id = r.get('ItemId')
            if item_id:
                if item_id not in items: items[item_id] = {'name': r.get('ItemName'), 'c': 0}
                items[item_id]['c'] += 1

            it = r.get('ItemType')
            if it == 'Movie': movies += 1
            elif it == 'Episode': eps += 1

            dc = r.get('DateCreated')
            if dc:
                # 直接解析小时和星期，避免创建 datetime 对象
                try:
                    # 格式: 2024-01-15T14:30:00 或 2024-01-15 14:30:00
                    date_part = dc[:10] if len(dc) >= 10 else ""
                    time_part = dc[11:16] if len(dc) >= 16 else ""

                    if time_part:
                        hour = int(time_part[:2])

                        if 2 <= hour <= 5: night_c += 1
                        if 5 <= hour <= 8: morning_c += 1

                    if date_part:
                        # 计算星期几 (0=周一, 6=周日)
                        from datetime import date as dt_date
                        parts = date_part.split('-')
                        if len(parts) == 3:
                            try:
                                d = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                                weekday = d.weekday()
                                if weekday in (5, 6): weekend_c += 1
                                if weekday in (0, 1, 2, 3, 4) and 9 <= hour <= 17: fish_c += 1
                            except:
                                pass
                except:
                    pass

        badges = []
        if night_c >= 2: badges.append({"id": "night", "name": "深夜修仙", "icon": "fa-moon", "color": "text-indigo-500", "bg": "bg-indigo-100", "desc": "深夜是灵魂最自由的时刻"})
        if weekend_c >= 5: badges.append({"id": "weekend", "name": "周末狂欢", "icon": "fa-champagne-glasses", "color": "text-pink-500", "bg": "bg-pink-100", "desc": "工作日唯唯诺诺，周末重拳出击"})
        if dur_total > 180000: badges.append({"id": "liver", "name": "核心肝帝", "icon": "fa-fire", "color": "text-red-500", "bg": "bg-red-100", "desc": "阅片无数，肝度爆表"})
        if fish_c >= 5: badges.append({"id": "fish", "name": "带薪观影", "icon": "fa-fish", "color": "text-cyan-500", "bg": "bg-cyan-100", "desc": "工作是老板的，快乐是自己的"})
        if morning_c >= 2: badges.append({"id": "morning", "name": "晨练追剧", "icon": "fa-sun", "color": "text-amber-500", "bg": "bg-amber-100", "desc": "比你优秀的人，连看片都比你早"})
        if len(devices) >= 2: badges.append({"id": "device", "name": "全平台制霸", "icon": "fa-gamepad", "color": "text-emerald-500", "bg": "bg-emerald-100", "desc": "手机、平板、电视，哪里都能看"})

        if items:
            loyal = max(items.values(), key=lambda x: x['c'])
            if loyal['c'] >= 3:
                safe_name = str(loyal.get('name') or '未知').split(' - ')[0][:10]
                badges.append({"id": "loyal", "name": "N刷狂魔", "icon": "fa-repeat", "color": "text-teal-500", "bg": "bg-teal-100", "desc": f"对《{safe_name}》爱得深沉"})

        total = movies + eps
        if total > 10:
            if movies / total > 0.6: badges.append({"id": "movie_lover", "name": "电影鉴赏家", "icon": "fa-film", "color": "text-blue-500", "bg": "bg-blue-100", "desc": "沉浸在两小时的艺术光影世界"})
            elif eps / total > 0.6: badges.append({"id": "tv_lover", "name": "追剧狂魔", "icon": "fa-tv", "color": "text-purple-500", "bg": "bg-purple-100", "desc": "一集接一集，根本停不下来"})

        return {"status": "success", "data": badges}
    except Exception as e:
        return {"status": "success", "data": []}
