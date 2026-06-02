# Remove Media Request Stop Redirect

## Requirement

Remove the pure redirect function `stop_media_request_services()` because it only calls `stop_community_cache_refresh_loop()` and adds no semantics.

## Scope

- Point bootstrap shutdown registration directly at `stop_community_cache_refresh_loop()`.
- Update tests to monkeypatch and call the real stop implementation.
- Keep `start_media_request_services()` because it initializes schema and starts the refresh loop.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change lifecycle behavior, stop ordering, route behavior, or cache refresh logic.
