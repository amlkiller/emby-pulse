import json
import os
import sys
from types import SimpleNamespace

import anyio
from starlette.responses import PlainTextResponse

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def _request(path="/api/login"):
    return SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.10"),
        headers={},
        url=SimpleNamespace(path=path),
    )


def test_rate_limit_middleware_returns_json_429_without_calling_downstream(monkeypatch):
    from app.core import rate_limiter as rate_limit_module

    limiter = rate_limit_module.RateLimiter()
    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setitem(rate_limit_module.RATE_LIMITS, "/api/test-limited", {"limit": 1, "window": 60})
    monkeypatch.setattr(rate_limit_module.time, "time", lambda: 1000.0)

    middleware = rate_limit_module.RateLimitMiddleware(app=None)
    request = _request("/api/test-limited")
    downstream_calls = 0

    async def call_next(_request):
        nonlocal downstream_calls
        downstream_calls += 1
        return PlainTextResponse("ok")

    async def run():
        first_response = await middleware.dispatch(request, call_next)
        second_response = await middleware.dispatch(request, call_next)
        return first_response, second_response

    first_response, second_response = anyio.run(run)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "60"
    assert json.loads(second_response.body) == {"detail": "请求过于频繁，请 60 秒后再试"}
    assert downstream_calls == 1
