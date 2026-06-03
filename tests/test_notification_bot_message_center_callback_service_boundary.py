import sys
import types
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.domains.notifications import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeMessageDao:
    def __init__(self):
        self.remark_rows = {}
        self.conversation = None
        self.added_blocks = []
        self.removed_blocks = []
        self.created_conversations = []
        self.inserted_admin_messages = []

    def get_local_user_remark_by_emby_id(self, user_id):
        return self.remark_rows.get(user_id)

    def add_notify_block(self, user_id):
        self.added_blocks.append(user_id)

    def remove_notify_block(self, user_id):
        self.removed_blocks.append(user_id)

    def get_conversation_by_user(self, user_id):
        return self.conversation

    def create_conversation(self, user_id, username):
        self.created_conversations.append((user_id, username))
        return 42

    def insert_admin_message(self, conv_id, sender_type, sender_name, content, preview):
        self.inserted_admin_messages.append((conv_id, sender_type, sender_name, content, preview))


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, json=None, proxies=None, timeout=None):
        self.calls.append((token, method, json, proxies, timeout))
        if self.error:
            raise self.error
        return FakeResponse()


class FakeMediaApi:
    def __init__(self):
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return FakeResponse(payload={"Name": "Bob"})


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _patch_legacy_dependencies(monkeypatch, *, telegram_error=None):
    dao = FakeMessageDao()
    telegram = FakeTelegramClient(error=telegram_error)
    media = FakeMediaApi()
    logger = FakeLogger()

    monkeypatch.setattr(bot_service, "message_dao", dao)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "logger", logger)

    return dao, telegram, media, logger


def test_reply_callback_uses_legacy_dependencies_and_enters_reply_mode(monkeypatch):
    dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch)
    dao.remark_rows["u1"] = {"remark": "Alice"}
    bot = bot_service.NotificationBot()

    bot._handle_msg_reply_callback("chat-1", 100, "u1", "token-1", {"https": "proxy"})

    assert bot._msg_reply_mode == {"chat-1": "u1"}
    assert telegram.calls == [
        (
            "token-1",
            "editMessageText",
            {
                "chat_id": "chat-1",
                "message_id": 100,
                "text": (
                    "💬 <b>回复模式</b>\n\n"
                    "👤 目标用户：Alice\n"
                    "🆔 用户ID：<code>u1</code>\n\n"
                    "📝 请直接发送消息内容，将转发给该用户\n"
                    "⚠️ 发送任意消息即可回复，或点击下方取消"
                ),
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": [[{"text": "❌ 取消回复", "callback_data": "msg_cancel:u1"}]]},
            },
            {"https": "proxy"},
            5,
        )
    ]
    assert logger.errors == []


def test_block_callback_adds_notify_block_and_replaces_keyboard(monkeypatch):
    dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch)
    bot = bot_service.NotificationBot()
    cq = {"from": {"first_name": "Root"}, "message": {"text": "Original message"}}

    bot._handle_msg_block_callback("chat-1", 101, "u2", "token-2", None, cq)

    assert dao.added_blocks == ["u2"]
    assert telegram.calls == [
        (
            "token-2",
            "editMessageText",
            {
                "chat_id": "chat-1",
                "message_id": 101,
                "text": "Original message\n\n━━━━━━━━━━━━━━\n🔇 已屏蔽该用户的消息通知\n(操作人: Root)",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": [[{"text": "🔊 取消屏蔽", "callback_data": "msg_unblock:u2"}]]},
            },
            None,
            5,
        )
    ]
    assert logger.errors == []


def test_unblock_callback_removes_notify_block_strips_old_status_and_restores_keyboard(monkeypatch):
    dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch)
    bot = bot_service.NotificationBot()
    cq = {
        "from": {"first_name": "Root"},
        "message": {"text": "Original message\n\n━━━━━━━━━━━━━━\n🔇 已屏蔽该用户的消息通知\n(操作人: Root)"},
    }

    bot._handle_msg_unblock_callback("chat-1", 102, "u3", "token-3", {"https": "proxy"}, cq)

    assert dao.removed_blocks == ["u3"]
    assert telegram.calls == [
        (
            "token-3",
            "editMessageText",
            {
                "chat_id": "chat-1",
                "message_id": 102,
                "text": "Original message\n\n━━━━━━━━━━━━━━\n🔊 已取消屏蔽，将恢复消息通知\n(操作人: Root)",
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "💬 回复消息", "callback_data": "msg_reply:u3"}],
                        [{"text": "🚫 屏蔽通知", "callback_data": "msg_block:u3"}],
                    ]
                },
            },
            {"https": "proxy"},
            5,
        )
    ]
    assert logger.errors == []


def test_reply_message_pops_mode_creates_conversation_and_sends_confirmation(monkeypatch):
    dao, _telegram, media, logger = _patch_legacy_dependencies(monkeypatch)
    forwarded = []
    monkeypatch.setitem(
        sys.modules,
        "app.domains.notifications.messages",
        types.SimpleNamespace(_send_bot_reply_to_user=lambda user_id, content, admin_name: forwarded.append((user_id, content, admin_name))),
    )

    bot = bot_service.NotificationBot()
    sent_messages = []
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent_messages.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )

    assert bot._handle_msg_reply_message("not in reply mode", "chat-1") is False

    bot._msg_reply_mode["chat-1"] = "u4"
    assert bot._handle_msg_reply_message("hello user", "chat-1") is True

    assert bot._msg_reply_mode == {}
    assert media.calls == ["/Users/u4"]
    assert dao.created_conversations == [("u4", "Bob")]
    assert dao.inserted_admin_messages == [(42, "bot", "管理员", "hello user", "hello user")]
    assert forwarded == [("u4", "hello user", "管理员")]
    assert sent_messages == [("chat-1", "✅ 消息已发送给用户 u4", "HTML", None, "tg")]
    assert logger.errors == []


def test_message_center_dispatcher_routes_reply_block_and_unblock(monkeypatch):
    dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch)
    dao.remark_rows["u1"] = {"remark": "Alice"}
    bot = bot_service.NotificationBot()

    assert bot_service.notification_bot_message_center_callback_service.handle_message_center_callback(
        bot,
        "msg_reply:u1",
        "chat-1",
        100,
        "token-1",
        {"https": "proxy"},
        {"message": {"text": "ignored"}},
    ) is True
    assert bot._msg_reply_mode == {"chat-1": "u1"}

    assert bot_service.notification_bot_message_center_callback_service.handle_message_center_callback(
        bot,
        "msg_block:u2",
        "chat-1",
        101,
        "token-2",
        None,
        {"from": {"first_name": "Root"}, "message": {"text": "Original message"}},
    ) is True

    assert bot_service.notification_bot_message_center_callback_service.handle_message_center_callback(
        bot,
        "msg_unblock:u2",
        "chat-1",
        102,
        "token-3",
        None,
        {"from": {"first_name": "Root"}, "message": {"text": "Original message\n\n━━━━━━━━━━━━━━\nold status"}},
    ) is True

    assert dao.added_blocks == ["u2"]
    assert dao.removed_blocks == ["u2"]
    assert [call[1] for call in telegram.calls] == ["editMessageText", "editMessageText", "editMessageText"]
    assert telegram.calls[0][2]["reply_markup"] == {"inline_keyboard": [[{"text": "❌ 取消回复", "callback_data": "msg_cancel:u1"}]]}
    assert telegram.calls[1][2]["reply_markup"] == {"inline_keyboard": [[{"text": "🔊 取消屏蔽", "callback_data": "msg_unblock:u2"}]]}
    assert telegram.calls[2][2]["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "💬 回复消息", "callback_data": "msg_reply:u2"}],
            [{"text": "🚫 屏蔽通知", "callback_data": "msg_block:u2"}],
        ]
    }
    assert logger.errors == []


def test_message_center_dispatcher_cancel_discards_mode_and_edits_message(monkeypatch):
    _dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch)
    bot = bot_service.NotificationBot()
    bot._msg_reply_mode["chat-1"] = "u1"

    handled = bot_service.notification_bot_message_center_callback_service.handle_message_center_callback(
        bot,
        "msg_cancel:u1",
        "chat-1",
        103,
        "token-4",
        {"https": "proxy"},
        {"message": {"text": "ignored"}},
    )

    assert handled is True
    assert bot._msg_reply_mode == {}
    assert telegram.calls == [
        (
            "token-4",
            "editMessageText",
            {
                "chat_id": "chat-1",
                "message_id": 103,
                "text": "❌ 已取消回复",
                "reply_markup": {"inline_keyboard": []},
            },
            {"https": "proxy"},
            5,
        )
    ]
    assert logger.errors == []


def test_message_center_dispatcher_non_message_data_is_not_handled(monkeypatch):
    dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch)
    bot = bot_service.NotificationBot()

    handled = bot_service.notification_bot_message_center_callback_service.handle_message_center_callback(
        bot,
        "risk_ban_u1",
        "chat-1",
        100,
        "token",
        None,
        {"message": {"text": "ignored"}},
    )

    assert handled is False
    assert bot._msg_reply_mode == {}
    assert dao.added_blocks == []
    assert dao.removed_blocks == []
    assert telegram.calls == []
    assert logger.errors == []


def test_message_center_cancel_swallows_telegram_edit_failures(monkeypatch):
    _dao, telegram, _media, logger = _patch_legacy_dependencies(monkeypatch, telegram_error=RuntimeError("telegram down"))
    bot = bot_service.NotificationBot()
    bot._msg_reply_mode["chat-1"] = "u1"

    handled = bot_service.notification_bot_message_center_callback_service.handle_message_center_callback(
        bot,
        "msg_cancel:u1",
        "chat-1",
        104,
        "token",
        None,
        {"message": {"text": "ignored"}},
    )

    assert handled is True
    assert bot._msg_reply_mode == {}
    assert len(telegram.calls) == 1
    assert logger.errors == []
