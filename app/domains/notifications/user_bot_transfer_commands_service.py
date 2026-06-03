import logging

from app.domains.points import point_dao
from app.domains.users import user_bot_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_delete_messages_later_provider = lambda: (lambda chat_id, message_ids, delay_seconds=30: None)
_point_dao_provider = lambda: point_dao
_user_bot_dao_provider = lambda: user_bot_dao
_media_api_provider = lambda: media_api
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    send_provider=None,
    delete_messages_later_provider=None,
    point_dao_provider=None,
    user_bot_dao_provider=None,
    media_api_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _send_provider
    global _delete_messages_later_provider
    global _point_dao_provider
    global _user_bot_dao_provider
    global _media_api_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if send_provider is not None:
        _send_provider = send_provider
    if delete_messages_later_provider is not None:
        _delete_messages_later_provider = delete_messages_later_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
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


def cmd_transfer(chat_id, tg_user_id, text, is_group=False, entities=None):
    """转赠积分"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    if len(parts) < 3:
        return _send_provider()(chat_id, "💡 使用方法：/transfer @用户 积分\n示例：/transfer @张三 100\n\n💡 也可以直接使用 Emby 用户名")

    try:
        try:
            amount = int(parts[-1])
        except ValueError:
            return _send_provider()(chat_id, "❌ 积分必须是数字")

        target = " ".join(parts[1:-1]).lstrip("@")

        if not target:
            return _send_provider()(chat_id, "❌ 请指定要转赠的用户")

        mentioned_user_id = _mentioned_user_id_from_entities(text, entities)
        if mentioned_user_id:
            target = mentioned_user_id

        target_binding = _user_bot_dao_provider().get_binding_by_tg_user_or_username(target)
        to_user_id = target_binding["emby_user_id"] if target_binding else None
        to_user_name = target_binding["emby_username"] if target_binding else None
        display_name = target_binding["tg_display_name"] if target_binding else None

        if not to_user_id:
            try:
                emby_users = _media_api_provider().get("/Users", timeout=5).json()
                user_map = {u["Name"]: u["Id"] for u in emby_users}
                to_user_id = user_map.get(target)
                to_user_name = target
            except Exception:
                pass

        if not to_user_id:
            return _send_provider()(chat_id, f"❌ 未找到用户：{target}\n\n💡 请确认对方已绑定机器人，或直接使用 Emby 用户名")

        result = _point_dao_provider().transfer_points(
            binding["emby_user_id"],
            binding["emby_username"],
            to_user_id,
            to_user_name,
            amount,
            target_exists=True,
        )
        if result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {result.get('message', '转赠失败')}")

        new_from_points = result["balance"]
        actual_amount = result["actual_amount"]
        fee = result["fee"]
        display_name = display_name or to_user_name

        result = _send_provider()(
            chat_id,
            f"✅ 转赠成功！\n\n💰 已转赠 <b>{actual_amount}</b> 积分给 <b>{display_name}</b>\n💸 手续费：{fee} 积分\n📊 余额：{new_from_points}",
        )

        if is_group and result:
            bot_msg_id = result.get("result", {}).get("message_id")
            if bot_msg_id:
                _delete_messages_later_provider()(chat_id, [bot_msg_id], 15)

        return result

    except ValueError:
        return _send_provider()(chat_id, "❌ 积分必须是数字")
    except Exception as e:
        _logger_provider().error(f"[UserBot] 转赠失败: {e}")
        return _send_provider()(chat_id, f"❌ 转赠失败：{str(e)}")


def cmd_redpacket(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """发红包"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    if len(parts) < 3:
        return _send_provider()(chat_id, "💡 使用方法：/hb 总积分 数量\n示例：/hb 1000 10")

    try:
        total_amount = int(parts[1])
        total_count = int(parts[2])

        config = _point_dao_provider().get_point_config()
        if int(config.get("enable_red_packet", 0)) == 0:
            return _send_provider()(chat_id, "❌ 积分红包功能未开启")

        if int(config.get("red_packet_admin_only", 1)) == 1:
            try:
                user_info = _media_api_provider().get(f"/Users/{binding['emby_user_id']}", timeout=5).json()
                is_admin = user_info.get("Policy", {}).get("IsAdministrator", False)
            except Exception:
                is_admin = False
            if not is_admin:
                return _send_provider()(chat_id, "❌ 仅管理员可发红包")

        if total_count < 1 or total_count > 100:
            return _send_provider()(chat_id, "❌ 红包数量需在 1-100 之间")

        creator_display = tg_name or binding["emby_username"]
        red_packet_result = _point_dao_provider().create_red_packet(
            total_amount,
            total_count,
            str(chat_id),
            binding["emby_user_id"],
            creator_display,
        )
        if red_packet_result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {red_packet_result.get('message', '发红包失败')}")

        packet_id = red_packet_result.get("packet_id")
        expire_hours = int(config.get("red_packet_expire_hours", 24))

        result = _send_provider()(
            chat_id,
            f"🧧 <b>积分红包</b>\n\n"
            f"🆔 红包ID：<b>#{packet_id}</b>\n"
            f"💰 总金额：<b>{total_amount}</b> 积分\n"
            f"📦 共 <b>{total_count}</b> 个\n"
            f"⏰ {expire_hours}小时后过期\n\n"
            f"💡 发送 /grab {packet_id} 抢红包",
        )

        if result and result.get("ok"):
            msg_id = result.get("result", {}).get("message_id")
            if msg_id:
                try:
                    _point_dao_provider().save_red_packet_message_id(packet_id, msg_id)
                except Exception as e:
                    _logger_provider().warning(f"[红包] 记录红包消息ID失败: {e}")

        if is_group and user_msg_id:
            _delete_messages_later_provider()(chat_id, [user_msg_id], 15)

        return result

    except ValueError:
        return _send_provider()(chat_id, "❌ 参数必须是数字")
    except Exception as e:
        _logger_provider().error(f"[UserBot] 发红包失败: {e}")
        return _send_provider()(chat_id, f"❌ 发红包失败：{str(e)}")
