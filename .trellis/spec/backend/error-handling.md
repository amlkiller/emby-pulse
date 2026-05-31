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
