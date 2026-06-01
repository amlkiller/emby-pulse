import asyncio
import json
import socket
import threading

import uvicorn

_user_portal_lock = threading.Lock()
_user_portal_thread = None
_user_portal_server = None


def build_user_portal_app(app, request_port: int):
    """Wrap the main app to enforce the user-portal path restrictions."""
    allowed = (
        "/request",
        "/request_login",
        "/static",
        "/favicon.ico",
        "/manifest.json",
        "/sw.js",
        "/apple-touch-icon.png",
        "/api/login",
        "/api/register",
        "/api/auth/settings",
        "/api/auth/avatar",
        "/api/requests",
        "/api/user/messages",
        "/api/user/announcements",
        "/api/user/my_series",
        "/api/user/request_update",
        "/api/user/points",
        "/api/user/mute_status",
        "/api/user/avatar",
        "/api/user/password",
        "/api/user/libraries",
        "/api/user/image",
        "/api/user/renew",
        "/api/announcements",
        "/api/wallpaper",
        "/api/proxy/",
        "/api/library/",
        "/api/pro/status",
        "/api/pro/activate",
        "/api/notifications",
        "/api/pwa/",
        "/api/ping",
        "/api/live",
        "/api/stats/dashboard",
        "/api/stats/badges",
        "/api/stats/trend",
        "/api/stats/user_details",
        "/api/stats/chart",
        "/api/stats/recent",
        "/api/stats/latest",
        "/api/stats/libraries",
        "/api/stats/top_movies",
        "/api/stats/monthly_stats",
        "/api/stats/recent_added",
        "/api/stats/poster_data",
        "/api/stats/live",
        "/api/points/config",
        "/api/points/rank",
        "/api/slot/",
        "/api/scratch/",
        "/api/wheel/",
        "/api/guess/",
        "/api/lottery/",
        "/invite",
    )
    blocked = (
        "/api/system",
        "/api/settings",
        "/api/users",
        "/api/manage",
        "/api/tokens",
        "/api/bot",
        "/api/risk",
        "/api/audit",
        "/api/tasks",
        "/api/db",
        "/api/requests/refresh_cache",
        "/api/requests/clear_cache",
        "/api/requests/pending_notify",
    )

    async def user_portal_app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        elif scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/":
                scope["path"] = "/request"
                scope["raw_path"] = b"/request"

            if not scope["path"].startswith(allowed) or scope["path"].startswith(blocked):
                body = json.dumps({"detail": "非法越界，后台管理界面已被物理阻断"}).encode("utf-8")
                await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return

            await app(scope, receive, send)
        else:
            await app(scope, receive, send)

    return user_portal_app


def start_user_portal_server(app, request_port: int) -> None:
    """Start the isolated user portal on the secondary port."""
    global _user_portal_server
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.bind(("0.0.0.0", request_port))
        sock.listen(100)
    except OSError:
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = uvicorn.Config(app=build_user_portal_app(app, request_port), log_level="error")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    with _user_portal_lock:
        _user_portal_server = server
    try:
        loop.run_until_complete(server.serve(sockets=[sock]))
    except BaseException:
        pass
    finally:
        loop.close()
        with _user_portal_lock:
            if _user_portal_server is server:
                _user_portal_server = None
            if threading.current_thread() is _user_portal_thread:
                globals()["_user_portal_thread"] = None


def start_user_portal_thread(app, request_port: int) -> None:
    global _user_portal_thread
    with _user_portal_lock:
        if _user_portal_thread and _user_portal_thread.is_alive():
            return
        _user_portal_thread = threading.Thread(
            target=start_user_portal_server,
            args=(app, request_port),
            daemon=True,
            name="user-portal-server",
        )
        _user_portal_thread.start()


def stop_user_portal_thread() -> None:
    global _user_portal_thread, _user_portal_server
    with _user_portal_lock:
        thread = _user_portal_thread
        server = _user_portal_server
        if server:
            server.should_exit = True

    if thread and thread.is_alive():
        thread.join(timeout=1)

    with _user_portal_lock:
        if thread is _user_portal_thread and (thread is None or not thread.is_alive()):
            _user_portal_thread = None
            _user_portal_server = None
