import datetime
import logging

from app.domains.points import point_dao


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_delete_messages_later_provider = lambda: (lambda chat_id, message_ids, delay_seconds=30: None)
_point_dao_provider = lambda: point_dao
_datetime_provider = lambda: datetime
_logger_provider = lambda: logger


def _notify_sys_all(message):
    from app.bot.notification_bot.bot_service import bot

    return bot.notifier.send_message("sys_notify", message, platform="all")


_notify_sys_all_provider = lambda: _notify_sys_all


def set_dependency_providers(
    *,
    get_binding_provider=None,
    send_provider=None,
    delete_messages_later_provider=None,
    point_dao_provider=None,
    datetime_provider=None,
    logger_provider=None,
    notify_sys_all_provider=None,
):
    global _get_binding_provider
    global _send_provider
    global _delete_messages_later_provider
    global _point_dao_provider
    global _datetime_provider
    global _logger_provider
    global _notify_sys_all_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if send_provider is not None:
        _send_provider = send_provider
    if delete_messages_later_provider is not None:
        _delete_messages_later_provider = delete_messages_later_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if notify_sys_all_provider is not None:
        _notify_sys_all_provider = notify_sys_all_provider


def cmd_grab(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """抢红包"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    if len(parts) < 2:
        return _send_provider()(chat_id, "💡 使用方法：/grab 红包ID\n示例：/grab 123")

    try:
        packet_id = int(parts[1])

        grab_result = _point_dao_provider().grab_red_packet(
            packet_id,
            binding["emby_user_id"],
            tg_name or binding["emby_username"],
            allow_creator=False,
        )
        if grab_result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {grab_result.get('message', '抢红包失败')}")

        if grab_result.get("is_last_one"):
            notify_msg = "🧧 <b>红包已抢完</b>\n\n"
            notify_msg += f"👤 <b>发红包</b>: {grab_result.get('creator_name')}\n"
            notify_msg += f"💰 <b>总金额</b>: {grab_result.get('total_amount')} 积分\n"
            notify_msg += f"📦 <b>总个数</b>: {grab_result.get('total_count')} 个\n\n"
            notify_msg += "📋 <b>领取明细</b>:\n"
            for i, log in enumerate(grab_result.get("grab_logs", []), 1):
                notify_msg += f"{i}. {log.get('user_name')}: {log.get('amount')} 积分\n"
            try:
                packet_chat_id = grab_result.get("chat_id")
                if packet_chat_id:
                    _send_provider()(packet_chat_id, notify_msg)
                    message_id = grab_result.get("message_id")
                    if message_id:
                        _delete_messages_later_provider()(int(packet_chat_id), [message_id], 15)
                else:
                    _notify_sys_all_provider()(notify_msg)
            except Exception as e:
                _logger_provider().error(f"[红包] 发送抢完通知失败: {e}")

        result = _send_provider()(
            chat_id,
            f"🎉 <b>恭喜你！</b>\n\n"
            f"🧧 抢到 <b>{grab_result.get('amount', 0)}</b> 积分\n"
            f"💰 余额：<b>{grab_result.get('balance', 0)}</b> 积分",
        )

        if is_group and result:
            bot_msg_id = result.get("result", {}).get("message_id")
            if bot_msg_id:
                msgs_to_delete = [bot_msg_id]
                if user_msg_id:
                    msgs_to_delete.append(user_msg_id)
                _delete_messages_later_provider()(chat_id, msgs_to_delete, 15)

        return result

    except ValueError:
        return _send_provider()(chat_id, "❌ 红包ID必须是数字")
    except Exception as e:
        _logger_provider().error(f"[UserBot] 抢红包失败: {e}")
        return _send_provider()(chat_id, f"❌ 抢红包失败：{str(e)}")


def cmd_lottery(chat_id, tg_user_id, text, is_group=False, user_msg_id=None):
    """彩票系统"""
    _logger_provider().info(f"[彩票] 命令调用: chat_id={chat_id}, text={text}")
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return _send_provider()(chat_id, "❌ 请先私聊机器人绑定账号")

    parts = text.split()
    _logger_provider().info(f"[彩票] parts={parts}")

    config = _point_dao_provider().get_point_config()
    if int(config.get("enable_lottery", 0)) == 0:
        return _send_provider()(chat_id, "❌ 彩票功能未开启")

    lottery_cost = int(config.get("lottery_cost", 10))
    lottery_max = int(config.get("lottery_max_per_day", 10))
    draw_hour = int(config.get("lottery_draw_hour", 20))

    datetime_module = _datetime_provider()
    today = datetime_module.datetime.now().strftime("%Y-%m-%d")

    if len(parts) == 1 or parts[1] in ["my", "我的"]:
        tickets = _point_dao_provider().list_user_lottery_tickets(binding["emby_user_id"])

        if not tickets:
            return _send_provider()(chat_id, "🎫 <b>我的彩票</b>\n\n最近没有购买彩票\n\n💡 发送 /lottery 1234 购买")

        msg = "🎫 <b>我的彩票</b>\n\n"
        current_date = None
        for ticket in tickets:
            numbers = ticket["numbers"]
            cost = ticket["cost"]
            draw_date = ticket["draw_date"]

            result_row = _point_dao_provider().get_lottery_winning_numbers(draw_date)

            if result_row and result_row["winning_numbers"]:
                winning_numbers = result_row["winning_numbers"]
                lucky_row = None
                if lucky_row:
                    status = "🍀 幸运奖"
                else:
                    match_count = sum(1 for i in range(4) if numbers[i] == winning_numbers[i])
                    if match_count == 4:
                        status = "🏆 一等奖"
                    elif match_count == 3:
                        status = "🥈 二等奖"
                    elif match_count == 2:
                        if (
                            numbers[0:2] == winning_numbers[0:2]
                            or numbers[1:3] == winning_numbers[1:3]
                            or numbers[2:4] == winning_numbers[2:4]
                        ):
                            status = "🥉 三等奖"
                        else:
                            status = "🎁 安慰奖"
                    else:
                        status = "❌ 未中奖"
            else:
                status = "⏳ 未开奖"

            if draw_date != current_date:
                if current_date:
                    msg += "\n"
                msg += f"📅 {draw_date}\n"
                current_date = draw_date

            msg += f"  {numbers} | {status}\n"

        return _send_provider()(chat_id, msg)

    if parts[1] in ["result", "结果", "开奖"]:
        result = _point_dao_provider().get_latest_lottery_result()

        if not result:
            return _send_provider()(chat_id, "🎫 <b>开奖结果</b>\n\n暂无开奖记录")

        draw_date = result["draw_date"]
        winning_numbers = result["winning_numbers"]
        total_pool = result["total_pool"]

        winners = _point_dao_provider().list_lottery_winners_for_date(draw_date)

        msg = f"🎫 <b>开奖结果</b> ({draw_date})\n\n"
        msg += f"🎲 中奖号码: <b>{winning_numbers}</b>\n"
        msg += f"💰 奖池: {total_pool} 积分\n\n"

        if winners:
            msg += "🏆 中奖名单:\n"
            level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}
            for winner in winners:
                msg += (
                    f"• {winner['username']} - "
                    f"{level_names.get(winner['prize_level'], '未知')} {winner['prize_amount']} 积分\n"
                )
        else:
            msg += "😢 本期无人中奖，奖池累积到下期"

        return _send_provider()(chat_id, msg)

    if parts[1] in ["pool", "奖池"]:
        today_drawn = _point_dao_provider().get_lottery_winning_numbers(today)

        if today_drawn and today_drawn["winning_numbers"]:
            target_date = (datetime_module.datetime.now() + datetime_module.timedelta(days=1)).strftime("%Y-%m-%d")
            draw_status = "✅ 已开奖"
            next_draw = f"明天 {draw_hour}:00"
        else:
            target_date = today
            draw_status = "⏳ 未开奖"
            next_draw = f"今天 {draw_hour}:00"

        pool_info = _point_dao_provider().get_lottery_pool_info(binding["emby_user_id"], today, target_date)
        target_pool = pool_info["today_pool"]
        target_tickets = pool_info["today_tickets"]

        ratio_1 = int(config.get("lottery_pool_ratio_1", 50))
        ratio_2 = int(config.get("lottery_pool_ratio_2", 20))
        ratio_3 = int(config.get("lottery_pool_ratio_3", 10))
        ratio_4 = int(config.get("lottery_pool_ratio_4", 5))

        msg = f"🎰 <b>当前奖池</b> ({target_date})\n\n"
        msg += f"💰 奖池总额: <b>{target_pool}</b> 积分\n"
        msg += f"🎫 本期购票: <b>{target_tickets}</b> 张\n\n"
        msg += f"📋 本期状态: {draw_status}\n"
        msg += f"⏰ 下次开奖: {next_draw}\n\n"
        msg += "📊 奖池分配:\n"
        msg += f"• 一等奖: {ratio_1}% = {int(target_pool * ratio_1 / 100)} 积分\n"
        msg += f"• 二等奖: {ratio_2}% = {int(target_pool * ratio_2 / 100)} 积分\n"
        msg += f"• 三等奖: {ratio_3}% = {int(target_pool * ratio_3 / 100)} 积分\n"
        msg += f"• 三等奖: {ratio_3}% = {int(target_pool * ratio_3 / 100)} 积分\n"
        msg += f"• 安慰奖: {ratio_4}% = {int(target_pool * ratio_4 / 100)} 积分\n"

        lucky_count = int(config.get("lottery_lucky_count", 0))
        if lucky_count > 0:
            lucky_ratio = int(config.get("lottery_lucky_ratio", 5))
            msg += f"• 幸运奖: {lucky_ratio}% = {int(target_pool * lucky_ratio / 100)} 积分 (抽{lucky_count}人)\n"

        return _send_provider()(chat_id, msg)

    numbers_list = []
    for part in parts[1:]:
        _logger_provider().info(f"[彩票] 验证号码: p={part}, len={len(part)}, isdigit={part.isdigit()}")
        if len(part) == 4 and part.isdigit():
            numbers_list.append(part)

    _logger_provider().info(f"[彩票] numbers_list={numbers_list}")

    if not numbers_list:
        _logger_provider().warning("[彩票] 号码验证失败，返回使用说明")
        return _send_provider()(
            chat_id,
            "💡 使用方法：\n/lottery 1234 - 购买一张彩票\n/lottery 1234 5678 - 购买多张\n/lottery my - 查看我的彩票\n/lottery result - 查看开奖结果\n\n🎫 彩票为4位数字(0000-9999)",
        )

    _logger_provider().info("[彩票] 开始检查购买数量和积分")

    today_drawn = _point_dao_provider().get_lottery_winning_numbers(today)
    if today_drawn and today_drawn["winning_numbers"]:
        tomorrow = (datetime_module.datetime.now() + datetime_module.timedelta(days=1)).strftime("%Y-%m-%d")
        draw_date_for_ticket = tomorrow
        draw_date_display = f"明天 ({tomorrow}) {draw_hour}:00"
    else:
        draw_date_for_ticket = today
        draw_date_display = f"今天 {draw_hour}:00"

    today_count = len(_point_dao_provider().list_lottery_ticket_numbers(binding["emby_user_id"], draw_date_for_ticket))
    _logger_provider().info(f"[彩票] {draw_date_for_ticket} 已购买: {today_count}, 限购: {lottery_max}")

    if today_count + len(numbers_list) > lottery_max:
        return _send_provider()(chat_id, f"❌ 每人每天最多购买 {lottery_max} 张彩票\n\n今天已购买: {today_count} 张")

    total_cost = len(numbers_list) * lottery_cost
    _logger_provider().info(f"[彩票] 彩票价格: {lottery_cost}, 数量: {len(numbers_list)}, 总花费: {total_cost}")
    current_points = _point_dao_provider().get_user_points_balance(binding["emby_user_id"])
    _logger_provider().info(f"[彩票] 积分: {current_points}, 需要: {total_cost}")

    if current_points < total_cost:
        _logger_provider().warning("[彩票] 积分不足")
        return _send_provider()(chat_id, f"❌ 积分不足！需要 {total_cost} 积分，当前: {current_points}")

    _logger_provider().info("[彩票] 积分检查通过，开始扣除积分")

    try:
        result = _point_dao_provider().buy_lottery_tickets(
            binding["emby_user_id"],
            binding["emby_username"],
            len(numbers_list),
            lottery_cost,
            lottery_max,
            draw_date_for_ticket,
            numbers_list,
        )
        if result.get("status") != "success":
            return _send_provider()(chat_id, f"❌ {result.get('message', '购买失败')}")
        new_points = result["new_points"]
        _logger_provider().info("[彩票] 购买成功，发送消息")
    except Exception as e:
        _logger_provider().error(f"[彩票] 数据库操作失败: {e}")
        return _send_provider()(chat_id, f"❌ 购买失败：{str(e)}")

    msg = "🎫 <b>购买成功！</b>\n\n"
    for i, number in enumerate(numbers_list, 1):
        msg += f"{i}. 号码: <b>{number}</b>\n"
    msg += f"\n💰 花费: {total_cost} 积分\n📊 余额: {new_points} 积分\n\n⏰ 开奖时间: {draw_date_display}"

    result = _send_provider()(chat_id, msg)

    if is_group and result:
        bot_msg_id = result.get("result", {}).get("message_id")
        if bot_msg_id:
            msgs_to_delete = [bot_msg_id]
            if user_msg_id:
                msgs_to_delete.append(user_msg_id)
            _delete_messages_later_provider()(chat_id, msgs_to_delete, 15)

    return result
