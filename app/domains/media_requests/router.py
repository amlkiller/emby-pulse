import json
import time
import re
from datetime import date
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from app.domains.users import public_service as user_service
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验
from pydantic import BaseModel
from typing import Optional, List
import threading

from app.core.config import REPORT_COVER_URL
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.request_portal_settings import get_pulse_url
from app.infra.db.notification_dao import add_system_notification
from app.domains.media_requests.media_request_dao import (
    claim_registration_invitation,
    create_media_feedback,
    decode_gap_cache,
    delete_media_request,
    ensure_media_request_schema,
    find_poster_for_feedback,
    get_media_request,
    get_pending_notify_data,
    get_update_cost_config,
    get_update_request_search_info,
    get_user_expire_date,
    get_user_password_hash,
    get_user_series_db_context,
    get_user_status_meta,
    list_all_feedback,
    list_all_requests,
    list_my_feedback,
    list_my_requests,
    list_request_status_notify_items,
    list_tg_bindings,
    restore_invitation_code,
    save_registered_user_meta,
    submit_batch_update_request_records,
    submit_new_media_request,
    submit_update_request_record,
    update_feedback_status,
    update_feedback_status_batch,
    update_media_request_status,
    update_user_password_hash,
)
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
# 🔥 补回丢失的这一行：引入基础数据模型
from app.schemas.models import MediaRequestSubmitModel as BaseSubmitModel
from app.domains.notifications import public_service as notification_service
from app.domains.notifications import notify_admin
from app.domains.playback import stats as playback_stats
# 🔥 引入媒体适配器用于创建用户
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import (
    get_media_server_main_public_url,
    get_media_server_main_public_or_host,
    get_media_server_user_routes,
    get_media_server_welcome_message,
)
from app.infra.config.moviepilot_settings import get_moviepilot_token, get_moviepilot_url
import logging
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")

router = APIRouter()

# ==================== 用户社区首页缓存 ====================
# 缓存结构: {key: {"data": ..., "expires_at": timestamp}}
_community_cache = {}
_community_cache_lock = threading.Lock()
_COMMUNITY_CACHE_MAX_SIZE = 64
_community_refresh_lock = threading.Lock()
_community_refresh_started = False
_community_refresh_start_lock = threading.Lock()
_community_refresh_stop_event = threading.Event()
_community_refresh_thread = None

# 缓存 TTL 配置（秒）
COMMUNITY_CACHE_TTL = 300  # 默认 5 分钟
COMMUNITY_CACHE_TTL_HUB = 600  # hub_data 缓存 10 分钟（计算量大）
COMMUNITY_CACHE_TTL_TOP = 300  # 热播榜缓存 5 分钟
COMMUNITY_CACHE_TTL_LATEST = 180  # 最新收录缓存 3 分钟

def _get_cache(key: str):
    """获取缓存数据，过期或空数据返回 None"""
    with _community_cache_lock:
        entry = _community_cache.get(key)
        if entry and entry["expires_at"] > time.time():
            data = entry["data"]
            # 🔥 空数据不返回，让调用方重新获取
            if data:
                return data
    return None

def _set_cache(key: str, data, ttl: int = COMMUNITY_CACHE_TTL):
    """设置缓存"""
    with _community_cache_lock:
        now = time.time()
        expired_keys = [k for k, v in _community_cache.items() if v.get("expires_at", 0) <= now]
        for k in expired_keys:
            _community_cache.pop(k, None)
        if len(_community_cache) >= _COMMUNITY_CACHE_MAX_SIZE and key not in _community_cache:
            oldest_key = min(_community_cache, key=lambda k: _community_cache[k].get("expires_at", 0))
            _community_cache.pop(oldest_key, None)
        _community_cache[key] = {
            "data": data,
            "expires_at": now + ttl
        }

def _invalidate_cache(key: str = None):
    """清除缓存（可选指定 key，不指定则清除全部）"""
    with _community_cache_lock:
        if key:
            _community_cache.pop(key, None)
        else:
            _community_cache.clear()

def _check_user_exists(user_id: str) -> bool:
    """检查 Emby 用户是否仍然存在"""
    if not user_id:
        return False
    try:
        from app.infra.clients.media_server_client import media_api
        if media_api and media_api.host and media_api.api_key:
            res = media_api.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True  # 网络异常时不误判，允许继续操作

def get_tmdb_season_info(tmdb_id: int, season: int) -> tuple:
    """获取 TMDB 季信息（总集数、未播出集数）
    
    Returns:
        (total_episodes, unaired_episodes)
    """
    if not tmdb_id or not season:
        return 0, []
    try:
        if not tmdb_client.api_key:
            return 0, []
        proxies = get_safe_proxies()
        season_data = tmdb_client.get_tv_season(tmdb_id, season, proxies=proxies, timeout=8).json()
        episodes = season_data.get("episodes", [])
        total = len(episodes)
        
        # 计算未播出的集数
        today = date.today().strftime("%Y-%m-%d")
        unaired_eps = []
        for ep in episodes:
            ep_num = ep.get("episode_number", 0)
            air_date = ep.get("air_date", "")
            if air_date and air_date > today:
                unaired_eps.append(ep_num)
        
        return total, unaired_eps
    except:
        return 0, []

def get_emby_admin():
    try:
        users = media_api.get("/Users", timeout=5).json()
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"): return u['Id']
        return users[0]['Id'] if users else None
    except: return None

def check_emby_exists(tmdb_id, media_type, season=0):
    if not media_api.host or not media_api.api_key: return False
    try:
        admin_id = get_emby_admin()
        if not admin_id: return False
        type_filter = "Movie" if media_type == "movie" else "Series"
        res = media_api.get(f"/Users/{admin_id}/Items", params={
            "AnyProviderIdEquals": f"tmdb.{tmdb_id}",
            "IncludeItemTypes": type_filter,
            "Recursive": "true",
        }, timeout=5).json()
        if not res.get("Items"): return False
        if media_type == "movie": return True
        sid = res["Items"][0]["Id"]
        s_res = media_api.get(f"/Shows/{sid}/Seasons", params={"UserId": admin_id}, timeout=5).json()
        local_seasons = [s.get("IndexNumber") for s in s_res.get("Items", [])]
        return season in local_seasons
    except: return False

class MediaRequestSubmitModel(BaseSubmitModel):
    seasons: List[int] = [0] 
    overview: Optional[str] = ""

class AdminActionModel(BaseModel):
    tmdb_id: int
    season: int = 0
    action: str
    reject_reason: Optional[str] = None

class BulkAdminActionModel(BaseModel):
    items: List[dict]
    action: str
    reject_reason: Optional[str] = None

class RequestLoginModel(BaseModel):
    username: str; password: str

class FeedbackSubmitModel(BaseModel):
    item_name: str
    issue_type: str
    description: Optional[str] = ""
    poster_path: Optional[str] = ""

class FeedbackActionModel(BaseModel):
    id: int
    action: str 

class BulkFeedbackActionModel(BaseModel):
    items: List[int]
    action: str

@router.post("/api/requests/auth")
def request_system_login(data: RequestLoginModel, request: Request):
    # 🔒 端口隔离检查：用户社区登录只能从用户端口访问
    host_header = request.headers.get("host", "")
    is_user_port = ":10308" in host_header or host_header.endswith(":10308")
    is_admin_port = ":10307" in host_header or host_header.endswith(":10307")
    
    # 如果从管理端口访问，拒绝用户社区登录
    if is_admin_port:
        return {"status": "error", "message": "请从用户社区端口(10308)登录"}
    
    host = get_media_server_main_public_or_host()
    if not host: return {"status": "error", "message": "未配置 Emby 服务器"}
    
    # 先获取用户列表，找到匹配的用户
    from datetime import date as date_module
    
    matched_user = None
    try:
        users_res = media_api.get("/Users", timeout=5)
        if users_res.status_code == 200:
            for u in users_res.json():
                if u.get("Name", "").lower() == data.username.lower():
                    matched_user = u
                    break
    except Exception as e:
        print(f"[用户社区登录] 获取用户列表失败: {e}")
    
    if not matched_user:
        return {"status": "error", "message": "账号或密码错误"}
    
    user_id = matched_user.get("Id")
    user_name = matched_user.get("Name")
    has_password = matched_user.get("HasPassword", False)
    is_emby_disabled = matched_user.get("Policy", {}).get("IsDisabled", False)
    
    # 检查数据库中的状态
    admin_disabled = 0
    expire_date = None
    try:
        row = get_user_status_meta(user_id)
        if row:
            admin_disabled, expire_date = row["admin_disabled"], row["expire_date"]
    except Exception as e:
        print(f"[用户社区登录] 检查用户状态失败: {e}")
    
    # 管理员封禁 - 拒绝登录
    if admin_disabled == 1:
        return {"status": "error", "message": "您的账号已被禁用，如需启用请联系管理员", "disabled": True}
    
    # 检查是否过期
    is_expired = False
    if expire_date:
        try:
            exp_date = date_module.fromisoformat(expire_date)
            if exp_date < date_module.today():
                is_expired = True
        except:
            pass
    
    # 验证密码
    if not has_password:
        return {"status": "error", "message": "安全要求：请先在 Emby 中为账号设置密码"}

    password_valid = False
    if has_password:
        if is_emby_disabled:
            # 🔒 安全修复：已禁用账号不修改 Emby IsDisabled 状态，使用本地哈希验证
            stored_hash = None
            try:
                row = get_user_password_hash(user_id)
                if row and row["emby_pw_hash"]:
                    stored_hash = row["emby_pw_hash"]
            except:
                pass

            if stored_hash:
                try:
                    import bcrypt
                    password_valid = bcrypt.checkpw(data.password.encode('utf-8'), stored_hash.encode('utf-8'))
                except:
                    password_valid = False
            else:
                # 无哈希缓存（用户从未成功登录过），安全拒绝
                return {"status": "error", "message": "账号已过期，请联系管理员续费后登录", "disabled": True, "need_renew": True}
        else:
            # 正常账号：通过 Emby API 验证密码
            try:
                res = media_api.authenticate_by_name(data.username, data.password, timeout=8)
                password_valid = res.status_code == 200
            except Exception as e:
                print(f"[用户社区登录] 验证密码失败: {e}")

    if not password_valid:
        return {"status": "error", "message": "账号或密码错误"}

    # 🔒 登录成功后缓存密码哈希（用于过期账号本地验证，永不修改 Emby IsDisabled）
    if has_password and data.password:
        try:
            import bcrypt
            pw_hash = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
            update_user_password_hash(user_id, pw_hash)
        except:
            pass

    # 登录成功 - 清除整个 Session，防止残留其他用户数据
    request.session.clear()
    request.session["req_user"] = {"Id": user_id, "Name": user_name, "expired": is_expired}
    
    if is_expired:
        return {"status": "success", "expired": True, "message": f"您的账号已于 {expire_date} 过期，请及时续费"}
    return {"status": "success"}

@router.get("/api/requests/check")
def check_auth(request: Request):
    user = request.session.get("req_user")
    if user: 
        user_id = user.get("Id")
        
        # 检查 Emby 账号是否仍然存在
        if not _check_user_exists(user_id):
            request.session.pop("req_user", None)
            return {"status": "error", "message": "账号已被删除", "account_deleted": True}
        
        # 检查是否被封禁（实时检查，防止被封后仍能使用）
        try:
            row = get_user_status_meta(user_id)
            
            if row and row["admin_disabled"] == 1:
                # 被管理员封禁，强制登出
                request.session.pop("req_user", None)
                return {"status": "error", "message": "您的账号已被禁用，如需启用请联系管理员", "disabled": True}
        except:
            pass
        
        expire_date = "永久有效"
        is_expired = False
        if user_id:
            try:
                row = get_user_expire_date(user_id)
                if row and row["expire_date"]:
                    expire_date = row["expire_date"]
                    from datetime import date
                    try:
                        exp_date = date.fromisoformat(expire_date)
                        if exp_date < date.today():
                            is_expired = True
                    except:
                        pass
            except Exception: pass
            
        # 返回用户可见的线路（根据权限过滤）
        user_routes = get_media_server_user_routes(user.get("Id"))
        server_url = json.dumps(user_routes) if user_routes else get_media_server_main_public_or_host()
        return {
            "status": "success",
            "user": {**user, "expire_date": expire_date, "expired": is_expired},
            "server_url": server_url
        }
    return {"status": "error"}

@router.post("/api/requests/logout")
def request_system_logout(request: Request):
    # 🔥 完全清除 session，不只是 pop req_user
    request.session.clear()
    return {"status": "success"}

@router.get("/api/requests/item_info")
def get_item_info(item_id: str, request: Request):
    # 🔒 安全检查：管理员或已绑定 Emby 的报片用户
    if not (user_service.is_admin_user(request) or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    try:
        admin_id = get_emby_admin()
        if not admin_id: return {"status": "error"}
        
        res = media_api.get(f"/Users/{admin_id}/Items/{item_id}", timeout=5)
        if res.status_code == 200:
            d = res.json()
            return {"status": "success", "data": {
                "Id": d.get("Id"),
                "Name": d.get("Name", "未知"),
                "Type": d.get("Type", ""),
                "ProductionYear": d.get("ProductionYear", ""),
                "CommunityRating": d.get("CommunityRating", "N/A"),
                "Overview": d.get("Overview", ""),
                "Genres": d.get("Genres", [])
            }}
        return {"status": "error"}
    except Exception as e: 
        return {"status": "error"}

@router.get("/api/requests/hub_data")
def get_hub_data(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error"}
    
    # 🔥 尝试从缓存获取（hub_data 是全局数据，不依赖用户）
    cache_key = "hub_data"
    cached = _get_cache(cache_key)
    if cached:
        return {"status": "success", "data": cached, "from_cache": True}
    
    host = get_media_server_main_public_or_host()
    uid = user['Id']
    
    top_rated = []; genres_data = []
    try:
        import random 
        # 🔥 使用 /Items API 而不是 /Users/{uid}/Items
        tr_res = media_api.get("/Items", params={
            "IncludeItemTypes": "Movie,Series",
            "Recursive": "true",
            "SortBy": "CommunityRating",
            "SortOrder": "Descending",
            "Limit": 100,
            "Fields": "CommunityRating",
        }, timeout=5).json()
        logger.debug(f"[hub_data] 镇站之宝返回: {len(tr_res.get('Items', []))} 条")
        
        valid_items = []
        for i in tr_res.get("Items", []):
            rating = i.get("CommunityRating", 0)
            if 8.0 <= rating <= 9.8:
                valid_items.append({
                    "Id": i.get("Id"), "Name": i.get("Name"), "Type": i.get("Type"),
                    "CommunityRating": rating
                })
                
        random.shuffle(valid_items)
        top_rated = valid_items[:10]
        logger.debug(f"[hub_data] 镇站之宝筛选后: {len(top_rated)} 条")
                
        # 🔥 使用 /Items API
        g_res = media_api.get("/Items", params={
            "IncludeItemTypes": "Movie,Series",
            "Recursive": "true",
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "Limit": 200,
            "Fields": "Genres",
        }, timeout=5).json()
        logger.debug(f"[hub_data] 流派分析返回: {len(g_res.get('Items', []))} 条")
        genre_counts = {}
        total_items = 0
        for i in g_res.get("Items", []):
            gs = i.get("Genres", [])
            if gs:
                total_items += 1
                for g in gs: genre_counts[g] = genre_counts.get(g, 0) + 1
        
        if total_items > 0:
            sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:6] 
            for k, v in sorted_genres:
                genres_data.append({"name": k, "count": v, "pct": round(v / total_items * 100)})
        logger.debug(f"[hub_data] 流派分析结果: {len(genres_data)} 种")
    except Exception as e: 
        logger.error(f"[hub_data] 获取失败: {e}")
    
    # 🔥 存入缓存
    result_data = {"top_rated": top_rated, "genres": genres_data}
    _set_cache(cache_key, result_data, COMMUNITY_CACHE_TTL_HUB)
    
    return {"status": "success", "data": result_data}

@router.get("/api/requests/search")
def search_tmdb(query: str, request: Request):
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}
    
    proxies = get_safe_proxies()
    try:
        res = tmdb_client.search_multi(query, proxies=proxies, timeout=10).json()
        results = []
        for i in res.get("results", []):
            if i.get("media_type") in ["movie", "tv"]:
                results.append({"tmdb_id": i['id'], "media_type": i['media_type'], "title": i.get('title') or i.get('name'), "year": (i.get('release_date') or i.get('first_air_date') or "")[:4], "poster_path": f"https://image.tmdb.org/t/p/w500{i['poster_path']}" if i.get('poster_path') else "", "overview": i.get('overview', ''), "vote_average": round(i.get('vote_average', 0), 1), "local_status": -1})
        return {"status": "success", "data": results}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/requests/trending")
def get_tmdb_trending(request: Request):
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}
    
    proxies = get_safe_proxies()
    try:
        results = []
        for page in [1, 2]:
            res = tmdb_client.get_trending(media_type="all", time_window="week", page=page, proxies=proxies, timeout=10).json()
            for i in res.get("results", []):
                if i.get("media_type") in ["movie", "tv"] and i.get("poster_path"):
                    results.append({
                        "tmdb_id": i['id'], 
                        "media_type": i['media_type'], 
                        "title": i.get('title') or i.get('name'), 
                        "year": (i.get('release_date') or i.get('first_air_date') or "")[:4], 
                        "poster_path": f"https://image.tmdb.org/t/p/w500{i['poster_path']}", 
                        "overview": i.get('overview', ''), 
                        "vote_average": round(i.get('vote_average', 0), 1), 
                        "local_status": -1
                    })
        return {"status": "success", "data": results}
    except Exception as e: 
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/requests/tv/{tmdb_id}")
def get_tv_details(tmdb_id: int, request: Request):
    # 🔒 安全检查：管理员或已绑定 Emby 的报片用户
    if not (user_service.is_admin_user(request) or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    proxies = get_safe_proxies()
    try:
        local_seasons_map = {} 
        
        admin_id = get_emby_admin()
        if admin_id:
            s_res = media_api.get(f"/Users/{admin_id}/Items", params={
                "AnyProviderIdEquals": f"tmdb.{tmdb_id}",
                "IncludeItemTypes": "Series",
                "Recursive": "true",
            }, timeout=5).json()
            if s_res.get("Items"):
                sid = s_res["Items"][0]["Id"]
                ep_res = media_api.get(f"/Users/{admin_id}/Items", params={
                    "ParentId": sid,
                    "IncludeItemTypes": "Episode",
                    "Recursive": "true",
                    "Fields": "ParentIndexNumber",
                }, timeout=5).json()
                for ep in ep_res.get("Items", []):
                    sn = ep.get("ParentIndexNumber")
                    if sn is not None:
                        local_seasons_map[sn] = local_seasons_map.get(sn, 0) + 1

        tmdb_res = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=10).json()
        seasons = []
        for s in tmdb_res.get("seasons", []):
            if s["season_number"] > 0: 
                sn = s["season_number"]
                seasons.append({
                    "season_number": sn, 
                    "name": s["name"], 
                    "episode_count": s["episode_count"],
                    "exists_locally": sn in local_seasons_map,
                    "local_ep_count": local_seasons_map.get(sn, 0)
                })
        return {"status": "success", "seasons": seasons}
    except Exception as e: 
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/requests/check/{media_type}/{tmdb_id}")
def check_local_status(media_type: str, tmdb_id: int, request: Request):
    # 🔒 安全检查：管理员或已绑定 Emby 的报片用户
    if not (user_service.is_admin_user(request) or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    exists = check_emby_exists(tmdb_id, media_type)
    return {"status": "success", "exists": exists}

@router.post("/api/requests/submit")
async def submit_media_request(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "请先绑定 Emby 账号"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除，请重新登录", "account_deleted": True}
    
    uid = user['Id']
    uname = user['Name']

    try:
        data = await request.json()
        tmdb_id = int(data.get("tmdb_id") or 0)
        # 兼容前端发 seasons(数组) 或 season(单数)
        seasons_raw = data.get("seasons")
        if seasons_raw is None:
            seasons_raw = [data.get("season")] if data.get("season") is not None else []
        # 过滤掉无效季数（0或负数）
        seasons = [int(s) for s in seasons_raw if int(s) > 0] if isinstance(seasons_raw, list) else ([int(seasons_raw)] if int(seasons_raw) > 0 else [])
        media_type = data.get("media_type")
        
        # 🔒 XSS 防护：过滤 title 中的危险字符
        title_raw = data.get("title", "")
        title = re.sub(r'<[^>]*>', '', title_raw)  # 移除 HTML 标签
        title = title[:200]  # 限制长度
        
        year = data.get("year")
        
        # 🔒 XSS 防护：过滤 poster_path
        poster_path_raw = data.get("poster_path", "")
        poster_path = poster_path_raw[:500] if poster_path_raw else ""

        # 验证季数
        if media_type == "tv" and not seasons:
            return {"status": "error", "message": "请选择有效的季数"}

        # 电影没有季数概念，设置为0以便插入数据库
        if media_type == "movie" and not seasons:
            seasons = [0]

        result = submit_new_media_request(uid, uname, tmdb_id, media_type, title, year, poster_path, seasons)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}

        try:
            season_str = f" 第 {','.join(str(s) for s in seasons)} 季" if media_type == "tv" and any(s > 0 for s in seasons) else ""
            msg = f"🎬 <b>收到新求片心愿</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title} ({year}){season_str}\n\n请及时前往后台审批处理。"
            
            admin_url = get_pulse_url() or get_media_server_main_public_url() or "http://127.0.0.1:10307"
            # 构建季数字符串用于回调（多季用逗号分隔）
            season_str_cb = ",".join(str(s) for s in seasons) if media_type == "tv" and any(s > 0 for s in seasons) else "0"
            # 标题需要编码以便在 callback_data 中使用（替换下划线）
            title_safe = title.replace("_", "-")
            
            # 检查影巢插件是否启用
            hdhive_enabled = False
            try:
                from app.plugins import get_plugin
                hdhive_plugin = get_plugin("hdhive")
                hdhive_enabled = hdhive_plugin and hdhive_plugin.enabled
            except:
                pass
            
            # 构建按钮：影巢搜索按钮（如果插件启用）
            if hdhive_enabled:
                keyboard = {"inline_keyboard": [
                    [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tmdb_id}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}"}],
                    [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_{tmdb_id}_{media_type}_{season_str_cb}_{title_safe}"}, {"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tmdb_id}"}],
                    [{"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
                ]}
            else:
                keyboard = {"inline_keyboard": [
                    [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tmdb_id}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}"}],
                    [{"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tmdb_id}"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
                ]}
            
            # 🔥 使用 notify_rules 配置控制通知渠道
            rule = notify_admin.get_notify_rule('request_new')
            if rule and rule.get('enabled'):
                channels = rule.get('channels', [])
                platform = "none"
                if 'tg_bot' in channels and 'wecom' in channels:
                    platform = "all"
                elif 'tg_bot' in channels:
                    platform = "tg"
                elif 'wecom' in channels:
                    platform = "wecom"
                
                if platform != "none":
                    notification_service.send_photo("sys_notify", f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else REPORT_COVER_URL, msg, reply_markup=keyboard, platform=platform)
                
                # Web 通知中心 - 只有勾选 web 才发送
                if 'web' in channels:
                    add_system_notification("request", f"收到新求片: {title}", f"用户 {uname} 提交了新的心愿单", "/requests_admin")
            # else: 关闭状态不发送任何通知
        except Exception as e:
            logger.error(f"[求片通知] 发送失败: {e}")

        return {"status": "success", "message": "心愿已提交！系统将尽快处理您的请求。"}
        
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "提交失败")}

@router.get("/api/requests/my")
def get_my_requests(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    uid = str(user.get("Id", ""))
    rows = list_my_requests(uid)
    
    results = []
    for r in rows:
        results.append({
            "tmdb_id": r[0], 
            "title": r[1] + (f" (S{r[5]})" if r[6]=='tv' else ""), 
            "year": r[2], 
            "poster_path": r[3], 
            "status": r[4], 
            "season": r[5], 
            "requested_at": r[7], 
            "reject_reason": r[8],
            "episodes": r[9] or "",
            "request_type": r[10] or "new"
        })
    return {"status": "success", "data": results}

@router.get("/api/manage/requests")
def get_all_requests(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    rows = list_all_requests()
    
    # 🔥 收集需要获取 TMDB 封面的 tmdb_id
    tmdb_ids_to_fetch = []
    for r in rows:
        poster_path = r[4] or ""
        tmdb_id = r[0]
        if poster_path and ("/emby/Items/" in poster_path or ":8096" in poster_path or poster_path.startswith("/api/library/image/")):
            if tmdb_id:
                tmdb_ids_to_fetch.append(tmdb_id)
        elif not poster_path and tmdb_id:
            tmdb_ids_to_fetch.append(tmdb_id)
    
    # 🔥 并发获取 TMDB 封面（ThreadPoolExecutor）
    tmdb_posters = {}
    if tmdb_ids_to_fetch:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        proxies = get_safe_proxies()
        def fetch_tmdb_poster(tid):
            try:
                tmdb_info = tmdb_client.get_tv_details(tid, proxies=proxies, timeout=3).json()
                return (tid, tmdb_info.get("poster_path"))
            except:
                return (tid, None)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_tmdb_poster, tid) for tid in set(tmdb_ids_to_fetch)]
            for future in as_completed(futures, timeout=10):
                tid, poster = future.result()
                if poster:
                    tmdb_posters[tid] = poster
    
    results = []
    for r in rows:
        # 判断是否为追新（有 episodes 或库里已有该剧）
        is_update = r[12] == 'update' if r[12] else False
        episodes_str = r[11] or ""
        
        # 构建标题显示
        title_display = r[2]
        series_name = r[2]  # 保存原始剧名用于追新
        if r[1] == 'tv':
            if episodes_str:
                # 追新：显示具体集数，标题去掉季数
                title_display = f"{r[2]} 第 {r[6]} 季 E{episodes_str.replace(',', '-')}集"
            else:
                title_display += f" 第 {r[6]} 季"
        
        # 🔥 处理封面路径（使用预获取的 TMDB 封面）
        poster_path = r[4] or ""
        tmdb_id = r[0]
        
        if poster_path and ("/emby/Items/" in poster_path or ":8096" in poster_path or poster_path.startswith("/api/library/image/")):
            # 本地路径，使用预获取的 TMDB 封面
            poster_path = ""
            if tmdb_id in tmdb_posters:
                poster_path = f"https://image.tmdb.org/t/p/w500{tmdb_posters[tmdb_id]}"
        
        if not poster_path:
            # 尝试使用预获取的 TMDB 封面
            if tmdb_id in tmdb_posters:
                poster_path = f"https://image.tmdb.org/t/p/w500{tmdb_posters[tmdb_id]}"
        elif not poster_path.startswith("http"):
            # TMDB 相对路径，补全
            poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        results.append({
            "tmdb_id": r[0], 
            "media_type": r[1], 
            "title": title_display, 
            "series_name": series_name,  # 原始剧名
            "year": r[3], 
            "poster_path": poster_path, 
            "status": r[5], 
            "season": r[6], 
            "created_at": r[7], 
            "request_count": r[8], 
            "requested_by": r[9], 
            "reject_reason": r[10],
            "episodes": episodes_str,
            "request_type": r[12] or "new",
            "series_id": r[13] or "",
            "is_update": is_update
        })
    return {"status": "success", "data": results}

@router.post("/api/manage/requests/batch")
def batch_manage_action(data: BulkAdminActionModel, request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    # 🔥 预先批量查询所有需要通知的工单信息（优化数据库查询）
    notify_items = []  # 收集所有需要通知的工单
    
    for item in data.items:
        tid = item['tmdb_id']; sn = item['season']
        if data.action == "approve":
            row = get_media_request(tid, sn)
            
            mp_url = get_moviepilot_url(); mp_token = get_moviepilot_token()
            if mp_url and mp_token and row:
                payload = { "name": row["title"], "tmdbid": int(tid), "year": str(row["year"]), "type": "电影" if row["media_type"]=="movie" else "电视剧" }
                if row["media_type"] == "tv": payload["season"] = sn
                try: moviepilot_client.subscribe(mp_url, mp_token, payload, timeout=10)
                except Exception: pass
            update_media_request_status(tid, sn, 1)
            
        elif data.action == "manual":
            update_media_request_status(tid, sn, 4)
            
        elif data.action == "reject":
            update_media_request_status(tid, sn, 3, data.reject_reason)
        elif data.action == "finish":
            update_media_request_status(tid, sn, 2)
        elif data.action == "hdhive_done":
            # 影巢转存完成后，状态设为待入库(7)
            update_media_request_status(tid, sn, 7)
        elif data.action == "delete":
            delete_media_request(tid, sn)
    
    # 🔥 批量通知用户（审批通过、入库完成、拒绝、手动接单、影巢转存完成）
    if data.action in ["approve", "finish", "reject", "manual", "hdhive_done"]:
        try:
            rule = notify_admin.get_notify_rule('request_status')
            logger.info(f"[状态变更通知] action={data.action}, rule={rule}")
            
            if rule and rule.get('enabled') and 'tg_bot' in rule.get('channels', []):
                # 🔥 批量查询所有工单信息和用户绑定关系
                notify_items, user_ids = list_request_status_notify_items(data.items)
                tg_bindings = list_tg_bindings(user_ids)
                logger.info(f"[状态变更通知] 共 {len(notify_items)} 个工单需要通知，TG绑定数: {len(tg_bindings)}")
                
                # 🔥 发送通知
                for ni in notify_items:
                    req_row = ni['request']
                    title = req_row['title']
                    year = req_row['year'] or ''
                    media_type = req_row['media_type']
                    season = req_row['season']
                    episodes = req_row['episodes'] or ''
                    poster = req_row['poster_path'] or ''
                    
                    # 构建标题
                    if media_type == 'tv':
                        if episodes:
                            title_text = f"{title} S{season}E{episodes.replace(',', '-')}"
                        else:
                            title_text = f"{title} S{season}"
                    else:
                        title_text = title
                    
                    # 状态文本和图标
                    if data.action == "approve":
                        status_icon = "🚀"
                        status_text = "审批通过，正在下载中"
                    elif data.action == "finish":
                        status_icon = "✅"
                        status_text = "已入库完成，可以观看啦！"
                    elif data.action == "reject":
                        status_icon = "❌"
                        status_text = f"已拒绝\n📝 原因: {data.reject_reason or '未说明'}"
                    elif data.action == "manual":
                        status_icon = "✋"
                        status_text = "已手动接单，正在处理中"
                    elif data.action == "hdhive_done":
                        status_icon = "📥"
                        status_text = "影巢转存成功，等待入库"
                    else:
                        status_icon = "📢"
                        status_text = "状态已更新"
                    
                    # 🔥 处理封面 URL
                    img_url = None
                    if poster:
                        if poster.startswith('http://') or poster.startswith('https://'):
                            img_url = poster
                        elif poster.startswith('/'):
                            img_url = f"https://image.tmdb.org/t/p/w300{poster}"
                    
                    msg = f"{status_icon} <b>求片状态更新</b>\n\n📺 <b>内容：</b>{title_text} ({year})\n📢 <b>状态：</b>{status_text}"
                    
                    # 发送通知给所有请求该片的用户
                    for u in ni['users']:
                        user_id = u['user_id']
                        tg_id = tg_bindings.get(user_id)
                        
                        if tg_id:
                            logger.info(f"[状态变更通知] 发送通知: user_id={user_id}, tg_id={tg_id}, action={data.action}")
                            try:
                                if img_url:
                                    notification_service.send_user_bot_photo(int(tg_id), img_url, msg)
                                else:
                                    notification_service.send_user_bot_message(int(tg_id), msg)
                                logger.info(f"[状态变更通知] 发送成功: tg_id={tg_id}")
                            except Exception as e3:
                                logger.error(f"[状态变更通知] 发送失败: tg_id={tg_id}, error={e3}")
                        else:
                            logger.info(f"[状态变更通知] 用户 {user_id} 未绑定TG，跳过通知")
            else:
                logger.warning(f"[状态变更通知] 规则未启用或渠道不含tg_bot")
        except Exception as e:
            logger.error(f"[状态变更通知] 发送失败: {e}")
            
    return {"status": "success", "message": f"操作已执行"}

@router.post("/api/manage/requests/action")
def manage_request_action(data: AdminActionModel, request: Request):
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    return batch_manage_action(BulkAdminActionModel(items=[{"tmdb_id": data.tmdb_id, "season": data.season}], action=data.action, reject_reason=data.reject_reason), request)

@router.get("/api/requests/pending_notify")
def get_pending_notify(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        req_count, req_rows, feed_count, feed_rows = get_pending_notify_data()
        
        items = []
        for r in req_rows:
            items.append({
                "id": f"req_{r['tmdb_id']}_{r['season']}", 
                "title": r['title'] + (f" (第{r['season']}季)" if r['media_type'] == 'tv' else ""), 
                "poster": r['poster_path'], 
                "users": r['users'], 
                "time": r['created_at'],
                "type": "request"
            })
            
        for f in feed_rows:
            items.append({
                "id": f"feed_{f['id']}",
                "title": f"⚠️ 报错: {f['item_name']}",
                "poster": f['poster'] or "", 
                "users": f"{f['username']} - {f['issue_type']}",
                "time": f['created_at'],
                "type": "feedback"
            })
            
        items.sort(key=lambda x: x['time'], reverse=True)
        return {"status": "success", "count": req_count + feed_count, "items": items[:5]}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/requests/feedback/submit")
def submit_feedback(data: FeedbackSubmitModel, request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "请重新登录"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除，请重新登录", "account_deleted": True}
    
    uid = str(user.get("Id", "")); uname = user.get("Name") or "未知用户"
    
    actual_poster = data.poster_path
    if actual_poster and actual_poster.startswith("/"):
        base_url = get_pulse_url() or str(request.base_url).rstrip('/')
        actual_poster = f"{base_url}{actual_poster}"
        
    if not actual_poster or 'undefined' in actual_poster:
        r = find_poster_for_feedback(data.item_name)
        if r and r["poster_path"]: actual_poster = r["poster_path"]
        
    if not actual_poster or 'undefined' in actual_poster: actual_poster = ""

    feed_id = create_media_feedback(data.item_name, uid, uname, data.issue_type, data.description, actual_poster)
    
    msg = (f"🚨 <b>新资源报错提醒</b>\n\n"
           f"👤 <b>用户</b>：{uname}\n"
           f"🎬 <b>媒体</b>：{data.item_name}\n"
           f"🏷️ <b>问题</b>：{data.issue_type}\n"
           f"📝 <b>描述</b>：{data.description or '无'}")
    
    admin_url = get_pulse_url() or str(request.base_url).rstrip('/')
    keyboard = {"inline_keyboard": [
        [{"text": "🛠️ 标记修复中", "callback_data": f"feed_fix_{feed_id}"},
         {"text": "✅ 标记已修复", "callback_data": f"feed_done_{feed_id}"}],
        [{"text": "❌ 暂不处理(忽略)", "callback_data": f"feed_reject_{feed_id}"},
         {"text": "💻 网页处理", "url": f"{admin_url}/requests_admin"}]
    ]}
    
    img_url = actual_poster or REPORT_COVER_URL
    
    # 🔥 使用 notify_rules 配置控制通知渠道
    try:
        rule = notify_admin.get_notify_rule('feedback_new')
        
        if rule and rule.get('enabled'):
            channels = rule.get('channels', [])
            platform = "none"
            if 'tg_bot' in channels and 'wecom' in channels:
                platform = "all"
            elif 'tg_bot' in channels:
                platform = "tg"
            elif 'wecom' in channels:
                platform = "wecom"
            
            if platform != "none":
                notification_service.send_photo("sys_notify", img_url, msg, reply_markup=keyboard, platform=platform)
            
            # Web 通知中心
            if 'web' in channels:
                add_system_notification(
                    notify_type="system",
                    title=f"⚠️ 资源报错: {uname}",
                    message=f"{data.item_name} - {data.issue_type}",
                    action_url="/requests_admin?tab=feedback"
                )
        else:
            # 默认不发送（关闭状态）
            pass
    except Exception as e:
        logger.error(f"[报错通知] 发送失败: {e}")
    
    return {"status": "success", "message": "反馈已提交，感谢您的协助！"}

@router.get("/api/requests/feedback/my")
def get_my_feedback(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    uid = str(user.get("Id", ""))
    rows = list_my_feedback(uid)
    results = [{"id": r[0], "item_name": r[1], "issue_type": r[2], "description": r[3], "status": r[4], "created_at": r[5]} for r in rows]
    return {"status": "success", "data": results}

@router.get("/api/manage/feedback")
def get_all_feedback(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    rows = list_all_feedback()
    results = [{"id": r[0], "item_name": r[1], "username": r[2], "issue_type": r[3], "description": r[4], "status": r[5], "created_at": r[6]} for r in rows]
    return {"status": "success", "data": results}

@router.post("/api/manage/feedback/action")
def manage_feedback_action(data: FeedbackActionModel, request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    status_map = {"fix": 1, "done": 2, "reject": 3, "delete": -1}
    st = status_map.get(data.action, 0)
    update_feedback_status(data.id, st)
    return {"status": "success", "message": "已更新工单状态"}

@router.post("/api/manage/feedback/batch")
def batch_feedback_action(data: BulkFeedbackActionModel, request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    status_map = {"fix": 1, "done": 2, "reject": 3, "delete": -1}
    st = status_map.get(data.action, 0)
    update_feedback_status_batch(data.items, st)
    return {"status": "success", "message": "批量操作已完成"}

@router.get("/api/requests/safe_top")
def get_safe_top_media(category: str, request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}
    
    uid = user['Id']
    logger.debug(f"[热播榜] 用户 {uid} 请求 {category} 榜单")
    
    # 🔥 尝试从缓存获取全局热播榜数据
    cache_key = f"safe_top_{category}"
    global_items = _get_cache(cache_key)
    logger.debug(f"[热播榜] 缓存命中: {global_items is not None}, 数据量: {len(global_items) if global_items else 0}")
    
    if not global_items:
        try:
            logger.debug(f"[热播榜] 调用 api_top_movies 获取数据...")
            global_res = playback_stats.api_top_movies(user_id="all", category=category, sort_by="count")
            logger.debug(f"[热播榜] api_top_movies 返回状态: {global_res.get('status')}, 数据量: {len(global_res.get('data', []))}")
            global_items = global_res.get("data", [])
            
            if global_items:
                # 🔥 缓存全局数据（不过滤用户权限）
                _set_cache(cache_key, global_items[:50], COMMUNITY_CACHE_TTL_TOP)
                logger.debug(f"[热播榜] 已缓存 {len(global_items[:50])} 条数据")
            else:
                logger.warning(f"[热播榜] api_top_movies 返回空数据，未缓存")
        except Exception as e:
            logger.error(f"[热播榜] 数据获取失败: {e}")
            return {"status": "error", "data": [], "error": safe_error_message(e)}
    
    if not global_items:
        logger.warning(f"[热播榜] 最终数据为空")
        return {"status": "success", "data": []}
    
    # 🔥 用户权限过滤（这部分很快，不需要缓存）
    try:
        candidate_items = global_items[:50]
        item_ids = ",".join([str(i["ItemId"]) for i in candidate_items])
        logger.debug(f"[热播榜] 待过滤 ItemIds 数量: {len(candidate_items)}, 总长度: {len(item_ids)}")
        
        # 🔥 尝试不同的 API 调用方式
        # 方式1: 不带 Recursive 参数
        res1 = media_api.get(f"/Users/{uid}/Items", params={"Ids": item_ids}, timeout=5)
        items1 = res1.json().get("Items", [])
        logger.debug(f"[热播榜] 方式1 结果: 状态码 {res1.status_code}, Items 数量 {len(items1)}")
        
        # 方式2: 使用 /Items 而不是 /Users/{uid}/Items
        res2 = media_api.get("/Items", params={"Ids": item_ids, "UserId": uid}, timeout=5)
        items2 = res2.json().get("Items", [])
        logger.debug(f"[热播榜] 方式2 结果: 状态码 {res2.status_code}, Items 数量 {len(items2)}")
        
        # 使用能返回数据的方式
        emby_items = items1 if items1 else items2
        if not emby_items:
            logger.warning(f"[热播榜] 两种方式都返回空")
            return {"status": "success", "data": []}
        
        allowed_ids = {str(item["Id"]) for item in emby_items}
        logger.debug(f"[热播榜] 用户有权限的 Item 数量: {len(allowed_ids)}")
        
        safe_top_10 = [i for i in candidate_items if str(i["ItemId"]) in allowed_ids][:10]
        logger.debug(f"[热播榜] 过滤后剩余: {len(safe_top_10)} 条")
        
        return {"status": "success", "data": safe_top_10, "from_cache": True}
    except Exception as e:
        logger.error(f"[热播榜] 权限过滤失败: {e}")
        return {"status": "error", "data": [], "error": safe_error_message(e)}

@router.get("/api/requests/safe_latest")
def get_safe_latest(limit: int = 15, request: Request = None):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}
    
    uid = user['Id']
    
    # 🔥 尝试从缓存获取全局最新数据
    cache_key = "safe_latest"
    global_items = _get_cache(cache_key)
    
    if not global_items:
        try:
            global_res = playback_stats.api_latest_media(limit=40)
            global_items = global_res.get("data", [])
            
            if global_items:
                # 🔥 缓存全局数据
                _set_cache(cache_key, global_items, COMMUNITY_CACHE_TTL_LATEST)
        except Exception as e:
            print(f"最新数据获取失败: {e}")
            return {"status": "error", "data": []}
    
    if not global_items:
        return {"status": "success", "data": []}
    
    # 🔥 用户权限过滤
    try:
        item_ids = ",".join([str(i.get("Id") or i.get("ItemId")) for i in global_items])
        logger.debug(f"[最新收录] 待过滤 ItemIds 数量: {len(global_items)}")
        
        # 🔥 尝试不同的 API 调用方式
        # 方式1: 不带 Recursive
        emby_res1 = media_api.get(f"/Users/{uid}/Items", params={"Ids": item_ids}, timeout=5).json()
        items1 = emby_res1.get("Items", [])
        logger.debug(f"[最新收录] 方式1 结果: {len(items1)} 条")
        
        # 方式2: 带 UserId 参数
        emby_res2 = media_api.get("/Items", params={"Ids": item_ids, "UserId": uid}, timeout=5).json()
        items2 = emby_res2.get("Items", [])
        logger.debug(f"[最新收录] 方式2 结果: {len(items2)} 条")
        
        emby_items = items1 if items1 else items2
        if not emby_items:
            logger.warning(f"[最新收录] 两种方式都返回空")
            return {"status": "success", "data": []}
        
        allowed_ids = {str(item["Id"]) for item in emby_items}
        
        safe_items = []
        for i in global_items:
            i_id = str(i.get("Id") or i.get("ItemId"))
            if i_id in allowed_ids:
                safe_items.append(i)
        
        logger.debug(f"[最新收录] 过滤后剩余: {len(safe_items)} 条")
                
        return {"status": "success", "data": safe_items[:limit], "from_cache": True}
    except Exception as e:
        logger.error(f"[最新收录] 权限过滤失败: {e}")
        return {"status": "error", "data": []}


# ==================== 用户社区缓存管理 ====================

def _refresh_community_cache():
    """后台刷新用户社区首页缓存（由定时任务调用）"""
    if not _community_refresh_lock.acquire(blocking=False):
        logger.info("用户社区缓存正在刷新，跳过本次请求")
        return
    try:
        # 获取 admin 用户 ID
        admin_id = get_emby_admin()
        if not admin_id:
            logger.warning("缓存刷新失败: 无法获取 admin 用户")
            return
        
        # 1. 刷新 hub_data
        try:
            import random
            # 🔥 使用 /Items API 而不是 /Users/{uid}/Items，避免权限问题
            tr_res = media_api.get("/Items", params={
                "IncludeItemTypes": "Movie,Series",
                "Recursive": "true",
                "SortBy": "CommunityRating",
                "SortOrder": "Descending",
                "Limit": 100,
                "Fields": "CommunityRating",
            }, timeout=10).json()
            items = tr_res.get("Items", [])
            logger.debug(f"[后台刷新] 镇站之宝返回: {len(items)} 条")
            
            # 🔥 打印前3条数据结构
            for idx, item in enumerate(items[:3]):
                logger.debug(f"[后台刷新] 镇站之宝第{idx+1}条: Name={item.get('Name')}, CommunityRating={item.get('CommunityRating')}, Type={item.get('Type')}")
            
            valid_items = []
            for i in items:
                rating = i.get("CommunityRating", 0) or 0
                if 8.0 <= rating <= 9.8:
                    valid_items.append({
                        "Id": i.get("Id"), "Name": i.get("Name"), "Type": i.get("Type"),
                        "CommunityRating": rating
                    })
            random.shuffle(valid_items)
            top_rated = valid_items[:10]
            logger.debug(f"[后台刷新] 镇站之宝筛选后: {len(top_rated)} 条")
            
            # 🔥 使用 /Items API
            g_res = media_api.get("/Items", params={
                "IncludeItemTypes": "Movie,Series",
                "Recursive": "true",
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Limit": 200,
                "Fields": "Genres",
            }, timeout=10).json()
            g_items = g_res.get("Items", [])
            logger.debug(f"[后台刷新] 流派分析返回: {len(g_items)} 条")
            
            # 🔥 打印前3条数据结构
            for idx, item in enumerate(g_items[:3]):
                logger.debug(f"[后台刷新] 流派第{idx+1}条: Name={item.get('Name')}, Genres={item.get('Genres')}")
            
            genre_counts = {}
            total_items = 0
            for i in g_items:
                gs = i.get("Genres", [])
                if gs:
                    total_items += 1
                    for g in gs: genre_counts[g] = genre_counts.get(g, 0) + 1
            
            genres_data = []
            if total_items > 0:
                sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:6]
                for k, v in sorted_genres:
                    genres_data.append({"name": k, "count": v, "pct": round(v / total_items * 100)})
            logger.debug(f"[后台刷新] 流派分析结果: {len(genres_data)} 种")
            
            _set_cache("hub_data", {"top_rated": top_rated, "genres": genres_data}, COMMUNITY_CACHE_TTL_HUB)
            logger.info("hub_data 缓存已刷新")
        except Exception as e:
            logger.error(f"hub_data 缓存刷新失败: {e}")
        
        # 2. 刷新 safe_latest
        try:
            global_res = playback_stats.api_latest_media(limit=40)
            global_items = global_res.get("data", [])
            if global_items:
                _set_cache("safe_latest", global_items, COMMUNITY_CACHE_TTL_LATEST)
                logger.info("safe_latest 缓存已刷新")
        except Exception as e:
            logger.error(f"safe_latest 缓存刷新失败: {e}")
        
        # 3. 刷新 safe_top (Movie 和 Episode)
        try:
            for category in ["Movie", "Episode"]:
                global_res = playback_stats.api_top_movies(user_id="all", category=category, sort_by="count")
                global_items = global_res.get("data", [])
                if global_items:
                    _set_cache(f"safe_top_{category}", global_items[:50], COMMUNITY_CACHE_TTL_TOP)
                    logger.info(f"safe_top_{category} 缓存已刷新")
        except Exception as e:
            logger.error(f"safe_top 缓存刷新失败: {e}")
            
    except Exception as e:
        logger.error(f"用户社区缓存刷新失败: {e}")
    finally:
        try:
            _community_refresh_lock.release()
        except RuntimeError:
            pass


def start_community_cache_refresh_loop() -> None:
    global _community_refresh_started, _community_refresh_thread
    with _community_refresh_start_lock:
        if _community_refresh_started:
            return
        _community_refresh_started = True
        _community_refresh_stop_event.clear()

    def _refresh_loop():
        if _community_refresh_stop_event.wait(15):
            return
        _refresh_community_cache()
        while not _community_refresh_stop_event.wait(300):
            _refresh_community_cache()

    _community_refresh_thread = threading.Thread(target=_refresh_loop, daemon=True, name="community-cache-refresh")
    _community_refresh_thread.start()


def stop_community_cache_refresh_loop() -> None:
    global _community_refresh_started, _community_refresh_thread
    with _community_refresh_start_lock:
        if not _community_refresh_started:
            return
        _community_refresh_stop_event.set()
        thread = _community_refresh_thread
        _community_refresh_started = False
        _community_refresh_thread = None
    if thread and thread.is_alive():
        thread.join(timeout=1)


def start_media_request_services() -> None:
    ensure_media_request_schema()
    start_community_cache_refresh_loop()


def stop_media_request_services() -> None:
    stop_community_cache_refresh_loop()


@router.post("/api/requests/refresh_cache")
def refresh_community_cache_api(request: Request):
    """手动刷新用户社区首页缓存（管理员接口）"""
    if not request.session.get("user"):
        return JSONResponse(status_code=401, content={"status": "error", "message": "未登录"})
    if not user_service.is_admin_user(request):
        return JSONResponse(status_code=403, content={"status": "error", "message": "需要管理员权限"})

    # 后台执行刷新
    _refresh_community_cache()
    return {"status": "success", "message": "缓存已刷新"}


@router.post("/api/requests/clear_cache")
def clear_community_cache_api(request: Request):
    """清除用户社区首页缓存（管理员接口）"""
    if not request.session.get("user"):
        return JSONResponse(status_code=401, content={"status": "error", "message": "未登录"})
    if not user_service.is_admin_user(request):
        return JSONResponse(status_code=403, content={"status": "error", "message": "需要管理员权限"})

    _invalidate_cache()
    return {"status": "success", "message": "缓存已清除"}


# ==================== 追新功能 API ====================

class UpdateRequestModel(BaseModel):
    """追新请求模型"""
    series_id: str
    tmdb_id: int
    title: str
    year: Optional[str] = ""
    poster_path: Optional[str] = ""
    season: int
    episodes: List[int]  # 请求的集数列表


def _get_local_episodes(series_id: str, season: int) -> set:
    """获取库里某剧集某季已有的集数"""
    try:
        from app.infra.clients.media_server_client import media_api
        admin_id = get_emby_admin()
        if not admin_id:
            return set()
        
        eps_data = media_api.get(f"/Users/{admin_id}/Items", params={
            "ParentId": series_id,
            "IncludeItemTypes": "Episode",
            "Recursive": "true",
            "Fields": "IndexNumber,ParentIndexNumber"
        }, timeout=10).json().get("Items", [])
        
        local_eps = set()
        for ep in eps_data:
            sn = ep.get("ParentIndexNumber")
            en = ep.get("IndexNumber")
            if sn == season and en is not None:
                local_eps.add(en)
        
        return local_eps
    except Exception as e:
        print(f"[追新] 获取本地集数失败: {e}")
        return set()


def _get_tmdb_season_episodes(tmdb_id: int, season: int) -> dict:
    """获取 TMDB 某季的集数信息"""
    proxies = get_safe_proxies()
    
    try:
        res = tmdb_client.get_tv_season(tmdb_id, season, proxies=proxies, timeout=10).json()
        
        episodes = []
        for ep in res.get("episodes", []):
            episodes.append({
                "episode_number": ep.get("episode_number"),
                "name": ep.get("name", ""),
                "air_date": ep.get("air_date", "")
            })
        
        return {
            "total_episodes": len(episodes),
            "episodes": episodes
        }
    except Exception as e:
        print(f"[追新] 获取 TMDB 集数失败: {e}")
        return {"total_episodes": 0, "episodes": []}


@router.get("/api/user/my_series")
def get_user_series(request: Request):
    """获取用户观看过的剧集列表（用于追新）- 缓存优化版"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    uid = user['Id']
    proxies = get_safe_proxies()
    
    try:
        # 🚀 优化：从缺集管理缓存读取数据，大幅提速
        cache_row, cache_interval_hours, update_requests = get_user_series_db_context()
        
        # 3. 检查缓存是否过期
        cache_expired = False
        if cache_row:
            updated_at = cache_row["updated_at"] or ""
            try:
                from datetime import datetime, timedelta
                cache_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                cache_expired = (now - cache_time) > timedelta(hours=cache_interval_hours)
            except:
                cache_expired = True
        
        # 4. 获取用户最近播放的剧集（用于匹配缓存）
        try:
            eps_res = media_api.get(f"/Users/{uid}/Items", params={
                "IncludeItemTypes": "Episode",
                "Recursive": "true",
                "SortBy": "DatePlayed",
                "SortOrder": "Descending",
                "Limit": 50,
                "Fields": "SeriesId,SeriesName",
            }, timeout=10).json()
        except:
            eps_res = {"Items": []}
        
        # 5. 按 series_id 分组用户观看的剧集
        user_series_ids = set()
        for ep in eps_res.get("Items", []):
            series_id = ep.get("SeriesId")
            if series_id:
                user_series_ids.add(series_id)
        
        # 🚀 7. 从缓存匹配用户观看的剧集
        results = []
        gap_cache = decode_gap_cache(cache_row)
        
        # 如果缓存为空或过期，提示用户刷新
        if not gap_cache:
            # 获取追新积分配置
            update_config = get_update_cost_config()
            
            return {
                "status": "success",
                "data": [],
                "cache_info": {
                    "exists": False,
                    "expired": True,
                    "updated_at": "",
                    "interval_hours": cache_interval_hours
                },
                "update_cost_info": {
                    "enabled": update_config["enabled"],
                    "cost": update_config["cost"]
                }
            }
        
        # 8. 匹配用户观看的剧集
        for series in gap_cache:
            series_id = series.get("series_id")
            tmdb_id = series.get("tmdb_id")  # 🔥 修复：用 tmdb_id 查询状态
            if series_id not in user_series_ids:
                continue
            
            # 过滤掉已完结的剧集
            if series.get("tmdb_status") in ["Ended", "Canceled"]:
                continue
            
            # 获取该剧的追新请求状态 - 🔥 修复：用 tmdb_id + season
            gaps = series.get("gaps", [])
            series_request_status = {}
            for gap in gaps:
                season = gap.get("season")
                req_key = f"{tmdb_id}_{season}"  # tmdb_id + season
                if req_key in update_requests:
                    series_request_status[season] = update_requests[req_key]
            
            # 构建每季的缺集信息
            seasons_info = []
            grouped_gaps = {}
            for gap in gaps:
                sn = gap.get("season")
                if sn not in grouped_gaps:
                    grouped_gaps[sn] = []
                grouped_gaps[sn].append(gap.get("episode"))
            
            # 🔥 按季排序显示
            for sn in sorted(grouped_gaps.keys()):
                missing_eps = sorted(grouped_gaps[sn]) if grouped_gaps[sn] else []
                req_key = f"{tmdb_id}_{sn}"  # 🔥 修复：用 tmdb_id + season
                req_status = update_requests.get(req_key)
                
                # 🔥 修复：从 gaps 数据推断总集数和本地集数
                # gaps 里只有缺失的集数，无法准确知道总集数
                # 使用缺失集数的最大值作为最小总集数估计
                tmdb_total = max(missing_eps) if missing_eps else 10  # 默认假设10集
                local_count = 0  # 缓存模式无法准确获取本地集数
                
                seasons_info.append({
                    "season": int(sn),  # 🔥 确保是整数
                    "local_count": local_count,
                    "tmdb_total": tmdb_total,
                    "local_eps": [],
                    "missing_eps": missing_eps,
                    "unaired_eps": [],
                    "request_status": req_status
                })
            
            if seasons_info:
                results.append({
                    "series_id": series_id,
                    "series_name": series.get("series_name", "未知剧集"),
                    "tmdb_id": series.get("tmdb_id"),
                    "poster": series.get("poster", ""),
                    "year": "",
                    "total_seasons": len(seasons_info),
                    "seasons": seasons_info
                })
        
        # 9. 获取追新积分配置
        update_config = get_update_cost_config()
        
        return {
            "status": "success",
            "data": results[:10],
            "cache_info": {
                "exists": bool(cache_row),
                "expired": cache_expired,
                "updated_at": cache_row["updated_at"] if cache_row else "",
                "interval_hours": cache_interval_hours
            },
            "update_cost_info": {
                "enabled": update_config["enabled"],
                "cost": update_config["cost"],
                "mode": update_config["mode"],
                "base_cost": update_config["cost"]
            }
        }
    
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/user/my_series/refresh")
def refresh_my_series_cache(request: Request, bg_tasks: BackgroundTasks):
    """手动刷新追剧缓存（触发后台重新扫描）"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    # 触发缺集管理重新扫描
    try:
        # 调用 gaps 模块的扫描功能
        from app.domains.media_requests.gaps import scan_state, state_lock, run_scan_task
        
        with state_lock:
            if scan_state["is_scanning"]:
                return {"status": "success", "message": "正在扫描中，请稍后再查看"}
            scan_state.update({"is_scanning": True, "progress": 0, "total": 0, "results": [], "error": None, "current_item": "系统准备中..."})
        
        bg_tasks.add_task(run_scan_task)
        return {"status": "success", "message": "已触发后台扫描，请稍后刷新查看"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# 🔥 辅助函数：获取请求状态文本（同步版本）
def getRequestStatusTextSync(status):
    status_map = {0: '待审批', 1: '下载中', 2: '已完成', 3: '已拒绝', 4: '手动接单', 7: '待入库'}
    return status_map.get(status, '未知')


@router.post("/api/user/request_update")
async def submit_update_request(request: Request):
    """提交追新请求"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}
    
    uid = user['Id']
    uname = user['Name']
    
    try:
        data = await request.json()
        series_id = data.get("series_id")
        tmdb_id = int(data.get("tmdb_id") or 0)
        title = data.get("title")
        year = data.get("year", "")
        poster_path = data.get("poster_path", "")
        season = int(data.get("season") or 0)
        episodes = data.get("episodes", [])  # 列表 [6, 7, 8]
        
        if not tmdb_id or not season or not episodes:
            return {"status": "error", "message": "参数不完整"}
        
        # 验证集数
        episodes = [int(e) for e in episodes if int(e) > 0]
        if not episodes:
            return {"status": "error", "message": "请选择有效的集数"}
        
        # 🔥 检查未播出集数（禁止追更未播出的剧集）
        _, unaired_eps = get_tmdb_season_info(tmdb_id, season)
        unaired_requested = [e for e in episodes if e in unaired_eps]
        if unaired_requested:
            return {"status": "error", "message": f"以下集数尚未播出，无法追更：E{','.join(str(e) for e in unaired_requested)}"}
        
        result = submit_update_request_record(uid, uname, series_id, tmdb_id, title, year, poster_path, season, episodes)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}
        episodes_str = result["episodes_str"]
        
        # 发送通知
        try:
            # 🔥 从 TMDB 获取年份（前端提交的 year 可能为空）
            actual_year = year
            if not actual_year or actual_year == "":
                try:
                    proxies = get_safe_proxies()
                    tmdb_info = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=5).json()
                    first_air_date = tmdb_info.get("first_air_date", "")
                    actual_year = first_air_date[:4] if first_air_date else ""
                except:
                    actual_year = ""
            
            year_display = f" ({actual_year})" if actual_year else ""
            
            add_system_notification("request", f"收到追新请求: {title}", 
                               f"用户 {uname} 请求更新 S{season}E{episodes_str}", "/requests_admin")
            
            msg = f"🔄 <b>收到追新请求</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title}{year_display}\n📀 <b>季集：</b>第 {season} 季 E{episodes_str.replace(',', '-')}集\n\n请及时处理。"
            
            admin_url = get_pulse_url() or get_media_server_main_public_url() or "http://127.0.0.1:10307"
            keyboard = {"inline_keyboard": [
                [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_ep_{tmdb_id}_{season}_{episodes_str}_{title.replace('_', '-').replace(':', '').replace('：', '').replace(' ', '-')}"}],
                [{"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}_{season}"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
            ]}
            
            # 🔥 处理封面路径：本地路径需要从 TMDB 获取
            poster_url = REPORT_COVER_URL
            if poster_path and poster_path.startswith("/api/"):
                # 本地 API 路径，从 TMDB 获取封面
                try:
                    proxies = get_safe_proxies()
                    tmdb_info = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=5).json()
                    tmdb_poster = tmdb_info.get("poster_path")
                    if tmdb_poster:
                        poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_poster}"
                except:
                    pass
            elif poster_path and poster_path.startswith("/") and not poster_path.startswith("/api/"):
                # TMDB 相对路径
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            elif poster_path and poster_path.startswith("http"):
                # 完整 URL
                poster_url = poster_path
            
            notification_service.send_photo("sys_notify", poster_url, msg, reply_markup=keyboard, platform="all")
        except Exception as e:
            print(f"[追新] 发送通知失败: {e}")
        
        return {"status": "success", "message": f"追新请求已提交！等待管理员处理 S{season}E{episodes_str}"}
    
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "提交失败")}


@router.post("/api/user/request_update_batch")
async def submit_update_request_batch(request: Request):
    """批量提交追新请求（一次扣费）"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}
    
    uid = user['Id']
    uname = user['Name']
    
    try:
        data = await request.json()
        requests_list = data.get("requests", [])
        series_name = data.get("series_name", "")
        tmdb_id = int(data.get("tmdb_id") or 0)
        
        if not requests_list:
            return {"status": "error", "message": "没有追新请求"}
        
        result = submit_batch_update_request_records(uid, uname, requests_list, series_name, tmdb_id)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}
        total_seasons = result["total_seasons"]
        total_episodes = result["total_episodes"]
        total_cost = result["total_cost"]
        cost_mode = result["cost_mode"]
        print(f"[追新批量] 模式={cost_mode}, 季数={total_seasons}, 集数={total_episodes}, 扣分={total_cost}")
        
        # 发送通知
        try:
            # 🔥 构建详细季集信息
            season_details = []
            for req in requests_list:
                req_season = req.get("season")
                req_episodes = req.get("episodes", [])
                if req_season and req_episodes:
                    eps_str = ",".join(str(e) for e in sorted(req_episodes))
                    season_details.append(f"第 {req_season} 季 E{eps_str.replace(',', '-')}集")
            
            season_detail_str = "\n".join(season_details)
            
            add_system_notification("request", f"收到批量追新请求: {series_name}", 
                               f"用户 {uname} 请求更新\n{season_detail_str}", "/requests_admin")
            
            # 🔥 从 TMDB 获取封面
            poster_url = REPORT_COVER_URL
            try:
                proxies = get_safe_proxies()
                tmdb_info = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=5).json()
                tmdb_poster = tmdb_info.get("poster_path")
                first_air_date = tmdb_info.get("first_air_date", "")
                year_display = f" ({first_air_date[:4]})" if first_air_date else ""
                if tmdb_poster:
                    poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_poster}"
            except:
                year_display = ""
            
            msg = f"🔄 <b>收到批量追新请求</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{series_name}{year_display}\n\n📀 <b>季集详情：</b>\n{season_detail_str}\n\n请及时处理。"
            
            admin_url = get_pulse_url() or get_media_server_main_public_url() or "http://127.0.0.1:10307"
            
            # 🔥 简化按钮：影巢搜索（标题）+ 手动接单 + 网页审批
            keyboard = {"inline_keyboard": [
                [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_{tmdb_id}_{series_name.replace('_', '-').replace(':', '').replace('：', '').replace(' ', '-')}"}],
                [{"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}_0"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
            ]}
            
            notification_service.send_photo("sys_notify", poster_url, msg, reply_markup=keyboard, platform="all")
        except Exception as e:
            print(f"[追新批量] 发送通知失败: {e}")
        
        return {"status": "success", "message": f"批量追新请求已提交！{total_seasons} 季 {total_episodes} 集"}
    
    except Exception as e:
        print(f"[追新批量] 错误: {e}")
        return {"status": "error", "message": safe_error_message(e, "提交失败")}


@router.post("/api/manage/requests/search_episodes")
def search_episodes_for_update(payload: dict, request: Request):
    """搜索单集资源（追新工单使用，复用缺集搜索逻辑）"""
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "无权访问"}
    
    tmdb_id = payload.get("tmdb_id")
    season = payload.get("season")
    episodes = payload.get("episodes", [])
    
    if not tmdb_id or season is None or not episodes:
        return {"status": "error", "message": "参数不完整"}
    
    # 获取剧集名称 - 优先从数据库获取追新请求的标题
    row = get_update_request_search_info(tmdb_id, season)
    
    series_name = row["title"] if row else "未知剧集"
    series_id = row["series_id"] if row else ""
    
    # 调用缺集搜索 API - 传递完整参数
    try:
        from app.domains.media_requests.gaps import search_mp_for_gap
        result = search_mp_for_gap({
            "series_name": series_name,
            "series_id": series_id,
            "tmdb_id": tmdb_id,
            "season": season,
            "episodes": episodes,
            "type": "tv"
        })
        # 转换返回格式，适配前端
        if result.get("status") == "success" and result.get("data"):
            raw_results = result["data"].get("results", [])
            # 确保返回完整的字段
            processed_results = []
            for r in raw_results:
                processed_results.append({
                    "ui_title": r.get("ui_title", r.get("title", "")),
                    "ui_size": r.get("ui_size", 0),
                    "ui_seeders": r.get("ui_seeders", 0),
                    "ui_extracted_episodes": r.get("ui_extracted_episodes", []),
                    "ui_matched_episodes": r.get("ui_matched_episodes", []),
                    "ui_site": r.get("ui_site", "MP"),
                    "ui_desc": r.get("ui_desc", ""),
                    "ui_resolution": r.get("ui_resolution", ""),
                    "ui_resource": r.get("ui_resource", ""),
                    "ui_labels": r.get("ui_labels", []),
                    "ui_chinese_audio": r.get("ui_chinese_audio", False),
                    "ui_chinese_sub": r.get("ui_chinese_sub", False),
                    "match_score": r.get("match_score", 0),
                    "is_pack": r.get("is_pack", False),
                    "enclosure": r.get("enclosure", ""),
                    "org_payload": r.get("org_payload", r)
                })
            return {"status": "success", "results": processed_results}
        return result
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "搜索失败")}


@router.post("/api/manage/requests/download_episodes")
def download_episodes_for_update(payload: dict, request: Request):
    """下载单集资源（追新工单使用，复用缺集下载逻辑）"""
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "无权访问"}
    
    series_id = payload.get("series_id")
    series_name = payload.get("series_name")
    tmdb_id = payload.get("tmdb_id")
    season = payload.get("season")
    episodes = payload.get("episodes", [])
    torrent_info = payload.get("torrent_info", {})
    
    if not episodes:
        return {"status": "error", "message": "未指定集数"}
    
    # 调用缺集下载 API
    try:
        from app.domains.media_requests.gaps import download_gap_item
        result = download_gap_item({
            "series_id": series_id or "",
            "series_name": series_name,
            "tmdb_id": tmdb_id,
            "season": season,
            "episodes": episodes,
            "torrent_info": torrent_info
        })
        
        # 更新工单状态为下载中
        if result.get("status") == "success":
            episodes_str = ",".join(str(e) for e in episodes)
            # 更新所有匹配的追新工单
            update_media_request_status(tmdb_id, season, 1)
        
        return result
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "下载失败")}


# ==================== 用户社区注册 API ====================

class UserRegisterModel(BaseModel):
    """用户社区注册模型"""
    code: str
    username: str
    password: str

def _restore_invitation_code(code):
    """Emby 用户创建失败时回滚邀请码消费计数"""
    try:
        restore_invitation_code(code)
    except Exception:
        pass


@router.post("/api/requests/register")
async def user_community_register(data: UserRegisterModel, request: Request):
    """用户社区注册 API - 注册成功后自动登录"""
    try:
        # 1. 先校验用户名和密码（不消耗邀请码）
        username = data.username.strip()
        if not username or len(username) < 2:
            return {"status": "error", "message": "用户名至少需要 2 个字符"}

        if len(username) > 16:
            return {"status": "error", "message": "用户名最多 16 个字符，当前 " + str(len(username)) + " 个字符"}

        safe_name = re.sub(r'[^a-zA-Z0-9一-龥_\-.@]', '', username)

        if safe_name != username:
            invalid_chars = set(re.findall(r'[^a-zA-Z0-9一-龥_\-.@]', username))
            invalid_str = ', '.join(f"'{c}'" for c in list(invalid_chars)[:5])
            return {"status": "error", "message": f"用户名包含不支持的字符: {invalid_str}。只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 ."}

        if not safe_name:
            return {"status": "error", "message": "用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 ."}

        password = data.password.strip()
        pw_valid, pw_error = validate_password_strength(password)
        if not pw_valid:
            return {"status": "error", "message": pw_error}

        # 2. 检查 Emby 用户名是否已存在
        try:
            users = media_api.get("/Users", timeout=5).json()
            if any(u['Name'].lower() == safe_name.lower() for u in users):
                return {"status": "error", "message": f"用户名 {safe_name} 已被占用，请换一个"}
        except Exception as e:
            return {"status": "error", "message": safe_error_message(e, "检查用户名失败")}

        # 3. 所有校验通过后，原子抢占邀请码（防 TOCTOU 竞态）
        invite, invite_error = claim_registration_invitation(data.code, safe_name)
        if invite_error:
            return {"status": "error", "message": invite_error}

        days = invite['days'] if invite['days'] else 30
        template_user_id = invite['template_user_id'] if invite['template_user_id'] else None
        routes = invite['routes'] if invite['routes'] else ''
        route_mode = invite['route_mode'] if invite['route_mode'] else 'block'
        req_free = invite['req_free'] if 'req_free' in invite.keys() else 0
        req_free_count = invite['req_free_count'] if 'req_free_count' in invite.keys() else -1

        # 4. 创建 Emby 用户
        try:
            create_res = media_api.post("/Users/New", json={"Name": safe_name}, timeout=10)
            if create_res.status_code not in [200, 201]:
                _restore_invitation_code(data.code)
                return {"status": "error", "message": f"创建账号失败: {create_res.text}"}
            
            new_user = create_res.json()
            uid = new_user.get("Id")
            
            # 设置密码
            media_api.post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)
            
            # 应用模板（如果有）
            admin_enabled_folders = None
            if template_user_id:
                try:
                    tpl = media_api.get(f"/Users/{template_user_id}", timeout=5).json()
                    if tpl.get("Policy"):
                        policy = tpl["Policy"]
                        policy["IsAdministrator"] = False
                        policy["IsDisabled"] = False
                        media_api.post(f"/Users/{uid}/Policy", json=policy, timeout=5)
                        # 🔥 保存管理员设置的媒体库权限
                        if not policy.get("EnableAllFolders", True):
                            admin_enabled_folders = policy.get("EnabledFolders", [])
                except:
                    pass
            else:
                try:
                    # 读取完整 Policy 再合并，避免 Emby 整体替换清空默认权限
                    user_info = media_api.get(f"/Users/{uid}", timeout=5).json()
                    policy = user_info.get("Policy", {})
                    policy["IsDisabled"] = False
                    media_api.post(f"/Users/{uid}/Policy", json=policy, timeout=3)
                except:
                    pass
            
            # 6. 保存用户元数据
            import datetime as dt
            # 处理永久注册码：days = -1 或 days = 0 或 days >= 36500（100年）视为永久
            expire_date = None
            if days == -1 or days == 0 or days >= 36500:
                expire_date = None  # 永久有效用 None 表示
            elif days > 0:
                expire_date = (dt.date.today() + dt.timedelta(days=days)).strftime("%Y-%m-%d")
            
            allow_routes = ""
            block_routes = ""
            if routes:
                if route_mode == 'allow':
                    allow_routes = routes
                else:
                    block_routes = routes
            
            save_registered_user_meta(uid, expire_date, allow_routes, block_routes, req_free, req_free_count, admin_enabled_folders)

            # 清除用户列表缓存
            try:
                from app.domains.users import public_service as user_service
                user_service.invalidate_emby_users_cache()
            except:
                pass
            
            # 8. 发送通知
            try:
                from app.infra.db.notification_dao import add_system_notification
                rule = notify_admin.get_notify_rule('user_register')
                days_display = "永久" if (days == -1 or days == 0 or days >= 36500) else f"{days} 天"
                msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{data.code}\n📱 注册渠道：用户社区"
                
                if rule and rule.get('enabled'):
                    channels = rule.get('channels', [])
                    
                    # TG机器人/企业微信
                    if 'tg_bot' in channels or 'wecom' in channels:
                        platform = "all" if ('tg_bot' in channels and 'wecom' in channels) else ("tg" if 'tg_bot' in channels else "wecom")
                        notification_service.send_message("sys_notify", msg, platform=platform)
                    
                    # Web通知中心
                    if 'web' in channels:
                        add_system_notification("user", f"新用户注册: {safe_name}", f"用户社区注册，有效期 {days_display}", "/users_manage")
                else:
                    # 兜底：使用旧方式发送通知
                    notification_service.send_message("sys_notify", msg, platform="all")
                    add_system_notification("user", f"新用户注册: {safe_name}", f"用户社区注册，有效期 {days_display}", "/users_manage")
            except Exception as e:
                logger.error(f"[用户社区注册] 发送通知失败: {e}")
            
            # 9. 🔥 获取用户可访问的线路（使用 get_user_routes 根据权限过滤）
            user_routes = get_media_server_user_routes(uid)
            if not user_routes:
                # 如果没有线路，使用默认服务器地址
                server_url = get_media_server_main_public_or_host()
                if server_url:
                    user_routes = [{"name": "默认推荐节点", "url": server_url, "is_main": True}]
            
            # 10. 🔥 自动登录用户社区
            # 🔥 安全：清除整个 Session，防止残留其他用户数据
            request.session.clear()
            request.session["req_user"] = {"Id": uid, "Name": safe_name}
            
            # 11. 获取欢迎消息
            welcome_message = get_media_server_welcome_message()
            
            return {
                "status": "success",
                "message": "注册成功",
                "user": {"Id": uid, "Name": safe_name},
                "expire_days": days,
                "expire_date": expire_date,
                "server_url": json.dumps(user_routes) if user_routes else "",
                "welcome_message": welcome_message
            }
            
        except Exception as e:
            logger.error(f"[用户社区注册] 创建用户失败: {e}")
            _restore_invitation_code(data.code)
            return {"status": "error", "message": safe_error_message(e, "注册失败")}
            
    except Exception as e:
        logger.error(f"[用户社区注册] 系统错误: {e}")
        return {"status": "error", "message": safe_error_message(e, "系统错误")}
