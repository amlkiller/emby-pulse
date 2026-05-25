import os
import sys
from types import SimpleNamespace

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_notify_rule_default_is_enabled_when_missing(monkeypatch):
    from app.routers import notify_admin

    class FakeCursor:
        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return None

    class FakeConn:
        row_factory = None

        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(notify_admin.sqlite3, "connect", lambda *args, **kwargs: FakeConn())

    rule = notify_admin.get_notify_rule("request_new")

    assert rule["enabled"] == 1
    assert rule["channels"] == ["tg_bot", "wecom", "web"]


def test_notify_rule_respects_saved_disabled_rule(monkeypatch):
    from app.routers import notify_admin

    class FakeRow(dict):
        pass

    class FakeCursor:
        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return FakeRow({
                "notify_type": "request_new",
                "notify_name": "工单提交",
                "enabled": 0,
                "channels": '["web"]',
            })

    class FakeConn:
        row_factory = None

        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(notify_admin.sqlite3, "connect", lambda *args, **kwargs: FakeConn())

    rule = notify_admin.get_notify_rule("request_new")

    assert rule["enabled"] == 0
    assert rule["channels"] == ["web"]


def test_dashboard_context_cache_keys_are_isolated():
    from app.routers import stats

    admin_req = SimpleNamespace(session={"user": {"auth_type": "emby"}})
    filtered_admin_req = SimpleNamespace(session={"user": {"role": "admin"}})
    user_req = SimpleNamespace(session={"req_user": {"Id": "user-a"}})

    assert stats._get_dashboard_context(admin_req) == ("admin:all", None, True)
    assert stats._get_dashboard_context(filtered_admin_req, "user-b") == ("admin:user-b", "user-b", True)
    assert stats._get_dashboard_context(user_req, "ignored") == ("user:user-a", "user-a", False)


def test_dashboard_cache_is_per_context(monkeypatch):
    from app.routers import stats

    monkeypatch.setattr(stats, "_DASHBOARD_CACHE_TTL", 300)
    stats._dashboard_cache.clear()
    stats._dashboard_cache_user_ids.clear()

    stats._set_dashboard_cache("admin:all", {"dashboard": {"total_plays": 100}}, None, ts=1000)
    stats._set_dashboard_cache("user:user-a", {"dashboard": {"total_plays": 7}}, "user-a", ts=1000)

    assert stats._get_dashboard_cached_data("admin:all", now=1100)["dashboard"]["total_plays"] == 100
    assert stats._get_dashboard_cached_data("user:user-a", now=1100)["dashboard"]["total_plays"] == 7
    assert stats._get_dashboard_cached_data("admin:user-a", now=1100) is None
