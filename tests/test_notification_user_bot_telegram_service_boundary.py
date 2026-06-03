import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"ok": True}

    def json(self):
        return self._payload


def test_tg_api_uses_legacy_token_client_proxy_and_timeout(monkeypatch):
    from app.domains.notifications import user_bot_service

    calls = []

    def fake_post_api(token, method, json=None, proxies=None, timeout=None):
        calls.append((token, method, json, proxies, timeout))
        return FakeResponse(payload={"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "legacy-token")
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: {"https": "http://proxy"})
    monkeypatch.setattr(user_bot_service, "telegram_client", SimpleNamespace(post_api=fake_post_api))

    assert user_bot_service._tg_api("sendMessage", {"chat_id": 1}) == {"ok": True, "result": {"message_id": 1}}
    assert calls == [
        ("legacy-token", "sendMessage", {"chat_id": 1}, {"https": "http://proxy"}, 8),
    ]


def test_tg_api_explicit_token_overrides_legacy_token_and_handles_failures(monkeypatch):
    from app.domains.notifications import user_bot_service

    calls = []

    def fake_post_api(token, method, json=None, proxies=None, timeout=None):
        calls.append((token, method))
        return FakeResponse(status_code=500, payload={"ok": False})

    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "legacy-token")
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: None)
    monkeypatch.setattr(user_bot_service, "telegram_client", SimpleNamespace(post_api=fake_post_api))

    assert user_bot_service._tg_api("getMe", token="explicit-token") is None
    assert calls == [("explicit-token", "getMe")]

    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "")
    assert user_bot_service._tg_api("getMe") is None

    def failing_post_api(*args, **kwargs):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "legacy-token")
    monkeypatch.setattr(user_bot_service, "telegram_client", SimpleNamespace(post_api=failing_post_api))
    assert user_bot_service._tg_api("getMe") is None


def test_send_builds_legacy_payload_and_calls_legacy_tg_api(monkeypatch):
    from app.domains.notifications import user_bot_service

    calls = []

    def fake_tg_api(method, data=None, token=None):
        calls.append((method, data, token))
        return {"ok": True}

    monkeypatch.setattr(user_bot_service, "_tg_api", fake_tg_api)

    assert user_bot_service._send(10, "hello", reply_markup={"inline_keyboard": []}) == {"ok": True}
    assert calls == [
        (
            "sendMessage",
            {"chat_id": 10, "text": "hello", "parse_mode": "HTML", "reply_markup": {"inline_keyboard": []}},
            None,
        ),
    ]


def test_edit_uses_legacy_tg_api_and_falls_back_to_legacy_send(monkeypatch):
    from app.domains.notifications import user_bot_service

    calls = []

    def fake_tg_api(method, data=None, token=None):
        calls.append((method, data, token))
        return {"ok": False}

    def fake_send(chat_id, text, reply_markup=None):
        calls.append(("send_fallback", chat_id, text, reply_markup))
        return {"ok": True, "fallback": True}

    monkeypatch.setattr(user_bot_service, "_tg_api", fake_tg_api)
    monkeypatch.setattr(user_bot_service, "_send", fake_send)

    assert user_bot_service._edit(10, 99, "updated", reply_markup={"k": "v"}) == {"ok": True, "fallback": True}
    assert calls == [
        (
            "editMessageText",
            {"chat_id": 10, "message_id": 99, "text": "updated", "parse_mode": "HTML", "reply_markup": {"k": "v"}},
            None,
        ),
        ("send_fallback", 10, "updated", {"k": "v"}),
    ]


def test_edit_returns_success_without_fallback(monkeypatch):
    from app.domains.notifications import user_bot_service

    calls = []

    monkeypatch.setattr(
        user_bot_service,
        "_tg_api",
        lambda method, data=None, token=None: calls.append((method, data, token)) or {"ok": True, "edited": True},
    )
    monkeypatch.setattr(
        user_bot_service,
        "_send",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("successful edit should not send")),
    )

    assert user_bot_service._edit(10, 99, "updated") == {"ok": True, "edited": True}
    assert calls == [
        (
            "editMessageText",
            {"chat_id": 10, "message_id": 99, "text": "updated", "parse_mode": "HTML"},
            None,
        ),
    ]


def test_reply_routes_through_legacy_edit_or_send(monkeypatch):
    from app.domains.notifications import user_bot_service

    calls = []

    def fake_edit(chat_id, message_id, text, reply_markup=None):
        calls.append(("edit", chat_id, message_id, text, reply_markup))
        return {"route": "edit"}

    def fake_send(chat_id, text, reply_markup=None):
        calls.append(("send", chat_id, text, reply_markup))
        return {"route": "send"}

    monkeypatch.setattr(user_bot_service, "_edit", fake_edit)
    monkeypatch.setattr(user_bot_service, "_send", fake_send)

    assert user_bot_service._reply(1, "with msg", reply_markup={"a": 1}, msg_id=2) == {"route": "edit"}
    assert user_bot_service._reply(1, "no msg", reply_markup={"b": 2}) == {"route": "send"}
    assert calls == [
        ("edit", 1, 2, "with msg", {"a": 1}),
        ("send", 1, "no msg", {"b": 2}),
    ]
