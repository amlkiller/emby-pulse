import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_main_menu_keyboard_for_unbound_user_uses_legacy_wrapper(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    monkeypatch.setattr(user_bot_service, "get_user_bot_portal_url", lambda: "https://portal.example")

    assert user_bot_service._main_menu_keyboard(None) == {"inline_keyboard": [
        [{"text": "📝 绑定已有账号", "callback_data": "ub_menu_bind"}, {"text": "🆕 注册新账号", "callback_data": "ub_menu_register"}],
        [{"text": "🎟️ 注册码激活", "callback_data": "ub_menu_code"}, {"text": "📊 媒体库统计", "callback_data": "ub_menu_library"}],
    ]}


def test_main_menu_keyboard_for_bound_user_without_portal_url(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    monkeypatch.setattr(user_bot_service, "get_user_bot_portal_url", lambda: "")

    assert user_bot_service._main_menu_keyboard({"emby_user_id": "u1"}) == {"inline_keyboard": [
        [{"text": "✅ 每日签到", "callback_data": "ub_menu_checkin"}, {"text": "👤 个人中心", "callback_data": "ub_menu_profile"}],
        [{"text": "🏪 积分商城", "callback_data": "ub_menu_shop"}, {"text": "🎬 我要求片", "callback_data": "ub_menu_request"}],
        [{"text": "📋 我的求片", "callback_data": "ub_menu_myrequests"}],
        [{"text": "📊 媒体库统计", "callback_data": "ub_menu_library"}],
        [{"text": "🔐 修改密码", "callback_data": "ub_menu_password"}, {"text": "📡 服务器状态", "callback_data": "ub_menu_server"}],
        [{"text": "🎟️ 续期码续期", "callback_data": "ub_menu_renew"}],
        [{"text": "🔓 解绑账号", "callback_data": "ub_menu_unbind"}],
    ]}


def test_main_menu_keyboard_for_bound_user_uses_patched_legacy_portal_url(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    monkeypatch.setattr(user_bot_service, "get_user_bot_portal_url", lambda: "https://portal.example")

    keyboard = user_bot_service._main_menu_keyboard({"emby_user_id": "u1"})

    assert keyboard["inline_keyboard"][-1] == [{"text": "🌐 网页版用户中心", "url": "https://portal.example"}]
    assert len(keyboard["inline_keyboard"]) == 8
