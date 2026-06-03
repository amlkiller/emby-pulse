import json
import re
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from app.domains.media_requests import community_cache_service
from app.domains.media_requests.auth_router import (
    RequestLoginModel,
    check_auth,
    request_system_login,
    request_system_logout,
    router as auth_router,
    set_dependency_providers as set_auth_dependency_providers,
)
from app.domains.media_requests.cache_control_router import (
    clear_community_cache_api,
    refresh_community_cache_api,
    router as cache_control_router,
    set_dependency_providers as set_cache_control_dependency_providers,
    start_community_cache_refresh_loop,
    start_media_request_services,
    stop_community_cache_refresh_loop,
)
from app.domains.media_requests.discovery_router import (
    check_emby_exists,
    check_local_status,
    get_emby_admin,
    get_hub_data,
    get_item_info,
    get_tmdb_season_info,
    get_tmdb_trending,
    get_tv_details,
    router as discovery_router,
    search_tmdb,
    set_dependency_providers as set_discovery_dependency_providers,
)
from app.domains.media_requests.feedback_router import (
    BulkFeedbackActionModel,
    FeedbackActionModel,
    FeedbackSubmitModel,
    batch_feedback_action,
    get_all_feedback,
    get_my_feedback,
    manage_feedback_action,
    router as feedback_router,
    set_dependency_providers as set_feedback_dependency_providers,
    submit_feedback,
)
from app.domains.media_requests.management_router import (
    AdminActionModel,
    BulkAdminActionModel,
    batch_manage_action,
    get_all_requests,
    get_my_requests,
    get_pending_notify,
    manage_request_action,
    router as management_router,
    set_dependency_providers as set_management_dependency_providers,
)
from app.domains.media_requests.safe_media_router import (
    get_safe_latest,
    get_safe_top_media,
    router as safe_media_router,
    set_dependency_providers as set_safe_media_dependency_providers,
)
from app.domains.users import public_service as user_service
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验
from pydantic import BaseModel
from typing import Optional, List

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
# Compatibility exports for existing router callers, tests, and diagnostics.
_community_cache = community_cache_service._community_cache
_community_cache_lock = community_cache_service._community_cache_lock
_community_refresh_started = False
_community_refresh_thread = None

COMMUNITY_CACHE_TTL = community_cache_service.COMMUNITY_CACHE_TTL
COMMUNITY_CACHE_TTL_HUB = community_cache_service.COMMUNITY_CACHE_TTL_HUB
COMMUNITY_CACHE_TTL_TOP = community_cache_service.COMMUNITY_CACHE_TTL_TOP
COMMUNITY_CACHE_TTL_LATEST = community_cache_service.COMMUNITY_CACHE_TTL_LATEST

_get_cache = community_cache_service._get_cache
_set_cache = community_cache_service._set_cache
_invalidate_cache = community_cache_service._invalidate_cache


def _sync_community_cache_task_state() -> None:
    global _community_refresh_started, _community_refresh_thread
    _community_refresh_started = community_cache_service._community_refresh_started
    _community_refresh_thread = community_cache_service._community_refresh_thread


def _refresh_community_cache():
    return community_cache_service._refresh_community_cache(admin_resolver=get_emby_admin)

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


set_auth_dependency_providers(
    media_api_provider=lambda: media_api,
    main_server_url_provider=lambda: get_media_server_main_public_or_host,
    user_routes_provider=lambda: get_media_server_user_routes,
    user_status_meta_provider=lambda: get_user_status_meta,
    user_password_hash_provider=lambda: get_user_password_hash,
    update_user_password_hash_provider=lambda: update_user_password_hash,
    user_expire_date_provider=lambda: get_user_expire_date,
    check_user_exists_provider=lambda: _check_user_exists,
)


set_feedback_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
    check_user_exists_provider=lambda: _check_user_exists,
    pulse_url_provider=lambda: get_pulse_url,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    find_poster_for_feedback_provider=lambda: find_poster_for_feedback,
    create_media_feedback_provider=lambda: create_media_feedback,
    list_my_feedback_provider=lambda: list_my_feedback,
    list_all_feedback_provider=lambda: list_all_feedback,
    update_feedback_status_provider=lambda: update_feedback_status,
    update_feedback_status_batch_provider=lambda: update_feedback_status_batch,
    notify_admin_provider=lambda: notify_admin,
    notification_service_provider=lambda: notification_service,
    system_notification_provider=lambda: add_system_notification,
    logger_provider=lambda: logger,
)


set_discovery_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
    tmdb_client_provider=lambda: tmdb_client,
    check_user_exists_provider=lambda: _check_user_exists,
    get_emby_admin_provider=lambda: get_emby_admin,
    check_emby_exists_provider=lambda: check_emby_exists,
    get_cache_provider=lambda: _get_cache,
    set_cache_provider=lambda: _set_cache,
    cache_ttl_hub_provider=lambda: COMMUNITY_CACHE_TTL_HUB,
    main_server_url_provider=lambda: get_media_server_main_public_or_host,
    safe_proxies_provider=lambda: get_safe_proxies,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)


set_management_dependency_providers(
    user_service_provider=lambda: user_service,
    list_my_requests_provider=lambda: list_my_requests,
    list_all_requests_provider=lambda: list_all_requests,
    tmdb_client_provider=lambda: tmdb_client,
    safe_proxies_provider=lambda: get_safe_proxies,
    get_media_request_provider=lambda: get_media_request,
    moviepilot_url_provider=lambda: get_moviepilot_url,
    moviepilot_token_provider=lambda: get_moviepilot_token,
    moviepilot_client_provider=lambda: moviepilot_client,
    update_media_request_status_provider=lambda: update_media_request_status,
    delete_media_request_provider=lambda: delete_media_request,
    notify_admin_provider=lambda: notify_admin,
    list_request_status_notify_items_provider=lambda: list_request_status_notify_items,
    list_tg_bindings_provider=lambda: list_tg_bindings,
    notification_service_provider=lambda: notification_service,
    get_pending_notify_data_provider=lambda: get_pending_notify_data,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
    batch_manage_action_provider=lambda: batch_manage_action,
)


set_safe_media_dependency_providers(
    media_api_provider=lambda: media_api,
    playback_stats_provider=lambda: playback_stats,
    logger_provider=lambda: logger,
    check_user_exists_provider=lambda: _check_user_exists,
    get_cache_provider=lambda: _get_cache,
    set_cache_provider=lambda: _set_cache,
    cache_ttl_top_provider=lambda: COMMUNITY_CACHE_TTL_TOP,
    cache_ttl_latest_provider=lambda: COMMUNITY_CACHE_TTL_LATEST,
    safe_error_message_provider=lambda: safe_error_message,
)


set_cache_control_dependency_providers(
    community_cache_service_provider=lambda: community_cache_service,
    refresh_community_cache_provider=lambda: _refresh_community_cache,
    invalidate_cache_provider=lambda: _invalidate_cache,
    sync_task_state_provider=lambda: _sync_community_cache_task_state,
    ensure_schema_provider=lambda: ensure_media_request_schema,
    user_service_provider=lambda: user_service,
)


class MediaRequestSubmitModel(BaseSubmitModel):
    seasons: List[int] = [0] 
    overview: Optional[str] = ""

router.include_router(auth_router)

router.include_router(discovery_router)

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

router.include_router(management_router)

router.include_router(feedback_router)

router.include_router(safe_media_router)


router.include_router(cache_control_router)


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
