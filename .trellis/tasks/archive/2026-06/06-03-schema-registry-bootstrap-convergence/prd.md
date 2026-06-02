# Plugin Lifecycle Convergence

## Context

`docs/架构审计.md` lists incomplete lifecycle management as an architecture risk. Most bootstrap-started services now go through `app/bootstrap/service_registry.py`, but weather cache preload still starts as a bare daemon thread from `prepare_runtime()`.

## Scope

- Move weather cache preload startup into the bootstrap service registry.
- Keep existing behavior: preload still runs asynchronously after a short startup delay.
- Add an explicit stop hook so shutdown can interrupt the startup delay and clear thread handles.
- Preserve app creation and route behavior.
- Add focused regression tests for idempotent start/stop and registry wiring.

## Out Of Scope

- Wrapper/pass-through function cleanup handled on other branches.
- Broad plugin scheduler cleanup.
- Schema registry refactors, after current scan showed no low-risk runtime DDL duplication left outside registry-owned paths.

## Verification

- Compile changed Python files with `uv run`.
- Run focused lifecycle tests.
- Run full pytest suite if feasible before commit.
