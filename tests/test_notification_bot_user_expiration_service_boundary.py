import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime.datetime(2026, 6, 3, 9, 0)


class FakeDateTimeModule:
    datetime = FakeDateTime


class FakeMediaResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self, responses=None, error_users=None):
        self.responses = responses or {}
        self.error_users = set(error_users or [])
        self.gets = []
        self.posts = []

    def get(self, path, timeout=None):
        self.gets.append((path, timeout))
        user_id = path.rsplit("/", 1)[-1]
        if user_id in self.error_users:
            raise RuntimeError(f"{user_id} get failed")
        return self.responses.get(path, FakeMediaResponse())

    def post(self, path, json=None, timeout=None):
        self.posts.append((path, json, timeout))


class FakeUserDao:
    def __init__(self, rows, error=None):
        self.rows = rows
        self.error = error
        self.calls = 0

    def list_users_with_expire_date(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.rows


def _make_daemon():
    from app.domains.notifications import bot_service

    return bot_service.SystemDaemon()


def _patch_dependencies(monkeypatch, *, rows, responses=None, error_users=None, dao_error=None):
    from app.domains.notifications import bot_service

    user_dao = FakeUserDao(rows, error=dao_error)
    media_api = FakeMediaApi(responses=responses, error_users=error_users)

    monkeypatch.setattr(bot_service, "user_dao", user_dao)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    return user_dao, media_api


def test_user_expiration_empty_users_skip_media_side_effects(monkeypatch):
    user_dao, media_api = _patch_dependencies(monkeypatch, rows=[])
    daemon = _make_daemon()

    daemon._check_user_expiration()

    assert user_dao.calls == 1
    assert media_api.gets == []
    assert media_api.posts == []


def test_user_expiration_skips_unexpired_and_today_users(monkeypatch):
    user_dao, media_api = _patch_dependencies(
        monkeypatch,
        rows=[
            {"user_id": "today", "expire_date": "2026-06-03"},
            {"user_id": "future", "expire_date": "2026-06-04"},
        ],
    )
    daemon = _make_daemon()

    daemon._check_user_expiration()

    assert user_dao.calls == 1
    assert media_api.gets == []
    assert media_api.posts == []


def test_user_expiration_disables_expired_user_and_preserves_policy_fields(monkeypatch):
    policy = {"IsDisabled": False, "IsAdministrator": True, "Other": "keep"}
    user_dao, media_api = _patch_dependencies(
        monkeypatch,
        rows=[{"user_id": "expired", "expire_date": "2026-06-02"}],
        responses={"/Users/expired": FakeMediaResponse(payload={"Policy": policy})},
    )
    daemon = _make_daemon()

    daemon._check_user_expiration()

    assert user_dao.calls == 1
    assert media_api.gets == [("/Users/expired", 5)]
    assert media_api.posts == [
        ("/Users/expired/Policy", {"IsDisabled": True, "IsAdministrator": True, "Other": "keep"}, 5)
    ]
    assert policy == {"IsDisabled": True, "IsAdministrator": True, "Other": "keep"}


def test_user_expiration_skips_already_disabled_and_non_200_response(monkeypatch):
    user_dao, media_api = _patch_dependencies(
        monkeypatch,
        rows=[
            {"user_id": "disabled", "expire_date": "2026-06-01"},
            {"user_id": "missing", "expire_date": "2026-06-01"},
        ],
        responses={
            "/Users/disabled": FakeMediaResponse(payload={"Policy": {"IsDisabled": True, "Other": "keep"}}),
            "/Users/missing": FakeMediaResponse(status_code=404, payload={"Policy": {"IsDisabled": False}}),
        },
    )
    daemon = _make_daemon()

    daemon._check_user_expiration()

    assert user_dao.calls == 1
    assert media_api.gets == [("/Users/disabled", 5), ("/Users/missing", 5)]
    assert media_api.posts == []


def test_user_expiration_per_user_exception_is_swallowed_and_loop_continues(monkeypatch):
    user_dao, media_api = _patch_dependencies(
        monkeypatch,
        rows=[
            {"user_id": "broken", "expire_date": "2026-06-01"},
            {"user_id": "expired", "expire_date": "2026-06-01"},
        ],
        responses={"/Users/expired": FakeMediaResponse(payload={"Policy": {"IsDisabled": False, "Keep": 1}})},
        error_users={"broken"},
    )
    daemon = _make_daemon()

    daemon._check_user_expiration()

    assert user_dao.calls == 1
    assert media_api.gets == [("/Users/broken", 5), ("/Users/expired", 5)]
    assert media_api.posts == [("/Users/expired/Policy", {"IsDisabled": True, "Keep": 1}, 5)]


def test_user_expiration_outer_exception_is_swallowed(monkeypatch):
    user_dao, media_api = _patch_dependencies(
        monkeypatch,
        rows=[],
        dao_error=RuntimeError("dao down"),
    )
    daemon = _make_daemon()

    daemon._check_user_expiration()

    assert user_dao.calls == 1
    assert media_api.gets == []
    assert media_api.posts == []
