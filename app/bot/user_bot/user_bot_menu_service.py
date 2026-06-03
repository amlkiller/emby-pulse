from app.infra.config.user_bot_settings import get_user_bot_portal_url


_portal_url_provider = lambda: get_user_bot_portal_url()


def set_dependency_providers(*, portal_url_provider=None):
    global _portal_url_provider

    if portal_url_provider is not None:
        _portal_url_provider = portal_url_provider


def main_menu_keyboard(binding=None):
    """生成主菜单 inline keyboard"""
    if not binding:
        return {"inline_keyboard": [
            [{"text": "📝 绑定已有账号", "callback_data": "ub_menu_bind"}, {"text": "🆕 注册新账号", "callback_data": "ub_menu_register"}],
            [{"text": "🎟️ 注册码激活", "callback_data": "ub_menu_code"}, {"text": "📊 媒体库统计", "callback_data": "ub_menu_library"}]
        ]}
    rows = [
        [{"text": "✅ 每日签到", "callback_data": "ub_menu_checkin"}, {"text": "👤 个人中心", "callback_data": "ub_menu_profile"}],
        [{"text": "🏪 积分商城", "callback_data": "ub_menu_shop"}, {"text": "🎬 我要求片", "callback_data": "ub_menu_request"}],
        [{"text": "📋 我的求片", "callback_data": "ub_menu_myrequests"}],
        [{"text": "📊 媒体库统计", "callback_data": "ub_menu_library"}],
        [{"text": "🔐 修改密码", "callback_data": "ub_menu_password"}, {"text": "📡 服务器状态", "callback_data": "ub_menu_server"}],
        [{"text": "🎟️ 续期码续期", "callback_data": "ub_menu_renew"}],
        [{"text": "🔓 解绑账号", "callback_data": "ub_menu_unbind"}],
    ]
    portal_url = _portal_url_provider()
    if portal_url:
        rows.append([{"text": "🌐 网页版用户中心", "url": portal_url}])
    return {"inline_keyboard": rows}
