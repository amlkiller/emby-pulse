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


def test_playback_stats_includes_dashboard_child_route_and_compat_export():
    from app.domains.playback import dashboard_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/dashboard" and "GET" in methods for path, methods in routes)
    assert stats.api_dashboard is dashboard_router.api_dashboard

    dashboard_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/dashboard" and "GET" in methods
    )
    libraries_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/libraries" and "GET" in methods
    )
    assert dashboard_index < libraries_index


def test_dashboard_denies_unauthenticated_before_cache_query_or_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_cached_stats(*args, **kwargs):
        raise AssertionError("dashboard should not read cache without login")

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("dashboard should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("dashboard should not query playback stats without login")

    def fail_media_get(*args, **kwargs):
        raise AssertionError("dashboard should not read media counts without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "get_cached_stats", fail_get_cached_stats)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)

    response = stats.api_dashboard(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_dashboard_cache_hit_uses_scoped_key_and_skips_query_or_media(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []
    cached_response = {"status": "success", "data": {"cached": True}}

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_get_cached_stats(cache_key):
        calls.append(("get_cached_stats", cache_key))
        return cached_response

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("dashboard cache hit should not build stats filter")

    def fail_query(*args, **kwargs):
        raise AssertionError("dashboard cache hit should not query playback stats")

    def fail_media_get(*args, **kwargs):
        raise AssertionError("dashboard cache hit should not read media counts")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "get_cached_stats", fake_get_cached_stats)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)

    response = stats.api_dashboard(request, user_id="all")

    assert response is cached_response
    assert calls == [
        ("check_login", request),
        ("get_cached_stats", "dashboard_local-u"),
    ]


def test_dashboard_cache_miss_allows_non_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []

    class CountsResponse:
        status_code = 200

        def json(self):
            calls.append(("counts_json",))
            return {"MovieCount": 4, "SeriesCount": 2, "EpisodeCount": 9}

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_get_cached_stats(cache_key):
        calls.append(("get_cached_stats", cache_key))
        return None

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE UserId = ?", [user_id]

    def fake_query(sql, params):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params)))
        if "COUNT(*) as c" in normalized_sql:
            return [{"c": 11}]
        if "COUNT(DISTINCT UserId) as c" in normalized_sql:
            return [{"c": 1}]
        if "SUM(PlayDuration) as c" in normalized_sql:
            return [{"c": 3600}]
        raise AssertionError(f"unexpected dashboard query: {normalized_sql}")

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        return CountsResponse()

    def fake_set_cached_stats(cache_key, value):
        calls.append(("set_cached_stats", cache_key, value))

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "get_cached_stats", fake_get_cached_stats)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)
    monkeypatch.setattr(stats, "set_cached_stats", fake_set_cached_stats)

    response = stats.api_dashboard(request, user_id="all")

    expected_response = {
        "status": "success",
        "data": {
            "total_plays": 11,
            "active_users": 1,
            "total_duration": 3600,
            "library": {"movie": 4, "series": 2, "episode": 9},
        },
    }
    assert response == expected_response
    assert calls == [
        ("check_login", request),
        ("get_cached_stats", "dashboard_local-u"),
        ("build_stats_base_filter", "local-u"),
        ("query", "SELECT COUNT(*) as c FROM PlaybackActivity WHERE UserId = ?", ["local-u"]),
        (
            "query",
            "SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-30 days')",
            ["local-u"],
        ),
        ("query", "SELECT SUM(PlayDuration) as c FROM PlaybackActivity WHERE UserId = ?", ["local-u"]),
        ("media_get", "/Items/Counts", 5),
        ("counts_json",),
        ("set_cached_stats", "dashboard_local-u", expected_response),
    ]


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


def test_playback_stats_includes_recent_activity_child_route_and_compat_export():
    from app.domains.playback import recent_activity_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/recent" and "GET" in methods for path, methods in routes)
    assert stats.api_recent_activity is recent_activity_router.api_recent_activity

    libraries_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/libraries" and "GET" in methods
    )
    recent_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/recent" and "GET" in methods
    )
    latest_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/latest" and "GET" in methods
    )
    assert libraries_index < recent_index < latest_index


def test_recent_activity_denies_unauthenticated_before_query_or_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("recent activity should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("recent activity should not query playback stats without login")

    def fail_media_get(*args, **kwargs):
        raise AssertionError("recent activity should not fetch media tags without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)

    response = stats.api_recent_activity(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_recent_activity_allows_non_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE UserId = ?", [user_id]

    def fake_query(sql, params):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params)))
        return [
            {
                "DateCreated": "2026-06-03T12:00:00",
                "UserId": "local-u",
                "ItemId": "item-1",
                "ItemName": "",
                "ItemType": "Movie",
            }
        ]

    def fake_get_user_map_local():
        calls.append(("get_user_map_local",))
        return {"local-u": "Local User"}

    def fake_media_get(path, params=None, timeout=None):
        calls.append(("media_get", path, dict(params or {}), timeout))
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"Items": [{"Id": "item-1", "ImageTags": {"Primary": "abcdef123456"}}]},
        )

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)
    monkeypatch.setattr(stats, "get_user_map_local", fake_get_user_map_local)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)

    response = stats.api_recent_activity(request, user_id="all")

    assert response == {
        "status": "success",
        "data": [
            {
                "DateCreated": "2026-06-03T12:00:00",
                "ItemId": "item-1",
                "ItemName": "",
                "ItemType": "Movie",
                "UserName": "Local User",
                "DisplayName": "未知记录",
                "ImageTag": "abcdef12",
            }
        ],
    }
    assert calls == [
        ("check_login", request),
        ("build_stats_base_filter", "local-u"),
        (
            "query",
            "SELECT DateCreated, UserId, ItemId, ItemName, ItemType FROM PlaybackActivity WHERE UserId = ? ORDER BY DateCreated DESC LIMIT 50",
            ["local-u"],
        ),
        ("get_user_map_local",),
        ("media_get", "/Items", {"Ids": "item-1", "Fields": "ImageTags"}, 5),
    ]


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


def test_playback_stats_includes_chart_child_routes_and_compat_export():
    from app.domains.playback import chart_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/chart" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/stats/trend" and "GET" in methods for path, methods in routes)
    assert stats.api_chart_stats is chart_router.api_chart_stats

    user_details_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/user_details" and "GET" in methods
    )
    chart_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/chart" and "GET" in methods
    )
    trend_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/trend" and "GET" in methods
    )
    poster_data_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/poster_data" and "GET" in methods
    )
    assert user_details_index < chart_index < trend_index < poster_data_index


def test_chart_stats_denies_unauthenticated_before_query_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("chart stats should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("chart stats should not query playback stats without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)

    response = stats.api_chart_stats(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_chart_stats_allows_non_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE UserId = ?", [user_id]

    def fake_query(sql, params):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params)))
        return [{"Label": "2026-06", "Duration": 120}]

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)

    response = stats.api_chart_stats(request, user_id="all", dimension="month")

    assert response == {"status": "success", "data": {"2026-06": 120}}
    assert calls == [
        ("check_login", request),
        ("build_stats_base_filter", "local-u"),
        (
            "query",
            "SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-365 days') GROUP BY Label ORDER BY Label",
            ["local-u"],
        ),
    ]


def test_playback_stats_includes_poster_child_route_and_compat_export():
    from app.domains.playback import poster_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/poster_data" and "GET" in methods for path, methods in routes)
    assert stats.api_poster_data is poster_router.api_poster_data

    chart_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/chart" and "GET" in methods
    )
    trend_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/trend" and "GET" in methods
    )
    poster_data_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/poster_data" and "GET" in methods
    )
    top_users_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/top_users_list" and "GET" in methods
    )
    assert chart_index < trend_index < poster_data_index < top_users_index


def test_poster_data_denies_unauthenticated_before_query_or_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("poster data should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("poster data should not query playback stats without login")

    def fail_media_get(*args, **kwargs):
        raise AssertionError("poster data should not read media API without login")

    def fail_resolve_poster_ids(*args, **kwargs):
        raise AssertionError("poster data should not resolve posters without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)
    monkeypatch.setattr(stats, "resolve_poster_ids", fail_resolve_poster_ids)

    response = stats.api_poster_data(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_poster_data_allows_non_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []

    class GenreResponse:
        status_code = 200

        def json(self):
            calls.append(("genre_json",))
            return {"Genres": ["Drama", "Sci-Fi"]}

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        if user_id == "all":
            return "WHERE 1=1", []
        return "WHERE UserId = ?", [user_id]

    def fake_query(sql, params, one=False):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params), one))
        if "COUNT(*) as Plays" in normalized_sql:
            return [{"Plays": 99}]
        if "COUNT(*) as plays" in normalized_sql:
            return {"plays": 2, "duration": 7200}
        if "GROUP BY day" in normalized_sql:
            return [{"day": "2026-06-01", "duration": 7200}]
        if "BETWEEN 1 AND 5" in normalized_sql:
            return {"DateCreated": "2026-06-01T02:30:00", "ItemName": "Movie One", "ItemType": "Movie"}
        return [
            {
                "ItemName": "Movie One",
                "ItemId": "m1",
                "ItemType": "Movie",
                "Count": 2,
                "Duration": 7200,
            }
        ]

    def fake_media_get(path, params=None, timeout=None):
        calls.append(("media_get", path, params, timeout))
        return GenreResponse()

    def fake_get_clean_name(name, item_type):
        calls.append(("get_clean_name", name, item_type))
        return name

    def fake_resolve_poster_ids(items):
        calls.append(("resolve_poster_ids", [(item["ItemName"], item["ItemId"]) for item in items]))
        for item in items:
            item["PosterResolved"] = True

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)
    monkeypatch.setattr(stats, "get_clean_name", fake_get_clean_name)
    monkeypatch.setattr(stats, "resolve_poster_ids", fake_resolve_poster_ids)

    response = stats.api_poster_data(request, user_id="all", period="month")

    assert response == {
        "status": "success",
        "data": {
            "plays": 2,
            "hours": 2,
            "server_plays": 99,
            "top_list": [
                {
                    "ItemName": "Movie One",
                    "ItemId": "m1",
                    "Count": 2,
                    "Duration": 7200,
                    "PosterResolved": True,
                }
            ],
            "daily_stats": [{"date": "2026-06-01", "duration": 7200}],
            "favorite_type": "Drama",
            "streak_days": 0,
            "mood_data": {
                "late_night": {"time": "02:30", "date": "06月01日", "name": "Movie One"},
                "binge_day": {"date": "06月01日", "hours": 2.0},
                "genres": ["Drama", "Sci-Fi"],
            },
        },
    }
    assert calls == [
        ("check_login", request),
        ("build_stats_base_filter", "local-u"),
        ("build_stats_base_filter", "all"),
        ("build_stats_base_filter", "all"),
        (
            "query",
            "SELECT COUNT(*) as Plays FROM PlaybackActivity WHERE 1=1 AND DateCreated > date('now', 'localtime', '-30 days')",
            [],
            False,
        ),
        (
            "query",
            "SELECT COUNT(*) as plays, COALESCE(SUM(PlayDuration), 0) as duration FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-30 days')",
            ["local-u"],
            True,
        ),
        (
            "query",
            "SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as day, COALESCE(SUM(PlayDuration), 0) as duration FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY day ORDER BY day DESC",
            ["local-u"],
            False,
        ),
        (
            "query",
            "SELECT DateCreated, ItemName, ItemType FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-30 days') AND CAST(substr(replace(DateCreated, 'T', ' '), 12, 2) AS INTEGER) BETWEEN 1 AND 5 ORDER BY substr(replace(DateCreated, 'T', ' '), 12, 8) DESC LIMIT 1",
            ["local-u"],
            True,
        ),
        ("get_clean_name", "Movie One", "Movie"),
        (
            "query",
            "SELECT ItemName, ItemId, ItemType, COUNT(*) as Count, COALESCE(SUM(PlayDuration), 0) as Duration FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY ItemName ORDER BY Count DESC LIMIT 200",
            ["local-u"],
            False,
        ),
        ("get_clean_name", "Movie One", "Movie"),
        ("media_get", "/Users/local-u/Items/m1", {"Fields": "Genres"}, 2),
        ("genre_json",),
        ("resolve_poster_ids", [("Movie One", "m1")]),
    ]


def test_playback_stats_includes_top_users_child_route_and_compat_export():
    from app.domains.playback import stats
    from app.domains.playback import top_users_router

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/top_users_list" and "GET" in methods for path, methods in routes)
    assert stats.api_top_users_list is top_users_router.api_top_users_list

    poster_data_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/poster_data" and "GET" in methods
    )
    top_users_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/top_users_list" and "GET" in methods
    )
    badges_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/badges" and "GET" in methods
    )
    assert poster_data_index < top_users_index < badges_index


def test_top_users_list_denies_non_admin_before_query_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("top users should not build stats filter without admin permission")

    def fail_query(*args, **kwargs):
        raise AssertionError("top users should not query playback stats without admin permission")

    def fail_get_user_map_local():
        raise AssertionError("top users should not read user map without admin permission")

    def fail_get_hidden_users():
        raise AssertionError("top users should not read hidden users without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)
    monkeypatch.setattr(stats, "get_user_map_local", fail_get_user_map_local)
    monkeypatch.setattr(stats, "get_hidden_users", fail_get_hidden_users)

    response = stats.api_top_users_list(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_top_users_list_allows_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE 1=1", []

    def fake_query(sql, params):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params)))
        return [
            {"UserId": "u1", "Plays": 7, "TotalTime": 700},
            {"UserId": "u2", "Plays": 6, "TotalTime": 600},
            {"UserId": "u3", "Plays": 5, "TotalTime": 500},
            {"UserId": "u4", "Plays": 4, "TotalTime": 400},
            {"UserId": "u5", "Plays": 3, "TotalTime": 300},
            {"UserId": "u6", "Plays": 2, "TotalTime": 200},
            {"UserId": "u7", "Plays": 1, "TotalTime": 100},
        ]

    def fake_get_user_map_local():
        calls.append(("get_user_map_local",))
        return {"u1": "Alice", "u3": "Carol", "u4": "Dave", "u5": "Eve", "u6": "Frank"}

    def fake_get_hidden_users():
        calls.append(("get_hidden_users",))
        return [2, "u7"]

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)
    monkeypatch.setattr(stats, "get_user_map_local", fake_get_user_map_local)
    monkeypatch.setattr(stats, "get_hidden_users", fake_get_hidden_users)

    response = stats.api_top_users_list(request, period="all")

    assert response == {
        "status": "success",
        "data": [
            {"UserId": "u1", "Plays": 7, "TotalTime": 700, "UserName": "Alice"},
            {"UserId": "u2", "Plays": 6, "TotalTime": 600, "UserName": "User u2"},
            {"UserId": "u3", "Plays": 5, "TotalTime": 500, "UserName": "Carol"},
            {"UserId": "u4", "Plays": 4, "TotalTime": 400, "UserName": "Dave"},
            {"UserId": "u5", "Plays": 3, "TotalTime": 300, "UserName": "Eve"},
        ],
    }
    assert calls == [
        ("is_admin_user", request),
        ("build_stats_base_filter", "all"),
        (
            "query",
            "SELECT UserId, COUNT(*) as Plays, SUM(PlayDuration) as TotalTime FROM PlaybackActivity WHERE 1=1 GROUP BY UserId ORDER BY TotalTime DESC LIMIT 10",
            [],
        ),
        ("get_user_map_local",),
        ("get_hidden_users",),
    ]


def test_playback_stats_includes_badges_child_route_and_compat_export():
    from app.domains.playback import badges_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/badges" and "GET" in methods for path, methods in routes)
    assert stats.api_badges is badges_router.api_badges

    top_users_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/top_users_list" and "GET" in methods
    )
    badges_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/badges" and "GET" in methods
    )
    monthly_stats_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/monthly_stats" and "GET" in methods
    )
    assert top_users_index < badges_index < monthly_stats_index


def test_badges_denies_unauthenticated_before_query_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("badges should not build stats filter without login")

    def fail_get_playback_column_name():
        raise AssertionError("badges should not inspect playback columns without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("badges should not query playback stats without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats, "get_playback_column_name", fail_get_playback_column_name)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)

    response = stats.api_badges(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_badges_allows_non_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []
    rows = [
        {"DateCreated": "2026-06-01T10:00:00", "PlayDuration": 200000, "Client": "TV", "ItemId": "m1", "ItemName": "Movie One", "ItemType": "Movie"},
        {"DateCreated": "2026-06-01T11:00:00", "PlayDuration": 1000, "Client": "Phone", "ItemId": "m1", "ItemName": "Movie One", "ItemType": "Movie"},
        {"DateCreated": "2026-06-01T12:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m1", "ItemName": "Movie One", "ItemType": "Movie"},
        {"DateCreated": "2026-06-01T13:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m2", "ItemName": "Movie Two", "ItemType": "Movie"},
        {"DateCreated": "2026-06-01T14:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m3", "ItemName": "Movie Three", "ItemType": "Movie"},
        {"DateCreated": "2026-06-06T03:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m4", "ItemName": "Movie Four", "ItemType": "Movie"},
        {"DateCreated": "2026-06-06T04:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m5", "ItemName": "Movie Five", "ItemType": "Movie"},
        {"DateCreated": "2026-06-06T05:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m6", "ItemName": "Movie Six", "ItemType": "Movie"},
        {"DateCreated": "2026-06-06T06:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "m7", "ItemName": "Movie Seven", "ItemType": "Movie"},
        {"DateCreated": "2026-06-07T10:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "e1", "ItemName": "Episode One", "ItemType": "Episode"},
        {"DateCreated": "2026-06-07T11:00:00", "PlayDuration": 1000, "Client": "TV", "ItemId": "e2", "ItemName": "Episode Two", "ItemType": "Episode"},
    ]

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
        return rows

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats, "get_playback_column_name", fake_get_playback_column_name)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)

    response = stats.api_badges(request, user_id="all")

    assert response["status"] == "success"
    badge_ids = [badge["id"] for badge in response["data"]]
    assert badge_ids == [
        "night",
        "weekend",
        "liver",
        "fish",
        "morning",
        "device",
        "loyal",
        "movie_lover",
    ]
    loyal_badge = next(badge for badge in response["data"] if badge["id"] == "loyal")
    assert loyal_badge["desc"] == "对《Movie One》爱得深沉"
    assert calls == [
        ("check_login", request),
        ("build_stats_base_filter", "local-u"),
        ("get_playback_column_name",),
        (
            "query",
            "SELECT DateCreated, PlayDuration, COALESCE(ClientName, DeviceName) as Client, ItemId, ItemName, ItemType FROM PlaybackActivity WHERE UserId = ?",
            ["local-u"],
        ),
    ]


def test_playback_stats_includes_monthly_child_route_and_compat_export():
    from app.domains.playback import monthly_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/monthly_stats" and "GET" in methods for path, methods in routes)
    assert stats.api_monthly_stats is monthly_router.api_monthly_stats

    badges_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/badges" and "GET" in methods
    )
    monthly_stats_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/monthly_stats" and "GET" in methods
    )
    recent_added_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/recent_added" and "GET" in methods
    )
    assert badges_index < monthly_stats_index < recent_added_index


def test_monthly_stats_denies_unauthenticated_before_query_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_build_stats_base_filter(*args, **kwargs):
        raise AssertionError("monthly stats should not build stats filter without login")

    def fail_query(*args, **kwargs):
        raise AssertionError("monthly stats should not query playback stats without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fail_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fail_query)

    response = stats.api_monthly_stats(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_monthly_stats_allows_non_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"id": "local-u"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_build_stats_base_filter(user_id):
        calls.append(("build_stats_base_filter", user_id))
        return "WHERE UserId = ?", [user_id]

    def fake_query(sql, params):
        normalized_sql = " ".join(sql.split())
        calls.append(("query", normalized_sql, list(params)))
        return [
            {"Month": "2026-05", "Duration": 120},
            {"Month": "2026-06", "Duration": None},
        ]

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "build_stats_base_filter", fake_build_stats_base_filter)
    monkeypatch.setattr(stats.playback_store, "query", fake_query)

    response = stats.api_monthly_stats(request, user_id="all")

    assert response == {"status": "success", "data": {"2026-05": 120, "2026-06": 0}}
    assert calls == [
        ("check_login", request),
        ("build_stats_base_filter", "local-u"),
        (
            "query",
            "SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Month, SUM(PlayDuration) as Duration FROM PlaybackActivity WHERE UserId = ? AND DateCreated > date('now', 'localtime', '-12 months') GROUP BY Month ORDER BY Month",
            ["local-u"],
        ),
    ]


def test_playback_stats_includes_recent_added_child_route_and_compat_export():
    from app.domains.playback import recent_added_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/stats/recent_added" and "GET" in methods for path, methods in routes)
    assert stats.api_recent_added is recent_added_router.api_recent_added

    monthly_stats_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/monthly_stats" and "GET" in methods
    )
    recent_added_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/recent_added" and "GET" in methods
    )
    preload_status_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/dashboard/preload_status" and "GET" in methods
    )
    assert monthly_stats_index < recent_added_index < preload_status_index


def test_recent_added_denies_unauthenticated_before_stats_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_added_stats_sync():
        raise AssertionError("recent added should not fetch stats without login")

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "_get_added_stats_sync", fail_get_added_stats_sync)

    response = stats.api_recent_added(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_recent_added_internal_call_skips_login_and_uses_stats_monkeypatch(monkeypatch):
    from app.domains.playback import stats

    calls = []

    def fail_check_login(*args, **kwargs):
        raise AssertionError("internal recent added call should skip login")

    def fake_get_added_stats_sync():
        calls.append("get_added_stats_sync")
        return {"total": 3, "week": [0, 1, 2]}

    monkeypatch.setattr(stats, "check_login", fail_check_login)
    monkeypatch.setattr(stats, "_get_added_stats_sync", fake_get_added_stats_sync)

    response = stats.api_recent_added()

    assert response == {"status": "success", "data": {"total": 3, "week": [0, 1, 2]}}
    assert calls == ["get_added_stats_sync"]


def test_recent_added_authenticated_call_uses_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_check_login(seen_request):
        calls.append(("check_login", seen_request))
        return True

    def fake_get_added_stats_sync():
        calls.append(("get_added_stats_sync",))
        return {"libraries": [{"Name": "Movies", "count": 2}]}

    monkeypatch.setattr(stats, "check_login", fake_check_login)
    monkeypatch.setattr(stats, "_get_added_stats_sync", fake_get_added_stats_sync)

    response = stats.api_recent_added(request)

    assert response == {"status": "success", "data": {"libraries": [{"Name": "Movies", "count": 2}]}}
    assert calls == [
        ("check_login", request),
        ("get_added_stats_sync",),
    ]


def test_playback_stats_includes_preload_status_child_route_and_compat_export():
    from app.domains.playback import preload_status_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/dashboard/preload_status" and "GET" in methods for path, methods in routes)
    assert stats.api_preload_status is preload_status_router.api_preload_status

    recent_added_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/recent_added" and "GET" in methods
    )
    preload_status_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/dashboard/preload_status" and "GET" in methods
    )
    dashboard_init_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/dashboard/init" and "GET" in methods
    )
    assert recent_added_index < preload_status_index < dashboard_init_index


def test_preload_status_denies_non_admin_before_cache_side_effects(monkeypatch):
    import asyncio

    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_dashboard_cache_entry(*args, **kwargs):
        raise AssertionError("preload status should not read cache without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "_get_dashboard_cache_entry", fail_get_dashboard_cache_entry)

    response = asyncio.run(stats.api_preload_status(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_preload_status_allows_admin_through_stats_monkeypatches(monkeypatch):
    import asyncio

    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_dashboard_cache_entry(cache_key):
        calls.append(("get_dashboard_cache_entry", cache_key))
        return {
            "data": {
                "libraries": [{"Id": "l1"}, {"Id": "l2"}],
                "users": [{"Id": "u1"}],
            },
            "ts": 90.4,
        }

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "_get_dashboard_cache_entry", fake_get_dashboard_cache_entry)
    monkeypatch.setattr(stats, "_DASHBOARD_PRELOAD_KEY", "custom-preload")
    monkeypatch.setattr(stats, "_DASHBOARD_CACHE_TTL", 321)
    monkeypatch.setattr(stats, "time", SimpleNamespace(time=lambda: 100.9))

    response = asyncio.run(stats.api_preload_status(request))

    assert response == {
        "status": "success",
        "data": {
            "cached": True,
            "cache_age": 10,
            "cache_ttl": 321,
            "libraries_count": 2,
            "users_count": 1,
        },
    }
    assert calls == [
        ("is_admin_user", request),
        ("get_dashboard_cache_entry", "custom-preload"),
    ]


def test_playback_stats_includes_dashboard_init_child_route_and_compat_export():
    from app.domains.playback import dashboard_init_router
    from app.domains.playback import stats

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/dashboard/init" and "GET" in methods for path, methods in routes)
    assert stats.api_dashboard_init is dashboard_init_router.api_dashboard_init

    preload_status_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/dashboard/preload_status" and "GET" in methods
    )
    dashboard_init_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/dashboard/init" and "GET" in methods
    )
    system_monitor_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/system/monitor" and "GET" in methods
    )
    assert preload_status_index < dashboard_init_index < system_monitor_index


def test_dashboard_init_denies_non_admin_before_cache_or_fetch_side_effects(monkeypatch):
    import asyncio

    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_dashboard_context(*args, **kwargs):
        raise AssertionError("dashboard init should not resolve context without admin permission")

    def fail_get_dashboard_cached_data(*args, **kwargs):
        raise AssertionError("dashboard init should not read cache without admin permission")

    def fail_fetch_dashboard_core(*args, **kwargs):
        raise AssertionError("dashboard init should not fetch data without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "_get_dashboard_context", fail_get_dashboard_context)
    monkeypatch.setattr(stats, "_get_dashboard_cached_data", fail_get_dashboard_cached_data)
    monkeypatch.setattr(stats, "_fetch_dashboard_core", fail_fetch_dashboard_core)

    response = asyncio.run(stats.api_dashboard_init(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_dashboard_init_cache_hit_uses_stats_monkeypatches_and_strips_user_ids(monkeypatch):
    import asyncio

    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    cached_data = {
        "dashboard": {"total_plays": 3},
        "users": [],
        "libraries": [],
        "top_users": [{"UserId": "u1", "UserName": "Alice", "TotalTime": 90}],
        "trend": {},
    }
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_dashboard_context(seen_request, user_id):
        calls.append(("get_dashboard_context", seen_request, user_id))
        return "user:u1", "u1", False

    def fake_mark_dashboard_access(cache_key, now):
        calls.append(("mark_dashboard_access", cache_key, now))

    def fake_get_dashboard_cached_data(cache_key, now):
        calls.append(("get_dashboard_cached_data", cache_key, now))
        return cached_data

    def fail_fetch_dashboard_core(*args, **kwargs):
        raise AssertionError("dashboard init cache hit should not fetch data")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "_get_dashboard_context", fake_get_dashboard_context)
    monkeypatch.setattr(stats, "_mark_dashboard_access", fake_mark_dashboard_access)
    monkeypatch.setattr(stats, "_get_dashboard_cached_data", fake_get_dashboard_cached_data)
    monkeypatch.setattr(stats, "_fetch_dashboard_core", fail_fetch_dashboard_core)
    monkeypatch.setattr(stats, "time", SimpleNamespace(time=lambda: 123.4))

    response = asyncio.run(stats.api_dashboard_init(request, user_id="all"))

    assert response == {
        "status": "success",
        "data": {
            "dashboard": {"total_plays": 3},
            "users": [],
            "libraries": [],
            "top_users": [{"UserName": "Alice", "TotalTime": 90}],
            "trend": {},
        },
        "cached": True,
    }
    assert cached_data["top_users"][0]["UserId"] == "u1"
    assert calls == [
        ("is_admin_user", request),
        ("get_dashboard_context", request, "all"),
        ("mark_dashboard_access", "user:u1", 123.4),
        ("get_dashboard_cached_data", "user:u1", 123.4),
    ]


def test_dashboard_init_cache_miss_fetches_and_writes_cache_through_stats_monkeypatches(monkeypatch):
    import asyncio

    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_dashboard_context(seen_request, user_id):
        calls.append(("get_dashboard_context", seen_request, user_id))
        return "admin:all", None, True

    def fake_mark_dashboard_access(cache_key, now):
        calls.append(("mark_dashboard_access", cache_key, now))

    def fake_get_dashboard_cached_data(cache_key, now):
        calls.append(("get_dashboard_cached_data", cache_key, now))
        return None

    async def fake_fetch_dashboard_core(user_id):
        calls.append(("fetch_dashboard_core", user_id))
        return {"total_plays": 7, "active_users": 2, "total_duration": 300, "library": {"movie": 1}}

    async def fake_fetch_users_list():
        calls.append(("fetch_users_list",))
        return [{"UserId": "u1", "UserName": "Alice"}]

    async def fake_fetch_libraries():
        calls.append(("fetch_libraries",))
        return [{"Id": "lib1", "Name": "Movies"}]

    async def fake_fetch_top_users():
        calls.append(("fetch_top_users",))
        return [{"UserId": "u1", "UserName": "Alice", "TotalTime": 300}]

    async def fake_fetch_trend(user_id):
        calls.append(("fetch_trend", user_id))
        return {"2026-06-03": 300}

    def fake_set_dashboard_cache(cache_key, data, user_id, now):
        calls.append(("set_dashboard_cache", cache_key, data, user_id, now))

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "_get_dashboard_context", fake_get_dashboard_context)
    monkeypatch.setattr(stats, "_mark_dashboard_access", fake_mark_dashboard_access)
    monkeypatch.setattr(stats, "_get_dashboard_cached_data", fake_get_dashboard_cached_data)
    monkeypatch.setattr(stats, "_fetch_dashboard_core", fake_fetch_dashboard_core)
    monkeypatch.setattr(stats, "_fetch_users_list", fake_fetch_users_list)
    monkeypatch.setattr(stats, "_fetch_libraries", fake_fetch_libraries)
    monkeypatch.setattr(stats, "_fetch_top_users", fake_fetch_top_users)
    monkeypatch.setattr(stats, "_fetch_trend", fake_fetch_trend)
    monkeypatch.setattr(stats, "_set_dashboard_cache", fake_set_dashboard_cache)
    monkeypatch.setattr(stats, "time", SimpleNamespace(time=lambda: 200.5))

    response = asyncio.run(stats.api_dashboard_init(request))

    result_data = {
        "dashboard": {"total_plays": 7, "active_users": 2, "total_duration": 300, "library": {"movie": 1}},
        "users": [{"UserId": "u1", "UserName": "Alice"}],
        "libraries": [{"Id": "lib1", "Name": "Movies"}],
        "top_users": [{"UserId": "u1", "UserName": "Alice", "TotalTime": 300}],
        "trend": {"2026-06-03": 300},
    }
    assert response == {"status": "success", "data": result_data, "cached": False}
    assert calls == [
        ("is_admin_user", request),
        ("get_dashboard_context", request, None),
        ("mark_dashboard_access", "admin:all", 200.5),
        ("get_dashboard_cached_data", "admin:all", 200.5),
        ("fetch_dashboard_core", None),
        ("fetch_users_list",),
        ("fetch_libraries",),
        ("fetch_top_users",),
        ("fetch_trend", None),
        ("set_dashboard_cache", "admin:all", result_data, None, 200.5),
    ]


def test_dashboard_init_timeout_returns_stale_cache_through_stats_monkeypatches(monkeypatch):
    import asyncio

    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    stale_data = {
        "dashboard": {"total_plays": 9},
        "users": [],
        "libraries": [],
        "top_users": [{"UserId": "u1", "UserName": "Alice"}],
        "trend": {},
    }
    calls = []

    async def slow_fetch_dashboard_core(user_id):
        calls.append(("fetch_dashboard_core", user_id))
        await asyncio.sleep(0)
        return {"total_plays": 0}

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_dashboard_context(seen_request, user_id):
        calls.append(("get_dashboard_context", seen_request, user_id))
        return "user:u1", "u1", False

    def fake_mark_dashboard_access(cache_key, now):
        calls.append(("mark_dashboard_access", cache_key, now))

    def fake_get_dashboard_cached_data(cache_key, now):
        calls.append(("get_dashboard_cached_data", cache_key, now))
        return None

    def fake_wait_for(awaitable, timeout):
        calls.append(("wait_for", timeout))
        awaitable.close()
        raise asyncio.TimeoutError("too slow")

    def fake_get_dashboard_cache_entry(cache_key):
        calls.append(("get_dashboard_cache_entry", cache_key))
        return {"data": stale_data, "ts": 100}

    def fake_print(message):
        calls.append(("print", message))

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats, "_get_dashboard_context", fake_get_dashboard_context)
    monkeypatch.setattr(stats, "_mark_dashboard_access", fake_mark_dashboard_access)
    monkeypatch.setattr(stats, "_get_dashboard_cached_data", fake_get_dashboard_cached_data)
    monkeypatch.setattr(stats, "_fetch_dashboard_core", slow_fetch_dashboard_core)
    monkeypatch.setattr(stats, "_get_dashboard_cache_entry", fake_get_dashboard_cache_entry)
    monkeypatch.setattr(stats, "time", SimpleNamespace(time=lambda: 300.0))
    monkeypatch.setattr(stats.asyncio, "wait_for", fake_wait_for)
    from app.domains.playback import dashboard_init_router

    dashboard_init_router.set_dependency_providers(print_provider=lambda: fake_print)
    try:
        response = asyncio.run(stats.api_dashboard_init(request))
    finally:
        dashboard_init_router.set_dependency_providers(print_provider=lambda: print)

    assert response == {
        "status": "success",
        "data": {
            "dashboard": {"total_plays": 9},
            "users": [],
            "libraries": [],
            "top_users": [{"UserName": "Alice"}],
            "trend": {},
        },
        "cached": True,
        "timeout": True,
    }
    assert calls == [
        ("is_admin_user", request),
        ("get_dashboard_context", request, None),
        ("mark_dashboard_access", "user:u1", 300.0),
        ("get_dashboard_cached_data", "user:u1", 300.0),
        ("wait_for", 5),
        ("print", "[Dashboard Init] 请求超时: too slow"),
        ("get_dashboard_cache_entry", "user:u1"),
    ]


def test_playback_stats_includes_system_monitor_child_route_and_compat_export():
    from app.domains.playback import stats
    from app.domains.playback import system_monitor_router

    routes = [
        (route.path, route.methods)
        for route in stats.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/system/monitor" and "GET" in methods for path, methods in routes)
    assert stats.api_system_monitor is system_monitor_router.api_system_monitor

    dashboard_init_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/dashboard/init" and "GET" in methods
    )
    system_monitor_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/system/monitor" and "GET" in methods
    )
    item_detail_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/stats/item_detail" and "GET" in methods
    )
    assert dashboard_init_index < system_monitor_index < item_detail_index


def test_system_monitor_denies_non_admin_before_psutil_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_cpu_percent(*args, **kwargs):
        raise AssertionError("system monitor should not read cpu without admin permission")

    def fail_virtual_memory(*args, **kwargs):
        raise AssertionError("system monitor should not read memory without admin permission")

    def fail_disk_usage(*args, **kwargs):
        raise AssertionError("system monitor should not read disk without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.psutil, "cpu_percent", fail_cpu_percent)
    monkeypatch.setattr(stats.psutil, "virtual_memory", fail_virtual_memory)
    monkeypatch.setattr(stats.psutil, "disk_usage", fail_disk_usage)

    response = stats.api_system_monitor(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_system_monitor_allows_admin_through_stats_monkeypatches(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_cpu_percent(interval=0):
        calls.append(("cpu_percent", interval))
        return 12.5

    def fake_virtual_memory():
        calls.append(("virtual_memory",))
        return SimpleNamespace(percent=34.5)

    def fake_disk_usage(path):
        calls.append(("disk_usage", path))
        return SimpleNamespace(percent=56.5)

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.psutil, "cpu_percent", fake_cpu_percent)
    monkeypatch.setattr(stats.psutil, "virtual_memory", fake_virtual_memory)
    monkeypatch.setattr(stats.psutil, "disk_usage", fake_disk_usage)

    response = stats.api_system_monitor(request)

    assert response == {
        "status": "success",
        "data": {
            "cpu": 12.5,
            "memory": 34.5,
            "disk": 56.5,
        },
    }
    assert calls == [
        ("is_admin_user", request),
        ("cpu_percent", 0),
        ("virtual_memory",),
        ("disk_usage", "/"),
    ]


def test_system_monitor_uses_stats_safe_error_message_monkeypatch(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fail_cpu_percent(interval=0):
        calls.append(("cpu_percent", interval))
        raise RuntimeError("raw sensor failure")

    def fake_safe_error_message(error, fallback=None):
        calls.append(("safe_error_message", str(error), fallback))
        return "safe monitor error"

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.psutil, "cpu_percent", fail_cpu_percent)
    monkeypatch.setattr(stats, "safe_error_message", fake_safe_error_message)

    response = stats.api_system_monitor(request)

    assert response == {"status": "error", "message": "safe monitor error"}
    assert calls == [
        ("is_admin_user", request),
        ("cpu_percent", 0),
        ("safe_error_message", "raw sensor failure", "探针读取失败"),
    ]


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
