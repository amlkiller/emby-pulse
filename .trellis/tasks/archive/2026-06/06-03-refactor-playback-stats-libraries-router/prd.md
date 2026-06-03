# Refactor Playback Stats Libraries Router

## Goal

Continue the P2 architecture audit work by extracting one focused endpoint group from `app/domains/playback/stats.py`, reducing the large mixed-responsibility playback stats router without changing behavior.

## Scope

- Extract `GET /api/stats/libraries` into a new playback domain child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position.
- Preserve compatibility exports from `app.domains.playback.stats` for `api_get_libraries`.
- Preserve existing monkeypatch behavior by resolving old `stats` module globals through provider callables at request time, especially:
  - `stats.user_service.is_admin_user`
  - `stats.media_api.get`
  - `stats.get_admin_user_id`
  - `stats.safe_error_message`
- Add or update focused boundary tests for child router inclusion, compatibility export, and route ordering.

## Non-Goals

- Do not change request/response payloads, admin permission checks, media server calls, image tag behavior, or safe error mapping.
- Do not refactor dashboard, recent activity, latest media, live sessions, top movies, chart, poster, badges, dashboard cache tasks, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change database schema or external client transport behavior.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates `/api/stats/libraries` to a new child router module.
- `/api/stats/libraries` remains present under `stats.router`.
- `app.domains.playback.stats.api_get_libraries` remains the same function object as the new child router export.
- Existing tests that monkeypatch `stats` module globals still pass.
- Verification passes:
  - `uv run python -m compileall` for changed Python files.
  - An import/route compatibility check through `uv run python -c ...` with UTF-8 output on Windows if needed.
  - Focused playback stats boundary tests.
  - Full `uv run pytest tests/ -v`.
