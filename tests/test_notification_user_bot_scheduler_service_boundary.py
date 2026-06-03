import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeDateTime:
    class datetime:
        @classmethod
        def now(cls):
            return real_datetime.datetime(2026, 6, 3, 20, 3, 0)


class FakeStopEvent:
    def __init__(self):
        self.waits = []
        self.stopped = False

    def wait(self, seconds):
        self.waits.append(seconds)
        if seconds == 60:
            self.stopped = True
            return True
        return False

    def is_set(self):
        return self.stopped


class FakePointDao:
    def __init__(self):
        self.config = {"enable_lottery": 1, "lottery_draw_hour": 20}
        self.winning_numbers = None
        self.expired_invites = [
            {
                "id": "pk-1",
                "chat_id": 10,
                "message_id": 55,
                "challenger_tg_name": "AliceTG",
                "target_tg_name": "BobTG",
            }
        ]
        self.marked_expired = []

    def get_point_config(self):
        return self.config

    def get_lottery_winning_numbers(self, today):
        assert today == "2026-06-03"
        return self.winning_numbers

    def list_expired_pending_pk_invites_with_messages(self):
        return self.expired_invites

    def mark_pk_invitation_expired(self, invite_id):
        self.marked_expired.append(invite_id)


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


def test_scheduler_loop_preserves_lottery_draw_and_pk_expiry_via_legacy_providers(monkeypatch):
    from app.bot.user_bot import user_bot_scheduler_service
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    stop_event = FakeStopEvent()
    point_dao = FakePointDao()
    logger = FakeLogger()
    tg_calls = []
    draw_calls = []

    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "datetime", FakeDateTime)
    monkeypatch.setattr(user_bot_service, "_tg_api", lambda method, data=None: tg_calls.append((method, data)))
    monkeypatch.setattr(user_bot_service, "do_lottery_draw", lambda: draw_calls.append("draw"))
    monkeypatch.setattr(user_bot_service, "logger", logger)

    user_bot_scheduler_service.run_scheduler_loop(lambda: True, stop_event)

    assert stop_event.waits == [30, 60]
    assert draw_calls == ["draw"]
    assert point_dao.marked_expired == ["pk-1"]
    assert tg_calls == [
        (
            "editMessageText",
            {
                "chat_id": 10,
                "message_id": 55,
                "text": "⏰ <b>PK邀请已过期</b>\n\nAliceTG 向 BobTG 发起的PK邀请已过期",
                "parse_mode": "HTML",
            },
        )
    ]
    assert logger.infos == [
        "[彩票] 到达开奖时间 20:00，执行自动开奖...",
        "[PK] 已处理 1 个过期邀请",
    ]
    assert logger.errors == []
