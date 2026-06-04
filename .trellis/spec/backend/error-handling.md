# Error Handling

> How errors are handled in this project.

---

## Overview

The backend uses FastAPI/Starlette exceptions for request-level failures and a top-level application exception handler for unexpected errors. The handler returns a generic JSON payload with an opaque `request_id` and keeps stack traces in logs.

Validation and permission failures should continue to use the existing HTTPException-based patterns in routers and shared dependencies.

---

## Error Types

Prefer framework exceptions (`HTTPException`) over custom error classes unless a domain-specific failure needs to travel across layers.

---

## Error Handling Patterns

* Use `HTTPException` for client-facing request failures.
* Catch unexpected errors at the app boundary and log them with context.
* Keep startup failures visible through `print()` or logger output, but do not hide them silently.

---

## API Error Responses

Unexpected server errors return:

```json
{"error":"internal_error","request_id":"..."}
```

---

## Common Mistakes

* Logging sensitive payloads or secrets in exception traces.
* Swallowing startup exceptions without a message.
* Introducing custom error shapes in one router without updating the rest of the API.

---

## Scenario: Expected Middleware Rejections

### 1. Scope / Trigger

- Trigger: backend middleware rejects a request before it reaches a route handler.
- Applies to `BaseHTTPMiddleware.dispatch(...)` implementations such as rate limiting, CSRF, and security gate middleware.

### 2. Signatures

- Middleware rejection: `return JSONResponse(status_code=<4xx>, content={"detail": <message>}, headers=<optional>)`
- Normal route/dependency rejection: `raise HTTPException(status_code=<4xx>, detail=<message>, headers=<optional>)`

### 3. Contracts

- Expected middleware rejections must return a Starlette/FastAPI `Response` object directly.
- Preserve existing API error payload shapes when replacing a middleware-raised `HTTPException`; most client errors should use `{"detail": "..."}`
- Preserve protocol headers such as `Retry-After` for `429` responses.
- Do not call `call_next(request)` after a middleware rejection.

### 4. Validation & Error Matrix

- Rate limit exceeded -> `429` JSON response with `detail` and `Retry-After`.
- CSRF validation failed -> `403` JSON response with `detail`.
- Unexpected middleware failure -> let the app boundary log and return the generic internal-error response.

### 5. Good/Base/Bad Cases

- Good: rate-limit middleware returns `JSONResponse(status_code=429, content={"detail": msg}, headers={"Retry-After": seconds})`.
- Base: route handlers and shared dependencies raise `HTTPException` for normal request-level failures.
- Bad: `BaseHTTPMiddleware.dispatch(...)` raises `HTTPException(429)` for expected control flow.

### 6. Tests Required

- Middleware rejection tests must assert the status code, JSON body, relevant headers, and that downstream handlers are not called.
- Regression tests for `429` middleware behavior should verify the response is returned directly rather than relying on FastAPI exception handling.

### 7. Wrong vs Correct

#### Wrong

```python
if not allowed:
    raise HTTPException(status_code=429, detail=msg, headers={"Retry-After": seconds})
```

#### Correct

```python
if not allowed:
    return JSONResponse(
        status_code=429,
        content={"detail": msg},
        headers={"Retry-After": seconds},
    )
```
