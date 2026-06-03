import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaRequestDao:
    def __init__(self):
        self.updates = []

    def update_feedback_status(self, feed_id, status):
        self.updates.append((feed_id, status))


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, **kwargs):
        self.calls.append((token, method, kwargs))
        if self.error:
            raise self.error


def _patch_dependencies(monkeypatch, *, telegram_error=None):
    from app.domains.notifications import bot_service

    dao = FakeMediaRequestDao()
    telegram = FakeTelegramClient(error=telegram_error)
    monkeypatch.setattr(bot_service, "media_request_dao", dao)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    return dao, telegram


def test_feedback_callback_text_message_updates_status_and_edits_text(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram = _patch_dependencies(monkeypatch)
    cq = {"message": {"text": "资源报错工单", "message_id": 7}, "from": {"first_name": "Alice"}}

    handled = bot_service.notification_bot_feedback_callback_service.handle_feedback_callback(
        "feed_fix_42",
        cq,
        "chat-1",
        7,
        "token",
        {"proxy": "ok"},
    )

    assert handled is True
    assert dao.updates == [(42, 1)]
    assert telegram.calls == [
        (
            "token",
            "editMessageText",
            {
                "json": {
                    "chat_id": "chat-1",
                    "message_id": 7,
                    "text": "资源报错工单\n\n━━━━━━━━━━━━━━\n🛠️ 已标记：修复中\n(操作人: Alice)",
                    "reply_markup": {"inline_keyboard": []},
                },
                "proxies": {"proxy": "ok"},
                "timeout": 5,
            },
        )
    ]


def test_feedback_callback_caption_message_updates_status_and_edits_caption(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram = _patch_dependencies(monkeypatch)
    cq = {"message": {"caption": "带图报错", "message_id": 8}, "from": {"first_name": "Bob"}}

    handled = bot_service.notification_bot_feedback_callback_service.handle_feedback_callback(
        "feed_done_43",
        cq,
        "chat-2",
        8,
        "token",
        None,
    )

    assert handled is True
    assert dao.updates == [(43, 2)]
    assert telegram.calls == [
        (
            "token",
            "editMessageCaption",
            {
                "json": {
                    "chat_id": "chat-2",
                    "message_id": 8,
                    "caption": "带图报错\n\n━━━━━━━━━━━━━━\n✅ 已标记：修复完成\n(操作人: Bob)",
                    "reply_markup": {"inline_keyboard": []},
                },
                "proxies": None,
                "timeout": 5,
            },
        )
    ]


def test_feedback_callback_reject_uses_default_text_and_admin_operator(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram = _patch_dependencies(monkeypatch)
    cq = {"message": {"message_id": 9}, "from": {}}

    handled = bot_service.notification_bot_feedback_callback_service.handle_feedback_callback(
        "feed_reject_44",
        cq,
        "chat-3",
        9,
        "token",
        {},
    )

    assert handled is True
    assert dao.updates == [(44, 3)]
    assert telegram.calls[0][2]["json"]["text"] == "资源报错工单\n\n━━━━━━━━━━━━━━\n❌ 已标记：暂不处理(忽略)\n(操作人: Admin)"


def test_feedback_callback_unknown_action_is_handled_without_side_effects(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_feedback_callback_service.handle_feedback_callback(
        "feed_noop_45",
        {"message": {"text": "资源报错工单"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is True
    assert dao.updates == []
    assert telegram.calls == []


def test_feedback_callback_non_feed_data_is_not_handled(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_feedback_callback_service.handle_feedback_callback(
        "req_approve_1",
        {"message": {"text": "求片"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is False
    assert dao.updates == []
    assert telegram.calls == []


def test_feedback_callback_swallows_telegram_edit_failures_after_status_update(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram = _patch_dependencies(monkeypatch, telegram_error=RuntimeError("telegram down"))

    handled = bot_service.notification_bot_feedback_callback_service.handle_feedback_callback(
        "feed_fix_46",
        {"message": {"text": "资源报错工单"}, "from": {"first_name": "Admin"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is True
    assert dao.updates == [(46, 1)]
    assert len(telegram.calls) == 1
