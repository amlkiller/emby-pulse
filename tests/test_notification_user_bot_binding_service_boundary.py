import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeLogger:
    def __init__(self):
        self.calls = []

    def warning(self, message):
        self.calls.append(("warning", message))

    def error(self, message):
        self.calls.append(("error", message))


def _reset_user_bot_binding_state(monkeypatch, now=100.0):
    from app.domains.notifications import user_bot_service

    monkeypatch.setattr(user_bot_service, "_binding_cache", {})
    monkeypatch.setattr(user_bot_service, "_blacklist_cache", {})
    monkeypatch.setattr(user_bot_service, "_emby_account_cache", {})
    monkeypatch.setattr(user_bot_service, "_cache_lock", FakeLock())
    monkeypatch.setattr(user_bot_service, "_BINDING_CACHE_TTL", 60)
    monkeypatch.setattr(user_bot_service, "_BLACKLIST_CACHE_TTL", 300)
    monkeypatch.setattr(user_bot_service, "_EMBY_ACCOUNT_CACHE_TTL", 60)
    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(time=lambda: now))
    return user_bot_service


def test_user_bot_binding_lookup_uses_legacy_cache_before_dao(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch, now=120.0)
    cached_binding = {"emby_user_id": "u1", "emby_username": "Alice"}
    user_bot_service._binding_cache["tg1"] = {"binding": cached_binding, "cached_at": 100.0}

    def fail_get_binding(*args, **kwargs):
        raise AssertionError("cached binding lookup should not call dao")

    monkeypatch.setattr(user_bot_service.user_bot_dao, "get_binding", fail_get_binding)

    assert user_bot_service._get_binding("tg1") is cached_binding


def test_user_bot_binding_lookup_miss_uses_legacy_dao_and_updates_cache(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch, now=200.0)
    calls = []

    def fake_get_binding(tg_user_id):
        calls.append(("get_binding", tg_user_id))
        return {"emby_user_id": "u2", "emby_username": "Bob"}

    monkeypatch.setattr(user_bot_service.user_bot_dao, "get_binding", fake_get_binding)

    assert user_bot_service._get_binding(123) == {"emby_user_id": "u2", "emby_username": "Bob"}
    assert user_bot_service._binding_cache == {
        "123": {
            "binding": {"emby_user_id": "u2", "emby_username": "Bob"},
            "cached_at": 200.0,
        }
    }
    assert calls == [("get_binding", "123")]


def test_user_bot_bind_and_unbind_user_mutate_legacy_cache_and_dao(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch, now=300.0)
    calls = []

    def fake_bind_user(tg_user_id, emby_user_id, emby_username, init_password, tg_username, tg_display_name):
        calls.append(("bind_user", tg_user_id, emby_user_id, emby_username, init_password, tg_username, tg_display_name))

    def fake_delete_user_binding(tg_user_id):
        calls.append(("delete_user_binding", tg_user_id))

    monkeypatch.setattr(user_bot_service.user_bot_dao, "bind_user", fake_bind_user)
    monkeypatch.setattr(user_bot_service.user_bot_dao, "delete_user_binding", fake_delete_user_binding)

    user_bot_service._bind_user("tg1", "emby1", "Alice", "pw", "alice_tg", "Alice TG")

    assert user_bot_service._binding_cache["tg1"] == {
        "binding": {"emby_user_id": "emby1", "emby_username": "Alice", "init_password": "pw"},
        "cached_at": 300.0,
    }

    user_bot_service._unbind_user("tg1")

    assert "tg1" not in user_bot_service._binding_cache
    assert calls == [
        ("bind_user", "tg1", "emby1", "Alice", "pw", "alice_tg", "Alice TG"),
        ("delete_user_binding", "tg1"),
    ]


def test_user_bot_channel_binding_uses_legacy_get_binding_wrapper(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch)
    calls = []

    def fake_get_channel_binding(channel_id):
        calls.append(("get_channel_binding", channel_id))
        return {"tg_user_id": "tg1", "channel_title": "Channel One"}

    def fake_get_binding(tg_user_id):
        calls.append(("get_binding_wrapper", tg_user_id))
        return {"emby_user_id": "emby1", "emby_username": "Alice"}

    monkeypatch.setattr(user_bot_service.user_bot_dao, "get_channel_binding", fake_get_channel_binding)
    monkeypatch.setattr(user_bot_service, "_get_binding", fake_get_binding)

    assert user_bot_service._get_channel_binding("channel-1") == {
        "emby_user_id": "emby1",
        "emby_username": "Alice",
        "channel_title": "Channel One",
        "bound_tg_user_id": "tg1",
    }
    assert calls == [
        ("get_channel_binding", "channel-1"),
        ("get_binding_wrapper", "tg1"),
    ]


def test_user_bot_blacklist_cache_uses_legacy_state_and_dao(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch, now=500.0)
    calls = []

    def fake_is_blacklisted(tg_user_id):
        calls.append(("is_blacklisted", tg_user_id))
        return True

    def fake_add_to_blacklist(tg_user_id, reason):
        calls.append(("add_to_blacklist", tg_user_id, reason))

    monkeypatch.setattr(user_bot_service.user_bot_dao, "is_blacklisted", fake_is_blacklisted)
    monkeypatch.setattr(user_bot_service.user_bot_dao, "add_to_blacklist", fake_add_to_blacklist)

    assert user_bot_service._is_blacklisted(321) is True
    assert user_bot_service._is_blacklisted(321) is True
    user_bot_service._add_to_blacklist(321, "reason")

    assert user_bot_service._blacklist_cache == {"321": {"blacklisted": True, "cached_at": 500.0}}
    assert calls == [
        ("is_blacklisted", "321"),
        ("add_to_blacklist", 321, "reason"),
    ]


def test_user_bot_emby_account_cache_and_network_fallback_use_legacy_media(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch, now=600.0)
    calls = []

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        return SimpleNamespace(status_code=404)

    monkeypatch.setattr(user_bot_service.media_api, "get", fake_media_get)

    assert user_bot_service._check_emby_account({"emby_user_id": "u1"}) is False
    assert user_bot_service._check_emby_account({"emby_user_id": "u1"}) is False
    assert calls == [("media_get", "/Users/u1", 5)]

    def failing_media_get(path, timeout=None):
        calls.append(("media_get_fail", path, timeout))
        raise RuntimeError("network down")

    monkeypatch.setattr(user_bot_service.media_api, "get", failing_media_get)
    assert user_bot_service._check_emby_account({"emby_user_id": "u2"}) is True
    assert calls[-1] == ("media_get_fail", "/Users/u2", 5)


def test_user_bot_bot_user_helpers_preserve_dao_fallbacks_and_logging(monkeypatch):
    user_bot_service = _reset_user_bot_binding_state(monkeypatch)
    fake_logger = FakeLogger()
    calls = []

    def fake_record_bot_user(tg_user_id, tg_name):
        calls.append(("record_bot_user", tg_user_id, tg_name))

    def fake_list_bot_users():
        calls.append(("list_bot_users",))
        return [{"tg_user_id": "1", "tg_name": "Alice"}]

    monkeypatch.setattr(user_bot_service.user_bot_dao, "record_bot_user", fake_record_bot_user)
    monkeypatch.setattr(user_bot_service.user_bot_dao, "list_bot_users", fake_list_bot_users)
    monkeypatch.setattr(user_bot_service, "logger", fake_logger)

    user_bot_service._record_bot_user("1", "Alice")
    assert user_bot_service._get_all_bot_users() == [{"tg_user_id": "1", "tg_name": "Alice"}]

    def failing_record_bot_user(tg_user_id, tg_name):
        raise RuntimeError("write failed")

    def failing_list_bot_users():
        raise RuntimeError("read failed")

    monkeypatch.setattr(user_bot_service.user_bot_dao, "record_bot_user", failing_record_bot_user)
    monkeypatch.setattr(user_bot_service.user_bot_dao, "list_bot_users", failing_list_bot_users)

    user_bot_service._record_bot_user("2", "Bob")
    assert user_bot_service._get_all_bot_users() == []
    assert calls == [
        ("record_bot_user", "1", "Alice"),
        ("list_bot_users",),
    ]
    assert fake_logger.calls == [("error", "记录机器人用户失败: write failed")]
