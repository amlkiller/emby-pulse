import datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def get(self, path, params=None, timeout=None):
        self.calls.append((path, params, timeout))
        if self.error:
            raise self.error
        return self.response


def _patch_dependencies(monkeypatch, *, admin_id="admin-1", response=None, error=None):
    from app.bot.notification_bot import bot_service

    media_api = FakeMediaApi(response=response, error=error)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: admin_id)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    return media_api


def test_parse_emby_time_preserves_fractional_plain_and_invalid_inputs():
    from app.bot.notification_bot import bot_service

    daemon = bot_service.SystemDaemon()

    assert daemon._parse_emby_time("2026-06-03T12:34:56.1234567Z") == datetime.datetime(
        2026, 6, 3, 12, 34, 56, 123456
    )
    assert daemon._parse_emby_time("2026-06-03T12:34:56Z") == datetime.datetime(2026, 6, 3, 12, 34, 56)
    assert daemon._parse_emby_time("") is None
    assert daemon._parse_emby_time(None) is None
    assert daemon._parse_emby_time("not-a-date") is None


def test_check_fresh_episodes_skips_media_call_without_admin(monkeypatch):
    from app.bot.notification_bot import bot_service

    media_api = _patch_dependencies(monkeypatch, admin_id=None)
    daemon = bot_service.SystemDaemon()

    assert daemon._check_fresh_episodes("series-1") == []
    assert media_api.calls == []


def test_check_fresh_episodes_requests_recent_episodes_and_groups_within_two_minutes(monkeypatch):
    from app.bot.notification_bot import bot_service

    first = {"Id": "e-1", "DateCreated": "2026-06-03T12:00:00Z"}
    second = {"Id": "e-2", "DateCreated": "2026-06-03T11:58:30Z"}
    old = {"Id": "e-old", "DateCreated": "2026-06-03T11:55:00Z"}
    media_api = _patch_dependencies(
        monkeypatch,
        response=FakeResponse(payload={"Items": [first, second, old]}),
    )
    daemon = bot_service.SystemDaemon()

    assert daemon._check_fresh_episodes("series-1") == [first, second]
    assert media_api.calls == [
        (
            "/Users/admin-1/Items",
            {
                "ParentId": "series-1",
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "Limit": 1000,
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Fields": "DateCreated,Name,ParentIndexNumber,IndexNumber",
            },
            10,
        )
    ]


def test_check_fresh_episodes_preserves_status_empty_invalid_and_exception_branches(monkeypatch):
    from app.bot.notification_bot import bot_service

    daemon = bot_service.SystemDaemon()

    _patch_dependencies(monkeypatch, response=FakeResponse(status_code=500, payload={"Items": [{"Id": "e"}]}))
    assert daemon._check_fresh_episodes("series-1") == []

    _patch_dependencies(monkeypatch, response=FakeResponse(payload={"Items": []}))
    assert daemon._check_fresh_episodes("series-1") == []

    first_invalid = {"Id": "e-invalid", "DateCreated": "bad-date"}
    second_valid = {"Id": "e-valid", "DateCreated": "2026-06-03T12:00:00Z"}
    _patch_dependencies(monkeypatch, response=FakeResponse(payload={"Items": [first_invalid, second_valid]}))
    assert daemon._check_fresh_episodes("series-1") == [first_invalid]

    first_valid = {"Id": "e-first", "DateCreated": "2026-06-03T12:00:00Z"}
    second_invalid = {"Id": "e-invalid", "DateCreated": "bad-date"}
    _patch_dependencies(monkeypatch, response=FakeResponse(payload={"Items": [first_valid, second_invalid]}))
    assert daemon._check_fresh_episodes("series-1") == [first_valid]

    _patch_dependencies(monkeypatch, error=RuntimeError("network failed"))
    assert daemon._check_fresh_episodes("series-1") == []


def test_check_fresh_episodes_wrapper_uses_instance_parse_method(monkeypatch):
    from app.bot.notification_bot import bot_service

    first = {"Id": "e-1", "DateCreated": "first"}
    second = {"Id": "e-2", "DateCreated": "second"}
    _patch_dependencies(monkeypatch, response=FakeResponse(payload={"Items": [first, second]}))
    daemon = bot_service.SystemDaemon()
    parse_calls = []

    def parse_time(value):
        parse_calls.append(value)
        if value == "first":
            return datetime.datetime(2026, 6, 3, 12, 0)
        return None

    daemon._parse_emby_time = parse_time

    assert daemon._check_fresh_episodes("series-1") == [first]
    assert parse_calls == ["first", "second"]
