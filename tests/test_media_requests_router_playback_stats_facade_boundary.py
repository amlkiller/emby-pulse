import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, calls):
        self.calls = calls

    def get(self, path, params=None, timeout=None):
        self.calls.append(("media_get", path, params, timeout))
        if path.endswith("/Items") or path == "/Items":
            ids = str((params or {}).get("Ids", ""))
            if ids:
                return FakeMediaResponse(payload={"Items": [{"Id": item_id} for item_id in ids.split(",")]})
            return FakeMediaResponse(
                payload={
                    "Items": [
                        {
                            "Id": "hub-1",
                            "Name": "Hub Movie",
                            "Type": "Movie",
                            "CommunityRating": 9.1,
                            "Genres": ["Drama"],
                        }
                    ]
                }
            )
        return FakeMediaResponse(payload={"Items": []})


def test_media_requests_router_does_not_import_private_playback_stats():
    path = _REPO_ROOT / "app/domains/media_requests/router.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.playback.stats":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.playback" and (
                "stats" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.playback.stats" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_get_safe_top_media_uses_playback_public_facade_before_media_filter(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []
    request = SimpleNamespace(session={"req_user": {"Id": "user-1"}})

    def fake_api_top_movies(**kwargs):
        calls.append(("api_top_movies", kwargs))
        return {"status": "success", "data": [{"ItemId": "item-1", "Name": "Top Movie"}]}

    monkeypatch.setattr(media_requests_router, "_check_user_exists", lambda user_id: True)
    monkeypatch.setattr(media_requests_router, "_get_cache", lambda key: None)
    monkeypatch.setattr(
        media_requests_router,
        "_set_cache",
        lambda *args: calls.append(("_set_cache", args)),
    )
    monkeypatch.setattr(media_requests_router.playback_service, "api_top_movies", fake_api_top_movies)
    monkeypatch.setattr(media_requests_router, "media_api", FakeMediaApi(calls))

    response = media_requests_router.get_safe_top_media("Movie", request)

    assert response == {
        "status": "success",
        "data": [{"ItemId": "item-1", "Name": "Top Movie"}],
        "from_cache": True,
    }
    assert calls[0] == (
        "api_top_movies",
        {"user_id": "all", "category": "Movie", "sort_by": "count"},
    )
    assert calls.index(("_set_cache", ("safe_top_Movie", [{"ItemId": "item-1", "Name": "Top Movie"}], 300))) < next(
        index for index, call in enumerate(calls) if call[0] == "media_get"
    )


def test_get_safe_latest_uses_playback_public_facade_before_media_filter(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []
    request = SimpleNamespace(session={"req_user": {"Id": "user-1"}})

    def fake_api_latest_media(**kwargs):
        calls.append(("api_latest_media", kwargs))
        return {"status": "success", "data": [{"Id": "latest-1", "Name": "Latest Movie"}]}

    monkeypatch.setattr(media_requests_router, "_check_user_exists", lambda user_id: True)
    monkeypatch.setattr(media_requests_router, "_get_cache", lambda key: None)
    monkeypatch.setattr(
        media_requests_router,
        "_set_cache",
        lambda *args: calls.append(("_set_cache", args)),
    )
    monkeypatch.setattr(media_requests_router.playback_service, "api_latest_media", fake_api_latest_media)
    monkeypatch.setattr(media_requests_router, "media_api", FakeMediaApi(calls))

    response = media_requests_router.get_safe_latest(limit=10, request=request)

    assert response == {
        "status": "success",
        "data": [{"Id": "latest-1", "Name": "Latest Movie"}],
        "from_cache": True,
    }
    assert calls[0] == ("api_latest_media", {"limit": 40})
    assert calls.index(("_set_cache", ("safe_latest", [{"Id": "latest-1", "Name": "Latest Movie"}], 180))) < next(
        index for index, call in enumerate(calls) if call[0] == "media_get"
    )


def test_refresh_community_cache_uses_playback_public_facade_for_latest_and_top(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []

    def fake_api_latest_media(**kwargs):
        calls.append(("api_latest_media", kwargs))
        return {"status": "success", "data": [{"Id": "latest-1"}]}

    def fake_api_top_movies(**kwargs):
        calls.append(("api_top_movies", kwargs))
        return {"status": "success", "data": [{"ItemId": f"top-{kwargs['category']}"}]}

    monkeypatch.setattr(media_requests_router, "get_emby_admin", lambda: "admin")
    monkeypatch.setattr(media_requests_router, "media_api", FakeMediaApi(calls))
    monkeypatch.setattr(media_requests_router.playback_service, "api_latest_media", fake_api_latest_media)
    monkeypatch.setattr(media_requests_router.playback_service, "api_top_movies", fake_api_top_movies)
    monkeypatch.setattr(
        media_requests_router,
        "_set_cache",
        lambda *args: calls.append(("_set_cache", args)),
    )

    media_requests_router._refresh_community_cache()

    assert ("api_latest_media", {"limit": 40}) in calls
    assert ("api_top_movies", {"user_id": "all", "category": "Movie", "sort_by": "count"}) in calls
    assert ("api_top_movies", {"user_id": "all", "category": "Episode", "sort_by": "count"}) in calls
    assert ("_set_cache", ("safe_latest", [{"Id": "latest-1"}], 180)) in calls
    assert ("_set_cache", ("safe_top_Movie", [{"ItemId": "top-Movie"}], 300)) in calls
    assert ("_set_cache", ("safe_top_Episode", [{"ItemId": "top-Episode"}], 300)) in calls
