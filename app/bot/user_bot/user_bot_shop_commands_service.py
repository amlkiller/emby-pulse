import logging

from app.core.security_utils import safe_error_message
from app.domains.points import point_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_reply_provider = lambda: (lambda chat_id, text, reply_markup=None, msg_id=None: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_tg_api_provider = lambda: (lambda method, data=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_point_dao_provider = lambda: point_dao
_media_api_provider = lambda: media_api
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger
_redeem_notification_sender_provider = lambda: _send_redeem_notification

_BACK_MENU = {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}


def set_dependency_providers(
    *,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    reply_provider=None,
    send_provider=None,
    tg_api_provider=None,
    main_menu_keyboard_provider=None,
    point_dao_provider=None,
    media_api_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
    redeem_notification_sender_provider=None,
):
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _reply_provider
    global _send_provider
    global _tg_api_provider
    global _main_menu_keyboard_provider
    global _point_dao_provider
    global _media_api_provider
    global _safe_error_message_provider
    global _logger_provider
    global _redeem_notification_sender_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if check_emby_account_provider is not None:
        _check_emby_account_provider = check_emby_account_provider
    if unbind_user_provider is not None:
        _unbind_user_provider = unbind_user_provider
    if reply_provider is not None:
        _reply_provider = reply_provider
    if send_provider is not None:
        _send_provider = send_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if redeem_notification_sender_provider is not None:
        _redeem_notification_sender_provider = redeem_notification_sender_provider


def _send_redeem_notification(uname, target_name, target_type, cost, actual_days):
    from app.bot.notification_bot.bot_service import bot
    from app.infra.db.notification_dao import add_system_notification

    notify_msg = f"🎁 <b>积分商城兑换</b>\n\n👤 {uname}\n🛒 {target_name}\n💰 {cost} 积分\n📱 来源：TG 用户机器人"
    if target_type == "random_renew":
        notify_msg += f"\n🎲 随机结果：{actual_days}天"
    bot.notifier.send_message("sys_notify", notify_msg, platform="all")
    add_system_notification("points", f"商城订单: {target_name}", f"用户 {uname} 通过TG机器人兑换", "/points")


def _reply_deleted_binding(chat_id, tg_user_id, *, use_reply=False, msg_id=None):
    _unbind_user_provider()(tg_user_id)
    text = "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。"
    if use_reply:
        _reply_provider()(
            chat_id,
            text,
            reply_markup=_main_menu_keyboard_provider()(None),
            msg_id=msg_id,
        )
        return
    _send_provider()(chat_id, text, reply_markup=_main_menu_keyboard_provider()(None))


def _get_store_items(points_info):
    items = points_info.get("store_items")
    if items is not None:
        return items

    config = points_info.get("config")
    if isinstance(config, dict):
        return config.get("store_items", [])

    return []


def cmd_shop(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 请先绑定账号：/bind 用户名")
        return

    if not _check_emby_account_provider()(binding):
        _reply_deleted_binding(chat_id, tg_user_id)
        return

    try:
        points_info = _point_dao_provider().get_user_points_info(binding["emby_user_id"])
        pts = points_info.get("points", 0)
        items = _get_store_items(points_info)
        if not items:
            _reply_provider()(chat_id, "🏪 积分商城暂无商品", reply_markup=_BACK_MENU, msg_id=msg_id)
            return
        msg = f"🏪 <b>积分商城</b>\n💰 你的余额：<b>{pts}</b> 积分\n\n"
        keyboard = {"inline_keyboard": []}
        for item in items:
            if item.get("type") == "random_renew":
                base_days = item.get("base_days", 30)
                random_min = item.get("random_min", -10)
                random_max = item.get("random_max", 60)
                min_days = base_days + random_min
                max_days = base_days + random_max
                msg += f"🎲 <b>{item['name']}</b> — {item['cost']} 积分\n  {item.get('desc', '')}\n  ⚡ 基础{base_days}天 + 随机{random_min}~{random_max}天 ({min_days}~{max_days}天)\n\n"
            else:
                msg += f"• <b>{item['name']}</b> — {item['cost']} 积分\n  {item.get('desc', '')}\n\n"
            keyboard["inline_keyboard"].append([{"text": f"🛒 {item['name']} ({item['cost']}积分)", "callback_data": f"ub_redeem_{item['id']}"}])
        keyboard["inline_keyboard"].append([{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}])
        _reply_provider()(chat_id, msg.strip(), reply_markup=keyboard, msg_id=msg_id)
    except Exception as e:
        _logger_provider().error(f"[商城] 加载失败: {e}")
        _reply_provider()(chat_id, f"❌ 商城加载失败：{_safe_error_message_provider()(e, '商城加载异常，请稍后重试')}", msg_id=msg_id)


def cmd_redeem_callback(chat_id, tg_user_id, item_id, cq_id):
    _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 未绑定账号")
        return

    if not _check_emby_account_provider()(binding):
        _reply_deleted_binding(chat_id, tg_user_id)
        return

    uid = binding["emby_user_id"]
    uname = binding["emby_username"]
    try:
        redeem_result = _point_dao_provider().redeem_store_item(uid, uname, item_id)
        if redeem_result.get("status") != "success":
            _send_provider()(chat_id, f"❌ {redeem_result.get('message', '兑换失败')}")
            return

        target_name = redeem_result["item_name"]
        target_type = redeem_result["item_type"]
        cost = redeem_result["cost"]
        new_pts = redeem_result["balance"]
        result_msg = ""
        actual_days = redeem_result.get("actual_days", 0)

        if target_type == "renew":
            new_exp = redeem_result["new_exp_str"]
            try:
                _media_api_provider().post(f"/Users/{uid}/Policy", json={"IsDisabled": False}, timeout=3)
            except Exception:
                pass
            result_msg = f"📅 账号已续期至 {new_exp}"

        elif target_type == "random_renew":
            base_days = redeem_result["base_days"]
            random_min = redeem_result["random_min"]
            random_max = redeem_result["random_max"]
            random_bonus = redeem_result["random_bonus"]
            new_exp = redeem_result["new_exp_str"]
            try:
                _media_api_provider().post(f"/Users/{uid}/Policy", json={"IsDisabled": False}, timeout=3)
            except Exception:
                pass

            bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)

            range_span = random_max - random_min
            if random_bonus >= random_max - range_span * 0.1:
                result_emoji = "👑✨"
                luck_text = "天选之人！欧皇降临！"
            elif random_bonus >= random_max - range_span * 0.3:
                result_emoji = "🍀🎉"
                luck_text = "运气不错！"
            elif random_bonus >= random_min + range_span * 0.3:
                result_emoji = "✨"
                luck_text = "还算可以"
            elif random_bonus >= random_min:
                result_emoji = "📦"
                luck_text = "中规中矩"
            elif random_bonus >= random_min - range_span * 0.2:
                result_emoji = "😅"
                luck_text = "稍微有点亏"
            else:
                result_emoji = "🌧️"
                luck_text = "运气不佳..."

            result_msg = f"🎲 {result_emoji} {luck_text}\n随机结果：基础{base_days}天 {bonus_text} = {actual_days}天\n📅 账号已续期至 {new_exp}"
        else:
            result_msg = "⚠️ 此商品需人工发货，请联系管理员"

        _send_provider()(chat_id, f"✅ <b>兑换成功！</b>\n\n🛒 {target_name}\n💰 花费 {cost} 积分，余额 {new_pts}\n{result_msg}")

        try:
            _redeem_notification_sender_provider()(uname, target_name, target_type, cost, actual_days)
        except Exception:
            pass
    except Exception as e:
        _logger_provider().error(f"[兑换] 执行失败: {e}")
        _send_provider()(chat_id, f"❌ 兑换失败：{_safe_error_message_provider()(e, '兑换操作异常，请稍后重试')}")
