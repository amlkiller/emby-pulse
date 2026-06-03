import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_users_public_service_emby_users_cache_and_invalidate(monkeypatch):
    from app.domains.users import public_service

    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return [{"Id": "u1", "Name": "User One"}]

    def fake_get(path, timeout):
        calls.append((path, timeout))
        return FakeResponse()

    monkeypatch.setattr(public_service, "_emby_users_cache", {"data": None, "expires": 0})
    monkeypatch.setattr(public_service, "time", SimpleNamespace(time=lambda: 100))
    monkeypatch.setattr(public_service.media_api, "get", fake_get)

    assert public_service.get_emby_users_cached() == [{"Id": "u1", "Name": "User One"}]
    assert public_service.get_emby_users_cached() == [{"Id": "u1", "Name": "User One"}]
    assert calls == [("/Users", 5)]

    public_service.invalidate_emby_users_cache()
    assert public_service._emby_users_cache == {"data": None, "expires": 0}


def test_users_public_service_delegates_admin_check(monkeypatch):
    from app.domains.users import auth, public_service

    calls = []
    request = object()

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(auth, "is_admin_user", fake_is_admin_user)

    assert public_service.is_admin_user(request) is True
    assert calls == [request]


def test_users_public_service_delegates_permission_check(monkeypatch):
    from app.domains.users import auth, public_service

    calls = []
    request = object()

    def fake_check_permission(seen_request, page):
        calls.append((seen_request, page))
        return True

    monkeypatch.setattr(auth, "check_permission", fake_check_permission)

    assert public_service.check_permission(request, "points") is True
    assert calls == [(request, "points")]


def test_users_public_service_exposes_page_permission_map(monkeypatch):
    from app.domains.users import auth, public_service

    permission_map = {"/settings": "settings", "/clients": "clients"}
    monkeypatch.setattr(auth, "PAGE_PERMISSION_MAP", permission_map)

    assert public_service.get_page_permission_map() is permission_map


def test_users_router_uses_public_service_cache_owner():
    router_source = (_REPO_ROOT / "app/domains/users/router.py").read_text(encoding="utf-8")
    manage_list_source = (_REPO_ROOT / "app/domains/users/manage_list_router.py").read_text(encoding="utf-8")

    assert "def get_emby_users_cached(" not in router_source
    assert "def invalidate_emby_users_cache(" not in router_source
    assert "def get_emby_users_cached(" not in manage_list_source
    assert "def invalidate_emby_users_cache(" not in manage_list_source
    assert "user_service_provider=lambda: user_service" in router_source
    assert "from app.domains.users import public_service as user_service" in manage_list_source
    assert "service.get_emby_users_cached()" in manage_list_source
    assert "service.invalidate_emby_users_cache()" in manage_list_source


def test_users_router_includes_child_routes_and_compat_exports():
    from app.domains.users import router

    routes = [(route.path, route.methods) for route in router.router.routes if hasattr(route, "methods")]

    assert any(path == "/api/users" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/libraries" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/admin_list" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/audit_logs" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/audit_logs/stats" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/audit_logs/{log_id}" and "DELETE" in methods for path, methods in routes)
    assert any(path == "/api/manage/audit_logs/clear" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/verify_password" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/check_delete_verified" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/user/libraries" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/user/hidden_libraries" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/invite/gen" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/invites" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/invites/export" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/invites/batch" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/template/default" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/template/default" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/req_permission" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/req_permission" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags/{tag_id}" and "DELETE" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags/name/{tag_name}" and "DELETE" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/tags" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/tags" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/user/image/{user_id}" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/image" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/user/avatar" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/user/password" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/pin" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/{user_id}" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/{user_id}" and "DELETE" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/new" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/update" and "POST" in methods for path, methods in routes)

    from app.domains.users import avatar_router
    from app.domains.users import audit_log_router
    from app.domains.users import batch_router
    from app.domains.users import delete_router
    from app.domains.users import delete_verification_router
    from app.domains.users import invitation_router
    from app.domains.users import libraries_router
    from app.domains.users import library_visibility_router
    from app.domains.users import manage_list_router
    from app.domains.users import new_user_router
    from app.domains.users import pin_router
    from app.domains.users import self_password_router
    from app.domains.users import single_user_router
    from app.domains.users import update_router

    assert router.get_user_avatar is avatar_router.get_user_avatar
    assert router.api_update_user_image is avatar_router.api_update_user_image
    assert router.api_user_self_avatar is avatar_router.api_user_self_avatar
    assert router.UserPasswordChangeModel is self_password_router.UserPasswordChangeModel
    assert router.api_user_self_password is self_password_router.api_user_self_password
    assert router.api_get_libraries is libraries_router.api_get_libraries
    assert router.api_get_audit_logs is audit_log_router.api_get_audit_logs
    assert router.api_get_audit_stats is audit_log_router.api_get_audit_stats
    assert router.api_delete_audit_log is audit_log_router.api_delete_audit_log
    assert router.api_clear_audit_logs is audit_log_router.api_clear_audit_logs
    assert router.PasswordVerifyModel is delete_verification_router.PasswordVerifyModel
    assert router.verify_emby_admin_password is delete_verification_router.verify_emby_admin_password
    assert router.get_emby_admin_users is delete_verification_router.get_emby_admin_users
    assert router.api_get_admin_list is delete_verification_router.api_get_admin_list
    assert router.api_verify_delete_password is delete_verification_router.api_verify_delete_password
    assert router.api_check_delete_verified is delete_verification_router.api_check_delete_verified
    assert router.InviteGenModelLocal is invitation_router.InviteGenModelLocal
    assert router.InviteBatchModelLocal is invitation_router.InviteBatchModelLocal
    assert router.api_gen_invite is invitation_router.api_gen_invite
    assert router.api_get_invites is invitation_router.api_get_invites
    assert router.api_export_invites is invitation_router.api_export_invites
    assert router.api_manage_invites_batch is invitation_router.api_manage_invites_batch
    assert router.HiddenLibrariesModel is library_visibility_router.HiddenLibrariesModel
    assert router.api_get_user_libraries is library_visibility_router.api_get_user_libraries
    assert router.api_update_hidden_libraries is library_visibility_router.api_update_hidden_libraries
    assert router.api_manage_users is manage_list_router.api_manage_users
    assert router.check_expired_users is manage_list_router.check_expired_users
    assert router.UserUpdateModelEx is update_router.UserUpdateModelEx
    assert router.api_manage_user_update is update_router.api_manage_user_update
    assert router.NewUserModelEx is new_user_router.NewUserModelEx
    assert router.api_manage_user_new is new_user_router.api_manage_user_new
    assert router.BatchActionModelLocal is batch_router.BatchActionModelLocal
    assert router.api_manage_users_batch is batch_router.api_manage_users_batch
    assert router.api_manage_user_delete is delete_router.api_manage_user_delete
    assert router.PinUserModel is pin_router.PinUserModel
    assert router.api_pin_user is pin_router.api_pin_user
    assert router.api_get_single_user is single_user_router.api_get_single_user

    admin_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/admin_list" and "GET" in methods
    )
    audit_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/audit_logs" and "GET" in methods
    )
    verify_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/user/verify_password" and "POST" in methods
    )
    user_libraries_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/libraries" and "GET" in methods
    )
    hidden_libraries_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/user/hidden_libraries" and "POST" in methods
    )
    invitation_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/invite/gen" and "POST" in methods
    )
    manage_libraries_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/libraries" and "GET" in methods
    )
    manage_users_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/users" and "GET" in methods
    )
    single_user_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/{user_id}" and "GET" in methods
    )
    delete_user_index = next(
        i
        for i, (path, methods) in enumerate(routes)
        if path == "/api/manage/user/{user_id}" and "DELETE" in methods
    )
    avatar_image_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/image/{user_id}" and "GET" in methods
    )
    avatar_update_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/image" and "POST" in methods
    )
    self_avatar_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/avatar" and "POST" in methods
    )
    password_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/user/password" and "POST" in methods
    )
    template_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/template/default" and "POST" in methods
    )
    pin_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/pin" and "POST" in methods
    )
    users_list_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/users" and "GET" in methods
    )
    library_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/library" and "POST" in methods
    )
    update_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/update" and "POST" in methods
    )
    new_user_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/user/new" and "POST" in methods
    )
    batch_index = next(
        i for i, (path, methods) in enumerate(routes) if path == "/api/manage/users/batch" and "POST" in methods
    )
    assert admin_index < audit_index < verify_index
    assert avatar_image_index < avatar_update_index < self_avatar_index < password_index
    assert manage_libraries_index < manage_users_index < single_user_index
    assert verify_index < user_libraries_index < hidden_libraries_index < invitation_index < library_index
    assert library_index < update_index < new_user_index < delete_user_index < batch_index
    assert template_index < pin_index < users_list_index


def test_update_user_denies_non_admin_before_media_or_cache(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run before admin authorization")),
    )

    result = router.api_manage_user_update(router.UserUpdateModelEx(user_id="u1"), request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_update_user_rejects_unhealthy_media_before_cache_or_dao(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MediaApi:
        def health_check(self):
            return False

        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run when health check fails")

    class UserDaoMustNotRun:
        def get_user_meta(self, *_args, **_kwargs):
            raise AssertionError("user_dao.get_user_meta should not run when health check fails")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(router, "user_dao", UserDaoMustNotRun())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run when health check fails")),
    )

    result = router.api_manage_user_update(router.UserUpdateModelEx(user_id="u1"), request)

    assert result == {"status": "error", "message": "Emby 服务不可用，请稍后重试"}


def test_update_user_preserves_success_mapping_and_legacy_providers(monkeypatch):
    from app.domains.users import router

    calls = []
    request = SimpleNamespace(session={"user": {"id": "admin-1", "name": "Admin User"}})

    class Response:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    class MediaApi:
        def __init__(self):
            self.user_get_count = 0

        def health_check(self):
            calls.append(("health_check",))
            return True

        def get(self, path, timeout=None):
            calls.append(("get", path, timeout))
            if path == "/Users/u1":
                self.user_get_count += 1
                if self.user_get_count == 1:
                    return Response(200, {"Policy": {"IsDisabled": False, "EnableAllFolders": True}})
                if self.user_get_count == 2:
                    return Response(200, {"Policy": {"Existing": True}})
                return Response(200, {"Name": "Alice"})
            if path == "/Users/template-1":
                return Response(200, {"Policy": {"Template": True, "EnableAllFolders": False, "EnabledFolders": ["lib-1"]}})
            raise AssertionError(f"unexpected media_api.get path: {path}")

        def post(self, path, **kwargs):
            calls.append(("post", path, kwargs))
            return Response(204)

    class UserDao:
        def get_user_meta(self, user_id):
            calls.append(("get_user_meta", user_id))
            return {
                "expire_date": "2026-01-01",
                "is_vip": 0,
                "remark": "old",
                "max_concurrent": 1,
                "allow_routes": "old-a",
                "block_routes": "old-b",
            }

        def save_manage_user_meta(self, *args):
            calls.append(("save_manage_user_meta", args))

        def sync_user_library_permissions(self, *args):
            calls.append(("sync_user_library_permissions", args))
            return ["lib-merged"]

        def set_user_admin_disabled(self, *args):
            calls.append(("set_user_admin_disabled", args))

    def fake_clone_policy(target_policy, src_policy, copy_library, copy_policy, copy_parental):
        calls.append(("clone_policy", target_policy.copy(), src_policy.copy(), copy_library, copy_policy, copy_parental))
        merged = target_policy.copy()
        merged.update(src_policy)
        merged["cloned"] = True
        return merged

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(router, "user_dao", UserDao())
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", lambda: calls.append(("invalidate_cache",)))
    monkeypatch.setattr(router, "clone_policy", fake_clone_policy)
    monkeypatch.setattr(router, "get_client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(router, "add_audit_log", lambda **kwargs: calls.append(("add_audit_log", kwargs)))
    monkeypatch.setattr(
        router,
        "datetime",
        SimpleNamespace(datetime=SimpleNamespace(now=lambda: SimpleNamespace(isoformat=lambda: "2026-06-04T00:00:00"))),
    )

    result = router.api_manage_user_update(
        router.UserUpdateModelEx(
            user_id="u1",
            is_disabled=True,
            expire_date="2026-12-31",
            password="secret",
            max_concurrent=3,
            is_vip=True,
            remark="new",
            allow_routes="new-a",
            block_routes="new-b",
            req_free=1,
            req_free_count=5,
            tags="tag-a",
            apply_template_id="template-1",
        ),
        request,
    )

    assert result == {"status": "success", "message": "用户信息已更新"}
    assert ("invalidate_cache",) in calls
    assert (
        "save_manage_user_meta",
        (
            "u1",
            "2026-12-31",
            3,
            1,
            "new",
            "new-a",
            "new-b",
            1,
            5,
            "tag-a",
            "2026-06-04T00:00:00",
        ),
    ) in calls
    assert ("post", "/Users/u1/Password", {"json": {"Id": "u1", "NewPw": "secret"}}) in calls
    assert (
        "clone_policy",
        {"Existing": True},
        {"Template": True, "EnableAllFolders": False, "EnabledFolders": ["lib-1"]},
        True,
        True,
        True,
    ) in calls
    assert ("sync_user_library_permissions", ("u1", False, ["lib-1"])) in calls
    assert ("set_user_admin_disabled", ("u1", True)) in calls
    assert (
        "add_audit_log",
        {
            "admin_id": "admin-1",
            "admin_name": "Admin User",
            "action": "修改用户",
            "target_user_id": "u1",
            "target_user_name": "Alice",
            "details": (
                "重置密码, 禁用账号, 过期日期:2026-01-01→2026-12-31, VIP:普通→VIP, "
                "备注:old→new, 并发数:1→3, 允许线路:old-a→new-a, 屏蔽线路:old-b→new-b, 应用权限模板"
            ),
            "ip_address": "127.0.0.1",
        },
    ) in calls


def test_manage_users_denies_non_admin_before_expire_check_or_cache(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(
        router,
        "check_expired_users",
        lambda: (_ for _ in ()).throw(AssertionError("expire check should not run before admin authorization")),
    )
    monkeypatch.setattr(
        router.user_service,
        "get_emby_users_cached",
        lambda: (_ for _ in ()).throw(AssertionError("cache read should not run before admin authorization")),
    )
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run before admin authorization")),
    )

    result = router.api_manage_users(request, refresh=True)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_manage_users_preserves_refresh_and_response_mapping(monkeypatch):
    from app.domains.users import router

    calls = []
    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "check_expired_users", lambda: calls.append(("check_expired_users",)))
    monkeypatch.setattr(router, "get_media_server_public_host", lambda: "https://emby.example/")
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", lambda: calls.append(("invalidate_cache",)))
    monkeypatch.setattr(
        router.user_service,
        "get_emby_users_cached",
        lambda: [
            {
                "Id": "u1",
                "Name": "Alice",
                "LastLoginDate": "2026-06-04T01:00:00",
                "PrimaryImageTag": "image-1",
                "Policy": {
                    "IsDisabled": True,
                    "IsAdministrator": False,
                    "EnableAllFolders": False,
                    "EnabledFolders": ["lib-1"],
                    "ExcludedSubFolders": ["sub-1"],
                    "EnableContentDownloading": False,
                    "EnableVideoPlaybackTranscoding": False,
                    "EnableAudioPlaybackTranscoding": False,
                    "MaxParentalRating": 9,
                },
            }
        ],
    )

    class UserDao:
        def list_all_user_meta(self):
            calls.append(("list_all_user_meta",))
            return [
                {
                    "user_id": "u1",
                    "admin_disabled": 1,
                    "expire_date": "2026-12-31",
                    "note": "legacy-note",
                    "max_concurrent": 2,
                    "is_vip": 1,
                    "remark": "[PINNED]display note",
                    "allow_routes": "route-a",
                    "block_routes": "route-b",
                    "req_free": 1,
                    "req_free_count": 3,
                    "tags": "vip,trial",
                }
            ]

    class UserBotDao:
        def list_emby_tg_user_bindings(self):
            calls.append(("list_emby_tg_user_bindings",))
            return [{"emby_user_id": "u1", "tg_user_id": "tg-1"}]

    monkeypatch.setattr(router, "user_dao", UserDao())
    monkeypatch.setattr(router, "user_bot_dao", UserBotDao())

    result = router.api_manage_users(request, refresh=True)

    assert result == {
        "status": "success",
        "data": [
            {
                "Id": "u1",
                "Name": "Alice",
                "LastLoginDate": "2026-06-04T01:00:00",
                "IsDisabled": True,
                "IsAdmin": False,
                "AdminDisabled": True,
                "ExpireDate": "2026-12-31",
                "Note": "legacy-note",
                "PrimaryImageTag": "image-1",
                "EnableAllFolders": False,
                "EnabledFolders": ["lib-1"],
                "ExcludedSubFolders": ["sub-1"],
                "EnableDownloading": False,
                "EnableVideoTranscoding": False,
                "EnableAudioTranscoding": False,
                "MaxParentalRating": 9,
                "MaxConcurrent": 2,
                "IsVIP": True,
                "Remark": "display note",
                "Pinned": True,
                "AllowRoutes": "route-a",
                "BlockRoutes": "route-b",
                "TgUserId": "tg-1",
                "req_free": 1,
                "req_free_count": 3,
                "tags": "vip,trial",
            }
        ],
        "emby_url": "https://emby.example",
    }
    assert calls == [
        ("check_expired_users",),
        ("invalidate_cache",),
        ("list_all_user_meta",),
        ("list_emby_tg_user_bindings",),
    ]


def test_manage_users_preserves_media_unavailable_and_safe_error_mapping(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "check_expired_users", lambda: None)
    monkeypatch.setattr(router.user_service, "get_emby_users_cached", lambda: None)

    assert router.api_manage_users(request) == {"status": "error", "message": "媒体服务器无法连接"}

    monkeypatch.setattr(
        router.user_service,
        "get_emby_users_cached",
        lambda: (_ for _ in ()).throw(RuntimeError("raw secret error")),
    )
    monkeypatch.setattr(router, "safe_error_message", lambda exc: f"safe:{exc}")

    assert router.api_manage_users(request) == {"status": "error", "message": "safe:raw secret error"}


def test_batch_users_denies_missing_login_before_auth_or_media(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before login authorization")

    monkeypatch.setattr(
        router,
        "is_admin_user",
        lambda _request: (_ for _ in ()).throw(
            AssertionError("admin authorization should not run before login authorization")
        ),
    )
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())

    result = router.api_manage_users_batch(router.BatchActionModelLocal(user_ids=["u1"], action="enable"), request)

    assert result == {"status": "error"}


def test_batch_users_denies_non_admin_before_media(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())

    result = router.api_manage_users_batch(router.BatchActionModelLocal(user_ids=["u1"], action="enable"), request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_batch_users_rejects_more_than_100_before_media(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before batch size validation")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())

    result = router.api_manage_users_batch(
        router.BatchActionModelLocal(user_ids=[f"u{i}" for i in range(101)], action="enable"),
        request,
    )

    assert result == {"status": "error", "message": "单次批量操作最多 100 个用户"}


def test_batch_users_rejects_unhealthy_media_before_side_effects(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MediaApi:
        def health_check(self):
            return False

        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run when health check fails")

        def post(self, *_args, **_kwargs):
            raise AssertionError("media_api.post should not run when health check fails")

    class UserDaoMustNotRun:
        def save_user_admin_disabled(self, *_args, **_kwargs):
            raise AssertionError("user_dao side effects should not run when health check fails")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(router, "user_dao", UserDaoMustNotRun())
    monkeypatch.setattr(
        router,
        "add_audit_log",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("audit log should not run when health check fails")),
    )

    result = router.api_manage_users_batch(router.BatchActionModelLocal(user_ids=["u1"], action="enable"), request)

    assert result == {"status": "error", "message": "Emby 服务不可用，请稍后重试"}


def test_new_user_denies_non_admin_before_media_or_cache(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before admin authorization")

        def post(self, *_args, **_kwargs):
            raise AssertionError("media_api.post should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run before admin authorization")),
    )

    result = router.api_manage_user_new(router.NewUserModelEx(name="Alice"), request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_new_user_rejects_unhealthy_media_before_cache_or_create(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MediaApi:
        def health_check(self):
            return False

        def post(self, *_args, **_kwargs):
            raise AssertionError("media_api.post should not run when health check fails")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run when health check fails")),
    )

    result = router.api_manage_user_new(router.NewUserModelEx(name="Alice"), request)

    assert result == {"status": "error", "message": "Emby 服务不可用，请稍后重试"}


def test_new_user_preserves_success_mapping_and_legacy_providers(monkeypatch):
    from app.domains.users import router

    calls = []
    request = SimpleNamespace(session={"user": {"id": "admin-1", "name": "Admin User"}})

    class Response:
        def __init__(self, status_code=200, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class MediaApi:
        def health_check(self):
            calls.append(("health_check",))
            return True

        def post(self, path, **kwargs):
            calls.append(("post", path, kwargs))
            if path == "/Users/New":
                return Response(200, {"Id": "new-1"})
            return Response(204)

        def get(self, path, timeout=None):
            calls.append(("get", path, timeout))
            if path == "/Users/new-1":
                return Response(200, {"Policy": {"Existing": True}})
            if path == "/Users/template-1":
                return Response(200, {"Policy": {"Template": True}})
            raise AssertionError(f"unexpected media_api.get path: {path}")

    class UserDao:
        def create_user_meta(self, *args):
            calls.append(("create_user_meta", args))

    def fake_clone_policy(target_policy, src_policy, copy_library, copy_policy, copy_parental):
        calls.append(("clone_policy", target_policy.copy(), src_policy.copy(), copy_library, copy_policy, copy_parental))
        merged = target_policy.copy()
        merged.update(src_policy)
        merged["cloned"] = True
        return merged

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(router, "user_dao", UserDao())
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", lambda: calls.append(("invalidate_cache",)))
    monkeypatch.setattr(router, "get_default_user_template_id", lambda: "template-1")
    monkeypatch.setattr(router, "clone_policy", fake_clone_policy)
    monkeypatch.setattr(router, "get_client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(router, "add_audit_log", lambda **kwargs: calls.append(("add_audit_log", kwargs)))
    monkeypatch.setattr(
        router,
        "datetime",
        SimpleNamespace(datetime=SimpleNamespace(now=lambda: SimpleNamespace(isoformat=lambda: "2026-06-04T00:00:00"))),
    )

    result = router.api_manage_user_new(
        router.NewUserModelEx(
            name="Alice",
            password="secret",
            expire_date="2026-12-31",
            max_concurrent=2,
            is_vip=True,
            remark="note",
            allow_routes="r1",
            block_routes="r2",
            req_free=1,
            req_free_count=3,
        ),
        request,
    )

    assert result == {"status": "success", "message": "用户创建成功"}
    assert ("invalidate_cache",) in calls
    assert ("clone_policy", {"Existing": True}, {"Template": True}, True, True, True) in calls
    assert (
        "create_user_meta",
        (
            "new-1",
            "2026-12-31",
            2,
            1,
            "note",
            "r1",
            "r2",
            1,
            3,
            "2026-06-04T00:00:00",
        ),
    ) in calls
    assert (
        "add_audit_log",
        {
            "admin_id": "admin-1",
            "admin_name": "Admin User",
            "action": "创建用户",
            "target_user_id": "new-1",
            "target_user_name": "Alice",
            "ip_address": "127.0.0.1",
        },
    ) in calls

    policy_posts = [call for call in calls if call[0] == "post" and call[1] == "/Users/new-1/Policy"]
    assert policy_posts == [("post", "/Users/new-1/Policy", {"json": {"Existing": True, "Template": True, "cloned": True}})]


def test_delete_user_denies_missing_login_before_side_effects(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before login authorization")

        def delete(self, *_args, **_kwargs):
            raise AssertionError("media_api.delete should not run before login authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run before login authorization")),
    )

    result = router.api_manage_user_delete("u1", request)

    assert result == {"status": "error", "message": "未登录"}


def test_delete_user_denies_non_admin_before_media_or_cache(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class MediaApiMustNotRun:
        def health_check(self):
            raise AssertionError("media_api.health_check should not run before admin authorization")

        def delete(self, *_args, **_kwargs):
            raise AssertionError("media_api.delete should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run before admin authorization")),
    )

    result = router.api_manage_user_delete("u1", request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_delete_user_rejects_unhealthy_media_before_cache_or_delete(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MediaApi:
        def health_check(self):
            return False

        def delete(self, *_args, **_kwargs):
            raise AssertionError("media_api.delete should not run when health check fails")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(
        router.user_service,
        "invalidate_emby_users_cache",
        lambda: (_ for _ in ()).throw(AssertionError("cache invalidation should not run when health check fails")),
    )

    result = router.api_manage_user_delete("u1", request)

    assert result == {"status": "error", "message": "Emby 服务不可用，请稍后重试"}


def test_delete_user_requires_verified_password_before_delete_side_effects(monkeypatch):
    from app.domains.users import router

    calls = []
    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MediaApi:
        def health_check(self):
            return True

        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run before delete password verification")

        def delete(self, *_args, **_kwargs):
            raise AssertionError("media_api.delete should not run before delete password verification")

    class UserDaoMustNotRun:
        def delete_user_meta(self, *_args, **_kwargs):
            raise AssertionError("user_dao.delete_user_meta should not run before delete password verification")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", MediaApi())
    monkeypatch.setattr(router, "user_dao", UserDaoMustNotRun())
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", lambda: calls.append("invalidate"))
    monkeypatch.setattr(
        router,
        "add_audit_log",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("audit log should not run before delete password verification")
        ),
    )

    result = router.api_manage_user_delete("u1", request)

    assert result == {"status": "error", "message": "需要验证密码", "need_password": True}
    assert calls == ["invalidate"]


def test_single_user_denies_non_admin_before_media_or_dao_call(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class MediaApiMustNotRun:
        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run before admin authorization")

    class UserDaoMustNotRun:
        def get_user_meta(self, *_args, **_kwargs):
            raise AssertionError("user_dao.get_user_meta should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(router, "user_dao", UserDaoMustNotRun())

    result = router.api_get_single_user("u1", request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_single_user_preserves_response_mapping_and_error_branches(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1", "role": "admin"}})

    class MetaRow(dict):
        pass

    class SuccessResponse:
        status_code = 200

        def json(self):
            return {
                "Id": "u1",
                "Name": "Alice",
                "Policy": {
                    "EnableAllFolders": False,
                    "EnabledFolders": ["lib-1"],
                    "ExcludedSubFolders": ["sub-1"],
                    "EnableContentDownloading": False,
                    "EnableVideoPlaybackTranscoding": False,
                    "EnableAudioPlaybackTranscoding": False,
                    "MaxParentalRating": 9,
                    "BlockUnratedItems": True,
                    "BlockedTags": ["tag-a", "tag-b"],
                },
            }

    class ErrorResponse:
        status_code = 500

    class MediaApi:
        def __init__(self):
            self.response = SuccessResponse()

        def get(self, *_args, **_kwargs):
            return self.response

    media_api = MediaApi()
    meta_row = MetaRow(
        max_concurrent=2,
        is_vip=1,
        remark="note",
        req_free=1,
        req_free_count=3,
    )
    monkeypatch.setattr(router, "is_admin_user", lambda _request: True)
    monkeypatch.setattr(router, "media_api", media_api)
    monkeypatch.setattr(router, "user_dao", SimpleNamespace(get_user_meta=lambda _user_id: meta_row))

    assert router.api_get_single_user("u1", request) == {
        "status": "success",
        "data": {
            "Id": "u1",
            "Name": "Alice",
            "EnableAllFolders": False,
            "EnabledFolders": ["lib-1"],
            "ExcludedSubFolders": ["sub-1"],
            "EnableDownloading": False,
            "EnableVideoTranscoding": False,
            "EnableAudioTranscoding": False,
            "MaxParentalRating": 9,
            "BlockUnratedItems": True,
            "BlockedTags": "tag-a,tag-b",
            "MaxConcurrent": 2,
            "IsVIP": True,
            "Remark": "note",
            "req_free": 1,
            "req_free_count": 3,
        },
    }

    media_api.response = ErrorResponse()
    assert router.api_get_single_user("u1", request) == {"status": "error"}

    monkeypatch.setattr(
        router,
        "media_api",
        SimpleNamespace(get=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    assert router.api_get_single_user("u1", request) == {"status": "error"}


def test_manage_libraries_denies_non_admin_before_media_call(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class MediaApiMustNotRun:
        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())

    result = router.api_get_libraries(request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_avatar_fetch_denies_non_admin_before_media_call(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1"}})

    class MediaApiMustNotRun:
        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())

    response = router.get_user_avatar("u1", request)

    assert response.status_code == 403


def test_avatar_update_denies_non_admin_before_side_effects(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin-1"}})

    class MediaApiMustNotRun:
        def get(self, *_args, **_kwargs):
            raise AssertionError("media_api.get should not run before admin authorization")

        def delete(self, *_args, **_kwargs):
            raise AssertionError("media_api.delete should not run before admin authorization")

        def post(self, *_args, **_kwargs):
            raise AssertionError("media_api.post should not run before admin authorization")

    class NetworkClientMustNotRun:
        def get(self, *_args, **_kwargs):
            raise AssertionError("network_client.get should not run before admin authorization")

    class FileMustNotRead:
        content_type = "image/jpeg"

        async def read(self):
            raise AssertionError("file.read should not run before admin authorization")

    monkeypatch.setattr(router, "is_admin_user", lambda _request: False)
    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(router, "network_client", NetworkClientMustNotRun())
    monkeypatch.setattr(
        router,
        "add_audit_log",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("audit log should not run before admin authorization")
        ),
    )
    monkeypatch.setattr(
        router,
        "get_client_ip",
        lambda _request: (_ for _ in ()).throw(
            AssertionError("client IP lookup should not run before admin authorization")
        ),
    )

    result = asyncio.run(
        router.api_update_user_image(
            request,
            user_id="u1",
            url="https://example.com/avatar.jpg",
            file=FileMustNotRead(),
        )
    )

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_self_avatar_denies_missing_req_user_before_file_read():
    from app.domains.users import router

    request = SimpleNamespace(session={})

    class FileMustNotRead:
        content_type = "image/jpeg"

        async def read(self):
            raise AssertionError("file.read should not run before login authorization")

    result = asyncio.run(router.api_user_self_avatar(request, file=FileMustNotRead()))

    assert result == {"status": "error", "message": "请先登录"}


def test_self_password_denies_missing_req_user_before_validation_or_media(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={})

    class MediaApiMustNotRun:
        def authenticate_by_name(self, *_args, **_kwargs):
            raise AssertionError("media_api.authenticate_by_name should not run before login authorization")

        def post(self, *_args, **_kwargs):
            raise AssertionError("media_api.post should not run before login authorization")

    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(
        router,
        "validate_password_strength",
        lambda _password: (_ for _ in ()).throw(
            AssertionError("password validation should not run before login authorization")
        ),
    )

    result = router.api_user_self_password(
        router.UserPasswordChangeModel(old_password="old", new_password="new-valid"),
        request,
    )

    assert result == {"status": "error", "message": "请先登录"}


def test_self_password_rejects_invalid_new_password_before_media(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"req_user": {"Id": "u1", "Name": "Alice"}})

    class MediaApiMustNotRun:
        def authenticate_by_name(self, *_args, **_kwargs):
            raise AssertionError("media_api.authenticate_by_name should not run before password validation")

        def post(self, *_args, **_kwargs):
            raise AssertionError("media_api.post should not run before password validation")

    monkeypatch.setattr(router, "media_api", MediaApiMustNotRun())
    monkeypatch.setattr(router, "validate_password_strength", lambda _password: (False, "密码太弱"))

    result = router.api_user_self_password(
        router.UserPasswordChangeModel(old_password="old", new_password="weak"),
        request,
    )

    assert result == {"status": "error", "message": "密码太弱"}


def test_pin_route_denies_unauthenticated_before_side_effects(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={})

    class UserDaoMustNotRun:
        def set_user_pinned(self, *_args, **_kwargs):
            raise AssertionError("user_dao.set_user_pinned should not run before login authorization")

    monkeypatch.setattr(router, "user_dao", UserDaoMustNotRun())
    monkeypatch.setattr(
        router,
        "add_audit_log",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("audit log should not run before login authorization")
        ),
    )
    monkeypatch.setattr(
        router,
        "get_client_ip",
        lambda _request: (_ for _ in ()).throw(
            AssertionError("client IP lookup should not run before login authorization")
        ),
    )

    result = router.api_pin_user(router.PinUserModel(user_id="u1", pinned=True), request)

    assert result == {"status": "error", "message": "未登录"}


def test_pin_route_denies_non_admin_before_side_effects(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "user-1", "role": "viewer"}})

    class UserDaoMustNotRun:
        def set_user_pinned(self, *_args, **_kwargs):
            raise AssertionError("user_dao.set_user_pinned should not run before admin authorization")

    monkeypatch.setattr(router, "user_dao", UserDaoMustNotRun())
    monkeypatch.setattr(
        router,
        "add_audit_log",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("audit log should not run before admin authorization")
        ),
    )
    monkeypatch.setattr(
        router,
        "get_client_ip",
        lambda _request: (_ for _ in ()).throw(
            AssertionError("client IP lookup should not run before admin authorization")
        ),
    )

    result = router.api_pin_user(router.PinUserModel(user_id="u1", pinned=True), request)

    assert result == {"status": "error", "message": "需要管理员权限"}


def test_delete_verification_route_preserves_router_app_start_time_compat(monkeypatch):
    from app.domains.users import delete_verification_router, router

    request = SimpleNamespace(
        session={
            "user": {"id": "admin-1"},
            "delete_verified": True,
            "delete_verified_time": "2000-01-01T00:00:00",
        }
    )

    monkeypatch.setattr(router, "APP_START_TIME", "2999-01-01T00:00:00")
    monkeypatch.setattr(delete_verification_router, "is_admin_user", lambda request: True)

    assert router.api_check_delete_verified(request) == {"status": "success", "verified": False}
    assert request.session["delete_verified"] is False


def test_selected_external_callers_use_real_user_dao_for_persistence_calls():
    checked_paths = [
        _REPO_ROOT / "app/plugins/auto_expire/plugin.py",
        _REPO_ROOT / "app/plugins/keep_alive/plugin.py",
        _REPO_ROOT / "app/plugins/user_backup/user_backup_dao.py",
        _REPO_ROOT / "app/domains/media_requests/router.py",
        _REPO_ROOT / "app/domains/notifications/user_bot_service.py",
        _REPO_ROOT / "app/domains/system/views.py",
    ]
    violations = []

    for path in checked_paths:
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "app.domains.users.router":
                    imported_names = {alias.name for alias in node.names}
                    if "invalidate_emby_users_cache" in imported_names or "*" in imported_names:
                        violations.append(f"{rel_path}:{node.lineno}")
                if node.module == "app.domains.users":
                    imported_names = {alias.name for alias in node.names}
                    if "public_service" in imported_names:
                        continue

    assert violations == []


def test_plugins_do_not_import_private_users_auth_boundary():
    violations = []

    for path in (_REPO_ROOT / "app/plugins").rglob("*.py"):
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
