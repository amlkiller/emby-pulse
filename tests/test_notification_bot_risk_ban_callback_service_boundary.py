import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, **kwargs):
        self.calls.append((token, method, kwargs))
        if self.error:
            raise self.error


class FakeBot:
    def __init__(self):
        self.username_calls = []

    def _get_username(self, user_id):
        self.username_calls.append(user_id)
        return f"name-{user_id}"


def _patch_dependencies(monkeypatch, *, ban_result=True, telegram_error=None):
    from app.domains.notifications import bot_service

    ban_calls = []
    log_calls = []
    telegram = FakeTelegramClient(error=telegram_error)

    def ban_user(user_id):
        ban_calls.append(user_id)
        return ban_result

    def log_risk_action(user_id, username, action, reason):
        log_calls.append((user_id, username, action, reason))

    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(
        bot_service.notification_bot_risk_ban_callback_service,
        "_ban_user_provider",
        lambda: ban_user,
    )
    monkeypatch.setattr(
        bot_service.notification_bot_risk_ban_callback_service,
        "_log_risk_action_provider",
        lambda: log_risk_action,
    )
    return ban_calls, log_calls, telegram


def test_risk_ban_callback_success_bans_logs_and_edits_message(monkeypatch):
    from app.domains.notifications import bot_service

    ban_calls, log_calls, telegram = _patch_dependencies(monkeypatch, ban_result=True)
    bot = FakeBot()
    cq = {"message": {"text": "风控警报", "message_id": 7}, "from": {"first_name": "Alice"}}

    handled = bot_service.notification_bot_risk_ban_callback_service.handle_risk_ban_callback(
        bot,
        "risk_ban_u1",
        cq,
        "chat-1",
        7,
        "token",
        {"proxy": "ok"},
    )

    assert handled is True
    assert bot.username_calls == ["u1"]
    assert ban_calls == ["u1"]
    assert log_calls == [("u1", "name-u1", "ban", "机器快捷执法 (操作人: Alice)")]
    assert telegram.calls == [
        (
            "token",
            "editMessageText",
            {
                "json": {
                    "chat_id": "chat-1",
                    "message_id": 7,
                    "text": "风控警报\n\n━━━━━━━━━━━━━━\n✅ 已成功封禁该违规账号！\n(执行人: Alice)",
                    "reply_markup": {"inline_keyboard": []},
                },
                "proxies": {"proxy": "ok"},
                "timeout": 5,
            },
        )
    ]


def test_risk_ban_callback_failure_edits_failure_without_log(monkeypatch):
    from app.domains.notifications import bot_service

    ban_calls, log_calls, telegram = _patch_dependencies(monkeypatch, ban_result=False)
    bot = FakeBot()
    cq = {"message": {"text": "Risk alert", "message_id": 8}, "from": {"first_name": "Bob"}}

    handled = bot_service.notification_bot_risk_ban_callback_service.handle_risk_ban_callback(
        bot,
        "risk_ban_u2",
        cq,
        "chat-2",
        8,
        "token",
        None,
    )

    assert handled is True
    assert bot.username_calls == ["u2"]
    assert ban_calls == ["u2"]
    assert log_calls == []
    assert telegram.calls[0][2]["json"]["text"] == "Risk alert\n\n━━━━━━━━━━━━━━\n❌ 封禁失败，可能 API 权限不足。"


def test_risk_ban_callback_uses_default_operator_and_message_text(monkeypatch):
    from app.domains.notifications import bot_service

    _ban_calls, log_calls, telegram = _patch_dependencies(monkeypatch, ban_result=True)
    bot = FakeBot()
    cq = {"message": {"message_id": 9}, "from": {}}

    handled = bot_service.notification_bot_risk_ban_callback_service.handle_risk_ban_callback(
        bot,
        "risk_ban_u3",
        cq,
        "chat-3",
        9,
        "token",
        {},
    )

    assert handled is True
    assert log_calls == [("u3", "name-u3", "ban", "机器快捷执法 (操作人: Admin)")]
    assert telegram.calls[0][2]["json"]["text"] == "风控警报\n\n━━━━━━━━━━━━━━\n✅ 已成功封禁该违规账号！\n(执行人: Admin)"


def test_risk_ban_callback_non_risk_data_is_not_handled(monkeypatch):
    from app.domains.notifications import bot_service

    ban_calls, log_calls, telegram = _patch_dependencies(monkeypatch)
    bot = FakeBot()

    handled = bot_service.notification_bot_risk_ban_callback_service.handle_risk_ban_callback(
        bot,
        "feed_fix_1",
        {"message": {"text": "资源报错工单"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is False
    assert bot.username_calls == []
    assert ban_calls == []
    assert log_calls == []
    assert telegram.calls == []


def test_risk_ban_callback_swallows_telegram_edit_failures_after_ban(monkeypatch):
    from app.domains.notifications import bot_service

    ban_calls, log_calls, telegram = _patch_dependencies(monkeypatch, ban_result=True, telegram_error=RuntimeError("telegram down"))
    bot = FakeBot()

    handled = bot_service.notification_bot_risk_ban_callback_service.handle_risk_ban_callback(
        bot,
        "risk_ban_u4",
        {"message": {"text": "风控警报"}, "from": {"first_name": "Root"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is True
    assert ban_calls == ["u4"]
    assert log_calls == [("u4", "name-u4", "ban", "机器快捷执法 (操作人: Root)")]
    assert len(telegram.calls) == 1
