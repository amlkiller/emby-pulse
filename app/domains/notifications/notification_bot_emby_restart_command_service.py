import logging


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger
_get_plugin_provider = lambda: _default_get_plugin
_get_plugin_config_provider = lambda: _default_get_plugin_config


def _default_get_plugin(plugin_id):
    from app.plugins import get_plugin

    return get_plugin(plugin_id)


def _default_get_plugin_config(plugin_id):
    from app.plugins import get_plugin_config

    return get_plugin_config(plugin_id)


def set_dependency_providers(
    *,
    logger_provider=None,
    get_plugin_provider=None,
    get_plugin_config_provider=None,
):
    global _logger_provider
    global _get_plugin_provider
    global _get_plugin_config_provider

    if logger_provider is not None:
        _logger_provider = logger_provider
    if get_plugin_provider is not None:
        _get_plugin_provider = get_plugin_provider
    if get_plugin_config_provider is not None:
        _get_plugin_config_provider = get_plugin_config_provider


def _get_plugin(plugin_id):
    return _get_plugin_provider()(plugin_id)


def _get_plugin_config(plugin_id):
    return _get_plugin_config_provider()(plugin_id)


def cmd_emby_restart(bot, cid, text, platform):
    """Emby 服务器重启命令"""
    try:
        plugin = _get_plugin("emby_restart")
        if not plugin or not plugin.enabled:
            bot.send_message(cid, "❌ Emby 自动重启插件未启用", platform=platform)
            return

        config = _get_plugin_config("emby_restart")
        servers = config.get("servers", [])

        if not servers:
            bot.send_message(cid, "❌ 未配置 Emby 服务器，请先在插件面板中添加服务器", platform=platform)
            return

        msg = "🖥️ <b>Emby 服务器管理</b>\n\n请选择要重启的服务器：\n"

        for i, s in enumerate(servers):
            name = s.get('name', '未命名')
            msg += f"\n<b>{i+1}.</b> {name}"

        msg += f"\n\n💡 点击下方按钮重启对应服务器"

        inline_keyboard = []
        row = []
        for i, s in enumerate(servers):
            name = s.get('name', '未命名')[:8]
            row.append({"text": f"🔄 {name}", "callback_data": f"emby_restart:{i}"})
            if len(row) == 2:
                inline_keyboard.append(row)
                row = []
        if row:
            inline_keyboard.append(row)

        inline_keyboard.append([{"text": "🔄 重启全部服务器", "callback_data": "emby_restart:all"}])

        reply_markup = {"inline_keyboard": inline_keyboard}

        bot.send_message(cid, msg, platform=platform, reply_markup=reply_markup)

    except Exception as e:
        _logger_provider().error(f"[Bot] emby_restart error: {e}")
        bot.send_message(cid, f"❌ 执行失败: {str(e)}", platform=platform)


def handle_emby_restart_callback(bot, data, cid, cq, platform="tg"):
    try:
        plugin = _get_plugin("emby_restart")
        if not plugin or not plugin.enabled:
            bot.send_message(cid, "❌ Emby 自动重启插件未启用", platform=platform)
            return

        config = _get_plugin_config("emby_restart")
        servers = config.get("servers", [])

        action = data.split(":")[1]

        if action == "all":
            bot.send_message(cid, f"🔄 正在重启全部 {len(servers)} 台 Emby 服务器...", platform=platform)
            result = plugin.manual_restart()
            if result.get("success"):
                bot.send_message(cid, f"✅ {result.get('message', '重启成功')}", platform=platform)
            else:
                bot.send_message(cid, f"❌ {result.get('message', '重启失败')}", platform=platform)
        else:
            index = int(action)
            if index < 0 or index >= len(servers):
                bot.send_message(cid, "❌ 服务器不存在", platform=platform)
                return

            server = servers[index]
            name = server.get('name', '未命名')
            bot.send_message(cid, f"🔄 正在重启服务器 [{name}]...", platform=platform)

            result = plugin._restart_via_emby_api(server.get('host'), server.get('api_key'))
            if result.get("success"):
                bot.send_message(cid, f"✅ 服务器 [{name}] 重启成功", platform=platform)
            else:
                bot.send_message(cid, f"❌ 服务器 [{name}] 重启失败: {result.get('message', '未知错误')}", platform=platform)
    except Exception as e:
        _logger_provider().error(f"[Bot] emby_restart callback error: {e}")
        bot.send_message(cid, f"❌ 执行失败: {str(e)}", platform=platform)
