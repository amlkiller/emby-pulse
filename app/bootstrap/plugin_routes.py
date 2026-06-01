def register_calendar_notify_routes(app) -> None:
    from app.routers import calendar_notify

    app.include_router(calendar_notify.router)
    calendar_notify.init_calendar_notify_service()


def register_plugin_routes(app) -> None:
    from app.plugins import discover_plugins, get_enabled_plugins
    from app.routers import plugins as plugins_router

    discover_plugins()
    for plugin in get_enabled_plugins():
        try:
            app.include_router(plugin.router)
        except Exception as e:
            print(f"[🧩 插件] 注册路由失败: {plugin.id} - {e}")

    app.include_router(plugins_router.router)
    plugins_router.set_app(app)
