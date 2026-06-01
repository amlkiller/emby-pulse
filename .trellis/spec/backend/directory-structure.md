# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend lives under `app/` and currently uses a pragmatic FastAPI structure:

* `app/main.py` is the thin application entrypoint. Keep version constants and app factory wiring here only.
* `app/bootstrap/` owns application startup wiring: runtime preparation, middleware registration, route mounting, lifespan tasks, database initialization orchestration, logging setup, and the isolated user-portal ASGI wrapper.
* `app/core/` owns reusable cross-cutting runtime helpers used by multiple backend areas, such as security, sessions, configuration, middleware implementations, and short-lived compatibility shims.
* `app/infra/` owns infrastructure adapters such as database access and external service clients.
* `app/routers/` owns HTTP route handlers and should not accumulate startup/bootstrap work.
* `app/services/` owns long-running services and business workflows used by routers or startup tasks.

---

## Directory Layout

```
app/
├── bootstrap/
│   ├── database.py
│   ├── lifespan.py
│   ├── logging.py
│   ├── middleware.py
│   ├── routes.py
│   ├── runtime.py
│   └── user_portal.py
├── core/
├── infra/
│   ├── clients/
│   │   ├── media_server_client.py
│   │   ├── moviepilot_client.py
│   │   └── tmdb_client.py
│   └── db/
├── routers/
├── services/
├── plugins/
├── schemas/
├── utils/
└── main.py
```

---

## Module Organization

Bootstrap code should stay behavior-preserving and orchestration-focused. Do not move business rules into `app/bootstrap/`; if a startup task needs business logic, call the existing router/service function and leave domain behavior in its current layer until that feature is explicitly refactored.

When splitting large files, move one responsibility at a time and keep route URLs, response shapes, middleware order, and startup side effects stable unless a task explicitly approves behavior changes.

Infrastructure adapters should live under `app/infra/` rather than `app/core/` when they own transport/session/retry behavior for an external dependency. If a temporary compatibility import is needed during a migration, keep it in `app/core/` as a thin re-export only.

---

## Naming Conventions

Use lowercase module names that describe the application responsibility:

* `runtime.py` for pre-app runtime preparation.
* `middleware.py` for middleware classes and registration order.
* `routes.py` for static mounts and router/plugin registration.
* `lifespan.py` for FastAPI lifespan startup/shutdown tasks.
* `user_portal.py` for the isolated user portal ASGI wrapper and secondary-port server.

---

## Examples

`app/main.py` should remain a thin example of the desired application entrypoint: constants, `prepare_runtime()`, `create_app()`, exception handler registration, and the `uvicorn.run()` local entrypoint.

## Scenario: External Client Adapter Boundary

### 1. Scope / Trigger

- Trigger: any backend code that creates or changes HTTP/WebDAV/third-party transport calls for an external service.
- Applies to routers, services, plugins, utilities, and infrastructure modules under `app/`.

### 2. Signatures

- External client modules live in `app/infra/clients/<service>_client.py`.
- Each module should expose a focused client class and a singleton instance, for example `WebDavClient` and `webdav_client`.
- Public client methods should preserve call-site behavior by accepting the same material transport inputs: URL/path, headers, auth, params/data/json payloads, proxies, timeout, and redirect behavior when relevant.

### 3. Contracts

- Transport/session/retry/request construction belongs in `app/infra/clients/`.
- Routers, services, and plugins may keep business validation, response message mapping, XML/JSON parsing, file persistence, and domain-specific branching.
- Exception classes from the underlying transport library should not force callers to import that library directly; expose the needed exception type or wrap it at the client boundary.
- Client modules must not depend on routers, concrete domains, or plugin classes.

### 4. Validation & Error Matrix

- Existing timeout or status-code handling at the caller -> preserve the same branches unless the task explicitly changes behavior.
- Existing proxy/auth/header behavior -> pass through unchanged or normalize only where existing code already normalized.
- New direct `requests.*` in a router/service/plugin -> move it behind an infra client unless it is a clearly scoped byte-stream helper that the architecture notes allow to remain.
- Caller needs `requests.exceptions.Timeout` or similar -> expose it via the client boundary instead of adding a caller-side `requests` import.

### 5. Good/Base/Bad Cases

- Good: `app/plugins/user_backup/plugin.py` calls `webdav_client.request("PROPFIND", ...)` while keeping WebDAV XML parsing in the plugin.
- Base: `app/routers/system.py` keeps user-facing TMDB error messages while calling `tmdb_client.get_configuration(...)`.
- Bad: a plugin imports `requests` only to call `requests.get(...)` against a third-party service.
- Good: `app/utils/ip_location.py` keeps cache and location cleaning locally while delegating all external IP lookup HTTP calls to `ip_location_client`.
- Good: `app/routers/system_tools.py` keeps weather cache and fallback ordering locally while delegating QWeather/Amap/wttr transport calls to `weather_client`.
- Good: `app/routers/system.py` keeps proxy validation and ping response messages locally while delegating probe requests and exception aliases to `network_client`.

### 6. Tests Required

- Focused refactor: compile the changed client and caller files with `uv run --with-requirements requirements.txt python -m compileall <paths>`.
- Import-sensitive refactor: import the new client and the changed caller through `uv run --with-requirements requirements.txt python -c ...`.
- Before completing a batch: run `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` unless the user explicitly narrows verification scope.
- Search assertion: verify direct transport calls are removed from the migrated caller and remain only inside the relevant client.

### 7. Wrong vs Correct

#### Wrong

```python
import requests

resp = requests.request("PROPFIND", dir_url, auth=auth, timeout=30)
```

#### Correct

```python
from app.infra.clients.webdav_client import webdav_client

resp = webdav_client.request("PROPFIND", dir_url, auth=auth, timeout=30)
```
