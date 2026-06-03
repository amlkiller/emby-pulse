import sys
import threading
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.calls = []

    def info(self, message):
        self.calls.append(("info", message))

    def error(self, message):
        self.calls.append(("error", message))


def _reset_restriction_state(monkeypatch, now=100.0):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    monkeypatch.setattr(user_bot_service, "_restriction_cache", {})
    monkeypatch.setattr(user_bot_service, "_restriction_cache_lock", threading.RLock())
    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(time=lambda: now))
    monkeypatch.setattr(user_bot_service, "logger", FakeLogger())
    return user_bot_service


def test_check_user_in_chat_uses_legacy_tg_api_and_logger(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch)
    calls = []

    def fake_tg_api(method, data=None, token=None):
        calls.append((method, data, token))
        return {"ok": True, "result": {"status": "administrator"}}

    monkeypatch.setattr(user_bot_service, "_tg_api", fake_tg_api)

    assert user_bot_service._check_user_in_chat("tg1", "@channel") is True
    assert calls == [("getChatMember", {"chat_id": "@channel", "user_id": "tg1"}, None)]

    def failing_tg_api(method, data=None, token=None):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(user_bot_service, "_tg_api", failing_tg_api)

    assert user_bot_service._check_user_in_chat("tg2", "@channel") is False
    assert user_bot_service.logger.calls == [
        ("error", "检查用户 tg2 是否在 @channel 中失败: telegram down"),
    ]


def test_check_user_restrictions_disabled_skips_settings_and_chat_checks(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "is_user_bot_restriction_enabled", lambda: False)
    monkeypatch.setattr(
        user_bot_service,
        "get_user_bot_required_channels",
        lambda: (_ for _ in ()).throw(AssertionError("channels should not be read")),
    )
    monkeypatch.setattr(
        user_bot_service,
        "_check_user_in_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("chat should not be checked")),
    )

    assert user_bot_service._check_user_restrictions("tg1") == {
        "passed": True,
        "missing_channels": [],
        "missing_groups": [],
    }


def test_check_user_restrictions_uses_legacy_passed_cache(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch, now=120.0)
    user_bot_service._restriction_cache["tg1"] = {
        "passed": True,
        "missing_channels": [],
        "missing_groups": [],
        "cached_at": 100.0,
    }

    monkeypatch.setattr(user_bot_service, "is_user_bot_restriction_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_restriction_cache_ttl", lambda: 60)
    monkeypatch.setattr(
        user_bot_service,
        "_check_user_in_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache hit should not call chat")),
    )

    assert user_bot_service._check_user_restrictions("tg1") == {
        "passed": True,
        "missing_channels": [],
        "missing_groups": [],
    }


def test_check_user_restrictions_uses_legacy_settings_and_chat_wrapper(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch, now=200.0)
    calls = []
    membership = {
        "@channel-a": True,
        "@channel-b": False,
        "-1001": True,
        "-1002": False,
    }

    def fake_check_user_in_chat(tg_user_id, chat_id):
        calls.append((tg_user_id, chat_id))
        return membership[chat_id]

    monkeypatch.setattr(user_bot_service, "is_user_bot_restriction_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_restriction_cache_ttl", lambda: 60)
    monkeypatch.setattr(user_bot_service, "get_user_bot_required_channels", lambda: "@channel-a\n@channel-b\n")
    monkeypatch.setattr(
        user_bot_service,
        "get_user_bot_required_groups",
        lambda: '[{"id":"-1001","name":"Group One","link":"https://t.me/g1"},'
        '{"id":"-1002","name":"Group Two","link":"https://t.me/g2"}]',
    )
    monkeypatch.setattr(user_bot_service, "_check_user_in_chat", fake_check_user_in_chat)

    assert user_bot_service._check_user_restrictions("tg1") == {
        "passed": False,
        "missing_channels": ["@channel-b"],
        "missing_groups": [{"id": "-1002", "name": "Group Two", "link": "https://t.me/g2"}],
    }
    assert calls == [
        ("tg1", "@channel-a"),
        ("tg1", "@channel-b"),
        ("tg1", "-1001"),
        ("tg1", "-1002"),
    ]
    assert user_bot_service._restriction_cache == {}


def test_check_user_restrictions_caches_passed_result_in_legacy_cache(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch, now=300.0)

    monkeypatch.setattr(user_bot_service, "is_user_bot_restriction_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_restriction_cache_ttl", lambda: 60)
    monkeypatch.setattr(user_bot_service, "get_user_bot_required_channels", lambda: "@channel")
    monkeypatch.setattr(user_bot_service, "get_user_bot_required_groups", lambda: "-1001")
    monkeypatch.setattr(user_bot_service, "_check_user_in_chat", lambda _tg_user_id, _chat_id: True)

    assert user_bot_service._check_user_restrictions("tg1") == {
        "passed": True,
        "missing_channels": [],
        "missing_groups": [],
    }
    assert user_bot_service._restriction_cache == {
        "tg1": {
            "passed": True,
            "missing_channels": [],
            "missing_groups": [],
            "cached_at": 300.0,
        }
    }


def test_clear_restriction_cache_uses_legacy_cache(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch)
    user_bot_service._restriction_cache = {"tg1": {"passed": True}, "tg2": {"passed": True}}

    user_bot_service._clear_restriction_cache("tg1")

    assert user_bot_service._restriction_cache == {"tg2": {"passed": True}}


def test_format_restriction_message_preserves_channel_and_group_links(monkeypatch):
    user_bot_service = _reset_restriction_state(monkeypatch)

    message = user_bot_service._format_restriction_message({
        "passed": False,
        "missing_channels": ["@channel", "-100channel"],
        "missing_groups": [
            {"id": "-1001", "name": "Group One", "link": "https://t.me/g1"},
            {"id": "-1002", "name": "Group Two", "link": ""},
            "legacy-group",
        ],
    })

    assert '<a href="https://t.me/channel">@channel</a>' in message
    assert "• -100channel" in message
    assert '<a href="https://t.me/g1">Group One</a>' in message
    assert "• Group Two" in message
    assert "• legacy-group" in message
    assert message.endswith("💡 关注/加入后，发送 <b>/check</b> 重新验证。")
