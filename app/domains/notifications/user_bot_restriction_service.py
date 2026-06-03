import json
import logging
import threading
import time

from app.infra.config.user_bot_settings import (
    get_user_bot_required_channels,
    get_user_bot_required_groups,
    get_user_bot_restriction_cache_ttl,
    is_user_bot_restriction_enabled,
)


logger = logging.getLogger("uvicorn")

_restriction_cache = {}
_restriction_cache_lock = threading.Lock()

_tg_api_provider = lambda: (lambda method, data=None, token=None: None)
_restriction_enabled_provider = lambda: is_user_bot_restriction_enabled
_required_channels_provider = lambda: get_user_bot_required_channels
_required_groups_provider = lambda: get_user_bot_required_groups
_restriction_cache_ttl_provider = lambda: get_user_bot_restriction_cache_ttl
_restriction_cache_provider = lambda: _restriction_cache
_restriction_cache_lock_provider = lambda: _restriction_cache_lock
_check_user_in_chat_provider = lambda: check_user_in_chat
_logger_provider = lambda: logger
_time_provider = lambda: time


def set_dependency_providers(
    *,
    tg_api_provider=None,
    restriction_enabled_provider=None,
    required_channels_provider=None,
    required_groups_provider=None,
    restriction_cache_ttl_provider=None,
    restriction_cache_provider=None,
    restriction_cache_lock_provider=None,
    check_user_in_chat_provider=None,
    logger_provider=None,
    time_provider=None,
):
    global _tg_api_provider
    global _restriction_enabled_provider
    global _required_channels_provider
    global _required_groups_provider
    global _restriction_cache_ttl_provider
    global _restriction_cache_provider
    global _restriction_cache_lock_provider
    global _check_user_in_chat_provider
    global _logger_provider
    global _time_provider

    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if restriction_enabled_provider is not None:
        _restriction_enabled_provider = restriction_enabled_provider
    if required_channels_provider is not None:
        _required_channels_provider = required_channels_provider
    if required_groups_provider is not None:
        _required_groups_provider = required_groups_provider
    if restriction_cache_ttl_provider is not None:
        _restriction_cache_ttl_provider = restriction_cache_ttl_provider
    if restriction_cache_provider is not None:
        _restriction_cache_provider = restriction_cache_provider
    if restriction_cache_lock_provider is not None:
        _restriction_cache_lock_provider = restriction_cache_lock_provider
    if check_user_in_chat_provider is not None:
        _check_user_in_chat_provider = check_user_in_chat_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if time_provider is not None:
        _time_provider = time_provider


def check_user_in_chat(user_id: str, chat_id: str) -> bool:
    """检查用户是否在指定频道/群聊中"""
    try:
        result = _tg_api_provider()("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        if not result or not result.get("ok"):
            return False

        member = result.get("result", {})
        status = member.get("status", "")
        return status in ["member", "administrator", "creator", "restricted"]
    except Exception as e:
        _logger_provider().error(f"检查用户 {user_id} 是否在 {chat_id} 中失败: {e}")
        return False


def check_user_restrictions(tg_user_id: str) -> dict:
    """检查用户是否满足使用限制条件（智能缓存）"""
    result = {"passed": True, "missing_channels": [], "missing_groups": []}

    if not _restriction_enabled_provider()():
        return result

    cache_ttl = _restriction_cache_ttl_provider()()
    with _restriction_cache_lock_provider():
        cached = _restriction_cache_provider().get(tg_user_id)
        if cached and cached["passed"] and (_time_provider().time() - cached["cached_at"] < cache_ttl):
            return {"passed": True, "missing_channels": [], "missing_groups": []}

    required_channels = _required_channels_provider()()
    if required_channels:
        channels = [c.strip() for c in required_channels.split("\n") if c.strip()]
        for channel in channels:
            if not _check_user_in_chat_provider()(tg_user_id, channel):
                result["missing_channels"].append(channel)

    required_groups = _required_groups_provider()()
    _logger_provider().info(f"[使用限制] required_groups={repr(required_groups)}")
    if required_groups:
        try:
            groups_data = json.loads(required_groups) if required_groups.strip().startswith("[") else None
            if groups_data:
                for group in groups_data:
                    group_id = group.get("id", "")
                    if group_id:
                        in_chat = _check_user_in_chat_provider()(tg_user_id, group_id)
                        _logger_provider().info(f"[使用限制] 检查群聊 {group_id}, user={tg_user_id}, in_chat={in_chat}")
                        if not in_chat:
                            result["missing_groups"].append({
                                "id": group_id,
                                "name": group.get("name", group_id),
                                "link": group.get("link", ""),
                            })
            else:
                groups = [g.strip() for g in required_groups.split("\n") if g.strip()]
                _logger_provider().info(f"[使用限制] 解析后的群聊列表: {groups}")
                for group in groups:
                    in_chat = _check_user_in_chat_provider()(tg_user_id, group)
                    _logger_provider().info(f"[使用限制] 检查群聊 {group}, user={tg_user_id}, in_chat={in_chat}")
                    if not in_chat:
                        result["missing_groups"].append({"id": group, "name": group, "link": ""})
        except json.JSONDecodeError:
            groups = [g.strip() for g in required_groups.split("\n") if g.strip()]
            for group in groups:
                if not _check_user_in_chat_provider()(tg_user_id, group):
                    result["missing_groups"].append({"id": group, "name": group, "link": ""})

    result["passed"] = len(result["missing_channels"]) == 0 and len(result["missing_groups"]) == 0

    if result["passed"]:
        with _restriction_cache_lock_provider():
            _restriction_cache_provider()[tg_user_id] = {
                "passed": True,
                "missing_channels": [],
                "missing_groups": [],
                "cached_at": _time_provider().time(),
            }

    return result


def clear_restriction_cache(tg_user_id: str):
    """清除用户的限制检查缓存"""
    with _restriction_cache_lock_provider():
        _restriction_cache_provider().pop(tg_user_id, None)


def format_restriction_message(check_result: dict) -> str:
    """格式化限制检查失败的消息"""
    msg = "⚠️ <b>使用限制</b>\n\n"
    msg += "使用本机器人需要满足以下条件：\n\n"

    if check_result["missing_channels"]:
        msg += "📢 <b>必须关注的频道：</b>\n"
        for ch in check_result["missing_channels"]:
            if ch.startswith("@"):
                msg += f"• <a href=\"https://t.me/{ch[1:]}\">{ch}</a>\n"
            else:
                msg += f"• {ch}\n"
        msg += "\n"

    if check_result["missing_groups"]:
        msg += "👥 <b>必须加入的群聊：</b>\n"
        for grp in check_result["missing_groups"]:
            if isinstance(grp, dict):
                name = grp.get("name", grp.get("id", "未知群"))
                link = grp.get("link", "")
                if link:
                    msg += f"• <a href=\"{link}\">{name}</a>\n"
                else:
                    msg += f"• {name}\n"
            else:
                msg += f"• {grp}\n"
        msg += "\n"

    msg += "💡 关注/加入后，发送 <b>/check</b> 重新验证。"

    return msg
