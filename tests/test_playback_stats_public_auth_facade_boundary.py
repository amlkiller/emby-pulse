import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_playback_stats_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/playback/stats.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_playback_stats_includes_libraries_child_route_and_compat_export():
    from app.domains.playback import libraries_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/libraries" and "GET" in methods for path, methods in routes)
    assert stats.api_get_libraries is libraries_router.api_get_libraries

    dashboard_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/dashboard" and "GET" in methods
    )
    libraries_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/libraries" and "GET" in methods
    )
    recent_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/recent" and "GET" in methods
    )
    assert dashboard_index < libraries_index < recent_index


def test_playback_stats_includes_latest_child_route_and_compat_export():
    from app.domains.playback import latest_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/latest" and "GET" in methods for path, methods in routes)
    assert stats.api_latest_media is latest_router.api_latest_media

    recent_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/recent" and "GET" in methods
    )
    latest_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/latest" and "GET" in methods
    )
    live_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/live" and "GET" in methods
    )
    assert recent_index < latest_index < live_index


def test_playback_stats_includes_live_child_routes_and_compat_exports():
    from app.domains.playback import live_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/live" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/live" and "GET" in methods for path, methods in routes)
    assert stats.api_live_sessions is live_router.api_live_sessions
    assert stats.api_live_sessions_legacy is live_router.api_live_sessions_legacy

    latest_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/latest" and "GET" in methods
    )
    live_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/live" and "GET" in methods
    )
    legacy_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/live" and "GET" in methods
    )
    top_movies_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/top_movies" and "GET" in methods
    )
    assert latest_index < live_index < legacy_index < top_movies_index


def test_playback_stats_includes_top_movies_child_route_and_compat_export():
    from app.domains.playback import stats
    from app.domains.playback import top_movies_router

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/top_movies" and "GET" in methods for path, methods in routes)
    assert stats.api_top_movies is top_movies_router.api_top_movies

    legacy_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/live" and "GET" in methods
    )
    top_movies_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/top_movies" and "GET" in methods
    )
    user_details_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/user_details" and "GET" in methods
    )
    assert legacy_index < top_movies_index < user_details_index


def test_playback_stats_includes_user_details_child_route_and_compat_export():
    from app.domains.playback import stats
    from app.domains.playback import user_details_router

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/user_details" and "GET" in methods for path, methods in routes)
    assert stats.api_user_details is user_details_router.api_user_details

    top_movies_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/top_movies" and "GET" in methods
    )
    user_details_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/user_details" and "GET" in methods
    )
    chart_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/chart" and "GET" in methods
    )
    assert top_movies_index < user_details_index < chart_index


def test_user_details_denies_unauthenticated_before_query_or_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("user details should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("user details should not query playback stats without login")

    def fail_media_get(*args, **kwargs):
        raise AssertionError("user details should not read media API without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)

    response = stats.api_user_details(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_user_details_allows_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"role": "admin"}})
    calls = []

    class MediaResponse:
        status_code = 500

        def json(self):
            raise AssertionError("500 user detail response should not be decoded")

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE UserId = ?", [user_id]

    def fake_get_playback_column_name():
        calls.append(("get_playback_column_name",))
        return "ClientName"

    def fake_query(sql, params):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params)))
        if normalized_sql == "SELECT * FROM PlaybackActivity LIMIT 1":
            return [
                {
                    "DateCreated": "2026-06-03T12:30:00",
                    "ItemName": "Movie One",
                    "ItemId": "m1",
                    "PlayDuration": 120,
                    "UserId": "u1",
                    "ItemType": "Movie",
                    "DeviceName": "TV",
                    "ClientName": "Emby Theater",
                }
            ]
        return [
            {
                "DateCreated": "2026-06-03T12:30:00",
                "ItemName": "Movie One",
                "ItemId": "m1",
                "PlayDuration": 120,
                "UserId": "u1",
                "ItemType": "Movie",
                "Device": "TV",
                "Client": "Emby Theater",
            },
            {
                "DateCreated": "2026-06-03 13:00:00",
                "ItemName": "Episode One",
                "ItemId": "e1",
                "PlayDuration": 60,
                "UserId": "u2",
                "ItemType": "Episode",
                "Device": "Phone",
                "Client": "Mobile",
            },
        ]

    def fake_get_user_map_local():
        calls.append(("get_user_map_local",))
        return {"u1": "Alice", "u2": "Bob"}

    def fake_get_clean_name(name, item_type):
        calls.append(("get_clean_name", name, item_type))
        return name

    def fake_resolve_poster_ids(items):
        calls.append(("resolve_poster_ids", [item.get("ItemId") for item in items]))
        for item in items:
            item["PosterResolved"] = True

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        return MediaResponse()

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats, "get_playback_column_name", fake_get_playback_column_name)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)
    monkeypatch.setattr(stats, "get_user_map_local", fake_get_user_map_local)
    monkeypatch.setattr(stats, "get_clean_name", fake_get_clean_name)
    monkeypatch.setattr(stats, "resolve_poster_ids", fake_resolve_poster_ids)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)

    response = stats.api_user_details(request, user_id="u1")

    assert response["status"] == "success"
    data = response["data"]
    assert data["hourly"]["12"] == 1
    assert data["hourly"]["13"] == 1
    assert data["devices"] == [{"Device": "TV", "Plays": 1}, {"Device": "Phone", "Plays": 1}]
    assert data["clients"] == [{"Client": "Emby Theater", "Plays": 1}, {"Client": "Mobile", "Plays": 1}]
    assert data["preference"] == {"movie_plays": 1, "episode_plays": 1}
    assert data["overview"] == {
        "total_plays": 2,
        "total_duration": 180,
        "avg_duration": 90,
        "account_age_days": 1,
    }
    assert data["logs"][0]["UserName"] == "Alice"
    assert data["logs"][0]["PosterResolved"] is True
    assert data["top_fav"]["ItemName"] == "Movie One"
    assert data["top_fav"]["PosterResolved"] is True
    assert calls == [
        ("check_login", request),
        ("build_stats_base_filter", "u1"),
        ("get_playback_column_name",),
        ("query", "SELECT * FROM PlaybackActivity LIMIT 1", []),
        (
            "query",
            "SELECT DateCreated, ItemName, ItemId, PlayDuration, UserId, ItemType, COALESCE(DeviceName, 'Unknown') as Device, COALESCE(ClientName, 'Unknown') as Client FROM PlaybackActivity WHERE UserId = ? ORDER BY DateCreated DESC",
            ["u1"],
        ),
        ("get_user_map_local",),
        ("get_clean_name", "Movie One", "Movie"),
        ("get_clean_name", "Episode One", "Episode"),
        ("resolve_poster_ids", ["m1", "e1"]),
        ("resolve_poster_ids", ["m1"]),
        ("media_get", "/Users/u1", 3),
    ]


def test_top_movies_denies_unauthenticated_before_query_or_poster_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("top movies should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("top movies should not query playback stats without login")

    def fail_resolve_poster_ids(*args, **kwargs):
        raise AssertionError("top movies should not resolve posters without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats, "resolve_poster_ids", fail_resolve_poster_ids)

    response = stats.api_top_movies(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_top_movies_allows_internal_call_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    calls = []

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE 1=1", []

    def fake_query(sql, params):
        calls.append(("query", sql, list(params)))
        return [
            {"ItemName": "Movie One", "ItemId": "m1", "ItemType": "Movie", "PlayDuration": 120},
            {"ItemName": "Movie One", "ItemId": "m1", "ItemType": "Movie", "PlayDuration": 30},
            {"ItemName": "Movie Two", "ItemId": "m2", "ItemType": "Movie", "PlayDuration": 60},
        ]

    def fake_get_clean_name(name, item_type):
        calls.append(("get_clean_name", name, item_type))
        return name

    def fake_resolve_poster_ids(items):
        calls.append(("resolve_poster_ids", [(item["ItemName"], item["ItemId"]) for item in items]))
        for item in items:
            item["PosterResolved"] = True

    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)
    monkeypatch.setattr(stats, "get_clean_name", fake_get_clean_name)
    monkeypatch.setattr(stats, "resolve_poster_ids", fake_resolve_poster_ids)

    response = stats.api_top_movies(
        request=None,
        user_id="all",
        category="Movie",
        sort_by="time",
        exclude_types="Audio, MusicVideo",
        period="month",
    )

    assert response == {
        "status": "success",
        "data": [
            {
                "ItemName": "Movie One",
                "ItemId": "m1",
                "PlayCount": 2,
                "TotalTime": 150,
                "PosterResolved": True,
            },
            {
                "ItemName": "Movie Two",
                "ItemId": "m2",
                "PlayCount": 1,
                "TotalTime": 60,
                "PosterResolved": True,
            },
        ],
    }
    assert calls == [
        ("build_stats_base_filter", "all"),
        (
            "query",
            "SELECT ItemName, ItemId, ItemType, PlayDuration FROM PlaybackActivity WHERE 1=1 AND DateCreated >= date('now', 'localtime', 'start of month') AND ItemType = 'Movie' AND ItemType NOT IN (?,?) LIMIT 5000",
            ["Audio", "MusicVideo"],
        ),
        ("get_clean_name", "Movie One", "Movie"),
        ("get_clean_name", "Movie One", "Movie"),
        ("get_clean_name", "Movie Two", "Movie"),
        ("resolve_poster_ids", [("Movie One", "m1"), ("Movie Two", "m2")]),
    ]


def test_live_sessions_denies_non_admin_before_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_media_get(*args, **kwargs):
        raise AssertionError("live sessions should not be read without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)

    response = stats.api_live_sessions(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_live_sessions_legacy_allows_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    class SessionsResponse:
        status_code = 200

        def json(self):
            calls.append(("sessions_json",))
            return [
                {"Id": "s1", "NowPlayingItem": {"Name": "Movie One"}},
                {"Id": "s2"},
            ]

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        return SessionsResponse()

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)

    response = stats.api_live_sessions_legacy(request)

    assert response == {
        "status": "success",
        "data": [{"Id": "s1", "NowPlayingItem": {"Name": "Movie One"}}],
    }
    assert calls == [
        ("is_admin_user", request),
        ("is_admin_user", request),
        ("media_get", "/Sessions", 5),
        ("sessions_json",),
    ]


def test_latest_media_denies_unauthenticated_before_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_admin_user_id():
        raise AssertionError("admin media user should not be queried without login")

    def fail_media_get(*args, **kwargs):
        raise AssertionError("latest media should not be read without login")

    def fail_get_safe_proxies():
        raise AssertionError("proxies should not be read without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "get_admin_user_id", fail_get_admin_user_id)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)
    monkeypatch.setattr(stats, "get_safe_proxies", fail_get_safe_proxies)

    response = stats.api_latest_media(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_latest_media_allows_internal_call_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    calls = []

    class ItemsResponse:
        status_code = 200

        def json(self):
            calls.append(("items_json",))
            return {
                "Items": [
                    {
                        "Id": "movie-1",
                        "Name": "Movie One",
                        "Type": "Movie",
                        "ProductionYear": 2026,
                        "ProviderIds": {"Tmdb": "tmdb-1"},
                        "ImageTags": {"Primary": "abcdef123456"},
                    }
                ]
            }

    class TmdbResponse:
        status_code = 200

        def json(self):
            calls.append(("tmdb_json",))
            return {"poster_path": "/poster.jpg", "overview": "overview text"}

    class FakeTmdbClient:
        def get_movie_details(self, tmdb_id, proxies=None, timeout=None):
            calls.append(("tmdb_movie", tmdb_id, proxies, timeout))
            return TmdbResponse()

        def get_tv_details(self, *args, **kwargs):
            raise AssertionError("movie-only latest data should not fetch TV details")

    def fake_get_admin_user_id():
        calls.append(("get_admin_user_id",))
        return "admin-id"

    def fake_media_get(path, params=None, timeout=None):
        calls.append(("media_get", path, params, timeout))
        return ItemsResponse()

    def fake_get_safe_proxies():
        calls.append(("get_safe_proxies",))
        return {"http": "http://proxy"}

    monkeypatch.setattr(stats, "get_admin_user_id", fake_get_admin_user_id)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)
    monkeypatch.setattr(stats, "tmdb_client", FakeTmdbClient())
    monkeypatch.setattr(stats, "get_safe_proxies", fake_get_safe_proxies)

    response = stats.api_latest_media(request=None, limit=1)

    assert response == {
        "status": "success",
        "data": [
            {
                "Id": "movie-1",
                "Name": "Movie One",
                "Year": 2026,
                "Type": "Movie",
                "Poster": "",
                "Overview": "",
                "TmdbId": "tmdb-1",
                "ImageTag": "abcdef12",
            }
        ],
    }
    assert calls == [
        ("get_admin_user_id",),
        ("media_get", "/Users/admin-id/Items", {
            "SortBy": "DateCreated", "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Episode", "Recursive": "true",
            "Limit": 500, "Fields": "ProductionYear,SeriesName,SeriesId,ParentIndexNumber,IndexNumber,DateCreated,Overview,ImageTags,ProviderIds"
        }, 15),
        ("items_json",),
        ("get_safe_proxies",),
        ("tmdb_movie", "tmdb-1", {"http": "http://proxy"}, 8),
        ("tmdb_json",),
    ]


def test_get_libraries_denies_non_admin_before_query_or_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_media_get(*args, **kwargs):
        raise AssertionError("media libraries should not be read without admin permission")

    def fail_get_admin_user_id():
        raise AssertionError("admin media user should not be queried without admin permission")

    def fail_playback_query(*args, **kwargs):
        raise AssertionError("stats queries should not run without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)
    monkeypatch.setattr(stats, "get_admin_user_id", fail_get_admin_user_id)
    monkeypatch.setattr(stats.playback_store, "query", fail_playback_query)

    response = stats.api_get_libraries(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_libraries_allows_admin_through_public_facade(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    class LibrariesResponse:
        status_code = 200

        def json(self):
            calls.append(("libraries_json",))
            return [
                {
                    "ItemId": "lib-1",
                    "Name": "Movies",
                    "CollectionType": "movies",
                }
            ]

    class ItemResponse:
        status_code = 200

        def json(self):
            calls.append(("item_json",))
            return {"ImageTags": {"Primary": "abcdef123456"}}

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        if path == "/Library/VirtualFolders":
            return LibrariesResponse()
        if path == "/Users/admin-id/Items/lib-1":
            return ItemResponse()
        raise AssertionError(f"unexpected media path: {path}")

    def fake_get_admin_user_id():
        calls.append(("get_admin_user_id",))
        return "admin-id"

    def fail_playback_query(*args, **kwargs):
        raise AssertionError("library listing should not query playback stats")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)
    monkeypatch.setattr(stats, "get_admin_user_id", fake_get_admin_user_id)
    monkeypatch.setattr(stats.playback_store, "query", fail_playback_query)

    response = stats.api_get_libraries(request)

    assert response == {
        "status": "success",
        "data": [
            {
                "Id": "lib-1",
                "Name": "Movies",
                "CollectionType": "movies",
                "ImageTag": "abcdef12",
            }
        ],
    }
    assert calls == [
        ("is_admin_user", request),
        ("media_get", "/Library/VirtualFolders", 10),
        ("libraries_json",),
        ("get_admin_user_id",),
        ("media_get", "/Users/admin-id/Items/lib-1", 3),
        ("item_json",),
    ]
