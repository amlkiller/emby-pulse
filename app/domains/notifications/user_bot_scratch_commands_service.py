import logging
import random

from app.domains.points import point_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_delete_messages_later_provider = lambda: (lambda chat_id, message_ids, delay_seconds=30: None)
_tg_api_provider = lambda: (lambda method, data: None)
_point_dao_provider = lambda: point_dao
_media_api_provider = lambda: media_api
_random_provider = lambda: random
_logger_provider = lambda: logger
_cmd_scratch_impl_provider = lambda: _cmd_scratch_impl
_update_scratch_message_provider = lambda: _update_scratch_message
_scratch_draw_result_provider = lambda: _scratch_draw_result


def set_dependency_providers(
    *,
    get_binding_provider=None,
    send_provider=None,
    delete_messages_later_provider=None,
    tg_api_provider=None,
    point_dao_provider=None,
    media_api_provider=None,
    random_provider=None,
    logger_provider=None,
    cmd_scratch_impl_provider=None,
    update_scratch_message_provider=None,
    scratch_draw_result_provider=None,
):
    global _get_binding_provider
    global _send_provider
    global _delete_messages_later_provider
    global _tg_api_provider
    global _point_dao_provider
    global _media_api_provider
    global _random_provider
    global _logger_provider
    global _cmd_scratch_impl_provider
    global _update_scratch_message_provider
    global _scratch_draw_result_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if send_provider is not None:
        _send_provider = send_provider
    if delete_messages_later_provider is not None:
        _delete_messages_later_provider = delete_messages_later_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if random_provider is not None:
        _random_provider = random_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if cmd_scratch_impl_provider is not None:
        _cmd_scratch_impl_provider = cmd_scratch_impl_provider
    if update_scratch_message_provider is not None:
        _update_scratch_message_provider = update_scratch_message_provider
    if scratch_draw_result_provider is not None:
        _scratch_draw_result_provider = scratch_draw_result_provider


def _scratch_keyboard(card_id, slots, status="active"):
    buttons = []
    for num, is_scratched, _username in slots:
        if is_scratched or status == "completed":
            buttons.append({"text": f"{num}✅", "callback_data": f"scratch_done_{card_id}_{num}"})
        else:
            buttons.append({"text": str(num), "callback_data": f"scratch_{card_id}_{num}"})
    return [buttons[i:i + 3] for i in range(0, len(buttons), 3)]


def cmd_scratch(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """刮刮乐"""
    try:
        return _cmd_scratch_impl_provider()(chat_id, tg_user_id, text, is_group, tg_name, user_msg_id)
    except Exception as e:
        _logger_provider().error(f"[刮刮乐] 命令执行失败: {e}")
        return _send_provider()(chat_id, f"❌ 刮刮乐出错：{str(e)}")


def _cmd_scratch_impl(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """刮刮乐(内部实现)"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    config = _point_dao_provider().get_point_config()

    if int(config.get("enable_scratch", 0)) == 0:
        return _send_provider()(chat_id, "❌ 刮刮乐功能未开启")

    scratch_cost = int(config.get("scratch_cost", 100))

    parts = text.split()

    if len(parts) == 1 or parts[1] in ["info", "当前"]:
        card = _point_dao_provider().get_active_scratch_card()

        if not card:
            return _send_provider()(chat_id, "🎰 <b>刮刮乐</b>\n\n当前没有进行中的刮刮乐\n\n💡 发送 /scratch 开始 创建新刮刮乐")

        card_id = card["id"]
        total_slots = card["total_slots"]
        filled_slots = card["filled_slots"]
        price = card["price"]

        slots = _point_dao_provider().get_scratch_card_slots(card_id)

        msg = f"🎰 <b>刮刮乐 #{card_id}</b>\n\n"
        msg += f"💰 售价: {price} 积分/次\n"
        msg += f"📊 进度: {filled_slots}/{total_slots} 已刮\n\n"
        msg += "⚠️ 点击下方按钮刮奖，每人只能刮一次！"

        keyboard = _scratch_keyboard(card_id, slots)
        return _send_provider()(chat_id, msg, reply_markup={"inline_keyboard": keyboard})

    if parts[1] in ["start", "开始", "create", "创建"]:
        if int(config.get("scratch_admin_only", 0)) == 1:
            try:
                user_info = _media_api_provider().get(f"/Users/{binding['emby_user_id']}", timeout=5).json()
                is_admin = user_info.get("Policy", {}).get("IsAdministrator", False)
            except Exception:
                is_admin = False
            if not is_admin:
                return _send_provider()(chat_id, "❌ 仅管理员可发起刮刮乐")

        total_slots = int(config.get("scratch_slots", 9))
        price = scratch_cost

        big_prize_rate = float(config.get("scratch_big_prize_rate", 1)) / 100
        medium_prize_rate = float(config.get("scratch_medium_prize_rate", 10)) / 100

        prizes = []
        random_module = _random_provider()
        for _i in range(total_slots):
            rand = random_module.random()
            if rand < big_prize_rate:
                prizes.append(random_module.choice([666, 888, 999]))
            elif rand < big_prize_rate + medium_prize_rate:
                prizes.append(random_module.randint(50, 200))
            elif rand < big_prize_rate + medium_prize_rate + 0.3:
                prizes.append(random_module.randint(10, 50))
            else:
                prizes.append(random_module.randint(1, 10))

        random_module.shuffle(prizes)

        display_name = tg_name or binding["emby_username"]
        create_result = _point_dao_provider().create_scratch_card(
            total_slots=total_slots,
            price=price,
            created_by=display_name,
            chat_id=chat_id,
            prizes=prizes,
        )
        if create_result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {create_result.get('message', '创建刮刮乐失败')}")
        card_id = create_result["card_id"]

        msg = "🎰 <b>刮刮乐开始！</b>\n\n"
        msg += f"👤 发起人: {display_name}\n"
        msg += f"💰 售价: {price} 积分/次\n"
        msg += f"🎯 共 {total_slots} 个格子\n\n"
        msg += "🏆 大奖: 666/888/999 积分\n"
        msg += "🎯 中奖: 50-200 积分\n"
        msg += "🎁 小奖: 10-50 积分\n"
        msg += "😅 保底: 1-10 积分\n\n"
        msg += "⚠️ 每人只能刮一次！"

        buttons = []
        for i in range(1, total_slots + 1):
            buttons.append({"text": str(i), "callback_data": f"scratch_{card_id}_{i}"})
        keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]

        result = _send_provider()(chat_id, msg, reply_markup={"inline_keyboard": keyboard})

        if result and result.get("result", {}).get("message_id"):
            _point_dao_provider().save_scratch_card_message_id(card_id, result["result"]["message_id"])

        if is_group and user_msg_id:
            _delete_messages_later_provider()(chat_id, [user_msg_id], 15)

        return result

    return _send_provider()(chat_id, "💡 使用方法:\n/scratch - 查看当前刮刮乐\n/scratch 开始 - 创建新刮刮乐")


def _handle_scratch(chat_id, tg_user_id, card_id, slot_number, tg_name=""):
    """处理刮刮乐点击"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    try:
        card = _point_dao_provider().get_scratch_card(card_id)
        if not card:
            return _send_provider()(chat_id, "❌ 刮刮乐不存在")

        if card["status"] != "active":
            return _send_provider()(chat_id, "❌ 刮刮乐已结束")

        display_name = tg_name or binding["emby_username"]
        update_result = _point_dao_provider().update_scratch_card_slot(
            card_id,
            slot_number,
            binding["emby_user_id"],
            binding["emby_username"],
            card["price"],
            display_name,
        )
        if update_result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {update_result.get('message', '刮奖失败')}")

        new_points = update_result["new_points"]
        new_filled = update_result["new_filled"]
        total_slots = update_result["total_slots"]
        orig_chat_id = update_result["chat_id"]
        orig_msg_id = update_result["message_id"]
        is_last_one = new_filled >= total_slots

        if orig_msg_id and orig_chat_id:
            _update_scratch_message_provider()(orig_chat_id, orig_msg_id, card_id)

        if is_last_one:
            _scratch_draw_result_provider()(chat_id, card_id)
        else:
            _send_provider()(
                chat_id,
                f"✅ <b>{display_name} 刮开了格子 {slot_number}</b>\n\n"
                f"📊 进度: {new_filled}/{total_slots} 已刮\n"
                f"💳 余额: {new_points} 积分\n\n"
                f"⏳ 等待其他 {total_slots - new_filled} 个格子被刮开...",
            )

    except Exception as e:
        _logger_provider().error(f"[刮刮乐] 刮奖失败: {e}")
        _send_provider()(chat_id, f"❌ 刮奖失败：{str(e)}")


def _update_scratch_message(chat_id, msg_id, card_id):
    """更新刮刮乐消息的按钮状态"""
    try:
        card = _point_dao_provider().get_scratch_card(card_id)
        status = card["status"] if card else "completed"
        slots = _point_dao_provider().get_scratch_card_slots(card_id)

        keyboard = _scratch_keyboard(card_id, slots, status=status)

        _tg_api_provider()(
            "editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": msg_id,
                "reply_markup": {"inline_keyboard": keyboard},
            },
        )
    except Exception as e:
        _logger_provider().error(f"[刮刮乐] 更新消息失败: {e}")


def _scratch_draw_result(chat_id, card_id):
    """刮刮乐开奖"""
    try:
        slots = _point_dao_provider().complete_scratch_card(card_id)
        if not slots:
            _logger_provider().info(f"[刮刮乐] #{card_id} 已经开奖或不存在，跳过")
            return

        summary = f"🎊 <b>刮刮乐 #{card_id} 开奖！</b>\n\n"
        summary += "📋 中奖明细:\n"
        total_prize = 0

        for slot in slots:
            num = slot["slot_number"]
            prize = slot["prize_amount"]
            uname = slot["username"]

            if prize >= 666:
                emoji = "🏆"
            elif prize >= 50:
                emoji = "🎉"
            elif prize >= 10:
                emoji = "🎁"
            else:
                emoji = "😅"

            summary += f"{num}. {emoji} {uname or '未知'}: {prize} 积分\n"
            total_prize += prize

        summary += f"\n💰 总发放: {total_prize} 积分"

        card_info = _point_dao_provider().get_scratch_card_origin(card_id)
        if card_info:
            orig_chat_id = card_info["chat_id"]
            orig_msg_id = card_info["message_id"]
            if orig_chat_id and orig_msg_id:
                _delete_messages_later_provider()(int(orig_chat_id), [orig_msg_id], 15)

        _send_provider()(chat_id, summary)

    except Exception as e:
        _logger_provider().error(f"[刮刮乐] 开奖失败: {e}")
