# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend lives under `app/` and currently uses a pragmatic FastAPI structure
with most HTTP and business modules now grouped under `app/domains/`:

* `app/main.py` is the thin application entrypoint. Keep app factory wiring and local uvicorn entrypoint behavior here only; side-effect-free runtime metadata such as `APP_VERSION` belongs under `app/shared/`.
* `app/bootstrap/` owns application startup wiring: runtime preparation, middleware registration, route mounting, lifespan tasks, database initialization orchestration, logging setup, and the isolated user-portal ASGI wrapper.
* `app/core/` owns reusable cross-cutting runtime helpers used by multiple backend areas, such as security, sessions, configuration, middleware implementations, and short-lived compatibility shims.
* `app/infra/` owns infrastructure adapters such as database access, external service clients, and infrastructure-scoped configuration readers.
* `app/domains/` owns domain-local HTTP route handlers, services, DAO/query modules, policy helpers, and background service entrypoints.
* `app/plugins/` owns the plugin runtime plus built-in plugins.

The old top-level `app/routers/`, `app/services/`, `app/dao/`, and `app/queries/`
directories are no longer the current target layout in this checkout. Do not add
new modules there unless a task explicitly asks for a compatibility shim.

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
│   ├── config/
│   └── db/
├── domains/
│   ├── media_requests/
│   ├── notifications/
│   ├── playback/
│   ├── points/
│   ├── reports/
│   ├── risk/
│   ├── system/
│   └── users/
├── plugins/
├── schemas/
├── shared/
├── utils/
└── main.py
```

---

## Module Organization

Bootstrap code should stay behavior-preserving and orchestration-focused. Do not move business rules into `app/bootstrap/`; if a startup task needs business logic, call the existing domain router/service function and leave domain behavior in its current layer until that feature is explicitly refactored.

When splitting large files, move one responsibility at a time and keep route URLs, response shapes, middleware order, and startup side effects stable unless a task explicitly approves behavior changes.

When extracting inline callback or background-task branches, verify the state container's actual type before preserving cleanup calls. For example, a chat-id reply-mode map should use dict semantics such as `pop(key, None)`, not set-only cleanup such as `discard(key)`. Add focused coverage for the migrated cleanup path, because these branches may have been untested inside the larger file.

Infrastructure adapters should live under `app/infra/` rather than `app/core/` when they own transport/session/retry behavior for an external dependency. If a temporary compatibility import is needed during a migration, keep it in `app/core/` as a thin re-export only.

Current migration pattern: if a caller only needs generic external transport for file/image downloads or simple reachability probes, route it through `app/infra/clients/network_client.py` instead of leaving direct `requests.get(...)` calls in domains or plugins. Keep domain parsing, cache decisions, and user-facing error mapping at the caller.

Current configuration migration pattern: infrastructure-scoped settings readers live under `app/infra/config/` and are used to centralize config access for infra modules before broader service/router config cleanup is tackled. These readers should expose a typed contract rather than raw `cfg.get()` values: define defaults, empty-value behavior, allowed enum values, numeric lower/upper bounds where relevant, boolean string handling, and whether writes are normalized before persistence.

When multiple settings modules need the same primitive normalization, keep the reusable helper inside `app/infra/config/` rather than copying private coercion functions. For example, use `app.infra.config.coercion.coerce_positive_int()` for positive integer settings such as cache TTLs, thresholds, worker counts, and queue sizes; pass `minimum` / `maximum` when the setting has explicit bounds, and keep module-local constants for each setting's default and semantic bounds.

Current proxy configuration pattern: `app/utils/proxy_helper.py` keeps validation, caching, and audit logging, while raw `proxy_url` / `wecom_proxy_url` reads live under `app/infra/config/proxy_settings.py`.

Domain migration is in the "moved but not fully layered" stage. Several current
domain files are still intentionally large compatibility-preserving modules. When
cleaning them up, prefer small behavior-preserving slices:

* `router.py` for HTTP endpoints, dependency checks, template rendering, and response compatibility.
* `service.py` or named service modules for business orchestration and background workflows.
* `dao.py` / `*_dao.py` for system database persistence through `system_store`.
* `queries.py` / `*_queries.py` for playback/read-model queries through `playback_store`.
* `policy.py` for reusable decision rules.
* `events.py` for cross-domain event publication or handling.

Do not deepen cross-domain imports into private DAO/query modules. If one domain
needs another domain's behavior, prefer a public service function, a narrow
facade, or an event boundary.

Public service modules are semantic boundaries, not re-export bins. Keep a
`public_service.py` function only when it adds boundary value such as permission
policy, cache ownership, lazy runtime lookup, exception handling, normalization,
or cross-call orchestration. If a function only forwards arguments to a DAO,
query module, service object, or view helper without additional behavior, remove
the wrapper and point callers at the module that performs the work.

Foundation layers must not import concrete domains. `app/core/` and `app/infra/`
can expose shared stores, query helpers, and compatibility functions, but they
must not import `app.domains.*`. If a helper is needed by both infra/core and a
domain, put the helper in `app/infra/` or `app/shared/`, then let the domain
module wrap or re-export it for compatibility.

---

## Naming Conventions

Use lowercase module names that describe the application responsibility:

* `runtime.py` for pre-app runtime preparation.
* `middleware.py` for middleware classes and registration order.
* `routes.py` for static mounts and router/plugin registration.
* `lifespan.py` for FastAPI lifespan startup/shutdown tasks.
* `user_portal.py` for the isolated user portal ASGI wrapper and secondary-port server.
* Domain modules should use names that describe the slice (`router.py`,
  `*_dao.py`, `*_queries.py`, `*_service.py`, `policy.py`) rather than generic
  helpers.

---

## Examples

`app/main.py` should remain a thin example of the desired application entrypoint: `prepare_runtime()`, `create_app()`, exception handler registration, and the `uvicorn.run()` local entrypoint. Domain modules must not import `app.main` just to read shared metadata; import `app.shared.version.APP_VERSION` instead.

`app/bootstrap/routes.py` is the current source of truth for mounted domain
routers. Add new domain routers there rather than recreating a top-level
`app/routers/` module.

`app/bootstrap/services.py` is the current startup orchestrator and should route
startup through `app/bootstrap/service_registry.py`. New bootstrap-started
services should be registered with a stable name, an idempotent start callback,
and, where practical, a matching stop callback so lifespan shutdown can
eventually become complete. Keep direct ad hoc `start_*()` calls out of
`start_bootstrap_services()`; add them to the registry instead.

When adding a stop hook for a bootstrap service, keep it next to the matching
start function and make it reset the module's started state. Thread loops should
use a module-level or instance-level `threading.Event` plus a saved thread
handle; asyncio pollers should cancel the saved task and clear the task/started
flags. Replace long `time.sleep(...)` calls in lifecycle loops with
`Event.wait(...)` so shutdown can interrupt initial delays and refresh waits.
This lets `stop_bootstrap_services()` shut down and then restart services in the
same process during reloads or tests.

Delayed bootstrap preloads still count as lifecycle services. If a preload
thread waits before importing or starting a domain long-running loop, register
the preload in `app/bootstrap/services.py` and make its stop hook set the preload
event, join/clear the preload thread, and call the domain loop's own stop hook.
The domain loop should expose an idempotent `stop_*()` function that sets its
stop event, joins briefly, clears stopped thread handles, and allows later
restart. Do not start delayed daemon threads directly from `prepare_runtime()`.

Bootstrap-started server threads, such as the isolated user portal uvicorn
server, should save both the thread handle and the server handle. Their stop
hook should request shutdown through the server handle, join briefly, and clear
stopped handles without changing routing or socket binding behavior.

Built-in plugins under `app/plugins/` that own background scheduler/check loops
should follow the same lifecycle shape even when they are not started by
bootstrap. Store the worker thread handle on the plugin instance, store an
instance-level `threading.Event` stop signal, skip duplicate `on_enable()` starts
while the thread is alive, and make `on_disable()` set the event, join briefly,
and clear stopped handles so later re-enable works in the same process. Long
initial delays and interval waits inside these loops should use
`self._stop_event.wait(...)` instead of `time.sleep(...)` so plugin disable can
interrupt scheduler sleeps.

Event-driven plugins should make subscriptions reversible too. If `on_enable()`
subscribes a handler through `app.core.event_bus.bus`, guard the subscription with
an instance flag so repeated enables do not register duplicates, and make
`on_disable()` unsubscribe the same handler and clear the flag. Handlers that may
already be queued by the event bus should also check the plugin's enabled state
before starting new asynchronous work.

## Scenario: External Client Adapter Boundary

### 1. Scope / Trigger

- Trigger: any backend code that creates or changes HTTP/WebDAV/third-party transport calls for an external service.
- Applies to domains, plugins, utilities, and infrastructure modules under `app/`.

### 2. Signatures

- External client modules live in `app/infra/clients/<service>_client.py`.
- Each module should expose a focused client class and a singleton instance, for example `WebDavClient` and `webdav_client`.
- Public client methods should preserve call-site behavior by accepting the same material transport inputs: URL/path, headers, auth, params/data/json payloads, proxies, timeout, and redirect behavior when relevant.

### 3. Contracts

- Transport/session/retry/request construction belongs in `app/infra/clients/`.
- Domains and plugins may keep business validation, response message mapping, XML/JSON parsing, file persistence, and domain-specific branching.
- Exception classes from the underlying transport library should not force callers to import that library directly; expose the needed exception type or wrap it at the client boundary.
- Client modules must not depend on routers, concrete domains, or plugin classes.

### 4. Validation & Error Matrix

- Existing timeout or status-code handling at the caller -> preserve the same branches unless the task explicitly changes behavior.
- Existing proxy/auth/header behavior -> pass through unchanged or normalize only where existing code already normalized.
- New direct `requests.*` in a domain/plugin -> move it behind an infra client unless it is a clearly scoped byte-stream helper that the architecture notes allow to remain.
- Caller needs `requests.exceptions.Timeout` or similar -> expose it via the client boundary instead of adding a caller-side `requests` import.

### 5. Good/Base/Bad Cases

- Good: `app/plugins/user_backup/plugin.py` calls `webdav_client.request("PROPFIND", ...)` while keeping WebDAV XML parsing in the plugin.
- Base: `app/domains/system/router.py` keeps user-facing TMDB error messages while calling `tmdb_client.get_configuration(...)`.
- Bad: a plugin imports `requests` only to call `requests.get(...)` against a third-party service.
- Good: `app/utils/ip_location.py` keeps cache and location cleaning locally while delegating all external IP lookup HTTP calls to `ip_location_client`.
- Good: `app/domains/system/system_tools.py` keeps weather cache and fallback ordering locally while delegating QWeather/Amap/wttr transport calls to `weather_client`.
- Good: `app/domains/system/router.py` keeps proxy validation and ping response messages locally while delegating probe requests and exception aliases to `network_client`.

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
