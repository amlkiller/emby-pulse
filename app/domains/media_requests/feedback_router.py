import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List

from app.core.config import REPORT_COVER_URL
from app.domains.media_requests.media_request_dao import (
    create_media_feedback,
    find_poster_for_feedback,
    list_all_feedback,
    list_my_feedback,
    update_feedback_status,
    update_feedback_status_batch,
)
from app.domains.notifications import notify_admin
from app.domains.notifications import public_service as notification_service
from app.domains.users import public_service as user_service
from app.infra.clients.media_server_client import media_api
from app.infra.config.request_portal_settings import get_pulse_url
from app.infra.db.notification_dao import add_system_notification


router = APIRouter()

_user_service_provider = lambda: user_service
_media_api_provider = lambda: media_api
_pulse_url_provider = lambda: get_pulse_url
_report_cover_url_provider = lambda: REPORT_COVER_URL
_find_poster_for_feedback_provider = lambda: find_poster_for_feedback
_create_media_feedback_provider = lambda: create_media_feedback
_list_my_feedback_provider = lambda: list_my_feedback
_list_all_feedback_provider = lambda: list_all_feedback
_update_feedback_status_provider = lambda: update_feedback_status
_update_feedback_status_batch_provider = lambda: update_feedback_status_batch
_notify_admin_provider = lambda: notify_admin
_notification_service_provider = lambda: notification_service
_system_notification_provider = lambda: add_system_notification
_logger_provider = lambda: logging.getLogger("uvicorn")


def _check_user_exists(user_id: str) -> bool:
    if not user_id:
        return False
    try:
        media = _media_api_provider()
        if media and media.host and media.api_key:
            res = media.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True


_check_user_exists_provider = lambda: _check_user_exists


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


def set_dependency_providers(
    *,
    user_service_provider=None,
    media_api_provider=None,
    check_user_exists_provider=None,
    pulse_url_provider=None,
    report_cover_url_provider=None,
    find_poster_for_feedback_provider=None,
    create_media_feedback_provider=None,
    list_my_feedback_provider=None,
    list_all_feedback_provider=None,
    update_feedback_status_provider=None,
    update_feedback_status_batch_provider=None,
    notify_admin_provider=None,
    notification_service_provider=None,
    system_notification_provider=None,
    logger_provider=None,
):
    global _user_service_provider
    global _media_api_provider
    global _check_user_exists_provider
    global _pulse_url_provider
    global _report_cover_url_provider
    global _find_poster_for_feedback_provider
    global _create_media_feedback_provider
    global _list_my_feedback_provider
    global _list_all_feedback_provider
    global _update_feedback_status_provider
    global _update_feedback_status_batch_provider
    global _notify_admin_provider
    global _notification_service_provider
    global _system_notification_provider
    global _logger_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if check_user_exists_provider is not None:
        _check_user_exists_provider = check_user_exists_provider
    if pulse_url_provider is not None:
        _pulse_url_provider = pulse_url_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if find_poster_for_feedback_provider is not None:
        _find_poster_for_feedback_provider = find_poster_for_feedback_provider
    if create_media_feedback_provider is not None:
        _create_media_feedback_provider = create_media_feedback_provider
    if list_my_feedback_provider is not None:
        _list_my_feedback_provider = list_my_feedback_provider
    if list_all_feedback_provider is not None:
        _list_all_feedback_provider = list_all_feedback_provider
    if update_feedback_status_provider is not None:
        _update_feedback_status_provider = update_feedback_status_provider
    if update_feedback_status_batch_provider is not None:
        _update_feedback_status_batch_provider = update_feedback_status_batch_provider
    if notify_admin_provider is not None:
        _notify_admin_provider = notify_admin_provider
    if notification_service_provider is not None:
        _notification_service_provider = notification_service_provider
    if system_notification_provider is not None:
        _system_notification_provider = system_notification_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


@router.post("/api/requests/feedback/submit")
def submit_feedback(data: FeedbackSubmitModel, request: Request):
    check_user_exists = _check_user_exists_provider()
    get_pulse = _pulse_url_provider()
    find_poster = _find_poster_for_feedback_provider()
    create_feedback = _create_media_feedback_provider()
    notify_rules = _notify_admin_provider()
    notifications = _notification_service_provider()
    add_notification = _system_notification_provider()
    logger = _logger_provider()

    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请重新登录"}

    # 检查 Emby 账号是否仍然存在
    if not check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除，请重新登录", "account_deleted": True}

    uid = str(user.get("Id", ""))
    uname = user.get("Name") or "未知用户"

    actual_poster = data.poster_path
    if actual_poster and actual_poster.startswith("/"):
        base_url = get_pulse() or str(request.base_url).rstrip("/")
        actual_poster = f"{base_url}{actual_poster}"

    if not actual_poster or "undefined" in actual_poster:
        r = find_poster(data.item_name)
        if r and r["poster_path"]:
            actual_poster = r["poster_path"]

    if not actual_poster or "undefined" in actual_poster:
        actual_poster = ""

    feed_id = create_feedback(data.item_name, uid, uname, data.issue_type, data.description, actual_poster)

    msg = (f"🚨 <b>新资源报错提醒</b>\n\n"
           f"👤 <b>用户</b>：{uname}\n"
           f"🎬 <b>媒体</b>：{data.item_name}\n"
           f"🏷️ <b>问题</b>：{data.issue_type}\n"
           f"📝 <b>描述</b>：{data.description or '无'}")

    admin_url = get_pulse() or str(request.base_url).rstrip("/")
    keyboard = {"inline_keyboard": [
        [{"text": "🛠️ 标记修复中", "callback_data": f"feed_fix_{feed_id}"},
         {"text": "✅ 标记已修复", "callback_data": f"feed_done_{feed_id}"}],
        [{"text": "❌ 暂不处理(忽略)", "callback_data": f"feed_reject_{feed_id}"},
         {"text": "💻 网页处理", "url": f"{admin_url}/requests_admin"}]
    ]}

    img_url = actual_poster or _report_cover_url_provider()

    # 🔥 使用 notify_rules 配置控制通知渠道
    try:
        rule = notify_rules.get_notify_rule("feedback_new")

        if rule and rule.get("enabled"):
            channels = rule.get("channels", [])
            platform = "none"
            if "tg_bot" in channels and "wecom" in channels:
                platform = "all"
            elif "tg_bot" in channels:
                platform = "tg"
            elif "wecom" in channels:
                platform = "wecom"

            if platform != "none":
                notifications.send_photo("sys_notify", img_url, msg, reply_markup=keyboard, platform=platform)

            # Web 通知中心
            if "web" in channels:
                add_notification(
                    notify_type="system",
                    title=f"⚠️ 资源报错: {uname}",
                    message=f"{data.item_name} - {data.issue_type}",
                    action_url="/requests_admin?tab=feedback",
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
    if not user:
        return {"status": "error", "message": "未登录"}
    uid = str(user.get("Id", ""))
    rows = _list_my_feedback_provider()(uid)
    results = [
        {"id": r[0], "item_name": r[1], "issue_type": r[2], "description": r[3], "status": r[4], "created_at": r[5]}
        for r in rows
    ]
    return {"status": "success", "data": results}


@router.get("/api/manage/feedback")
def get_all_feedback(request: Request):
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    rows = _list_all_feedback_provider()()
    results = [
        {
            "id": r[0],
            "item_name": r[1],
            "username": r[2],
            "issue_type": r[3],
            "description": r[4],
            "status": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]
    return {"status": "success", "data": results}


@router.post("/api/manage/feedback/action")
def manage_feedback_action(data: FeedbackActionModel, request: Request):
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    status_map = {"fix": 1, "done": 2, "reject": 3, "delete": -1}
    st = status_map.get(data.action, 0)
    _update_feedback_status_provider()(data.id, st)
    return {"status": "success", "message": "已更新工单状态"}


@router.post("/api/manage/feedback/batch")
def batch_feedback_action(data: BulkFeedbackActionModel, request: Request):
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    status_map = {"fix": 1, "done": 2, "reject": 3, "delete": -1}
    st = status_map.get(data.action, 0)
    _update_feedback_status_batch_provider()(data.items, st)
    return {"status": "success", "message": "批量操作已完成"}
