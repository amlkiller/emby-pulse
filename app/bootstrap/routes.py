from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def register_static_assets(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory="static"), name="static")

    import os

    public_dir = os.path.join(os.getcwd(), "public")
    if not os.path.exists(public_dir):
        os.makedirs(public_dir, exist_ok=True)
    app.mount("/public", StaticFiles(directory=public_dir), name="public")


def register_routes(app: FastAPI) -> None:
    from app.routers import (
        api_tokens,
        auth,
        bot as bot_router,
        clients,
        db_tools,
        dedupe,
        gaps,
        history,
        insight,
        media_request,
        messages,
        notifications,
        notify_admin,
        notify_rules,
        points,
        pwa,
        proxy,
        report,
        risk,
        stats,
        system,
        system_tools,
        tasks,
        users,
        views,
        webhook,
    )
    from app.domains.playback import calendar, search
    from app.domains.system import audit, pro
    from .plugin_routes import register_calendar_notify_routes, register_plugin_routes

    app.include_router(views.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(stats.router)
    app.include_router(bot_router.router)
    app.include_router(system.router)
    app.include_router(api_tokens.router)
    app.include_router(proxy.router)
    app.include_router(report.router)
    app.include_router(insight.router)
    app.include_router(webhook.router)
    app.include_router(tasks.router)
    app.include_router(history.router)
    app.include_router(calendar.router)
    app.include_router(media_request.router)
    app.include_router(search.router)
    app.include_router(clients.router)
    app.include_router(gaps.router)
    app.include_router(risk.router)
    app.include_router(notifications.router)
    app.include_router(notify_admin.router)
    app.include_router(dedupe.router)
    app.include_router(notify_rules.router)
    app.include_router(system_tools.router)
    app.include_router(points.router)
    app.include_router(pro.router)
    app.include_router(db_tools.router)
    app.include_router(messages.router)
    app.include_router(pwa.router)

    register_calendar_notify_routes(app)
    register_plugin_routes(app)
    app.include_router(audit.router)
