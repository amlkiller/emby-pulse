# Logging Guidelines

> How logging is done in this project.

---

## Overview

The backend uses Python's standard `logging` module. Most runtime modules log
through the `uvicorn` logger so messages land in the same application log
stream:

```python
import logging

logger = logging.getLogger("uvicorn")
```

`app/main.py` also uses a dedicated `app.unhandled` logger for the global
unexpected-exception handler. That handler returns a generic JSON error to the
client and writes the stack trace with an opaque `request_id`.

Startup/bootstrap code may still use `print(...)` for visible container startup
messages, especially security, database, and service lifecycle status. Do not
silently swallow startup failures; log or print enough context for operators to
understand what degraded.

---

## Log Levels

- `debug`: best-effort cleanup failures, cache cleanup, optional diagnostics,
  ignored audit/log side effects, and expected noisy fallback paths.
- `info`: successful lifecycle events, audit events, plugin/service startup,
  scheduled work completion, and meaningful operator-visible state changes.
- `warning`: unsafe or degraded configuration that the app can recover from,
  slow queries, invalid proxy settings, suspicious security settings, and
  fallback behavior operators should fix.
- `error`: failed persistence, failed external actions, unexpected exceptions in
  services/plugins, and request handling failures that need investigation.

Examples from current code:

```python
# app/infra/db/query_perf.py
logger.warning(f"[慢查询] {elapsed_ms:.1f}ms rows={row_count} sql={normalized[:180]}")

# app/utils/proxy_helper.py
logger.warning(
    "[ProxyHelper] 配置中的 proxy_url 未通过安全校验，已自动降级为不使用代理: %s",
    result.get("error", "unknown"),
)

# app/core/audit_logger.py
logger.info(log_msg)
```

---

## Sensitive Data Filtering

`app.bootstrap.logging.configure_sensitive_log_filter()` attaches
`SensitiveLogFilter` to root, `uvicorn`, `uvicorn.access`, and `uvicorn.error`
handlers. The filter masks common token/API-key patterns and sensitive argument
keys such as `token`, `api_key`, `password`, `tg_bot_token`,
`emby_api_key`, and `moviepilot_token`.

This filter is a defense-in-depth layer, not permission to log secrets. New code
should still avoid placing raw tokens, passwords, API keys, cookies, full auth
headers, or sensitive request bodies in log messages.

---

## Error Logging

Client-facing errors should use the existing FastAPI/HTTPException patterns.
Unexpected server errors are handled at the app boundary:

```python
# app/main.py
request_id = uuid.uuid4().hex[:12]
logging.getLogger("app.unhandled").error(
    f"[未捕获异常] request_id={request_id} path={request.url.path} "
    f"method={request.method}\n{traceback.format_exc()}"
)
return JSONResponse(
    status_code=500,
    content={"error": "internal_error", "request_id": request_id},
)
```

When a router/service catches an internal exception but must return a generic
message, use the shared safe-error helpers or preserve the existing generic
message pattern. Do not return raw exception strings to clients unless the route
already owns that behavior and the data is known to be non-sensitive.

---

## Scenario: Telegram Polling Bot Diagnostics

### 1. Scope / Trigger

- Trigger: a Telegram bot service receives updates through Bot API polling (`getUpdates`) instead of Telegram webhooks.
- Applies to notification/user bot polling loops and startup code that prepares a bot token for polling.

### 2. Signatures

- Startup preparation: `deleteWebhook` through the shared Telegram client/service before starting `getUpdates`.
- Polling request: `getUpdates(token, params={"offset": <int>, "timeout": 30}, timeout=35, proxies=<safe proxies>)`.
- Logging calls must use `logging.getLogger("uvicorn")` or the module's injected logger provider.

### 3. Contracts

- Polling-mode bots must clear Telegram webhook state during startup because Telegram rejects `getUpdates` while a webhook is active.
- Logs may include the Telegram API method name, HTTP status code, `error_code`, and `description`.
- Logs must not include raw bot tokens, proxy URLs, request URLs containing tokens, or full third-party response bodies.
- If two local polling services can consume the same bot token, startup code should warn operators because the services can race and consume each other's updates.

### 4. Validation & Error Matrix

- `deleteWebhook` returns missing/false/exception -> warning: polling may not receive updates; mention token/proxy/API connectivity without printing secrets.
- `getUpdates` returns non-200 -> warning with sanitized status and Telegram error detail; retry remains allowed.
- Polling request raises a network exception -> warning with the exception summary; retry remains allowed.
- Same repeated polling failure -> avoid log spam by logging only when the warning signature changes or by otherwise rate-limiting.

### 5. Good/Base/Bad Cases

- Good: `"[UserBot] getUpdates 返回异常: status=409 error_code=409 description=Conflict: webhook active"`
- Base: `"[UserBot] polling 请求异常: network down"`
- Bad: silently sleeping after a non-200 `getUpdates` response.
- Bad: logging `https://api.telegram.org/bot<token>/getUpdates` or raw config containing token/proxy values.

### 6. Tests Required

- Regression tests must cover non-200 `getUpdates` responses and assert a warning is emitted with status/error detail.
- Regression tests must cover polling exceptions and assert they are warning-level and retry waits still happen.
- Startup tests that stub command registration should also stub webhook cleanup so they do not perform real Telegram API calls.

### 7. Wrong vs Correct

#### Wrong

```python
if res.status_code != 200:
    stop_event.wait(3)
```

#### Correct

```python
if res.status_code != 200:
    logger.warning("[UserBot] getUpdates 返回异常: status=%s", res.status_code)
    stop_event.wait(3)
```

---

## Audit Logging

Security and administrative events should use `app.core.audit_logger.log_audit`
when the action is part of the audit trail. Audit writes are best-effort: log the
failure, but do not break the main business flow unless the caller already
requires audit persistence.

Use normal application logging for operational details and audit logging for
security/accountability events such as login, config changes, user management,
backup/restore, invitation, points, and sensitive media actions.

---

## What to Log

- Startup status for database, security checks, middleware, plugins, background
  services, and user portal services.
- External dependency failures with service name, operation, status code when
  safe, and sanitized context.
- Background task failures and degraded fallback behavior.
- Database migration, repair, backup, restore, health, and slow-query events.
- Security-relevant configuration issues, including unsafe proxy values and weak
  or auto-generated tokens.

---

## What NOT to Log

- Raw Telegram, WeCom, Emby, TMDB, MoviePilot, weather, or webhook tokens.
- Passwords, cookies, session IDs, full authorization headers, TOTP secrets, or
  QR payloads.
- Full request/response bodies from third-party services when they may contain
  secrets or user data.
- User-supplied rich HTML or long free-form text unless sanitized or truncated.
- Sensitive configuration dictionaries without masking.

---

## Common Mistakes

- Logging an exception with `str(e)` and returning the same string to the user.
  Keep internal detail in logs and return a generic message when the route is
  security-sensitive.
- Adding `print(...)` inside request handlers for normal runtime behavior. Use a
  module logger instead.
- Logging proxy URLs, webhook URLs, tokens, or API keys while debugging
  connectivity. Log the validation result and service name instead.
- Catching startup exceptions without any visible log/print message.
