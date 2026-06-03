import logging
import random
import time

from app.domains.points import point_dao


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_tg_api_provider = lambda: (lambda method, data: None)
_delete_messages_later_provider = lambda: (lambda chat_id, message_ids, delay_seconds=30: None)
_point_dao_provider = lambda: point_dao
_random_provider = lambda: random
_sleep_provider = lambda: time.sleep
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    send_provider=None,
    tg_api_provider=None,
    delete_messages_later_provider=None,
    point_dao_provider=None,
    random_provider=None,
    sleep_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _send_provider
    global _tg_api_provider
    global _delete_messages_later_provider
    global _point_dao_provider
    global _random_provider
    global _sleep_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if send_provider is not None:
        _send_provider = send_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if delete_messages_later_provider is not None:
        _delete_messages_later_provider = delete_messages_later_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if random_provider is not None:
        _random_provider = random_provider
    if sleep_provider is not None:
        _sleep_provider = sleep_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_pk(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """PK掷骰子游戏 - 使用Telegram骰子动画"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    if len(parts) < 2:
        return _send_provider()(chat_id, "💡 使用方法：/pk 积分\n示例：/pk 100\n\n🎲 和机器人掷骰子比大小，赢了翻倍，输了扣分")

    try:
        amount = int(parts[1])

        if amount <= 0:
            return _send_provider()(chat_id, "❌ 积分必须大于0")
        config = _point_dao_provider().get_point_config()
        if int(config.get("enable_pk", 0)) == 0:
            return _send_provider()(chat_id, "❌ PK功能未开启")

        min_pk = int(config.get("pk_min", 10))
        max_pk = int(config.get("pk_max", 500))
        if amount < min_pk or amount > max_pk:
            return _send_provider()(chat_id, f"❌ PK积分需在 {min_pk}-{max_pk} 之间")

        pk_max_per_day = int(config.get("pk_max_per_day", 10))
        today_count = _point_dao_provider().count_today_point_logs(binding["emby_user_id"], action_like="PK%")
        if today_count >= pk_max_per_day:
            return _send_provider()(chat_id, f"❌ 今天PK次数已达上限 ({pk_max_per_day}次)\n\n💡 明天再来吧！")

        current_points = _point_dao_provider().get_user_points_balance(binding["emby_user_id"])
        if current_points < amount:
            return _send_provider()(chat_id, f"❌ 积分不足！当前积分: {current_points}")

        display_name = tg_name or binding["emby_username"]
        user_at = f"<a href='tg://user?id={tg_user_id}'>{display_name}</a>" if is_group else "你"

        start_msg = _send_provider()(
            chat_id,
            f"🎲 <b>PK 开始！</b>\n\n👤 {user_at} 发起挑战\n💰 赌注：<b>{amount}</b> 积分\n\n⏳ 正在掷骰子...",
        )
        start_msg_id = start_msg.get("result", {}).get("message_id") if start_msg else None

        user_dice_msg = _tg_api_provider()("sendDice", {"chat_id": chat_id, "emoji": "🎲"})
        if not user_dice_msg:
            return _send_provider()(chat_id, "❌ 发送骰子失败，请稍后重试")
        user_dice_msg_id = user_dice_msg.get("result", {}).get("message_id")
        user_dice = user_dice_msg.get("result", {}).get("dice", {}).get("value", _random_provider().randint(1, 6))

        _sleep_provider()(1.5)

        bot_dice_msg = _tg_api_provider()("sendDice", {"chat_id": chat_id, "emoji": "🎲"})
        if not bot_dice_msg:
            return _send_provider()(chat_id, "❌ 发送骰子失败，请稍后重试")
        bot_dice_msg_id = bot_dice_msg.get("result", {}).get("message_id")
        bot_dice = bot_dice_msg.get("result", {}).get("dice", {}).get("value", _random_provider().randint(1, 6))

        if user_dice > bot_dice:
            point_result = _point_dao_provider().apply_game_point_change(
                binding["emby_user_id"],
                binding["emby_username"],
                f"PK赢了 (骰子{user_dice}vs{bot_dice})",
                amount,
            )
            log_action = f"PK赢了 (骰子{user_dice}vs{bot_dice})"
            log_amount = amount
        elif user_dice < bot_dice:
            point_result = _point_dao_provider().apply_game_point_change(
                binding["emby_user_id"],
                binding["emby_username"],
                f"PK输了 (骰子{user_dice}vs{bot_dice})",
                -amount,
                require_min_points=amount,
            )
            log_action = f"PK输了 (骰子{user_dice}vs{bot_dice})"
            log_amount = -amount
        else:
            point_result = _point_dao_provider().apply_game_point_change(
                binding["emby_user_id"],
                binding["emby_username"],
                f"PK平局 (骰子{user_dice}vs{bot_dice})",
                0,
            )

        if point_result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {point_result.get('message', 'PK处理失败')}")

        new_points = point_result["points"]

        if log_amount > 0:
            result_text = f"🎉 <b>{user_at} 赢了！</b>\n\n🎲 掷出 <b>{user_dice}</b> 点，机器人掷出 <b>{bot_dice}</b> 点\n💰 获得 <b>+{amount}</b> 积分\n📊 余额：<b>{new_points}</b> 积分"
        elif log_amount < 0:
            result_text = f"😢 <b>{user_at} 输了！</b>\n\n🎲 掷出 <b>{user_dice}</b> 点，机器人掷出 <b>{bot_dice}</b> 点\n💰 扣除 <b>-{amount}</b> 积分\n📊 余额：<b>{new_points}</b> 积分"
        else:
            result_text = f"🤝 <b>平局！</b>\n\n🎲 {user_at} 掷出 <b>{user_dice}</b> 点，机器人掷出 <b>{bot_dice}</b> 点\n💰 积分不变\n📊 余额：<b>{new_points}</b> 积分"

        result = _send_provider()(chat_id, result_text)

        if is_group:
            msgs_to_delete = []
            if user_msg_id:
                msgs_to_delete.append(user_msg_id)
            if start_msg_id:
                msgs_to_delete.append(start_msg_id)
            if user_dice_msg_id:
                msgs_to_delete.append(user_dice_msg_id)
            if bot_dice_msg_id:
                msgs_to_delete.append(bot_dice_msg_id)
            if result:
                bot_msg_id = result.get("result", {}).get("message_id")
                if bot_msg_id:
                    msgs_to_delete.append(bot_msg_id)
            if msgs_to_delete:
                _delete_messages_later_provider()(chat_id, msgs_to_delete, 15)

        return result

    except ValueError:
        return _send_provider()(chat_id, "❌ 积分必须是数字")
    except Exception as e:
        _logger_provider().error(f"[UserBot] PK失败: {e}")
        return _send_provider()(chat_id, f"❌ PK失败：{str(e)}")
