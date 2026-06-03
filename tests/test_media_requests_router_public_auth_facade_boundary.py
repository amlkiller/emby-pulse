import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_media_requests_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/media_requests/router.py"
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


def test_media_requests_router_includes_auth_child_routes_and_compat_exports():
    from app.domains.media_requests import auth_router
    from app.domains.media_requests import router as media_requests_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/auth" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/requests/check" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/requests/logout" and "POST" in methods for path, methods in routes)
    assert media_requests_router.RequestLoginModel is auth_router.RequestLoginModel
    assert media_requests_router.request_system_login is auth_router.request_system_login
    assert media_requests_router.check_auth is auth_router.check_auth
    assert media_requests_router.request_system_logout is auth_router.request_system_logout

    auth_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/auth" and "POST" in methods
    )
    check_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/check" and "GET" in methods
    )
    logout_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/logout" and "POST" in methods
    )
    item_info_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/item_info" and "GET" in methods
    )
    assert auth_index < check_index < logout_index < item_info_index


def test_media_requests_router_includes_discovery_child_routes_and_compat_exports():
    from app.domains.media_requests import discovery_router
    from app.domains.media_requests import router as media_requests_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/item_info" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/requests/hub_data" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/requests/search" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/requests/trending" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/requests/tv/{tmdb_id}" and "GET" in methods for path, methods in routes)
    assert any(
        path == "/api/requests/check/{media_type}/{tmdb_id}" and "GET" in methods
        for path, methods in routes
    )
    assert media_requests_router.get_tmdb_season_info is discovery_router.get_tmdb_season_info
    assert media_requests_router.get_emby_admin is discovery_router.get_emby_admin
    assert media_requests_router.check_emby_exists is discovery_router.check_emby_exists
    assert media_requests_router.get_item_info is discovery_router.get_item_info
    assert media_requests_router.get_hub_data is discovery_router.get_hub_data
    assert media_requests_router.search_tmdb is discovery_router.search_tmdb
    assert media_requests_router.get_tmdb_trending is discovery_router.get_tmdb_trending
    assert media_requests_router.get_tv_details is discovery_router.get_tv_details
    assert media_requests_router.check_local_status is discovery_router.check_local_status

    logout_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/logout" and "POST" in methods
    )
    item_info_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/item_info" and "GET" in methods
    )
    hub_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/hub_data" and "GET" in methods
    )
    search_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/search" and "GET" in methods
    )
    trending_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/trending" and "GET" in methods
    )
    tv_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/tv/{tmdb_id}" and "GET" in methods
    )
    check_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/check/{media_type}/{tmdb_id}" and "GET" in methods
    )
    submit_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/submit" and "POST" in methods
    )
    assert logout_index < item_info_index < hub_index < search_index < trending_index
    assert trending_index < tv_index < check_index < submit_index


def test_media_requests_router_includes_submit_child_routes_and_compat_exports():
    from app.domains.media_requests import router as media_requests_router
    from app.domains.media_requests import submit_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/submit" and "POST" in methods for path, methods in routes)
    assert media_requests_router.MediaRequestSubmitModel is submit_router.MediaRequestSubmitModel
    assert media_requests_router.submit_media_request is submit_router.submit_media_request

    check_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/check/{media_type}/{tmdb_id}" and "GET" in methods
    )
    submit_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/submit" and "POST" in methods
    )
    my_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/my" and "GET" in methods
    )
    assert check_index < submit_index < my_index


def test_media_requests_router_includes_management_child_routes_and_compat_exports():
    from app.domains.media_requests import management_router
    from app.domains.media_requests import router as media_requests_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/my" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/requests" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/requests/batch" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/requests/action" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/requests/pending_notify" and "GET" in methods for path, methods in routes)
    assert media_requests_router.AdminActionModel is management_router.AdminActionModel
    assert media_requests_router.BulkAdminActionModel is management_router.BulkAdminActionModel
    assert media_requests_router.get_my_requests is management_router.get_my_requests
    assert media_requests_router.get_all_requests is management_router.get_all_requests
    assert media_requests_router.batch_manage_action is management_router.batch_manage_action
    assert media_requests_router.manage_request_action is management_router.manage_request_action
    assert media_requests_router.get_pending_notify is management_router.get_pending_notify

    submit_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/submit" and "POST" in methods
    )
    my_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/my" and "GET" in methods
    )
    manage_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/requests" and "GET" in methods
    )
    batch_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/requests/batch" and "POST" in methods
    )
    action_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/requests/action" and "POST" in methods
    )
    pending_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/pending_notify" and "GET" in methods
    )
    feedback_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/feedback/submit" and "POST" in methods
    )
    assert submit_index < my_index < manage_index < batch_index < action_index < pending_index
    assert pending_index < feedback_index


def test_media_requests_router_includes_feedback_child_routes_and_compat_exports():
    from app.domains.media_requests import feedback_router
    from app.domains.media_requests import router as media_requests_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/feedback/submit" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/requests/feedback/my" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/feedback" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/feedback/action" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/feedback/batch" and "POST" in methods for path, methods in routes)
    assert media_requests_router.FeedbackSubmitModel is feedback_router.FeedbackSubmitModel
    assert media_requests_router.FeedbackActionModel is feedback_router.FeedbackActionModel
    assert media_requests_router.BulkFeedbackActionModel is feedback_router.BulkFeedbackActionModel
    assert media_requests_router.submit_feedback is feedback_router.submit_feedback
    assert media_requests_router.get_my_feedback is feedback_router.get_my_feedback
    assert media_requests_router.get_all_feedback is feedback_router.get_all_feedback
    assert media_requests_router.manage_feedback_action is feedback_router.manage_feedback_action
    assert media_requests_router.batch_feedback_action is feedback_router.batch_feedback_action

    pending_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/pending_notify" and "GET" in methods
    )
    submit_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/feedback/submit" and "POST" in methods
    )
    my_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/feedback/my" and "GET" in methods
    )
    all_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/feedback" and "GET" in methods
    )
    action_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/feedback/action" and "POST" in methods
    )
    batch_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/feedback/batch" and "POST" in methods
    )
    safe_top_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/safe_top" and "GET" in methods
    )
    assert pending_index < submit_index < my_index < all_index < action_index < batch_index < safe_top_index


def test_media_requests_router_includes_safe_media_child_routes_and_compat_exports():
    from app.domains.media_requests import router as media_requests_router
    from app.domains.media_requests import safe_media_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/safe_top" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/requests/safe_latest" and "GET" in methods for path, methods in routes)
    assert media_requests_router.get_safe_top_media is safe_media_router.get_safe_top_media
    assert media_requests_router.get_safe_latest is safe_media_router.get_safe_latest

    batch_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/feedback/batch" and "POST" in methods
    )
    safe_top_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/safe_top" and "GET" in methods
    )
    safe_latest_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/safe_latest" and "GET" in methods
    )
    refresh_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/refresh_cache" and "POST" in methods
    )
    my_series_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/my_series" and "GET" in methods
    )
    assert batch_index < safe_top_index < safe_latest_index < refresh_index < my_series_index


def test_media_requests_router_includes_cache_control_child_routes_and_compat_exports():
    from app.domains.media_requests import cache_control_router
    from app.domains.media_requests import router as media_requests_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/refresh_cache" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/requests/clear_cache" and "POST" in methods for path, methods in routes)
    assert media_requests_router.start_community_cache_refresh_loop is (
        cache_control_router.start_community_cache_refresh_loop
    )
    assert media_requests_router.stop_community_cache_refresh_loop is (
        cache_control_router.stop_community_cache_refresh_loop
    )
    assert media_requests_router.start_media_request_services is cache_control_router.start_media_request_services
    assert media_requests_router.refresh_community_cache_api is cache_control_router.refresh_community_cache_api
    assert media_requests_router.clear_community_cache_api is cache_control_router.clear_community_cache_api

    safe_latest_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/safe_latest" and "GET" in methods
    )
    refresh_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/refresh_cache" and "POST" in methods
    )
    clear_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/clear_cache" and "POST" in methods
    )
    my_series_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/my_series" and "GET" in methods
    )
    assert safe_latest_index < refresh_index < clear_index < my_series_index


def test_media_requests_router_includes_user_series_child_routes_and_compat_exports():
    from app.domains.media_requests import router as media_requests_router
    from app.domains.media_requests import user_series_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/user/my_series" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/user/my_series/refresh" and "POST" in methods for path, methods in routes)
    assert media_requests_router._get_local_episodes is user_series_router._get_local_episodes
    assert media_requests_router._get_tmdb_season_episodes is user_series_router._get_tmdb_season_episodes
    assert media_requests_router.get_user_series is user_series_router.get_user_series
    assert media_requests_router.refresh_my_series_cache is user_series_router.refresh_my_series_cache

    clear_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/requests/clear_cache" and "POST" in methods
    )
    my_series_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/my_series" and "GET" in methods
    )
    refresh_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/user/my_series/refresh" and "POST" in methods
    )
    update_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/request_update" and "POST" in methods
    )
    assert clear_index < my_series_index < refresh_index < update_index


def test_media_requests_router_includes_update_child_routes_and_compat_exports():
    from app.domains.media_requests import router as media_requests_router
    from app.domains.media_requests import update_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/user/request_update" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/user/request_update_batch" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/requests/search_episodes" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/requests/download_episodes" and "POST" in methods for path, methods in routes)
    assert media_requests_router.UpdateRequestModel is update_router.UpdateRequestModel
    assert media_requests_router.getRequestStatusTextSync is update_router.getRequestStatusTextSync
    assert media_requests_router.submit_update_request is update_router.submit_update_request
    assert media_requests_router.submit_update_request_batch is update_router.submit_update_request_batch
    assert media_requests_router.search_episodes_for_update is update_router.search_episodes_for_update
    assert media_requests_router.download_episodes_for_update is update_router.download_episodes_for_update

    refresh_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/user/my_series/refresh" and "POST" in methods
    )
    update_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/request_update" and "POST" in methods
    )
    batch_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/user/request_update_batch" and "POST" in methods
    )
    search_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/requests/search_episodes" and "POST" in methods
    )
    download_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/requests/download_episodes" and "POST" in methods
    )
    register_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/register" and "POST" in methods
    )
    assert refresh_index < update_index < batch_index < search_index < download_index < register_index


def test_media_requests_router_includes_registration_child_routes_and_compat_exports():
    from app.domains.media_requests import registration_router
    from app.domains.media_requests import router as media_requests_router

    routes = [
        (route.path, route.methods)
        for route in media_requests_router.router.routes
        if hasattr(route, "methods")
    ]

    assert any(path == "/api/requests/register" and "POST" in methods for path, methods in routes)
    assert media_requests_router.UserRegisterModel is registration_router.UserRegisterModel
    assert media_requests_router._restore_invitation_code is registration_router._restore_invitation_code
    assert media_requests_router.user_community_register is registration_router.user_community_register

    download_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/requests/download_episodes" and "POST" in methods
    )
    register_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/requests/register" and "POST" in methods
    )
    assert download_index < register_index


def test_get_all_requests_denies_non_admin_before_dao_reads(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_list_all_requests():
        raise AssertionError("media requests should not be read without admin permission")

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(media_requests_router, "list_all_requests", fail_list_all_requests)

    response = media_requests_router.get_all_requests(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_all_feedback_allows_admin_through_public_facade(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    rows = [
        (1, "Movie", "User One", "bad_audio", "Audio is missing", 0, "2026-06-02 10:00:00"),
    ]
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_all_feedback():
        calls.append(("list_all_feedback",))
        return rows

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(media_requests_router, "list_all_feedback", fake_list_all_feedback)

    response = media_requests_router.get_all_feedback(request)

    assert response == {
        "status": "success",
        "data": [
            {
                "id": 1,
                "item_name": "Movie",
                "username": "User One",
                "issue_type": "bad_audio",
                "description": "Audio is missing",
                "status": 0,
                "created_at": "2026-06-02 10:00:00",
            }
        ],
    }
    assert calls == [
        ("is_admin_user", request),
        ("list_all_feedback",),
    ]


def test_refresh_cache_denies_non_admin_before_refresh(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_refresh_community_cache():
        raise AssertionError("community cache should not refresh without admin permission")

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(media_requests_router, "_refresh_community_cache", fail_refresh_community_cache)

    response = media_requests_router.refresh_community_cache_api(request)

    assert response.status_code == 403
    assert json.loads(response.body.decode("utf-8")) == {
        "status": "error",
        "message": "需要管理员权限",
    }
    assert calls == [request]


def test_search_episodes_denies_non_admin_before_search_dependencies(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_update_request_search_info(*args, **kwargs):
        raise AssertionError("update request search info should not be read without admin permission")

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        media_requests_router,
        "get_update_request_search_info",
        fail_get_update_request_search_info,
    )

    response = media_requests_router.search_episodes_for_update(
        {"tmdb_id": 100, "season": 1, "episodes": [1, 2]},
        request,
    )

    assert response == {"status": "error", "message": "无权访问"}
    assert calls == [request]
