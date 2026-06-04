# Fix Rate-Limit 429 Middleware Error Logging

## Goal

Stop expected rate-limit responses from being logged as unhandled ASGI application errors.

## Requirements

* Keep existing rate-limit thresholds and matching behavior unchanged.
* When a request exceeds a configured limit, return a JSON `429` response directly from the middleware.
* Preserve the existing client-facing response shape: `{"detail": "请求过于频繁，请 <n> 秒后再试"}`.
* Preserve the `Retry-After` response header.
* Do not call downstream handlers after a request is rate-limited.

## Acceptance Criteria

* [ ] Hitting a configured rate-limit path returns status `429` without raising `HTTPException` from `BaseHTTPMiddleware`.
* [ ] The JSON response body and `Retry-After` header remain compatible with the previous FastAPI exception response.
* [ ] Focused tests cover the rate-limited middleware path.
* [ ] Relevant Python checks run through `uv run`.

## Definition of Done

* The fix is localized to the rate-limiter middleware.
* Regression tests pass.
* No unrelated rate-limit config or route behavior changes.

## Out of Scope

* Changing rate-limit thresholds.
* Replacing the in-memory limiter.
* Reworking other middleware classes.

## Technical Notes

* Root cause: `app/core/rate_limiter.py` raised `HTTPException(429)` inside `BaseHTTPMiddleware`.
* Starlette/FastAPI exception handling around middleware-raised exceptions can wrap the expected client error into an `ExceptionGroup`, producing noisy `ERROR: Exception in ASGI application` logs.
* Middleware should directly return `JSONResponse(status_code=429, ...)` for this expected control-flow case.
