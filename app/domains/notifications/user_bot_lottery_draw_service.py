import datetime
import logging
import random

from app.domains.points import point_dao
from app.domains.users import user_bot_dao
from app.infra.clients.media_server_client import media_api
from app.infra.config.user_bot_settings import get_user_bot_allowed_groups


logger = logging.getLogger("uvicorn")

_datetime_provider = lambda: datetime
_random_provider = lambda: random
_point_dao_provider = lambda: point_dao
_media_api_provider = lambda: media_api
_allowed_groups_provider = lambda: get_user_bot_allowed_groups()
_get_binding_by_emby_id_provider = lambda: (lambda emby_user_id: None)
_user_bot_dao_provider = lambda: user_bot_dao
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    datetime_provider=None,
    random_provider=None,
    point_dao_provider=None,
    media_api_provider=None,
    allowed_groups_provider=None,
    get_binding_by_emby_id_provider=None,
    user_bot_dao_provider=None,
    send_provider=None,
    logger_provider=None,
):
    global _datetime_provider
    global _random_provider
    global _point_dao_provider
    global _media_api_provider
    global _allowed_groups_provider
    global _get_binding_by_emby_id_provider
    global _user_bot_dao_provider
    global _send_provider
    global _logger_provider

    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if random_provider is not None:
        _random_provider = random_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if allowed_groups_provider is not None:
        _allowed_groups_provider = allowed_groups_provider
    if get_binding_by_emby_id_provider is not None:
        _get_binding_by_emby_id_provider = get_binding_by_emby_id_provider
    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if send_provider is not None:
        _send_provider = send_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def do_lottery_draw():
    """执行彩票开奖（由定时任务调用）"""
    try:
        current_datetime = _datetime_provider()
        random_source = _random_provider()
        point_dao_obj = _point_dao_provider()
        media_api_obj = _media_api_provider()
        logger_obj = _logger_provider()

        today = current_datetime.datetime.now().strftime("%Y-%m-%d")
        draw_context = point_dao_obj.get_lottery_draw_context(today)
        if draw_context["already_drawn"]:
            logger_obj.info(f"[彩票] 今天已开奖: {draw_context['winning_numbers']}")
            return

        winning_numbers = "".join([str(random_source.randint(0, 9)) for _ in range(4)])

        total_pool = draw_context["total_pool"]
        raw_tickets = draw_context["tickets"]

        tickets = []
        for ticket in raw_tickets:
            ticket_id = ticket["id"]
            user_id = ticket["user_id"]
            username = ticket["username"]
            numbers = ticket["numbers"]
            try:
                user_info = media_api_obj.get(f"/Users/{user_id}", timeout=3)
                if user_info.status_code == 200:
                    tickets.append((ticket_id, user_id, username, numbers))
                else:
                    logger_obj.warning(f"[彩票] 用户 {user_id}({username}) 已被删除，跳过")
            except:
                tickets.append((ticket_id, user_id, username, numbers))  # 检查失败时保留

        if not tickets:
            logger_obj.info("[彩票] 今天没有彩票，跳过开奖")
            return

        winners = {1: [], 2: [], 3: [], 4: []}  # 一等奖、二等奖、三等奖、安慰奖

        for ticket_id, user_id, username, numbers in tickets:
            match_count = sum(1 for i in range(4) if numbers[i] == winning_numbers[i])

            if match_count == 4:
                winners[1].append((ticket_id, user_id, username))
            elif match_count == 3:
                winners[2].append((ticket_id, user_id, username))
            elif match_count == 2:
                if numbers[0:2] == winning_numbers[0:2] or numbers[1:3] == winning_numbers[1:3] or numbers[2:4] == winning_numbers[2:4]:
                    winners[3].append((ticket_id, user_id, username))
                else:
                    winners[4].append((ticket_id, user_id, username))

        config = point_dao_obj.get_point_config()
        prize_pool_ratios = {
            1: int(config.get("lottery_pool_ratio_1", 50)) / 100,
            2: int(config.get("lottery_pool_ratio_2", 20)) / 100,
            3: int(config.get("lottery_pool_ratio_3", 10)) / 100,
            4: int(config.get("lottery_pool_ratio_4", 5)) / 100,
        }

        lucky_count = int(config.get("lottery_lucky_count", 0))
        lucky_ratio = int(config.get("lottery_lucky_ratio", 5)) / 100

        prize_pools = {}
        for level, ratio in prize_pool_ratios.items():
            prize_pools[level] = int(total_pool * ratio)

        if lucky_count > 0:
            prize_pools[5] = int(total_pool * lucky_ratio)

        winners_by_level = {
            level: [
                {
                    "ticket_id": ticket_id,
                    "user_id": user_id,
                    "username": username,
                    "prize_amount": prize_pools[level] // len(winner_list) if prize_pools[level] > 0 else 0,
                }
                for ticket_id, user_id, username in winner_list
            ]
            for level, winner_list in winners.items()
        }

        for level, winner_list in winners.items():
            if not winner_list or prize_pools[level] <= 0:
                continue

            prize_per_person = prize_pools[level] // len(winner_list)
            if prize_per_person <= 0:
                prize_per_person = 1
            for winner in winners_by_level[level]:
                winner["prize_amount"] = prize_per_person

        lucky_winners = []
        if lucky_count > 0 and len(tickets) > 0 and prize_pools.get(5, 0) > 0:
            unique_users = {}
            for ticket_id, user_id, username, numbers in tickets:
                if user_id not in unique_users:
                    unique_users[user_id] = (ticket_id, username)

            user_list = list(unique_users.items())
            actual_lucky_count = min(lucky_count, len(user_list))
            if actual_lucky_count > 0:
                lucky_selected = random_source.sample(user_list, actual_lucky_count)
                prize_per_lucky = prize_pools[5] // actual_lucky_count
                if prize_per_lucky <= 0:
                    prize_per_lucky = 1

                for user_id, (ticket_id, username) in lucky_selected:
                    lucky_winners.append({"ticket_id": ticket_id, "user_id": user_id, "username": username, "prize_amount": prize_per_lucky})
                    logger_obj.info(f"[彩票] 幸运奖: {username} 获得 {prize_per_lucky} 积分")

        total_distributed = 0
        for level, winner_list in winners.items():
            if winner_list and level in prize_pools and prize_pools[level] > 0:
                total_distributed += prize_pools[level]
        if lucky_winners and prize_pools.get(5, 0) > 0:
            total_distributed += prize_pools[5]

        remaining_pool = total_pool - total_distributed
        if remaining_pool < 0:
            remaining_pool = 0

        save_result = point_dao_obj.save_lottery_draw_result(today, winning_numbers, winners_by_level, lucky_winners, remaining_pool)
        if save_result.get("status") != "success":
            logger_obj.info(f"[彩票] 开奖已跳过: {save_result}")
            return

        logger_obj.info(f"[彩票] 开奖完成: {winning_numbers}, 奖池: {total_pool}, 中奖人数: {sum(len(w) for w in winners_by_level.values())}")

        allowed_groups = _allowed_groups_provider()
        logger_obj.info(f"[彩票] 允许的群: {allowed_groups}")
        if allowed_groups:
            group_list = [g.strip() for g in allowed_groups.split("\n") if g.strip()]
            logger_obj.info(f"[彩票] 群列表: {group_list}")

            msg = f"🎰 <b>彩票开奖结果</b> ({today})\n\n"
            msg += f"🎲 中奖号码: <b>{winning_numbers}</b>\n"
            msg += f"💰 奖池: {total_pool} 积分\n\n"

            total_winners = sum(len(w) for w in winners_by_level.values()) + len(lucky_winners)
            if total_winners > 0:
                msg += "🏆 中奖名单:\n"
                level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}
                for level, winner_list in winners_by_level.items():
                    if winner_list:
                        prize_per_person = prize_pools[level] // len(winner_list) if prize_pools[level] > 0 else 0
                        for winner in winner_list:
                            user_id = winner["user_id"]
                            emby_username = winner["username"]
                            display = _resolve_lottery_display_name(user_id, emby_username)
                            msg += f"• {display} - {level_names[level]} (+{winner['prize_amount']}积分)\n"
                if lucky_winners:
                    for winner in lucky_winners:
                        user_id = winner["user_id"]
                        emby_username = winner["username"]
                        amount = winner["prize_amount"]
                        display = _resolve_lottery_display_name(user_id, emby_username)
                        msg += f"• {display} - 幸运奖 (+{amount}积分)\n"
            else:
                msg += "😢 本期无人中奖，奖池累积到下期\n"

            msg += "\n💡 发送 /彩票 奖池 查看当前奖池"
            msg += f"\n📊 剩余奖池: {remaining_pool} 积分已累积到下期"

            for group_id in group_list:
                try:
                    logger_obj.info(f"[彩票] 尝试发送到群: {group_id}")
                    result = _send_provider()(group_id, msg)
                    logger_obj.info(f"[彩票] 发送结果: {result}")
                except Exception as e:
                    logger_obj.error(f"[彩票] 发送开奖结果到群 {group_id} 失败: {e}")

        return {"status": "success", "winning_numbers": winning_numbers, "total_pool": total_pool}

    except Exception as e:
        _logger_provider().error(f"[彩票] 开奖失败: {e}")
        return {"status": "error", "message": str(e)}


def _resolve_lottery_display_name(user_id, emby_username):
    binding = _get_binding_by_emby_id_provider()(user_id)
    display = ""
    if binding and binding.get("tg_user_id"):
        tg_name = _user_bot_dao_provider().get_bot_user_name(binding["tg_user_id"])
        if tg_name:
            display = f"<a href='tg://user?id={binding['tg_user_id']}'>{tg_name}</a>"
    if not display:
        display = emby_username or f"用户{user_id}"
    return display
