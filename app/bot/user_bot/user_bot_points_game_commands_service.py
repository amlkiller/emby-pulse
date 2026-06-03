import logging

from app.core.security_utils import safe_error_message
from app.domains.points import point_dao
from app.domains.users import user_bot_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_point_dao_provider = lambda: point_dao
_user_bot_dao_provider = lambda: user_bot_dao
_media_api_provider = lambda: media_api
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    send_provider=None,
    point_dao_provider=None,
    user_bot_dao_provider=None,
    media_api_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _send_provider
    global _point_dao_provider
    global _user_bot_dao_provider
    global _media_api_provider
    global _safe_error_message_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
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


def cmd_rank(chat_id, tg_user_id, is_group=False):
    """积分排行榜"""
    try:
        try:
            emby_users = _media_api_provider().get("/Users", timeout=5).json()
            emby_user_ids = {u["Id"] for u in emby_users}
            emby_name_map = {u["Id"]: u["Name"] for u in emby_users}
        except Exception:
            emby_user_ids = set()
            emby_name_map = {}

        rows = _point_dao_provider().list_point_rank(limit=20)

        if not rows:
            return _send_provider()(chat_id, "📭 暂无积分数据")

        valid_rows = [(row["user_id"], row["points"]) for row in rows if row["user_id"] in emby_user_ids]

        if not valid_rows:
            return _send_provider()(chat_id, "📭 暂无积分数据")

        valid_rows = valid_rows[:10]

        tg_rows = _user_bot_dao_provider().list_tg_binding_names()
        tg_name_map = {}
        for row in tg_rows:
            if row["tg_display_name"]:
                tg_name_map[row["emby_user_id"]] = row["tg_display_name"]
            elif row["tg_username"]:
                tg_name_map[row["emby_user_id"]] = f"@{row['tg_username']}"

        msg = "🏆 <b>积分排行榜 Top 10</b>\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, row in enumerate(valid_rows):
            user_id = row[0]
            if user_id in tg_name_map:
                user_name = tg_name_map[user_id]
            else:
                emby_name = emby_name_map.get(user_id, "用户")
                if len(emby_name) > 2:
                    user_name = emby_name[:2] + "***"
                else:
                    user_name = "用户***"
            msg += f"{medals[i]} <b>{user_name}</b> - {row[1]} 积分\n"

        return _send_provider()(chat_id, msg.strip())
    except Exception as e:
        _logger_provider().error(f"[UserBot] 排行榜查询失败: {e}")
        return _send_provider()(chat_id, "❌ 查询失败")


def cmd_rob(chat_id, tg_user_id, text, is_group=False, entities=None):
    """打劫功能"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    if len(parts) < 2:
        return _send_provider()(chat_id, "💡 使用方法：/rob @用户\n示例：/rob @张三\n\n💡 也可以直接使用 Emby 用户名")

    try:
        target = " ".join(parts[1:]).lstrip("@")

        if not target:
            return _send_provider()(chat_id, "❌ 请指定要打劫的用户")

        mentioned_user_id = None
        if entities:
            for ent in entities:
                if ent.get("type") == "mention" or ent.get("type") == "text_mention":
                    if ent.get("type") == "text_mention" and ent.get("user"):
                        mentioned_user_id = str(ent["user"].get("id", ""))
                        break
                    elif ent.get("type") == "mention":
                        offset = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        mentioned_username = text[offset:offset + length].lstrip("@")
                        mentioned_user_id = _user_bot_dao_provider().get_tg_user_id_by_username(mentioned_username)
                        break

        to_user_id = None
        to_user_name = None
        to_tg_display_name = None

        if mentioned_user_id:
            row = _user_bot_dao_provider().get_binding_by_tg_user_or_username(mentioned_user_id)
            if row:
                to_user_id = row["emby_user_id"]
                to_user_name = row["emby_username"]
                to_tg_display_name = row["tg_display_name"] or row["emby_username"]

        if not to_user_id:
            row = _user_bot_dao_provider().get_binding_by_tg_user_or_username(target)
            if not row:
                try:
                    emby_users = _media_api_provider().get("/Users", timeout=5).json()
                    user_map = {u["Name"]: u["Id"] for u in emby_users}
                    to_user_id = user_map.get(target)
                    to_user_name = target
                    to_tg_display_name = target
                except Exception:
                    pass
            else:
                to_user_id = row["emby_user_id"]
                to_user_name = row["emby_username"]
                to_tg_display_name = row["tg_display_name"] or row["emby_username"]

        display_name = to_tg_display_name or to_user_name

        if not to_user_id:
            return _send_provider()(chat_id, f"❌ 未找到用户：{target}\n\n💡 请确认对方已绑定机器人，或直接使用 Emby 用户名")

        if to_user_id == binding["emby_user_id"]:
            return _send_provider()(chat_id, "❌ 不能打劫自己")

        result = _point_dao_provider().rob_points(
            binding["emby_user_id"],
            binding["emby_username"],
            to_user_id,
            to_user_name,
        )
        if result.get("status") != "success":
            message = result.get("message", "打劫失败")
            if message.startswith("你的积分低于") or message.startswith("对方积分低于"):
                return _send_provider()(chat_id, f"🛡️ {message}")
            return _send_provider()(chat_id, f"❌ {message}")

        if result.get("success"):
            return _send_provider()(
                chat_id,
                f"🎉 <b>打劫成功！</b>\n\n👤 从 <b>{display_name}</b> 身上抢到 <b>{result.get('amount', 0)}</b> 积分\n💰 当前余额：<b>{result.get('balance', 0)}</b> 积分",
            )
        return _send_provider()(
            chat_id,
            f"😢 <b>打劫失败！</b>\n\n💥 被 <b>{display_name}</b> 反杀，损失 <b>{result.get('counter_amount', 0)}</b> 积分\n💰 当前余额：<b>{result.get('balance', 0)}</b> 积分",
        )

    except Exception as e:
        _logger_provider().error(f"[UserBot] 打劫失败: {e}")
        return _send_provider()(chat_id, f"❌ 打劫失败：{_safe_error_message_provider()(e, '打劫操作异常，请稍后重试')}")
