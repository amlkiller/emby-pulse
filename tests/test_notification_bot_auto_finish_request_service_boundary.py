import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeMediaRequestDao:
    def __init__(self):
        self.finish_result = ([], [])
        self.finish_calls = []
        self.bindings = {}
        self.binding_calls = []
        self.finish_error = None
        self.binding_error = None

    def finish_media_requests_for_item(self, tmdb_id, season=None):
        self.finish_calls.append((tmdb_id, season))
        if self.finish_error:
            raise self.finish_error
        return self.finish_result

    def list_tg_bindings(self, user_ids):
        self.binding_calls.append(user_ids)
        if self.binding_error:
            raise self.binding_error
        return self.bindings


def _make_daemon():
    from app.bot.notification_bot import bot_service

    return bot_service.SystemDaemon()


def _patch_dependencies(monkeypatch, *, rule=None):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    media_request_dao = FakeMediaRequestDao()

    monkeypatch.setattr(bot_service, "logger", logger)
    monkeypatch.setattr(bot_service, "media_request_dao", media_request_dao)
    monkeypatch.setattr(bot_service, "get_notify_rule", lambda rule_type: rule)

    return logger, media_request_dao


def _patch_sender(monkeypatch, calls, error=None):
    from app.bot.notification_bot import notification_bot_auto_finish_request_service

    def fake_send(chat_id, message):
        calls.append((chat_id, message))
        if error:
            raise error

    notification_bot_auto_finish_request_service.set_dependency_providers(
        user_bot_send_provider=lambda: (lambda: fake_send),
    )


def test_auto_finish_empty_tmdb_id_skips_side_effects(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon._auto_finish_request("", season=2)

    assert media_request_dao.finish_calls == []
    assert logger.infos == []
    assert logger.errors == []


def test_auto_finish_converts_tmdb_and_notifies_only_when_both_lists_exist(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()
    notifications = []
    daemon._notify_request_status_change = lambda *args: notifications.append(args)

    media_request_dao.finish_result = ([{"title": "Show"}], [])
    daemon._auto_finish_request("123", season=2)

    media_request_dao.finish_result = ([{"title": "Show"}], [{"user_id": "u1"}])
    daemon._auto_finish_request("456", season=None)

    assert media_request_dao.finish_calls == [(123, 2), (456, None)]
    assert notifications == [(456, [{"title": "Show"}], [{"user_id": "u1"}], "finish")]
    assert logger.errors == []


def test_auto_finish_logs_invalid_tmdb_or_dao_failure(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon._auto_finish_request("bad")

    assert media_request_dao.finish_calls == []
    assert logger.errors == ["[自动入库] 更新工单状态失败: invalid literal for int() with base 10: 'bad'"]

    logger.errors.clear()
    media_request_dao.finish_error = RuntimeError("dao down")
    daemon._auto_finish_request("123")

    assert media_request_dao.finish_calls == [(123, None)]
    assert logger.errors == ["[自动入库] 更新工单状态失败: dao down"]


def test_status_change_disabled_rule_skips_binding_lookup_and_sends(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch, rule={"enabled": False, "channels": ["tg_bot"]})
    sent = []
    _patch_sender(monkeypatch, sent)
    daemon = _make_daemon()

    daemon._notify_request_status_change(1, [{"title": "Film", "year": 2026, "media_type": "movie", "season": None}], [{"user_id": "u1"}], "finish")

    assert media_request_dao.binding_calls == []
    assert sent == []
    assert logger.infos == ["[状态变更通知] 规则未启用或渠道不含tg_bot"]
    assert logger.errors == []


def test_status_change_sends_to_bound_users_with_existing_message_format(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch, rule={"enabled": True, "channels": ["tg_bot"]})
    media_request_dao.bindings = {"u1": "1001"}
    sent = []
    _patch_sender(monkeypatch, sent)
    daemon = _make_daemon()

    daemon._notify_request_status_change(
        123,
        [{"title": "Show", "year": 2025, "media_type": "tv", "season": 2}],
        [{"user_id": "u1"}, {"user_id": "u2"}],
        "finish",
    )

    assert media_request_dao.binding_calls == [["u1", "u2"]]
    assert sent == [
        (
            1001,
            "✅ <b>求片状态更新</b>\n\n📺 <b>内容：</b>Show S2 (2025)\n📢 <b>状态：</b>已入库完成，可以观看啦！",
        )
    ]
    assert logger.infos == ["[自动入库通知] 发送给用户: tg_id=1001, title=Show S2"]
    assert logger.errors == []


@pytest.mark.parametrize(
    ("action", "reject_reason", "expected"),
    [
        ("approve", None, "🚀 <b>求片状态更新</b>\n\n📺 <b>内容：</b>Film ()\n📢 <b>状态：</b>审批通过，正在下载中"),
        ("reject", "资源不可用", "❌ <b>求片状态更新</b>\n\n📺 <b>内容：</b>Film ()\n📢 <b>状态：</b>已拒绝\n📝 原因: 资源不可用"),
        ("manual", None, "✋ <b>求片状态更新</b>\n\n📺 <b>内容：</b>Film ()\n📢 <b>状态：</b>已手动接单，正在处理中"),
        ("hdhive_done", None, "📥 <b>求片状态更新</b>\n\n📺 <b>内容：</b>Film ()\n📢 <b>状态：</b>影巢转存成功，等待入库"),
        ("other", None, "📢 <b>求片状态更新</b>\n\n📺 <b>内容：</b>Film ()\n📢 <b>状态：</b>状态已更新"),
    ],
)
def test_status_change_preserves_action_text_branches(monkeypatch, action, reject_reason, expected):
    _logger, media_request_dao = _patch_dependencies(monkeypatch, rule={"enabled": True, "channels": ["tg_bot"]})
    media_request_dao.bindings = {"u1": "1001"}
    sent = []
    _patch_sender(monkeypatch, sent)
    daemon = _make_daemon()

    daemon._notify_request_status_change(
        123,
        [{"title": "Film", "year": None, "media_type": "movie", "season": None}],
        [{"user_id": "u1"}],
        action,
        reject_reason,
    )

    assert sent == [(1001, expected)]


def test_status_change_logs_send_failures_and_continues(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch, rule={"enabled": True, "channels": ["tg_bot"]})
    media_request_dao.bindings = {"u1": "1001", "u2": "1002"}
    sent = []
    _patch_sender(monkeypatch, sent, error=RuntimeError("send failed"))
    daemon = _make_daemon()

    daemon._notify_request_status_change(
        123,
        [{"title": "Film", "year": 2026, "media_type": "movie", "season": None}],
        [{"user_id": "u1"}, {"user_id": "u2"}],
        "finish",
    )

    assert len(sent) == 2
    assert logger.errors == ["[自动入库通知] 发送失败: send failed", "[自动入库通知] 发送失败: send failed"]


def test_status_change_outer_errors_are_logged_and_swallowed(monkeypatch):
    logger, media_request_dao = _patch_dependencies(monkeypatch, rule={"enabled": True, "channels": ["tg_bot"]})
    media_request_dao.binding_error = RuntimeError("binding down")
    sent = []
    _patch_sender(monkeypatch, sent)
    daemon = _make_daemon()

    daemon._notify_request_status_change(
        123,
        [{"title": "Film", "year": 2026, "media_type": "movie", "season": None}],
        [{"user_id": "u1"}],
        "finish",
    )

    assert sent == []
    assert logger.errors == ["[状态变更通知] 通知失败: binding down"]
