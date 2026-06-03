import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security_utils import safe_error_message
from app.domains.media_requests.media_request_dao import (
    delete_media_request,
    get_media_request,
    get_pending_notify_data,
    list_all_requests,
    list_my_requests,
    list_request_status_notify_items,
    list_tg_bindings,
    update_media_request_status,
)
from app.domains.notifications import notify_admin
from app.domains.notifications import public_service as notification_service
from app.domains.users import public_service as user_service
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.moviepilot_settings import get_moviepilot_token, get_moviepilot_url
from app.utils.proxy_helper import get_safe_proxies


router = APIRouter()

_user_service_provider = lambda: user_service
_list_my_requests_provider = lambda: list_my_requests
_list_all_requests_provider = lambda: list_all_requests
_tmdb_client_provider = lambda: tmdb_client
_safe_proxies_provider = lambda: get_safe_proxies
_get_media_request_provider = lambda: get_media_request
_moviepilot_url_provider = lambda: get_moviepilot_url
_moviepilot_token_provider = lambda: get_moviepilot_token
_moviepilot_client_provider = lambda: moviepilot_client
_update_media_request_status_provider = lambda: update_media_request_status
_delete_media_request_provider = lambda: delete_media_request
_notify_admin_provider = lambda: notify_admin
_list_request_status_notify_items_provider = lambda: list_request_status_notify_items
_list_tg_bindings_provider = lambda: list_tg_bindings
_notification_service_provider = lambda: notification_service
_get_pending_notify_data_provider = lambda: get_pending_notify_data
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logging.getLogger("uvicorn")
_batch_manage_action_provider = lambda: batch_manage_action


class AdminActionModel(BaseModel):
    tmdb_id: int
    season: int = 0
    action: str
    reject_reason: Optional[str] = None


class BulkAdminActionModel(BaseModel):
    items: List[dict]
    action: str
    reject_reason: Optional[str] = None


def set_dependency_providers(
    *,
    user_service_provider=None,
    list_my_requests_provider=None,
    list_all_requests_provider=None,
    tmdb_client_provider=None,
    safe_proxies_provider=None,
    get_media_request_provider=None,
    moviepilot_url_provider=None,
    moviepilot_token_provider=None,
    moviepilot_client_provider=None,
    update_media_request_status_provider=None,
    delete_media_request_provider=None,
    notify_admin_provider=None,
    list_request_status_notify_items_provider=None,
    list_tg_bindings_provider=None,
    notification_service_provider=None,
    get_pending_notify_data_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
    batch_manage_action_provider=None,
):
    global _user_service_provider
    global _list_my_requests_provider
    global _list_all_requests_provider
    global _tmdb_client_provider
    global _safe_proxies_provider
    global _get_media_request_provider
    global _moviepilot_url_provider
    global _moviepilot_token_provider
    global _moviepilot_client_provider
    global _update_media_request_status_provider
    global _delete_media_request_provider
    global _notify_admin_provider
    global _list_request_status_notify_items_provider
    global _list_tg_bindings_provider
    global _notification_service_provider
    global _get_pending_notify_data_provider
    global _safe_error_message_provider
    global _logger_provider
    global _batch_manage_action_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if list_my_requests_provider is not None:
        _list_my_requests_provider = list_my_requests_provider
    if list_all_requests_provider is not None:
        _list_all_requests_provider = list_all_requests_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if get_media_request_provider is not None:
        _get_media_request_provider = get_media_request_provider
    if moviepilot_url_provider is not None:
        _moviepilot_url_provider = moviepilot_url_provider
    if moviepilot_token_provider is not None:
        _moviepilot_token_provider = moviepilot_token_provider
    if moviepilot_client_provider is not None:
        _moviepilot_client_provider = moviepilot_client_provider
    if update_media_request_status_provider is not None:
        _update_media_request_status_provider = update_media_request_status_provider
    if delete_media_request_provider is not None:
        _delete_media_request_provider = delete_media_request_provider
    if notify_admin_provider is not None:
        _notify_admin_provider = notify_admin_provider
    if list_request_status_notify_items_provider is not None:
        _list_request_status_notify_items_provider = list_request_status_notify_items_provider
    if list_tg_bindings_provider is not None:
        _list_tg_bindings_provider = list_tg_bindings_provider
    if notification_service_provider is not None:
        _notification_service_provider = notification_service_provider
    if get_pending_notify_data_provider is not None:
        _get_pending_notify_data_provider = get_pending_notify_data_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if batch_manage_action_provider is not None:
        _batch_manage_action_provider = batch_manage_action_provider


@router.get("/api/requests/my")
def get_my_requests(request: Request):
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    uid = str(user.get("Id", ""))
    rows = _list_my_requests_provider()(uid)

    results = []
    for r in rows:
        results.append({
            "tmdb_id": r[0],
            "title": r[1] + (f" (S{r[5]})" if r[6] == 'tv' else ""),
            "year": r[2],
            "poster_path": r[3],
            "status": r[4],
            "season": r[5],
            "requested_at": r[7],
            "reject_reason": r[8],
            "episodes": r[9] or "",
            "request_type": r[10] or "new",
        })
    return {"status": "success", "data": results}


@router.get("/api/manage/requests")
def get_all_requests(request: Request):
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    rows = _list_all_requests_provider()()

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
        proxies = _safe_proxies_provider()()
        tmdb = _tmdb_client_provider()

        def fetch_tmdb_poster(tid):
            try:
                tmdb_info = tmdb.get_tv_details(tid, proxies=proxies, timeout=3).json()
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
            "is_update": is_update,
        })
    return {"status": "success", "data": results}


@router.post("/api/manage/requests/batch")
def batch_manage_action(data: BulkAdminActionModel, request: Request):
    users = _user_service_provider()
    get_request = _get_media_request_provider()
    get_mp_url = _moviepilot_url_provider()
    get_mp_token = _moviepilot_token_provider()
    moviepilot = _moviepilot_client_provider()
    update_status = _update_media_request_status_provider()
    delete_request = _delete_media_request_provider()
    notify_rules = _notify_admin_provider()
    list_notify_items = _list_request_status_notify_items_provider()
    list_bindings = _list_tg_bindings_provider()
    notifications = _notification_service_provider()
    logger = _logger_provider()

    if not users.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 🔥 预先批量查询所有需要通知的工单信息（优化数据库查询）
    notify_items = []  # 收集所有需要通知的工单

    for item in data.items:
        tid = item['tmdb_id']
        sn = item['season']
        if data.action == "approve":
            row = get_request(tid, sn)

            mp_url = get_mp_url()
            mp_token = get_mp_token()
            if mp_url and mp_token and row:
                payload = {"name": row["title"], "tmdbid": int(tid), "year": str(row["year"]), "type": "电影" if row["media_type"] == "movie" else "电视剧"}
                if row["media_type"] == "tv":
                    payload["season"] = sn
                try:
                    moviepilot.subscribe(mp_url, mp_token, payload, timeout=10)
                except Exception:
                    pass
            update_status(tid, sn, 1)

        elif data.action == "manual":
            update_status(tid, sn, 4)

        elif data.action == "reject":
            update_status(tid, sn, 3, data.reject_reason)
        elif data.action == "finish":
            update_status(tid, sn, 2)
        elif data.action == "hdhive_done":
            # 影巢转存完成后，状态设为待入库(7)
            update_status(tid, sn, 7)
        elif data.action == "delete":
            delete_request(tid, sn)

    # 🔥 批量通知用户（审批通过、入库完成、拒绝、手动接单、影巢转存完成）
    if data.action in ["approve", "finish", "reject", "manual", "hdhive_done"]:
        try:
            rule = notify_rules.get_notify_rule('request_status')
            logger.info(f"[状态变更通知] action={data.action}, rule={rule}")

            if rule and rule.get('enabled') and 'tg_bot' in rule.get('channels', []):
                # 🔥 批量查询所有工单信息和用户绑定关系
                notify_items, user_ids = list_notify_items(data.items)
                tg_bindings = list_bindings(user_ids)
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
                                    notifications.send_user_bot_photo(int(tg_id), img_url, msg)
                                else:
                                    notifications.send_user_bot_message(int(tg_id), msg)
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
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    return _batch_manage_action_provider()(
        BulkAdminActionModel(
            items=[{"tmdb_id": data.tmdb_id, "season": data.season}],
            action=data.action,
            reject_reason=data.reject_reason,
        ),
        request,
    )


@router.get("/api/requests/pending_notify")
def get_pending_notify(request: Request):
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        req_count, req_rows, feed_count, feed_rows = _get_pending_notify_data_provider()()

        items = []
        for r in req_rows:
            items.append({
                "id": f"req_{r['tmdb_id']}_{r['season']}",
                "title": r['title'] + (f" (第{r['season']}季)" if r['media_type'] == 'tv' else ""),
                "poster": r['poster_path'],
                "users": r['users'],
                "time": r['created_at'],
                "type": "request",
            })

        for f in feed_rows:
            items.append({
                "id": f"feed_{f['id']}",
                "title": f"⚠️ 报错: {f['item_name']}",
                "poster": f['poster'] or "",
                "users": f"{f['username']} - {f['issue_type']}",
                "time": f['created_at'],
                "type": "feedback",
            })

        items.sort(key=lambda x: x['time'], reverse=True)
        return {"status": "success", "count": req_count + feed_count, "items": items[:5]}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
