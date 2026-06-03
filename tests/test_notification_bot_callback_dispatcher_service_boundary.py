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


class FakeService:
    def __init__(self, calls, name, handled=False):
        self.calls = calls
        self.name = name
        self.handled = handled

    def handle_plugin_callback(self, data, cid, cq_id, cq):
        self.calls.append((self.name, data, cid, cq_id))
        return self.handled

    def handle_request_hdhive_callback(self, data, cid, cq_id):
        self.calls.append((self.name, "request_hdhive", data, cid, cq_id))
        return self.handled

    def handle_emby_restart_callback(self, bot, data, cid, cq, platform="tg"):
        self.calls.append((self.name, data, cid, platform, bot))
        return self.handled

    def handle_message_center_callback(self, bot, data, cid, mid, token, proxies, cq):
        self.calls.append((self.name, data, cid, mid, token, proxies, bot))
        return self.handled

    def handle_risk_ban_callback(self, bot, data, cq, cid, mid, token, proxies):
        self.calls.append((self.name, data, cid, mid, token, proxies, bot))
        return self.handled

    def handle_feedback_callback(self, data, cq, cid, mid, token, proxies):
        self.calls.append((self.name, data, cid, mid, token, proxies))
        return self.handled

    def handle_request_hdhive_search_callback(self, data, cid, cq_id, mid, token, proxies):
        self.calls.append((self.name, data, cid, cq_id, mid, token, proxies))
        return self.handled

    def handle_request_approval_menu_callback(self, data, cid, mid, token, proxies):
        self.calls.append((self.name, data, cid, mid, token, proxies))
        return self.handled

    def handle_request_approval_action_callback(self, data, cq, cid, mid, token, proxies):
        self.calls.append((self.name, data, cid, mid, token, proxies))
        return self.handled


class FakeBot:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.permission_checks = []

    def _check_admin_permission(self, cid, user_id):
        self.permission_checks.append((cid, user_id))
        return self.allowed


def _callback(data="noop", *, user_id=99):
    return {
        "id": "cq-1",
        "data": data,
        "message": {"chat": {"id": 42}, "message_id": 7},
        "from": {"id": user_id},
    }


def _patch_dispatcher(monkeypatch, *, telegram_error=None, handled_by=None):
    from app.bot.notification_bot import bot_service

    calls = []
    telegram = FakeTelegramClient(error=telegram_error)

    def service(name):
        return FakeService(calls, name, handled=(handled_by == name))

    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {"proxy": "ok"})
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "notification_bot_plugin_callback_service", service("plugin"))
    monkeypatch.setattr(bot_service, "notification_bot_emby_restart_command_service", service("emby"))
    monkeypatch.setattr(bot_service, "notification_bot_message_center_callback_service", service("message"))
    monkeypatch.setattr(bot_service, "notification_bot_risk_ban_callback_service", service("risk"))
    monkeypatch.setattr(bot_service, "notification_bot_feedback_callback_service", service("feedback"))
    monkeypatch.setattr(bot_service, "notification_bot_request_hdhive_search_callback_service", service("request_search"))
    monkeypatch.setattr(bot_service, "notification_bot_request_approval_menu_callback_service", service("request_menu"))
    monkeypatch.setattr(bot_service, "notification_bot_request_approval_action_callback_service", service("request_action"))
    return telegram, calls


def test_callback_dispatcher_rejects_management_callback_without_normal_ack(monkeypatch):
    from app.bot.notification_bot import bot_service

    telegram, calls = _patch_dispatcher(monkeypatch)
    bot = FakeBot(allowed=False)

    bot_service.notification_bot_callback_dispatcher_service.handle_callback(bot, _callback("req_approve_123", user_id=100))

    assert bot.permission_checks == [("42", 100)]
    assert telegram.calls == [
        (
            "token",
            "answerCallbackQuery",
            {
                "json": {"callback_query_id": "cq-1", "text": "⛔ 您没有权限执行此操作", "show_alert": True},
                "proxies": {"proxy": "ok"},
                "timeout": 5,
            },
        )
    ]
    assert calls == []


def test_callback_dispatcher_answers_then_delegates_plugin_callback(monkeypatch):
    from app.bot.notification_bot import bot_service

    telegram, calls = _patch_dispatcher(monkeypatch, handled_by="plugin")
    bot = FakeBot()

    bot_service.notification_bot_callback_dispatcher_service.handle_callback(bot, _callback("p115_tf_1"))

    assert bot.permission_checks == []
    assert telegram.calls == [
        (
            "token",
            "answerCallbackQuery",
            {"json": {"callback_query_id": "cq-1"}, "proxies": {"proxy": "ok"}, "timeout": 5},
        )
    ]
    assert calls == [("plugin", "p115_tf_1", "42", "cq-1")]


def test_callback_dispatcher_swallows_normal_ack_failure_and_continues(monkeypatch):
    from app.bot.notification_bot import bot_service

    telegram, calls = _patch_dispatcher(monkeypatch, telegram_error=RuntimeError("ack down"), handled_by="plugin")
    bot = FakeBot()

    bot_service.notification_bot_callback_dispatcher_service.handle_callback(bot, _callback("p115_tf_2"))

    assert len(telegram.calls) == 1
    assert calls == [("plugin", "p115_tf_2", "42", "cq-1")]


def test_callback_dispatcher_preserves_request_sub_dispatch_order(monkeypatch):
    from app.bot.notification_bot import bot_service

    telegram, calls = _patch_dispatcher(monkeypatch, handled_by="request_action")
    bot = FakeBot()

    bot_service.notification_bot_callback_dispatcher_service.handle_callback(bot, _callback("req_approve_123", user_id=101))

    assert bot.permission_checks == [("42", 101)]
    assert telegram.calls == [
        (
            "token",
            "answerCallbackQuery",
            {"json": {"callback_query_id": "cq-1"}, "proxies": {"proxy": "ok"}, "timeout": 5},
        )
    ]
    assert calls == [
        ("plugin", "req_approve_123", "42", "cq-1"),
        ("plugin", "request_hdhive", "req_approve_123", "42", "cq-1"),
        ("message", "req_approve_123", "42", 7, "token", {"proxy": "ok"}, bot),
        ("risk", "req_approve_123", "42", 7, "token", {"proxy": "ok"}, bot),
        ("feedback", "req_approve_123", "42", 7, "token", {"proxy": "ok"}),
        ("request_search", "req_approve_123", "42", "cq-1", 7, "token", {"proxy": "ok"}),
        ("request_menu", "req_approve_123", "42", 7, "token", {"proxy": "ok"}),
        ("request_action", "req_approve_123", "42", 7, "token", {"proxy": "ok"}),
    ]
