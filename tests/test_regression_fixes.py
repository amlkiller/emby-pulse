import os
import sys
from types import SimpleNamespace

import pytest

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_notify_rule_default_is_enabled_when_missing(monkeypatch):
    from app.routers import notify_admin

    monkeypatch.setattr(notify_admin, "get_notify_rule_row", lambda notify_type: None)

    rule = notify_admin.get_notify_rule("request_new")

    assert rule["enabled"] == 1
    assert rule["channels"] == ["tg_bot", "wecom", "web"]


def test_notify_rule_respects_saved_disabled_rule(monkeypatch):
    from app.routers import notify_admin

    class FakeRow(dict):
        pass

    monkeypatch.setattr(
        notify_admin,
        "get_notify_rule_row",
        lambda notify_type: FakeRow({
            "notify_type": "request_new",
            "notify_name": "工单提交",
            "enabled": 0,
            "channels": '["web"]',
        }),
    )

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


def test_webhook_token_accepts_url_query_param():
    from app.routers import webhook

    request = SimpleNamespace(headers={}, query_params={"token": "url-token"})

    assert webhook._get_webhook_token(request) == "url-token"


def test_webhook_token_prefers_header_over_url_query_param():
    from app.routers import webhook

    request = SimpleNamespace(
        headers={"X-Webhook-Token": "header-token"},
        query_params={"token": "url-token"},
    )

    assert webhook._get_webhook_token(request) == "header-token"


@pytest.mark.parametrize("is_admin", [True, False])
def test_request_login_rejects_passwordless_emby_users(monkeypatch, is_admin):
    from app.routers import media_request

    class FakeMediaResponse:
        status_code = 200

        def json(self):
            return [
                {
                    "Id": "user-a",
                    "Name": "zhangsan",
                    "HasPassword": False,
                    "Policy": {"IsAdministrator": is_admin, "IsDisabled": False},
                }
            ]

    class FakeCursor:
        def execute(self, *args, **kwargs):
            return self

        def fetchone(self):
            return None

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(media_request.cfg, "get", lambda key, default=None: "http://emby.local" if key == "emby_host" else default)
    monkeypatch.setattr(media_request.media_api, "get", lambda *args, **kwargs: FakeMediaResponse())
    monkeypatch.setattr(media_request.sqlite3, "connect", lambda *args, **kwargs: FakeConn())
    monkeypatch.setattr(
        media_request.requests,
        "post",
        lambda *args, **kwargs: pytest.fail("无密码用户不应调用 Emby 密码认证接口"),
    )

    request = SimpleNamespace(headers={"host": "127.0.0.1:10308"}, session={})
    data = media_request.RequestLoginModel(username="zhangsan", password="")

    result = media_request.request_system_login(data, request)

    assert result["status"] == "error"
    assert "设置密码" in result["message"]
    assert request.session == {}
