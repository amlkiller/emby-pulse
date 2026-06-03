import datetime
import logging

from app.domains.points import point_dao


logger = logging.getLogger("uvicorn")

_point_dao_provider = lambda: point_dao
_datetime_provider = lambda: datetime
_tg_api_provider = lambda: (lambda method, data=None: None)
_do_lottery_draw_provider = lambda: (lambda: None)
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    point_dao_provider=None,
    datetime_provider=None,
    tg_api_provider=None,
    do_lottery_draw_provider=None,
    logger_provider=None,
):
    global _point_dao_provider
    global _datetime_provider
    global _tg_api_provider
    global _do_lottery_draw_provider
    global _logger_provider

    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if do_lottery_draw_provider is not None:
        _do_lottery_draw_provider = do_lottery_draw_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def run_scheduler_loop(running_provider, stop_event):
    """Run user bot scheduled jobs until the owning bot is stopped."""
    if stop_event.wait(30):
        return

    while running_provider() and not stop_event.is_set():
        try:
            _run_lottery_draw_if_due()
            _expire_pending_pk_invitations()

            if stop_event.wait(60):
                return

        except Exception as e:
            _logger_provider().error(f"[UserBot] 定时任务异常: {e}")
            if stop_event.wait(60):
                return


def _run_lottery_draw_if_due():
    config = _point_dao_provider().get_point_config()

    if int(config.get("enable_lottery", 0)) != 1:
        return

    draw_hour = int(config.get("lottery_draw_hour", 20))
    datetime_module = _datetime_provider()
    now = datetime_module.datetime.now()

    if now.hour != draw_hour or now.minute >= 5:
        return

    today = now.strftime("%Y-%m-%d")
    result = _point_dao_provider().get_lottery_winning_numbers(today)

    if not result or not result["winning_numbers"]:
        _logger_provider().info(f"[彩票] 到达开奖时间 {draw_hour}:00，执行自动开奖...")
        _do_lottery_draw_provider()()


def _expire_pending_pk_invitations():
    try:
        expired_invites = _point_dao_provider().list_expired_pending_pk_invites_with_messages()

        for invite in expired_invites:
            invite_id = invite["id"]
            chat_id = invite["chat_id"]
            msg_id = invite["message_id"]
            challenger_name = invite["challenger_tg_name"] or "用户"
            target_name = invite["target_tg_name"] or "用户"

            try:
                _tg_api_provider()(
                    "editMessageText",
                    {
                        "chat_id": chat_id,
                        "message_id": msg_id,
                        "text": f"⏰ <b>PK邀请已过期</b>\n\n{challenger_name} 向 {target_name} 发起的PK邀请已过期",
                        "parse_mode": "HTML",
                    },
                )
            except:
                pass

            _point_dao_provider().mark_pk_invitation_expired(invite_id)

        if expired_invites:
            _logger_provider().info(f"[PK] 已处理 {len(expired_invites)} 个过期邀请")
    except Exception as e:
        _logger_provider().error(f"[PK] 处理过期邀请失败: {e}")
