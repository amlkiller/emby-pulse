import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Request

from app.core.config import REPORT_COVER_URL
from app.core.security_utils import safe_error_message
from app.domains.media_requests.media_request_dao import submit_new_media_request
from app.domains.notifications import notify_admin
from app.domains.notifications import public_service as notification_service
from app.infra.config.media_server_settings import get_media_server_main_public_url
from app.infra.config.request_portal_settings import get_pulse_url
from app.infra.db.notification_dao import add_system_notification
from app.schemas.models import MediaRequestSubmitModel as BaseSubmitModel


router = APIRouter()

_check_user_exists_provider = lambda: lambda user_id: True
_submit_new_media_request_provider = lambda: submit_new_media_request
_pulse_url_provider = lambda: get_pulse_url
_media_server_public_url_provider = lambda: get_media_server_main_public_url
_notify_admin_provider = lambda: notify_admin
_notification_service_provider = lambda: notification_service
_system_notification_provider = lambda: add_system_notification
_report_cover_url_provider = lambda: REPORT_COVER_URL
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logging.getLogger("uvicorn")


def _default_get_plugin_provider():
    from app.plugins import get_plugin

    return get_plugin


_get_plugin_provider = _default_get_plugin_provider


class MediaRequestSubmitModel(BaseSubmitModel):
    seasons: List[int] = [0]
    overview: Optional[str] = ""


def set_dependency_providers(
    *,
    check_user_exists_provider=None,
    submit_new_media_request_provider=None,
    pulse_url_provider=None,
    media_server_public_url_provider=None,
    notify_admin_provider=None,
    notification_service_provider=None,
    system_notification_provider=None,
    report_cover_url_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
    get_plugin_provider=None,
):
    global _check_user_exists_provider
    global _submit_new_media_request_provider
    global _pulse_url_provider
    global _media_server_public_url_provider
    global _notify_admin_provider
    global _notification_service_provider
    global _system_notification_provider
    global _report_cover_url_provider
    global _safe_error_message_provider
    global _logger_provider
    global _get_plugin_provider

    if check_user_exists_provider is not None:
        _check_user_exists_provider = check_user_exists_provider
    if submit_new_media_request_provider is not None:
        _submit_new_media_request_provider = submit_new_media_request_provider
    if pulse_url_provider is not None:
        _pulse_url_provider = pulse_url_provider
    if media_server_public_url_provider is not None:
        _media_server_public_url_provider = media_server_public_url_provider
    if notify_admin_provider is not None:
        _notify_admin_provider = notify_admin_provider
    if notification_service_provider is not None:
        _notification_service_provider = notification_service_provider
    if system_notification_provider is not None:
        _system_notification_provider = system_notification_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if get_plugin_provider is not None:
        _get_plugin_provider = get_plugin_provider


@router.post("/api/requests/submit")
async def submit_media_request(request: Request):
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先绑定 Emby 账号"}

    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists_provider()(user.get("Id")):
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

        result = _submit_new_media_request_provider()(uid, uname, tmdb_id, media_type, title, year, poster_path, seasons)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}

        try:
            season_str = f" 第 {','.join(str(s) for s in seasons)} 季" if media_type == "tv" and any(s > 0 for s in seasons) else ""
            msg = f"🎬 <b>收到新求片心愿</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title} ({year}){season_str}\n\n请及时前往后台审批处理。"

            admin_url = _pulse_url_provider()() or _media_server_public_url_provider()() or "http://127.0.0.1:10307"
            # 构建季数字符串用于回调（多季用逗号分隔）
            season_str_cb = ",".join(str(s) for s in seasons) if media_type == "tv" and any(s > 0 for s in seasons) else "0"
            # 标题需要编码以便在 callback_data 中使用（替换下划线）
            title_safe = title.replace("_", "-")

            # 检查影巢插件是否启用
            hdhive_enabled = False
            try:
                hdhive_plugin = _get_plugin_provider()("hdhive")
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
            rule = _notify_admin_provider().get_notify_rule('request_new')
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
                    _notification_service_provider().send_photo("sys_notify", f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else _report_cover_url_provider(), msg, reply_markup=keyboard, platform=platform)

                # Web 通知中心 - 只有勾选 web 才发送
                if 'web' in channels:
                    _system_notification_provider()("request", f"收到新求片: {title}", f"用户 {uname} 提交了新的心愿单", "/requests_admin")
            # else: 关闭状态不发送任何通知
        except Exception as e:
            _logger_provider().error(f"[求片通知] 发送失败: {e}")

        return {"status": "success", "message": "心愿已提交！系统将尽快处理您的请求。"}

    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "提交失败")}
