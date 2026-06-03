import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeDateTime:
    timedelta = real_datetime.timedelta

    class date:
        @classmethod
        def today(cls):
            return real_datetime.date(2026, 6, 3)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self):
        self.create_status = 201
        self.template = {"Policy": {"IsAdministrator": True, "IsDisabled": True, "Other": "keep"}}
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append(("get", path, timeout))
        if path.startswith("/Users/"):
            return FakeResponse(self.template)
        return FakeResponse([])

    def post(self, path, json=None, timeout=None):
        self.calls.append(("post", path, json, timeout))
        if path == "/Users/New":
            return FakeResponse({"Id": "u-new"}, self.create_status)
        return FakeResponse({"ok": True})


class FakeSecrets:
    def __init__(self):
        self.calls = []

    def token_urlsafe(self, length):
        self.calls.append(length)
        return "pw-token"


class FakeLock:
    def __init__(self, key, events):
        self.key = key
        self.events = events

    def __enter__(self):
        self.events.append(("lock_enter", self.key))
        return self

    def __exit__(self, exc_type, exc, tb):
        self.events.append(("lock_exit", self.key))
        return False


class FakeUserBotDao:
    def __init__(self):
        self.binding_count = 0
        self.log_error = None
        self.count_calls = 0
        self.logs = []

    def count_bindings(self):
        self.count_calls += 1
        return self.binding_count

    def create_registration_log(self, tg_user_id, safe_name, uid, source):
        if self.log_error:
            raise self.log_error
        self.logs.append((tg_user_id, safe_name, uid, source))


class FakeUserDao:
    def __init__(self):
        self.template_routes = None
        self.route_saves = []
        self.expire_saves = []
        self.route_reads = []

    def get_user_routes(self, template_id):
        self.route_reads.append(template_id)
        return self.template_routes

    def save_user_expire_routes(self, uid, expire, allow_routes, block_routes):
        self.route_saves.append((uid, expire, allow_routes, block_routes))

    def save_user_expire(self, uid, expire):
        self.expire_saves.append((uid, expire))


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.exceptions = []

    def error(self, message):
        self.errors.append(message)

    def exception(self, message):
        self.exceptions.append(message)


def _reset_open_registration_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    bound = []
    queue = {"enter": True, "events": []}
    quota = {"mode": "total", "quota": 0, "reserve": (True, None), "released": [], "set_open": [], "closed": []}
    users = {"cached": [], "after_refresh": []}
    media_api = FakeMediaApi()
    user_bot_dao = FakeUserBotDao()
    user_dao = FakeUserDao()
    secrets = FakeSecrets()
    logger = FakeLogger()
    locks = []

    monkeypatch.setattr(user_bot_service, "_user_state", {})
    monkeypatch.setattr(user_bot_service, "_enter_reg_queue", lambda chat_id: queue["events"].append(("enter", chat_id)) or queue["enter"])
    monkeypatch.setattr(user_bot_service, "_leave_reg_queue", lambda: queue["events"].append(("leave",)))
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "get_user_bot_reg_quota_mode", lambda: quota["mode"])
    monkeypatch.setattr(user_bot_service, "get_user_bot_reg_quota", lambda: quota["quota"])
    monkeypatch.setattr(user_bot_service, "_reserve_quota_slot", lambda quota_mode, quota_value: quota["reserve"])
    monkeypatch.setattr(
        user_bot_service,
        "_release_quota_slot",
        lambda committed, quota_mode, quota_value: quota["released"].append((committed, quota_mode, quota_value)),
    )
    monkeypatch.setattr(user_bot_service, "set_user_bot_open_reg_enabled", lambda value: quota["set_open"].append(value))
    monkeypatch.setattr(user_bot_service, "_send_open_reg_closed_notify", lambda reason="": quota["closed"].append(reason))
    monkeypatch.setattr(user_bot_service, "get_user_bot_max_reg", lambda: 0)
    monkeypatch.setattr(user_bot_service, "user_bot_dao", user_bot_dao)
    monkeypatch.setattr(user_bot_service, "secrets", secrets)
    monkeypatch.setattr(user_bot_service, "_get_username_lock", lambda key: locks.append(key) or FakeLock(key, queue["events"]))
    monkeypatch.setattr(user_bot_service, "get_users_list_cached", lambda max_age=None: users["cached"])
    monkeypatch.setattr(user_bot_service, "_quota_lock", FakeLock("quota", queue["events"]))

    def refresh_user_count_cache_locked(force=False, quota=0):
        queue["events"].append(("refresh", force, quota))
        user_bot_service._user_count_cache["users"] = users["after_refresh"]

    monkeypatch.setattr(user_bot_service, "_refresh_user_count_cache_locked", refresh_user_count_cache_locked)
    monkeypatch.setattr(user_bot_service, "_user_count_cache", {"users": users["after_refresh"]})
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "get_user_bot_template_user", lambda: "")
    monkeypatch.setattr(user_bot_service, "datetime", FakeDateTime)
    monkeypatch.setattr(user_bot_service, "get_user_bot_reg_days", lambda: 30)
    monkeypatch.setattr(user_bot_service, "get_user_bot_allow_routes", lambda: "")
    monkeypatch.setattr(user_bot_service, "get_user_bot_block_routes", lambda: "")
    monkeypatch.setattr(user_bot_service, "user_dao", user_dao)
    monkeypatch.setattr(
        user_bot_service,
        "_bind_user",
        lambda tg_user_id, uid, name, init_password="", tg_username="", tg_display_name="": bound.append(
            (tg_user_id, uid, name, init_password, tg_username, tg_display_name)
        ),
    )
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding=None: {"menu": binding})
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, bound, queue, quota, users, media_api, user_bot_dao, user_dao, secrets, locks, logger


def test_do_register_preserves_queue_rejection(monkeypatch):
    user_bot_service, sent, _bound, queue, _quota, _users, media_api, _user_bot_dao, _user_dao, _secrets, _locks, _logger = (
        _reset_open_registration_state(monkeypatch)
    )
    queue["enter"] = False

    user_bot_service._do_register(10, "tg1", "Alice")

    assert queue["events"] == [("enter", 10)]
    assert sent == []
    assert media_api.calls == []


def test_do_register_preserves_open_reg_and_quota_failures(monkeypatch):
    user_bot_service, sent, _bound, queue, quota, _users, _media_api, _user_bot_dao, _user_dao, _secrets, _locks, _logger = (
        _reset_open_registration_state(monkeypatch)
    )

    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_enabled", lambda: False)
    user_bot_service._do_register(10, "tg1", "Alice")
    assert sent[-1] == (10, "❌ 开放注册已关闭，请联系管理员获取注册码后使用 /code 注册码", None)
    assert queue["events"] == [("enter", 10), ("leave",)]

    sent.clear()
    queue["events"].clear()
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_enabled", lambda: True)
    quota["quota"] = 5
    quota["mode"] = "batch"
    quota["reserve"] = (False, "batch_full")

    user_bot_service._do_register(10, "tg1", "Alice")

    assert sent[-1] == (10, "❌ 本次开放注册名额已用完，请联系管理员", None)
    assert quota["set_open"] == [False]
    assert quota["closed"] == ["批次名额已满"]
    assert quota["released"] == []
    assert queue["events"] == [("enter", 10), ("leave",)]


def test_do_register_preserves_validation_and_max_reg_guard(monkeypatch):
    user_bot_service, sent, _bound, queue, _quota, _users, _media_api, user_bot_dao, _user_dao, _secrets, _locks, _logger = (
        _reset_open_registration_state(monkeypatch)
    )
    user_bot_dao.binding_count = 3
    monkeypatch.setattr(user_bot_service, "get_user_bot_max_reg", lambda: 3)

    user_bot_service._do_register(10, "tg1", "Alice")
    assert sent[-1] == (10, "❌ 注册名额已满，请联系管理员", None)
    assert user_bot_dao.count_calls == 1

    sent.clear()
    queue["events"].clear()
    user_bot_dao.binding_count = 0
    user_bot_service._do_register(10, "tg1", "abcdefghijklmnopq")
    assert sent[-1] == (10, "❌ 用户名最多 16 个字符，当前 17 个字符", None)
    assert queue["events"] == [("enter", 10), ("leave",)]

    sent.clear()
    user_bot_service._do_register(10, "tg1", "Bad Name!")
    assert sent[-1][0] == 10
    assert sent[-1][1].startswith("❌ 用户名包含不支持的字符:")


def test_do_register_preserves_duplicate_username_refresh_and_state_restore(monkeypatch):
    user_bot_service, sent, _bound, queue, quota, users, _media_api, _user_bot_dao, _user_dao, _secrets, locks, _logger = (
        _reset_open_registration_state(monkeypatch)
    )
    quota["quota"] = 5
    quota["reserve"] = (True, None)
    users["cached"] = [{"Name": "Alice"}]
    users["after_refresh"] = [{"Name": "Alice"}]

    user_bot_service._do_register(10, "tg1", "Alice")

    assert sent[-1] == (10, "❌ 用户名 <b>Alice</b> 已被占用，请换一个", None)
    assert user_bot_service._user_state == {"tg1": {"action": "register_name"}}
    assert locks == ["alice"]
    assert ("refresh", True, 0) in queue["events"]
    assert quota["released"] == [(False, "total", 5)]


def test_do_register_preserves_emby_create_failure_and_quota_release(monkeypatch):
    user_bot_service, sent, _bound, _queue, quota, _users, media_api, _user_bot_dao, _user_dao, _secrets, _locks, _logger = (
        _reset_open_registration_state(monkeypatch)
    )
    quota["quota"] = 5
    media_api.create_status = 500

    user_bot_service._do_register(10, "tg1", "Alice")

    assert sent[-1] == (10, "❌ 创建账号失败，请稍后重试", None)
    assert ("post", "/Users/New", {"Name": "Alice"}, 10) in media_api.calls
    assert quota["released"] == [(False, "total", 5)]


def test_do_register_preserves_success_with_direct_routes(monkeypatch):
    user_bot_service, sent, bound, _queue, quota, _users, media_api, user_bot_dao, user_dao, secrets, locks, _logger = (
        _reset_open_registration_state(monkeypatch)
    )
    quota["quota"] = 5
    monkeypatch.setattr(user_bot_service, "get_user_bot_template_user", lambda: "tpl1")
    monkeypatch.setattr(user_bot_service, "get_user_bot_allow_routes", lambda: "route-a")
    monkeypatch.setattr(user_bot_service, "get_user_bot_block_routes", lambda: "")

    user_bot_service._do_register(10, "tg1", "Alice", tg_username="alice_tg", tg_display_name="Alice TG")

    assert secrets.calls == [8]
    assert locks == ["alice"]
    assert user_dao.route_saves == [("u-new", "2026-07-03", "route-a", "")]
    assert user_dao.expire_saves == []
    assert bound == [("tg1", "u-new", "Alice", "pw-token", "alice_tg", "Alice TG")]
    assert user_bot_dao.logs == [("tg1", "Alice", "u-new", "open")]
    assert quota["released"] == [(True, "total", 5)]
    assert ("post", "/Users/u-new/Password", {"NewPw": "pw-token"}, 5) in media_api.calls
    assert ("post", "/Users/u-new/Policy", {"IsAdministrator": False, "IsDisabled": False, "Other": "keep"}, 5) in media_api.calls
    assert sent[-1] == (
        10,
        "🎉 <b>注册成功！</b>\n\n"
        "👤 用户名：<code>Alice</code>\n"
        "🔑 密码：<code>pw-token</code>\n"
        "📅 有效期至：2026-07-03\n\n"
        "💡 密码可在「个人中心」随时查看",
        {"menu": {"emby_user_id": "u-new", "emby_username": "Alice"}},
    )


def test_do_register_preserves_template_routes_log_failure_and_safe_error(monkeypatch):
    user_bot_service, sent, _bound, queue, _quota, _users, media_api, user_bot_dao, user_dao, _secrets, _locks, logger = (
        _reset_open_registration_state(monkeypatch)
    )
    monkeypatch.setattr(user_bot_service, "get_user_bot_template_user", lambda: "tpl1")
    user_dao.template_routes = {"allow_routes": "tpl-allow", "block_routes": "tpl-block"}
    user_bot_dao.log_error = RuntimeError("log raw")

    user_bot_service._do_register(10, "tg1", "Alice")

    assert user_dao.route_reads == ["tpl1"]
    assert user_dao.route_saves == [("u-new", "2026-07-03", "tpl-allow", "tpl-block")]
    assert logger.errors == ["记录注册日志失败: log raw"]

    sent.clear()
    queue["events"].clear()

    def raise_create(path, json=None, timeout=None):
        if path == "/Users/New":
            raise RuntimeError("create raw")
        return FakeResponse()

    media_api.post = raise_create
    user_bot_service._do_register(10, "tg1", "Bob")

    assert logger.errors[-1] == "[注册] 执行异常: create raw"
    assert sent[-1] == (10, "❌ 注册异常：safe:注册操作异常，请稍后重试", None)
    assert queue["events"][-1] == ("leave",)
