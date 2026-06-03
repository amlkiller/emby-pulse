import logging

from app.core.security_utils import safe_error_message
from app.domains.points import point_dao
from app.domains.users import user_bot_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_get_binding_by_emby_id_provider = lambda: (lambda emby_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_point_dao_provider = lambda: point_dao
_user_bot_dao_provider = lambda: user_bot_dao
_media_api_provider = lambda: media_api
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    get_binding_by_emby_id_provider=None,
    send_provider=None,
    point_dao_provider=None,
    user_bot_dao_provider=None,
    media_api_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _get_binding_by_emby_id_provider
    global _send_provider
    global _point_dao_provider
    global _user_bot_dao_provider
    global _media_api_provider
    global _safe_error_message_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if get_binding_by_emby_id_provider is not None:
        _get_binding_by_emby_id_provider = get_binding_by_emby_id_provider
    if send_provider is not None:
        _send_provider = send_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _mentioned_user_id_from_entities(text, entities):
    if not entities:
        return None
    for ent in entities:
        if ent.get("type") == "mention" or ent.get("type") == "text_mention":
            if ent.get("type") == "text_mention" and ent.get("user"):
                return str(ent["user"].get("id", ""))
            if ent.get("type") == "mention":
                offset = ent.get("offset", 0)
                length = ent.get("length", 0)
                mentioned_username = text[offset:offset + length].lstrip("@")
                return _user_bot_dao_provider().get_tg_user_id_by_username(mentioned_username)
    return None


def _resolve_pk_target(target, text, entities):
    mentioned_user_id = _mentioned_user_id_from_entities(text, entities)

    to_user_id = None
    to_user_name = None

    if mentioned_user_id:
        row = _user_bot_dao_provider().get_binding_by_tg_user_or_username(mentioned_user_id)
        if row:
            to_user_id = row["emby_user_id"]
            to_user_name = row["emby_username"]

    if not to_user_id:
        row = _user_bot_dao_provider().get_binding_by_tg_user_or_username(target)

        if not row:
            try:
                emby_users = _media_api_provider().get("/Users", timeout=5).json()
                user_map = {u["Name"]: u["Id"] for u in emby_users}
                to_user_id = user_map.get(target)
                to_user_name = target
            except Exception:
                pass
        else:
            to_user_id = row["emby_user_id"]
            to_user_name = row["emby_username"]

    return to_user_id, to_user_name


def cmd_pk_invite(chat_id, tg_user_id, text, is_group=False, entities=None, user_msg_id=None):
    """用户PK邀请"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    if len(parts) < 3:
        return _send_provider()(chat_id, "💡 使用方法：/upk @用户 积分\n示例：/upk @张三 100\n\n💡 也可以直接使用 Emby 用户名")

    try:
        try:
            points = int(parts[-1])
        except ValueError:
            return _send_provider()(chat_id, "❌ 下注积分必须是数字")

        target = " ".join(parts[1:-1]).lstrip("@")

        if not target:
            return _send_provider()(chat_id, "❌ 请指定要PK的用户")

        to_user_id, to_user_name = _resolve_pk_target(target, text, entities)

        if not to_user_id:
            return _send_provider()(chat_id, f"❌ 未找到用户：{target}\n\n💡 请确认对方已绑定机器人，或直接使用 Emby 用户名")

        if to_user_id == binding["emby_user_id"]:
            return _send_provider()(chat_id, "❌ 不能PK自己")

        target_binding = _get_binding_by_emby_id_provider()(to_user_id)
        target_tg_name = target_binding.get("tg_name") if target_binding else None
        challenger_tg_name = binding.get("tg_name") or binding["emby_username"]

        invite_result = _point_dao_provider().create_pk_invitation(
            binding["emby_user_id"],
            binding["emby_username"],
            challenger_tg_name,
            to_user_id,
            to_user_name,
            target_tg_name,
            points,
            chat_id,
            command_message_id=user_msg_id,
        )
        if invite_result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {invite_result.get('message', 'PK邀请失败')}")

        invite_id = invite_result["invite_id"]
        timeout_minutes = invite_result["timeout_minutes"]

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ 接受PK", "callback_data": f"pk_accept:{invite_id}"},
                    {"text": "❌ 拒绝PK", "callback_data": f"pk_reject:{invite_id}"},
                ]
            ]
        }

        target_tg_username = target_binding.get("tg_username") if target_binding else None
        target_mention = f"@{target_tg_username}" if target_tg_username else (target_tg_name or to_user_name)

        invite_msg = f"🎯 <b>{challenger_tg_name}</b> 向 {target_mention} 发起PK挑战！\n\n💰 下注：<b>{points}</b> 积分\n⏰ 请在 <b>{timeout_minutes}</b> 分钟内回应\n\n💡 点击下方按钮选择接受或拒绝"
        send_result = _send_provider()(chat_id, invite_msg, reply_markup=keyboard)

        if send_result and send_result.get("ok"):
            invite_msg_id = send_result.get("result", {}).get("message_id")
            _point_dao_provider().save_pk_invitation_message_id(invite_id, invite_msg_id)

    except Exception as e:
        _logger_provider().error(f"[UserBot] PK邀请失败: {e}")
        return _send_provider()(chat_id, f"❌ PK邀请失败：{_safe_error_message_provider()(e, 'PK邀请异常，请稍后重试')}")


def cmd_pk_accept(chat_id, tg_user_id, text, is_group=False):
    """接受PK邀请"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    try:
        invite = _point_dao_provider().get_latest_pending_pk_invitation_for_target(binding["emby_user_id"])

        if not invite:
            return _send_provider()(chat_id, "❌ 没有待处理的PK邀请")

        result = _point_dao_provider().accept_pk_invitation(invite["id"], binding["emby_user_id"])
        if result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {result.get('message', '接受PK失败')}")

        challenger_name = result["challenger_name"]
        target_name = result["target_name"]
        challenger_roll = result["challenger_roll"]
        target_roll = result["target_roll"]
        original_chat_id = result["chat_id"]
        if result.get("tie"):
            result_msg = f"⚖️ <b>平局！</b>\n\n{challenger_name}({challenger_roll}点) vs {target_name}({target_roll}点)\n\n积分退还，不扣手续费"
        else:
            result_msg = f"🎲 <b>PK结果</b>\n\n{challenger_name}({challenger_roll}点) vs {target_name}({target_roll}点)\n\n🎉 <b>{result['winner_name']}</b> 获胜！\n💰 获得 <b>{result['win_amount']}</b> 积分（扣{result['tax_rate']}%手续费）"
        if original_chat_id:
            _send_provider()(original_chat_id, result_msg)
        return _send_provider()(chat_id, result_msg)

    except Exception as e:
        _logger_provider().error(f"[UserBot] 接受PK失败: {e}")
        return _send_provider()(chat_id, f"❌ 接受PK失败：{_safe_error_message_provider()(e, '接受PK异常，请稍后重试')}")


def cmd_pk_reject(chat_id, tg_user_id, text, is_group=False):
    """拒绝PK邀请"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    try:
        invite = _point_dao_provider().get_latest_pending_pk_invitation_for_target(binding["emby_user_id"])

        if not invite:
            return _send_provider()(chat_id, "❌ 没有待处理的PK邀请")

        invite_id = invite["id"]
        challenger_name = invite["challenger_name"]
        original_chat_id = invite["chat_id"]

        _point_dao_provider().set_pk_invitation_status(invite_id, "rejected")

        if original_chat_id:
            _send_provider()(original_chat_id, f"❌ <b>{binding['emby_username']}</b> 拒绝了你的PK邀请")

        return _send_provider()(chat_id, f"✅ 已拒绝 <b>{challenger_name}</b> 的PK邀请")

    except Exception as e:
        _logger_provider().error(f"[UserBot] 拒绝PK失败: {e}")
        return _send_provider()(chat_id, f"❌ 拒绝PK失败：{_safe_error_message_provider()(e, '拒绝PK异常，请稍后重试')}")
