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
