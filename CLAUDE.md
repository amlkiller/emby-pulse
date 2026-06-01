# EmbyPulse-Pro (映迹专业版)

## Project Overview

Professional-grade management and monitoring hub for Emby/Jellyfin media servers.
FastAPI + Python 3.9 web application with plugin architecture, Telegram/WeCom integration, risk management, user portal, and Pro licensing.

- **Admin portal**: port 10307
- **User portal**: port 10308, isolated request/invite portal
- **Docker image**: `zeyu8023/embypulse-pro:latest`
- **License**: MIT with project-specific anti-closed-source clause

## Tech Stack

- **Backend**: FastAPI, uvicorn, SQLite WAL mode, Jinja2
- **Frontend**: Server-rendered templates plus vanilla JS and ECharts
- **Bots / notifications**: python-telegram-bot, Telegram Bot API, WeCom API
- **Image processing**: Pillow
- **Auth**: bcrypt, PyJWT, TOTP, database-backed sessions
- **Other**: pypinyin, croniter, openpyxl

## Current Architecture

The project is mid-refactor. Use `架构.md` as the authoritative architecture roadmap.

### Application Bootstrap

- `app/main.py` is intentionally thin: version constants, app factory wiring, and local uvicorn entrypoint.
- `app/bootstrap/` owns startup wiring, middleware registration, static mounts, route registration, lifespan tasks, database initialization, logging, runtime preparation, and user portal startup.
- Do not move business behavior into `app/bootstrap/`; call domain/router/service code from bootstrap wiring when needed.

### Database Boundary

- First-stage database boundary refactor is complete.
- `query_db()` has been removed and must not be reintroduced.
- `app/core/database.py` and `app/core/db_manager.py` compatibility shells have been removed.
- Database infrastructure lives under `app/infra/db/`, including system store, playback store, schema registry, and migration service.
- Business access should go through DAO/query modules such as `app/dao/*` and `app/queries/*`, or through domain-local DAO/query modules as the domain migration continues.
- Direct `sqlite3.connect()` should stay inside the infrastructure database boundary.

### External Client Boundary

- External service transport belongs under `app/infra/clients/`.
- Current client boundaries include media server, TMDB, Telegram, WeCom, MoviePilot, qBittorrent, Transmission, WebDAV, 115 Cloud, HDHive, image proxy, IP location, weather, and generic network probing.
- Routers, services, and plugins should not add new direct `requests.get/post/put/delete/request` calls. Add or extend an infra client instead.
- `media_api` and `MediaServerAdapter` live in `app/infra/clients/media_server_client.py`; old `app.core.media_adapter` imports should not be used.

### Configuration Boundary

- Third-stage config access governance is in progress.
- Infrastructure-scoped settings readers live under `app/infra/config/`.
- Prefer focused readers such as `media_server_settings`, `tmdb_settings`, `notification_settings`, `risk_settings`, `request_portal_settings`, `auth_settings`, `calendar_settings`, `weather_settings`, `report_settings`, and `user_bot_settings`.
- Avoid adding scattered `cfg.get()` / `cfg.set()` in routers, services, plugins, or domain code.

### Domain Migration

- Long-term target: related HTTP entrypoints, schemas, services, DAO/query code, and policies move into `app/domains/<name>/`.
- Existing migrated domains include `playback`, `media_requests`, `notifications`, `points`, `risk`, `system`, and `users`.
- `app/routers/*` may contain compatibility shims during migration. For moved router modules, prefer a module-level proxy shim:

```python
import sys
from app.domains.<domain> import <module> as _impl
sys.modules[__name__] = _impl
```

- Preserve route paths, response shapes, auth behavior, and side effects during migration batches.

## Key Directories

```text
app/
  main.py
  bootstrap/          # app startup, route/middleware/lifespan wiring
  core/               # cross-cutting runtime helpers: config, security, sessions, middleware
  infra/
    clients/          # external service adapters
    config/           # typed/focused settings readers
    db/               # database infrastructure and migrations
  domains/            # gradually consolidated business domains
  routers/            # HTTP routers and compatibility shims during migration
  services/           # long-running services and business workflows not yet domain-local
  dao/                # system DB DAO modules during transition
  queries/            # playback/stat query modules during transition
  plugins/            # plugin system and built-in plugins
  schemas/
  utils/
templates/
static/
tests/
```

## Plugin System

- Plugins are discovered from `app/plugins/<name>/plugin.py` classes inheriting `PluginBase`.
- Each plugin gets an `APIRouter` at `/api/plugins/{plugin_id}`.
- Plugin state and config persist in system DB tables.
- Lifecycle hooks include `on_enable()` and `on_disable()`.
- Pro-only plugins are gated by license checks.
- Plugin transport calls should also go through `app/infra/clients/`.

## Development Commands

Use `uv run --with-requirements requirements.txt` for any Python command that imports or executes project code.

```powershell
# Compile focused files
$env:PYTHONIOENCODING='utf-8'; uv run --with-requirements requirements.txt python -m compileall app tests

# Smoke-test app import
$env:PYTHONIOENCODING='utf-8'; uv run --with-requirements requirements.txt python -c "from app.main import app; print(len(app.routes))"

# Full test suite
$env:PYTHONIOENCODING='utf-8'; uv run --with-requirements requirements.txt --with pytest pytest tests/ -v
```

Do not report bare `python` or bare `uv run` dependency failures as code regressions.

## Running Locally

```powershell
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Windows console output may include Chinese or emoji; set `PYTHONIOENCODING=utf-8` when running commands that print application startup output.

## Security Notes

- Sensitive values should come from environment variables or existing secure config paths.
- Swagger/ReDoc are disabled in production.
- Sessions are backed by the application database.
- CSRF and security header middleware are registered through bootstrap middleware wiring.
- SSRF-sensitive URLs and proxy bases must pass validators in `app/utils/url_validator.py`; update tests when extending validators.
- Keep log sanitization for secrets intact.

## Versioning

- Runtime version is declared in `app/main.py` as `APP_VERSION`.
- Docker/CI version mirroring is handled by existing release workflow files.

## Working Rules For Agents

- Read `架构.md` before architecture refactors.
- Keep batches small and behavior-preserving.
- Commit completed changes when requested by the user.
- Do not include unrelated dirty files unless the user explicitly asks.
- Do not modify `fixplan.md` unless explicitly asked; it is a security remediation plan.
