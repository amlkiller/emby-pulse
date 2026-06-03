import datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeUserBotDao:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.searches = []

    def search_whois_bindings(self, keyword):
        self.searches.append(keyword)
        if self.error:
            raise self.error
        return self.rows


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _patch_whois_dependencies(monkeypatch, rows=None, error=None):
    dao = FakeUserBotDao(rows=rows, error=error)
    logger = FakeLogger()

    monkeypatch.setattr(bot_service, "user_bot_dao", dao)
    monkeypatch.setattr(bot_service, "logger", logger)

    return dao, logger


def _capture_bot_messages():
    bot = bot_service.NotificationBot()
    sent = []
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    return bot, sent


def test_whois_rejects_missing_or_empty_keyword_without_search(monkeypatch):
    dao, logger = _patch_whois_dependencies(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._cmd_whois("chat-1", "/whois", "tg")
    bot._cmd_whois("chat-1", "/whois @   ", "tg")

    assert dao.searches == []
    assert sent == [
        ("chat-1", "👤 请使用: /whois TG用户名/TG ID/Emby用户名", "HTML", None, "tg"),
        ("chat-1", "👤 请使用: /whois TG用户名/TG ID/Emby用户名", "HTML", None, "tg"),
    ]
    assert logger.errors == []


def test_whois_no_match_uses_normalized_search_and_legacy_escape(monkeypatch):
    dao, logger = _patch_whois_dependencies(monkeypatch, rows=[])
    monkeypatch.setattr(bot_service, "escape_html", lambda value: f"ESC[{value}]")
    bot, sent = _capture_bot_messages()

    bot._cmd_whois("chat-1", "/whois @<alice>", "tg")

    assert dao.searches == ["<alice>"]
    assert sent == [("chat-1", "📭 未找到与 <b>ESC[@<alice>]</b> 相关的绑定信息", "HTML", None, "tg")]
    assert logger.errors == []


def test_whois_single_result_formats_binding_and_escape_fields(monkeypatch):
    rows = [
        {
            "emby_username": "Alice <Admin>",
            "emby_user_id": "u1",
            "expire_date": "bad-date",
            "tg_user_id": "100",
            "tg_username": "alice",
            "tg_display_name": "Alice & Bob",
            "bound_at": "2026-01-02",
        }
    ]
    dao, logger = _patch_whois_dependencies(monkeypatch, rows=rows)
    bot, sent = _capture_bot_messages()

    bot._cmd_whois("chat-1", "/whois alice", "tg")

    assert dao.searches == ["alice"]
    assert sent == [
        (
            "chat-1",
            (
                "<b>绑定信息</b>\n"
                "👤 <b>Emby 用户：</b>Alice &lt;Admin&gt;\n"
                "🆔 <b>Emby ID：</b><code>u1</code>\n"
                "📅 <b>到期时间：</b>bad-date\n"
                "✈️ <b>TG ID：</b><code>100</code>\n"
                "🔗 <b>TG 用户名：</b>@alice\n"
                "🏷️ <b>TG 名称：</b>Alice &amp; Bob\n"
                "⏱️ <b>绑定时间：</b>2026-01-02"
            ),
            "HTML",
            None,
            "tg",
        )
    ]
    assert logger.errors == []


def test_whois_multiple_results_formats_numbered_rows(monkeypatch):
    rows = [
        {"emby_username": "Alice", "emby_user_id": "u1", "tg_user_id": "100", "tg_username": "@alice"},
        {"emby_username": "Bob", "emby_user_id": "u2", "tg_user_id": "200", "tg_username": "bob"},
    ]
    dao, logger = _patch_whois_dependencies(monkeypatch, rows=rows)
    bot, sent = _capture_bot_messages()

    bot._cmd_whois("chat-1", "/whois user", "wecom")

    assert dao.searches == ["user"]
    assert len(sent) == 1
    chat_id, message, parse_mode, reply_markup, platform = sent[0]
    assert chat_id == "chat-1"
    assert message.startswith("🔎 <b>找到 2 条匹配结果</b>\n\n<b>匹配 1</b>")
    assert "\n\n<b>匹配 2</b>" in message
    assert "👤 <b>Emby 用户：</b>Alice" in message
    assert "🔗 <b>TG 用户名：</b>@bob" in message
    assert parse_mode == "HTML"
    assert reply_markup is None
    assert platform == "wecom"
    assert logger.errors == []


def test_whois_expire_status_wrapper_preserves_date_cases():
    bot = bot_service.NotificationBot()
    today = datetime.date.today()

    assert bot._format_expire_status(None) == "永久有效"
    assert bot._format_expire_status("   ") == "永久有效"
    assert bot._format_expire_status(today.isoformat()) == f"{today.isoformat()}（今天到期）"
    assert bot._format_expire_status((today + datetime.timedelta(days=2)).isoformat()) == (
        f"{(today + datetime.timedelta(days=2)).isoformat()}（2 天后到期）"
    )
    assert bot._format_expire_status((today - datetime.timedelta(days=3)).isoformat()) == (
        f"{(today - datetime.timedelta(days=3)).isoformat()}（已过期 3 天）"
    )
    assert bot._format_expire_status("not-a-date") == "not-a-date"


def test_whois_logs_and_sends_failure_when_search_raises(monkeypatch):
    dao, logger = _patch_whois_dependencies(monkeypatch, error=RuntimeError("dao failed"))
    bot, sent = _capture_bot_messages()

    bot._cmd_whois("chat-1", "/whois alice", "tg")

    assert dao.searches == ["alice"]
    assert sent == [("chat-1", "❌ 查询绑定信息失败", "HTML", None, "tg")]
    assert logger.errors == ["[Bot] whois query error: dao failed"]
