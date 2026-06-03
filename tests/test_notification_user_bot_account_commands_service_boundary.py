import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeUserDao:
    def __init__(self):
        self.meta = {"points": 128, "expire_date": "2099-01-01"}
        self.error = None
        self.calls = []

    def get_user_points_expire(self, user_id):
        self.calls.append(user_id)
        if self.error:
            raise self.error
        return self.meta


class FakeStatsQueries:
    def __init__(self):
        self.last_play = {
            "ItemName": "A Very Long Movie Title For Display",
            "PlayDuration": 3720,
            "DateCreated": "2026-05-01T12:34:56",
        }
        self.error = None
        self.calls = []

    def get_user_last_play(self, user_id):
        self.calls.append(user_id)
        if self.error:
            raise self.error
        return self.last_play


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {
            "Policy": {"IsDisabled": False},
            "DateCreated": "2024-01-02T03:04:05",
        }

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self):
        self.response = FakeResponse()
        self.error = None
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if self.error:
            raise self.error
        return self.response


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))

    def warning(self, message):
        self.calls.append(("warning", message))


def _reset_account_command_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    replies = []
    unbound = []
    user_dao = FakeUserDao()
    stats_queries = FakeStatsQueries()
    media_api = FakeMediaApi()
    logger = FakeLogger()
    binding = {
        "emby_user_id": "user-1234567890",
        "emby_username": "Alice",
        "init_password": "secret-pass",
    }

    def fake_reply(chat_id, text, reply_markup=None, msg_id=None):
        replies.append((chat_id, text, reply_markup, msg_id))
        return {"result": {"message_id": 900 + len(replies)}}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    monkeypatch.setattr(user_bot_service, "_unbind_user", lambda tg_user_id: unbound.append(tg_user_id))
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_reply", fake_reply)
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding_arg=None: {"menu": binding_arg})
    monkeypatch.setattr(user_bot_service, "user_dao", user_dao)
    monkeypatch.setattr(user_bot_service, "stats_queries", stats_queries)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)
    return user_bot_service, sent, replies, unbound, user_dao, stats_queries, media_api, logger


def test_cmd_profile_unbound_uses_legacy_send(monkeypatch):
    user_bot_service, sent, replies, _unbound, user_dao, _stats, _media, _logger = _reset_account_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)

    user_bot_service.cmd_profile(10, "tg1", msg_id=5)

    assert sent == [(10, "❌ 请先绑定账号", None)]
    assert replies == []
    assert user_dao.calls == []


def test_cmd_profile_deleted_emby_account_unbinds_and_sends_menu(monkeypatch):
    user_bot_service, sent, _replies, unbound, user_dao, _stats, _media, _logger = _reset_account_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: False)

    user_bot_service.cmd_profile(10, "tg1", msg_id=5)

    assert unbound == ["tg1"]
    assert sent == [(10, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", {"menu": None})]
    assert user_dao.calls == []


def test_cmd_profile_success_formats_profile_from_runtime_dependencies(monkeypatch):
    user_bot_service, sent, replies, _unbound, user_dao, stats_queries, media_api, _logger = _reset_account_command_state(monkeypatch)

    result = user_bot_service.cmd_profile(10, "tg1", msg_id=5)

    assert result is None
    assert sent == []
    assert user_dao.calls == ["user-1234567890"]
    assert stats_queries.calls == ["user-1234567890"]
    assert media_api.calls == [("/Users/user-1234567890", 5)]
    chat_id, text, markup, msg_id = replies[0]
    assert chat_id == 10
    assert msg_id == 5
    assert "👤 <b>个人中心</b>" in text
    assert "📛 <b>用户名：</b><code>Alice</code>" in text
    assert "🔑 <b>密码：</b><tg-spoiler>secret-pass</tg-spoiler>" in text
    assert "🆔 <b>用户 ID：</b><code>user-123...</code>" in text
    assert "📅 <b>注册时间：</b>2024-01-02" in text
    assert "🔰 <b>账号状态：</b>✅ 正常" in text
    assert "💰 <b>积分余额：</b>128" in text
    assert "⏳ <b>有效期至：</b>♾️ 永久有效" in text
    assert "🎬 <b>最后播放：</b>🎬 A Very Long Movie Ti..." in text
    assert "📊 播放 62 分钟 • 2026-05-01 12:34" in text
    assert markup == {
        "inline_keyboard": [
            [
                {"text": "✅ 签到领积分", "callback_data": "ub_menu_checkin"},
                {"text": "🎟️ 续期", "callback_data": "ub_menu_renew"},
            ],
            [{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}],
        ]
    }


def test_cmd_profile_playback_failure_logs_warning_and_uses_fallback(monkeypatch):
    user_bot_service, _sent, replies, _unbound, _user_dao, stats_queries, media_api, logger = _reset_account_command_state(monkeypatch)
    stats_queries.error = RuntimeError("playback raw")
    media_api.response = FakeResponse(payload={"Policy": {"IsDisabled": True}, "DateCreated": ""})

    user_bot_service.cmd_profile(10, "tg1")

    assert logger.calls == [("warning", "获取播放记录失败: playback raw")]
    assert "🎬 <b>最后播放：</b>暂无播放记录" in replies[0][1]
    assert "🔰 <b>账号状态：</b>⛔ 已禁用" in replies[0][1]
    assert "📅 <b>注册时间：</b>未知" in replies[0][1]


def test_cmd_profile_outer_failure_is_logged_and_sanitized(monkeypatch):
    user_bot_service, _sent, replies, _unbound, user_dao, _stats, _media, logger = _reset_account_command_state(monkeypatch)
    user_dao.error = RuntimeError("raw profile failure")

    user_bot_service.cmd_profile(10, "tg1", msg_id=5)

    assert logger.calls == [("error", "[个人信息] 获取失败: raw profile failure")]
    assert replies == [(10, "❌ 获取信息失败：safe:获取信息异常，请稍后重试", None, 5)]


def test_cmd_unbind_and_confirm_use_legacy_providers(monkeypatch):
    user_bot_service, sent, _replies, unbound, _user_dao, _stats, _media, _logger = _reset_account_command_state(monkeypatch)

    user_bot_service.cmd_unbind(10, "tg1")
    assert sent == [(
        10,
        "🔓 <b>确认解绑？</b>\n\n当前绑定：<b>Alice</b>\n\n解绑后将无法使用签到、商城等功能。\n\n发送 /unbind_confirm 确认解绑",
        None,
    )]

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    user_bot_service.cmd_unbind(10, "tg1")
    assert sent == [(10, "❌ 你还没有绑定账号", None)]

    sent.clear()
    user_bot_service.cmd_unbind_confirm(10, "tg1")
    assert unbound == ["tg1"]
    assert sent == [(10, "✅ 已成功解绑账号。", {"menu": None})]
