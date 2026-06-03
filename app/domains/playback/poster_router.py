import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login, get_clean_name, resolve_poster_ids
from app.domains.playback.stats_queries import build_stats_base_filter
from app.infra.clients.media_server_client import media_api
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_playback_store_provider = lambda: playback_store
_media_api_provider = lambda: media_api
_get_clean_name_provider = lambda: get_clean_name
_resolve_poster_ids_provider = lambda: resolve_poster_ids


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    playback_store_provider=None,
    media_api_provider=None,
    get_clean_name_provider=None,
    resolve_poster_ids_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _playback_store_provider
    global _media_api_provider
    global _get_clean_name_provider
    global _resolve_poster_ids_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if get_clean_name_provider is not None:
        _get_clean_name_provider = get_clean_name_provider
    if resolve_poster_ids_provider is not None:
        _resolve_poster_ids_provider = resolve_poster_ids_provider


@router.get("/api/stats/poster_data")
def api_poster_data(request: Request, user_id: Optional[str] = None, period: str = 'all'):
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
        build_stats_base_filter_fn = _build_stats_base_filter_provider()
        playback_store_obj = _playback_store_provider()

        where_base, params = build_stats_base_filter_fn(user_id)
        date_filter = ""
        # 🔥 时区修复
        if period == 'week': date_filter = " AND DateCreated > date('now', 'localtime', '-7 days')"
        elif period == 'month': date_filter = " AND DateCreated > date('now', 'localtime', '-30 days')"

        server_res = playback_store_obj.query(f"SELECT COUNT(*) as Plays FROM PlaybackActivity {build_stats_base_filter_fn('all')[0]} {date_filter}", build_stats_base_filter_fn('all')[1])
        server_plays = server_res[0]['Plays'] if server_res else 0

        summary = playback_store_obj.query(
            f"SELECT COUNT(*) as plays, COALESCE(SUM(PlayDuration), 0) as duration FROM PlaybackActivity {where_base + date_filter}",
            params,
            one=True,
        )
        total_plays = int(summary['plays'] if summary else 0)
        total_duration = int(summary['duration'] if summary else 0)

        daily_rows = playback_store_obj.query(
            f"""SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as day,
                       COALESCE(SUM(PlayDuration), 0) as duration
                FROM PlaybackActivity {where_base + date_filter}
                GROUP BY day ORDER BY day DESC""",
            params,
        ) or []
        daily_duration = {r['day']: int(r['duration'] or 0) for r in daily_rows if r['day']}

        late_night_record = None
        late_row = playback_store_obj.query(
            f"""SELECT DateCreated, ItemName, ItemType
                FROM PlaybackActivity {where_base + date_filter}
                AND CAST(substr(replace(DateCreated, 'T', ' '), 12, 2) AS INTEGER) BETWEEN 1 AND 5
                ORDER BY substr(replace(DateCreated, 'T', ' '), 12, 8) DESC
                LIMIT 1""",
            params,
            one=True,
        )
        if late_row and late_row.get('DateCreated'):
            dc = late_row.get('DateCreated', '')
            m = re.search(r'T(\d{2}):(\d{2}):(\d{2})', dc) or re.search(r' (\d{2}):(\d{2}):(\d{2})', dc)
            if m:
                late_night_record = {
                    "time": f"{m.group(1)}:{m.group(2)}",
                    "date": dc[:10][5:].replace('-', '月') + '日',
                    "name": _get_clean_name_provider()(late_row.get('ItemName'), late_row.get('ItemType', ''))
                }

        top_rows = playback_store_obj.query(
            f"""SELECT ItemName, ItemId, ItemType, COUNT(*) as Count, COALESCE(SUM(PlayDuration), 0) as Duration
                FROM PlaybackActivity {where_base + date_filter}
                GROUP BY ItemName
                ORDER BY Count DESC
                LIMIT 200""",
            params,
        ) or []
        aggregated = {}
        for row in top_rows:
            row_dict = dict(row)
            clean = _get_clean_name_provider()(row_dict.get('ItemName'), row_dict.get('ItemType', ''))
            if clean not in aggregated:
                aggregated[clean] = {'ItemName': clean, 'ItemId': row_dict['ItemId'], 'Count': 0, 'Duration': 0}
            aggregated[clean]['Count'] += int(row_dict.get('Count') or 0)
            aggregated[clean]['Duration'] += int(row_dict.get('Duration') or 0)

        binge_day = None
        if daily_duration:
            max_day = max(daily_duration, key=daily_duration.get)
            max_dur = daily_duration[max_day]
            if max_dur > 3600:
                binge_day = {"date": max_day[5:].replace('-', '月') + '日', "hours": round(max_dur / 3600, 1)}

        genres = []
        favorite_type = None
        try:
            if user_id and user_id != 'all':
                # 🔥 从当前时间段播放的影片中获取类型（更准确）
                # 先获取这段时间播放过的 ItemId
                item_ids = list({r['ItemId'] for r in top_rows if r.get('ItemId')})[:50]  # 最多50个

                if item_ids:
                    genre_counts = defaultdict(int)
                    for item_id in item_ids:
                        try:
                            item_res = _media_api_provider().get(f"/Users/{user_id}/Items/{item_id}", params={"Fields": "Genres"}, timeout=2)
                            if item_res.status_code == 200:
                                item_data = item_res.json()
                                for g in item_data.get("Genres", []):
                                    genre_counts[g] += 1
                        except:
                            pass

                    if genre_counts:
                        sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                        genres = [k for k, v in sorted_genres]
                        favorite_type = sorted_genres[0][0] if sorted_genres else None
        except Exception: pass

        # 🔥 计算连续观影天数
        streak_days = 0
        if daily_duration:
            sorted_days = sorted(daily_duration.keys(), reverse=True)
            if sorted_days:
                today = datetime.now().strftime('%Y-%m-%d')
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

                # 从今天或昨天开始计算连续天数
                if sorted_days[0] in [today, yesterday]:
                    streak_days = 1
                    for i in range(1, len(sorted_days)):
                        prev_date = datetime.strptime(sorted_days[i-1], '%Y-%m-%d')
                        curr_date = datetime.strptime(sorted_days[i], '%Y-%m-%d')
                        if (prev_date - curr_date).days == 1:
                            streak_days += 1
                        else:
                            break

        # 🔥 构建每日统计数据
        daily_stats = [{"date": k, "duration": v} for k, v in daily_duration.items()]

        top_list = list(aggregated.values()); top_list.sort(key=lambda x: x['Count'], reverse=True)
        top_10 = top_list[:10]
        _resolve_poster_ids_provider()(top_10)

        return {
            "status": "success",
            "data": {
                "plays": total_plays,
                "hours": round(total_duration / 3600),
                "server_plays": server_plays,
                "top_list": top_10,
                "daily_stats": daily_stats,
                "favorite_type": favorite_type,
                "streak_days": streak_days,
                "mood_data": {
                    "late_night": late_night_record,
                    "binge_day": binge_day,
                    "genres": genres
                }
            }
        }
    except: return {"status": "error", "data": {"plays": 0, "hours": 0}}
