import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeBotServiceDao:
    def __init__(self):
        self.ensure_calls = 0
        self.saved = []
        self.rows = []
        self.deleted = []

    def ensure_request_admin_messages_table(self):
        self.ensure_calls += 1

    def save_request_admin_message(self, tmdb_id, chat_id, message_id, is_caption, original_text):
        self.saved.append((tmdb_id, chat_id, message_id, is_caption, original_text))

    def list_request_admin_messages(self, tmdb_id):
        return self.rows

    def delete_request_admin_messages(self, tmdb_id):
        self.deleted.append(tmdb_id)


class FakeTelegramClient:
    def __init__(self):
        self.calls = []

    def post_api(self, token, method, json=None, proxies=None, timeout=None):
        self.calls.append((token, method, json, proxies, timeout))
        return {"ok": True}


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


def _reset_request_admin_sync_state(monkeypatch):
    from app.domains.notifications import bot_service
    from app.domains.notifications import notification_bot_request_admin_message_sync_service

    dao = FakeBotServiceDao()
    telegram = FakeTelegramClient()
    logger = FakeLogger()

    monkeypatch.setattr(bot_service, "bot_service_dao", dao)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "logger", logger)

    monkeypatch.setattr(
        notification_bot_request_admin_message_sync_service,
        "_bot_service_dao_provider",
        lambda: bot_service.bot_service_dao,
    )
    monkeypatch.setattr(
        notification_bot_request_admin_message_sync_service,
        "_telegram_client_provider",
        lambda: bot_service.telegram_client,
    )
    monkeypatch.setattr(
        notification_bot_request_admin_message_sync_service,
        "_logger_provider",
        lambda: bot_service.logger,
    )

    return bot_service, dao, telegram, logger


def test_request_admin_message_sync_extracts_tmdb_id_from_legacy_wrappers(monkeypatch):
    bot_service, _dao, _telegram, _logger = _reset_request_admin_sync_state(monkeypatch)

    assert bot_service._extract_request_tmdb_id(None) is None
    assert bot_service._extract_request_tmdb_id({"inline_keyboard": [[{"callback_data": "noop_123"}]]}) is None
    assert bot_service._extract_request_tmdb_id({"inline_keyboard": [[{"callback_data": "req_approve_123"}]]}) == 123
    assert bot_service._extract_request_tmdb_id({"inline_keyboard": [[{"callback_data": "req_manual_456"}]]}) == 456
    assert bot_service._extract_request_tmdb_id({"inline_keyboard": [[{"callback_data": "req_reject_menu_789"}]]}) == 789


def test_request_admin_message_sync_records_valid_message_and_skips_incomplete_ones(monkeypatch):
    bot_service, dao, _telegram, logger = _reset_request_admin_sync_state(monkeypatch)

    bot_service._record_request_admin_message(None, "chat-1", 10, True, "caption")
    bot_service._record_request_admin_message(123, "", 10, True, "caption")
    bot_service._record_request_admin_message(123, "chat-1", None, True, "caption")
    bot_service._record_request_admin_message(123, "chat-1", 10, True, "caption")

    assert dao.ensure_calls == 1
    assert dao.saved == [(123, "chat-1", 10, True, "caption")]
    assert logger.errors == []


def test_request_admin_message_sync_updates_unique_copies_and_deletes_rows(monkeypatch):
    bot_service, dao, telegram, logger = _reset_request_admin_sync_state(monkeypatch)
    dao.rows = [
        {"chat_id": "chat-1", "message_id": 10, "is_caption": True, "original_text": ""},
        {"chat_id": "chat-1", "message_id": 10, "is_caption": True, "original_text": "duplicate"},
        {"chat_id": "chat-2", "message_id": 20, "is_caption": False, "original_text": "Original text"},
    ]

    bot_service._sync_request_admin_messages(
        123,
        "✅ 已审批",
        "Admin",
        "token-1",
        {"https": "proxy"},
        fallback_text="Fallback request",
        fallback_is_caption=True,
    )

    assert dao.ensure_calls == 1
    assert len(telegram.calls) == 2
    assert telegram.calls[0] == (
        "token-1",
        "editMessageCaption",
        {
            "chat_id": "chat-1",
            "message_id": 10,
            "caption": "Fallback request\n\n━━━━━━━━━━━━━━\n✅ 已审批\n(操作人: Admin)",
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": []},
        },
        {"https": "proxy"},
        5,
    )
    assert telegram.calls[1] == (
        "token-1",
        "editMessageText",
        {
            "chat_id": "chat-2",
            "message_id": 20,
            "text": "Original text\n\n━━━━━━━━━━━━━━\n✅ 已审批\n(操作人: Admin)",
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": []},
        },
        {"https": "proxy"},
        5,
    )
    assert dao.deleted == [123]
    assert logger.infos == []
    assert logger.errors == []


def test_request_admin_message_sync_logs_no_rows_with_fallback(monkeypatch):
    bot_service, dao, telegram, logger = _reset_request_admin_sync_state(monkeypatch)

    bot_service._sync_request_admin_messages(456, "❌ 已拒绝", "Admin", "token-1", None, fallback_text="Fallback request")

    assert dao.ensure_calls == 1
    assert telegram.calls == []
    assert dao.deleted == []
    assert logger.infos == ["[求片审核同步] 未找到已记录副本 tmdb_id=456"]
    assert logger.errors == []
