from fastapi import APIRouter, Request
from typing import Optional
from app.domains.playback import dashboard_cache_service
from app.domains.playback.latest_router import (
    api_latest_media,
    router as latest_router,
    set_dependency_providers as set_latest_dependency_providers,
)
from app.domains.playback.live_router import (
    api_live_sessions,
    api_live_sessions_legacy,
    router as live_router,
    set_dependency_providers as set_live_dependency_providers,
)
from app.domains.playback.top_movies_router import (
    api_top_movies,
    router as top_movies_router,
    set_dependency_providers as set_top_movies_dependency_providers,
)
from app.domains.playback.user_details_router import (
    api_user_details,
    router as user_details_router,
    set_dependency_providers as set_user_details_dependency_providers,
)
from app.domains.playback.libraries_router import (
    api_get_libraries,
    router as libraries_router,
    set_dependency_providers as set_libraries_dependency_providers,
)
from app.domains.playback.stats_helpers import (
    STATS_CACHE_TTL,
    _stats_cache,
    check_login,
    get_admin_user_id,
    get_cached_stats,
    get_clean_name,
    get_user_map_local,
    require_admin_login,
    resolve_poster_ids,
    set_cached_stats,
)
from app.domains.playback.stats_queries import build_stats_base_filter, get_playback_column_name
from app.infra.db.playback_store import playback_store
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
# 🔥 引入核心适配器
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.user_visibility_settings import get_hidden_users
from app.domains.users import public_service as user_service  # 🔒 引入管理员权限检查
import re
import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import psutil
import time  # 🔥 用于预热缓存时间戳
import copy
import logging
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")

router = APIRouter()

set_libraries_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
    get_admin_user_id_provider=lambda: get_admin_user_id,
    safe_error_message_provider=lambda: safe_error_message,
)

set_latest_dependency_providers(
    check_login_provider=lambda: check_login,
    get_admin_user_id_provider=lambda: get_admin_user_id,
    media_api_provider=lambda: media_api,
    tmdb_client_provider=lambda: tmdb_client,
    get_safe_proxies_provider=lambda: get_safe_proxies,
)

set_live_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
)

set_top_movies_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
    get_clean_name_provider=lambda: get_clean_name,
    resolve_poster_ids_provider=lambda: resolve_poster_ids,
    logger_provider=lambda: logger,
)

set_user_details_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    get_playback_column_name_provider=lambda: get_playback_column_name,
    playback_store_provider=lambda: playback_store,
    get_user_map_local_provider=lambda: get_user_map_local,
    get_clean_name_provider=lambda: get_clean_name,
    resolve_poster_ids_provider=lambda: resolve_poster_ids,
    media_api_provider=lambda: media_api,
)


@router.get("/api/stats/dashboard")
def api_dashboard(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查：必须登录
    if not check_login(request):
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

    # 🔥 尝试使用缓存（仅全局统计，不缓存特定用户）
    cache_key = f"dashboard_{user_id or 'all'}"
    cached = get_cached_stats(cache_key)
    if cached:
        return cached
    
    try:
        where, params = build_stats_base_filter(user_id)
        plays = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}", params)[0]['c']
        # 🔥 时区修复
        users = playback_store.query(f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days')", params)[0]['c']
        dur = playback_store.query(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}", params)[0]['c'] or 0
        base = {"total_plays": plays, "active_users": users, "total_duration": dur}
        lib = {"movie": 0, "series": 0, "episode": 0}
        
        try:
            # 🚀 替换为 media_api
            res = media_api.get("/Items/Counts", timeout=5)
            if res.status_code == 200:
                d = res.json()
                lib = {"movie": d.get("MovieCount", 0), "series": d.get("SeriesCount", 0), "episode": d.get("EpisodeCount", 0)}
        except Exception: pass
        
        result = {"status": "success", "data": {**base, "library": lib}}
        # 🔥 缓存结果
        set_cached_stats(cache_key, result)
        return result
    except: return {"status": "error", "data": {"total_plays":0, "library": {}}}

router.include_router(libraries_router)

@router.get("/api/stats/recent")
def api_recent_activity(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
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
        where, params = build_stats_base_filter(user_id)
        results = playback_store.query(f"SELECT DateCreated, UserId, ItemId, ItemName, ItemType FROM PlaybackActivity {where} ORDER BY DateCreated DESC LIMIT 50", params)
        if not results: return {"status": "success", "data": []}
        user_map = get_user_map_local()
        
        # 🔥 批量获取 ImageTag（减少 API 调用）
        item_ids = [row['ItemId'] for row in results]
        image_tags = {}
        if item_ids:
            try:
                # 批量查询 Emby 获取 ImageTags
                res = media_api.get("/Items", params={
                    "Ids": ",".join(item_ids[:50]),  # 最多50个
                    "Fields": "ImageTags"
                }, timeout=5)
                if res.status_code == 200:
                    for item in res.json().get("Items", []):
                        tag = item.get("ImageTags", {}).get("Primary", "")
                        if tag:
                            image_tags[item.get("Id")] = tag[:8]
            except:
                pass
        
        data = []
        for row in results:
            item = dict(row)
            item['UserName'] = user_map.get(item['UserId'], "User")
            item['DisplayName'] = item.get('ItemName') or '未知记录'
            item['ImageTag'] = image_tags.get(item['ItemId'], "")  # 🔥 添加 ImageTag
            if not is_admin:
                item.pop('UserId', None)  # 🔒 非管理员不暴露原始 UserId
            data.append(item)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": []}

router.include_router(latest_router)

router.include_router(live_router)

router.include_router(top_movies_router)


router.include_router(user_details_router)

@router.get("/api/stats/chart")
@router.get("/api/stats/trend")
def api_chart_stats(request: Request, user_id: Optional[str] = None, dimension: str = 'day'):
    # 🔒 安全检查
    if not check_login(request):
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
        where, params = build_stats_base_filter(user_id)
        # 🔥 时区修复
        if dimension == 'week': 
            sql = f"SELECT strftime('%Y-%W', substr(replace(DateCreated, 'T', ' '), 1, 19)) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-120 days') GROUP BY Label ORDER BY Label"
        elif dimension == 'month': 
            sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-365 days') GROUP BY Label ORDER BY Label"
        else: 
            sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY Label ORDER BY Label"
            
        results = playback_store.query(sql, params)
        data = {}
        if results:
            for r in results: data[r['Label']] = int(r['Duration'] or 0)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": {}}

@router.get("/api/stats/poster_data")
def api_poster_data(request: Request, user_id: Optional[str] = None, period: str = 'all'):
    # 🔒 安全检查
    if not check_login(request):
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
        where_base, params = build_stats_base_filter(user_id)
        date_filter = ""
        # 🔥 时区修复
        if period == 'week': date_filter = " AND DateCreated > date('now', 'localtime', '-7 days')"
        elif period == 'month': date_filter = " AND DateCreated > date('now', 'localtime', '-30 days')"
            
        server_res = playback_store.query(f"SELECT COUNT(*) as Plays FROM PlaybackActivity {build_stats_base_filter('all')[0]} {date_filter}", build_stats_base_filter('all')[1])
        server_plays = server_res[0]['Plays'] if server_res else 0

        summary = playback_store.query(
            f"SELECT COUNT(*) as plays, COALESCE(SUM(PlayDuration), 0) as duration FROM PlaybackActivity {where_base + date_filter}",
            params,
            one=True,
        )
        total_plays = int(summary['plays'] if summary else 0)
        total_duration = int(summary['duration'] if summary else 0)

        daily_rows = playback_store.query(
            f"""SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as day,
                       COALESCE(SUM(PlayDuration), 0) as duration
                FROM PlaybackActivity {where_base + date_filter}
                GROUP BY day ORDER BY day DESC""",
            params,
        ) or []
        daily_duration = {r['day']: int(r['duration'] or 0) for r in daily_rows if r['day']}

        late_night_record = None
        late_row = playback_store.query(
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
                    "name": get_clean_name(late_row.get('ItemName'), late_row.get('ItemType', ''))
                }

        top_rows = playback_store.query(
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
            clean = get_clean_name(row_dict.get('ItemName'), row_dict.get('ItemType', ''))
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
                            item_res = media_api.get(f"/Users/{user_id}/Items/{item_id}", params={"Fields": "Genres"}, timeout=2)
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
                from datetime import datetime, timedelta
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
        resolve_poster_ids(top_10)
        
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

@router.get("/api/stats/top_users_list")
def api_top_users_list(request: Request, period: str = 'all'):
    # 🔒 安全检查：仅管理员可查看全站用户排名
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        where_base, params = build_stats_base_filter('all')
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
        res = playback_store.query(sql, params)
        if not res: return {"status": "success", "data": []}
        user_map = get_user_map_local()
        hidden = get_hidden_users()
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

@router.get("/api/stats/badges")
def api_badges(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
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
        where, params = build_stats_base_filter(user_id)
        
        # 🚀 性能优化：一次查询获取所有需要的数据
        client_col = get_playback_column_name()
        raw_data = playback_store.query(f"SELECT DateCreated, PlayDuration, COALESCE({client_col}, DeviceName) as Client, ItemId, ItemName, ItemType FROM PlaybackActivity {where}", params)
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

@router.get("/api/stats/monthly_stats")
def api_monthly_stats(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
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
        where_base, params = build_stats_base_filter(user_id)
        # 🔥 时区修复
        where = where_base + " AND DateCreated > date('now', 'localtime', '-12 months')"
        sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Month, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} GROUP BY Month ORDER BY Month"
        results = playback_store.query(sql, params); data = {}
        if results: 
            for r in results: data[r['Month']] = int(r['Duration'] or 0)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": {}}

# ==========================================
# ==========================================
# 🔥 Pro 仪表盘：最近入库统计与趋势 (独立API，供charts.js调用)
# ==========================================
@router.get("/api/stats/recent_added")
def api_recent_added(request: Request = None):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not check_login(request):
        return {"status": "error", "message": "请先登录"}
    """独立API入口，复用 _get_added_stats_sync 的逻辑"""
    result = _get_added_stats_sync()
    return {"status": "success", "data": result}

# ==========================================
# 🔥 仪表盘聚合 API - 核心数据快速返回
# ==========================================
_executor = ThreadPoolExecutor(max_workers=8)

# Dashboard cache service compatibility exports. Existing tests and diagnostics
# reach these names through stats.py, while the implementation now lives in the
# domain-local service module.
_DASHBOARD_PRELOAD_KEY = dashboard_cache_service._DASHBOARD_PRELOAD_KEY
_dashboard_cache = dashboard_cache_service._dashboard_cache
_dashboard_cache_user_ids = dashboard_cache_service._dashboard_cache_user_ids
_DASHBOARD_CACHE_TTL = dashboard_cache_service._DASHBOARD_CACHE_TTL
_dashboard_last_access = dashboard_cache_service._dashboard_last_access

_normalize_dashboard_user_id = dashboard_cache_service._normalize_dashboard_user_id
_get_dashboard_context = dashboard_cache_service._get_dashboard_context
_get_dashboard_cache_entry = dashboard_cache_service._get_dashboard_cache_entry
_set_dashboard_cache = dashboard_cache_service._set_dashboard_cache
_mark_dashboard_access = dashboard_cache_service._mark_dashboard_access
_fetch_dashboard_core = dashboard_cache_service._fetch_dashboard_core
_fetch_users_list = dashboard_cache_service._fetch_users_list
_fetch_libraries = dashboard_cache_service._fetch_libraries
_fetch_top_users = dashboard_cache_service._fetch_top_users
_fetch_trend = dashboard_cache_service._fetch_trend
preload_dashboard_cache = dashboard_cache_service.preload_dashboard_cache
start_dashboard_cache_refresh_loop = dashboard_cache_service.start_dashboard_cache_refresh_loop

_dashboard_cache_tasks_started = False
_dashboard_preload_task = None
_dashboard_refresh_task = None


def _sync_dashboard_task_state() -> None:
    global _dashboard_cache_tasks_started, _dashboard_preload_task, _dashboard_refresh_task
    _dashboard_cache_tasks_started = dashboard_cache_service._dashboard_cache_tasks_started
    _dashboard_preload_task = dashboard_cache_service._dashboard_preload_task
    _dashboard_refresh_task = dashboard_cache_service._dashboard_refresh_task


def _get_dashboard_cached_data(cache_key: str, now: float = None):
    now = now or time.time()
    entry = _get_dashboard_cache_entry(cache_key)
    if entry.get("data") and (now - entry.get("ts", 0)) < _DASHBOARD_CACHE_TTL:
        return entry["data"]
    return None

@router.get("/api/dashboard/preload_status")
async def api_preload_status(request: Request):
    """
    获取缓存预热状态
    前端可以据此判断是否需要等待
    """
    # 🔒 管理后台聚合状态，仅管理员可访问
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    entry = _get_dashboard_cache_entry(_DASHBOARD_PRELOAD_KEY)
    data = entry.get("data")
    ts = entry.get("ts", 0)
    return {
        "status": "success",
        "data": {
            "cached": data is not None,
            "cache_age": round(time.time() - ts) if ts > 0 else 0,
            "cache_ttl": _DASHBOARD_CACHE_TTL,
            "libraries_count": len(data.get("libraries", [])) if data else 0,
            "users_count": len(data.get("users", [])) if data else 0
        }
    }


def start_dashboard_cache_tasks() -> None:
    dashboard_cache_service.start_dashboard_cache_tasks(
        preload_func=preload_dashboard_cache,
        refresh_func=start_dashboard_cache_refresh_loop,
    )
    _sync_dashboard_task_state()


def stop_dashboard_cache_tasks() -> None:
    dashboard_cache_service.stop_dashboard_cache_tasks()
    _sync_dashboard_task_state()


@router.get("/api/dashboard/init")
async def api_dashboard_init(request: Request, user_id: Optional[str] = None):
    # 🔒 管理后台首屏聚合接口，仅管理员可访问
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """
    仪表盘首屏聚合接口 - 核心数据快速返回
    """
    cache_key, effective_user_id, _is_admin = _get_dashboard_context(request, user_id)

    def _strip_user_id(data: dict) -> dict:
        """非管理员返回时剥离 top_users 中的原始 UserId"""
        if _is_admin:
            return data
        d = copy.deepcopy(data)
        for u in d.get("top_users", []):
            u.pop("UserId", None)
        return d

    now = time.time()
    _mark_dashboard_access(cache_key, now)
    
    # 🔥 检查内存缓存（30秒内直接返回）
    cached_data = _get_dashboard_cached_data(cache_key, now)
    if cached_data:
        return {
            "status": "success",
            "data": _strip_user_id(cached_data),
            "cached": True
        }
    
    # 🔥 并发执行核心数据（快速）
    try:
        results = await asyncio.gather(
            asyncio.wait_for(_fetch_dashboard_core(effective_user_id), timeout=5),
            asyncio.wait_for(_fetch_users_list(), timeout=3),
            asyncio.wait_for(_fetch_libraries(), timeout=5),
            asyncio.wait_for(_fetch_top_users(), timeout=3),
            asyncio.wait_for(_fetch_trend(effective_user_id), timeout=3),
            return_exceptions=True
        )
        
        dashboard, users, libraries, top_users, trend = results
    except asyncio.TimeoutError as e:
        print(f"[Dashboard Init] 请求超时: {e}")
        stale_entry = _get_dashboard_cache_entry(cache_key)
        if stale_entry.get("data"):
            return {"status": "success", "data": _strip_user_id(stale_entry["data"]), "cached": True, "timeout": True}
        dashboard = {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}}
        users = []
        libraries = []
        top_users = []
        trend = {}
    
    result_data = {
        "dashboard": dashboard if not isinstance(dashboard, Exception) else {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}},
        "users": users if not isinstance(users, Exception) else [],
        "libraries": libraries if not isinstance(libraries, Exception) else [],
        "top_users": top_users if not isinstance(top_users, Exception) else [],
        "trend": trend if not isinstance(trend, Exception) else {}
    }
    
    # 🔥 更新内存缓存
    _set_dashboard_cache(cache_key, result_data, effective_user_id, now)
    
    return {
        "status": "success",
        "data": _strip_user_id(result_data),
        "cached": False
    }


# 入库统计内存缓存
_added_stats_cache = {"data": None, "ts": 0}
_ADDED_STATS_CACHE_TTL = 300  # 5分钟缓存

def _get_added_stats_sync():
    """同步获取入库统计（用于线程池执行）"""
    import time
    
    # 🔥 检查内存缓存
    now = time.time()
    if _added_stats_cache["data"] and (now - _added_stats_cache["ts"]) < _ADDED_STATS_CACHE_TTL:
        return _added_stats_cache["data"]
    
    try:
        admin_id = None
        try:
            users = media_api.get("/Users", timeout=5).json()
            for u in users:
                if u.get("Policy", {}).get("IsAdministrator"):
                    admin_id = u['Id']
                    break
            if not admin_id and users:
                admin_id = users[0]['Id']
        except:
            pass

        # 获取所有媒体库
        libraries = []
        try:
            lib_res = media_api.get(f"/Users/{admin_id}/Views", timeout=10).json()
            libraries = lib_res.get("Items", [])
        except:
            pass

        today = datetime.datetime.now()
        start_of_week = today - datetime.timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

        week_counts = [0] * 7
        total_this_week = 0

        # 按媒体库分别查询
        for lib in libraries:
            try:
                lib_id = lib.get("Id")
                if not lib_id:
                    continue
                
                lib_count = 0
                start_index = 0
                page_size = 500
                should_stop = False
                
                while not should_stop and start_index < 10000:
                    params = {
                        "ParentId": lib_id,
                        "SortBy": "DateCreated",
                        "SortOrder": "Descending",
                        "IncludeItemTypes": "Movie,Series,Episode",
                        "Recursive": "true",
                        "StartIndex": start_index,
                        "Limit": page_size,
                        "Fields": "DateCreated"
                    }
                    res = media_api.get(f"/Users/{admin_id}/Items", params=params, timeout=20).json()
                    items = res.get("Items", [])
                    
                    if not items:
                        break
                    
                    page_has_this_week = False
                    for item in items:
                        date_str = item.get("DateCreated")
                        if not date_str:
                            continue
                        try:
                            clean_date = date_str.split('.')[0].replace("Z", "")
                            dt = datetime.datetime.fromisoformat(clean_date)
                            # UTC 转北京时间
                            dt_local = dt + datetime.timedelta(hours=8)
                            
                            if dt_local >= start_of_week:
                                week_counts[dt_local.weekday()] += 1
                                total_this_week += 1
                                lib_count += 1
                                page_has_this_week = True
                            else:
                                should_stop = True
                                break
                        except:
                            pass
                    
                    if not page_has_this_week:
                        should_stop = True
                    
                    start_index += page_size
                    if len(items) < page_size:
                        break
                        
            except:
                continue

        result = {"total_this_week": total_this_week, "trend": week_counts}
        
        # 🔥 更新缓存
        _added_stats_cache["data"] = result
        _added_stats_cache["ts"] = now
        
        return result
    except:
        return {"total_this_week": 0, "trend": [0]*7}


@router.get("/api/system/monitor")
def api_system_monitor(request: Request):
    # 🔒 管理员专用：只检查后台登录
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        # 🔥 interval=0 立即返回（非阻塞），使用上次采样值
        cpu_usage = psutil.cpu_percent(interval=0)

        # 内存使用率
        memory_info = psutil.virtual_memory()
        memory_usage = memory_info.percent

        # 根目录磁盘使用率
        disk_info = psutil.disk_usage('/')
        disk_usage = disk_info.percent

        return {
            "status": "success",
            "data": {
                "cpu": cpu_usage,
                "memory": memory_usage,
                "disk": disk_usage
            }
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "探针读取失败")}


# ==================== 🔥 内容风云榜详情 API ====================

@router.get("/api/stats/item_detail")
def api_item_detail(request: Request, item_id: str, item_name: Optional[str] = None):
    """获取媒体详情（谁在看、播放历史）"""
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：非管理员只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    current_user_id = None
    if not is_admin:
        current_user_id = (req_user or admin_user).get("Id")

    try:
        # 1. 获取媒体基础信息
        item_info = None
        item_type = None
        series_name = None
        series_id = None
        try:
            res = media_api.get(f"/Users/{request.session.get('user', {}).get('Id', '')}/Items/{item_id}")
            logger.info(f"[item_detail] Emby API status: {res.status_code}")
            if res.status_code == 200:
                item_info = res.json()
                item_type = item_info.get('Type')
                logger.info(f"[item_detail] item_type: {item_type}, item_name: {item_info.get('Name')}")
                # 🔥 如果是剧集，获取剧名和剧集ID
                if item_type == 'Episode':
                    # 尝试多个可能的字段名
                    series_name = item_info.get('SeriesName') or item_info.get('Series') or item_info.get('SeriesName')
                    series_id = item_info.get('SeriesId') or item_info.get('SeriesItemId')
                    logger.info(f"[item_detail] Episode detected, series_name: {series_name}, series_id: {series_id}")
        except Exception as e:
            logger.error(f"[item_detail] 获取媒体信息失败: {e}")
        
        # 🔥 如果 Emby API 失败，从 item_name 提取剧名和季
        if not series_name and item_name:
            # 从 "年少有为 - s01e05 - 第 5 集" 提取 "年少有为 - 第 1 季"
            # 或从 "纯真年代的爱情 - 第 1 季" 保留原样
            parts = item_name.split(' - ')
            if len(parts) >= 2:
                # 第一部分是剧名
                name_part = parts[0].strip()
                # 查找季信息
                season_part = None
                for p in parts[1:]:
                    # 匹配 "第 X 季" 或 "S01" 格式
                    m = re.search(r'第\s*\d+\s*季', p)
                    if m:
                        season_part = m.group()
                        break
                    m = re.search(r'S(\d+)', p, re.I)
                    if m:
                        season_num = int(m.group(1))
                        season_part = f"第 {season_num} 季"
                        break
                if season_part:
                    series_name = f"{name_part} - {season_part}"
                else:
                    series_name = name_part
            else:
                series_name = parts[0].strip()
            logger.info(f"[item_detail] 从 item_name 提取: {series_name}")
        
        # 2. 获取播放统计
        rows = []
        
        # 🔥 如果是剧集，始终按剧名查询所有集数
        if series_name or item_name:
            search_name = series_name or item_name
            # 提取剧名（去掉集数信息）
            # 例如 "逐玉 - s01e01 - 第 1 集" -> "逐玉"
            clean_name = search_name.split(' - ')[0].strip()
            # 去掉可能的季数信息
            clean_name = re.sub(r'\s*S\d+.*', '', clean_name, flags=re.I)
            clean_name = re.sub(r'\s*第.*季.*', '', clean_name)
            clean_name = clean_name.strip()
            logger.info(f"[item_detail] 按剧名查询: '{clean_name}' (原始: '{search_name}')")
            
            if is_admin:
                sql_by_name = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemName LIKE ?
                    ORDER BY DateCreated DESC
                    LIMIT 500
                """
                rows = playback_store.query(sql_by_name, [f"%{clean_name}%"])
            else:
                sql_by_name = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemName LIKE ? AND UserId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 500
                """
                rows = playback_store.query(sql_by_name, [f"%{clean_name}%", current_user_id])
            logger.info(f"[item_detail] 按剧名查询结果: {len(rows) if rows else 0} 条")
        else:
            # 🔥 电影等其他类型，按 ItemId 查询
            if is_admin:
                sql_by_id = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 100
                """
                rows = playback_store.query(sql_by_id, [item_id])
            else:
                sql_by_id = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemId = ? AND UserId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 100
                """
                rows = playback_store.query(sql_by_id, [item_id, current_user_id])
            logger.info(f"[item_detail] 按 ItemId 查询结果: {len(rows) if rows else 0} 条")
        
        if not rows:
            return {"status": "error", "message": "无播放记录"}
        
        # 🔥 获取用户 ID 到用户名的映射
        user_map = get_user_map_local()
        
        # 3. 统计数据
        total_plays = len(rows)
        total_time = sum(r.get('PlayDuration') or 0 for r in rows)
        
        # 用户统计 - 通过 UserId 查找用户名
        user_stats = {}
        for r in rows:
            uid = r.get('UserId') or 'unknown'
            if uid not in user_stats:
                # 🔥 优先从 user_map 获取用户名
                user_name = user_map.get(uid) or r.get('UserName') or '未知用户'
                user_stats[uid] = {
                    'UserId': uid,
                    'UserName': user_name,
                    'PlayCount': 0,
                    'TotalTime': 0
                }
            user_stats[uid]['PlayCount'] += 1
            user_stats[uid]['TotalTime'] += r.get('PlayDuration') or 0
        
        # 按播放次数排序
        top_users = sorted(user_stats.values(), key=lambda x: x['PlayCount'], reverse=True)[:10]
        
        # 4. 最近播放历史
        recent_plays = []
        for r in rows[:20]:
            uid = r.get('UserId')
            # 🔥 优先从 user_map 获取用户名
            user_name = user_map.get(uid) or r.get('UserName') or '未知用户'
            recent_plays.append({
                'UserName': user_name,
                'PlayDuration': r.get('PlayDuration') or 0,
                'DateCreated': r.get('DateCreated')
            })
        
        # 5. 时间分布（按天）
        time_distribution = {}
        for r in rows:
            if r.get('DateCreated'):
                day = r['DateCreated'][:10]  # YYYY-MM-DD
                if day not in time_distribution:
                    time_distribution[day] = {'plays': 0, 'time': 0}
                time_distribution[day]['plays'] += 1
                time_distribution[day]['time'] += r.get('PlayDuration') or 0
        
        # 按日期排序，取最近30天
        sorted_days = sorted(time_distribution.items(), key=lambda x: x[0], reverse=True)[:30]
        
        return {
            "status": "success",
            "data": {
                "ItemInfo": {
                    "Id": series_id or item_id,
                    "Name": series_name or (item_info.get('Name') if item_info else rows[0]['ItemName']),
                    "Type": item_info.get('Type') if item_info else rows[0]['ItemType'],
                    "Overview": item_info.get('Overview') if item_info else None,
                    "ProductionYear": item_info.get('ProductionYear') if item_info else None,
                    "CommunityRating": item_info.get('CommunityRating') if item_info else None,
                    "Genres": item_info.get('Genres') if item_info else None,
                } if item_info else {
                    "Id": item_id,
                    "Name": series_name or rows[0]['ItemName'],
                    "Type": rows[0]['ItemType'],
                    "Overview": None,
                    "ProductionYear": None,
                    "CommunityRating": None,
                    "Genres": None
                },
                "Stats": {
                    "TotalPlays": total_plays,
                    "TotalTime": total_time,
                    "TotalTimeHours": round(total_time / 3600, 1)
                },
                "TopUsers": top_users,
                "RecentPlays": recent_plays,
                "TimeDistribution": dict(sorted_days)
            }
        }
    except Exception as e:
        logger.error(f"[api_item_detail] 异常: {e}")
        return {"status": "error", "message": safe_error_message(e)}
