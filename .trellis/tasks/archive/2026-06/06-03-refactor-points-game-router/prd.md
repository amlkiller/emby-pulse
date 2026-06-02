# Refactor Points Game Router

## Goal

Reduce `app/domains/points/router.py` by extracting the web mini-game HTTP endpoints into a domain-local sub-router while preserving existing routes and behavior.

## Requirements

- Add `app/domains/points/game_router.py` for the slot, scratch-card, wheel, guess-number, and lottery HTTP endpoints currently defined at the end of `points/router.py`.
- Include the new game router from `points/router.py` so all existing URL paths remain registered under the same application router.
- Preserve request/session checks, response dict shapes, point DAO calls, in-memory scratch/guess state behavior, randomization behavior, and error sanitization.
- Do not change non-game points endpoints, notification behavior, point DAO contracts, schema bootstrap behavior, or user-portal path allowlists.
- Keep points route boundary tests meaningful after the split.

## Acceptance Criteria

- [ ] `points/router.py` no longer contains the mini-game endpoint bodies for slot, scratch-card, wheel, guess-number, or lottery.
- [ ] `game_router.py` owns those mini-game routes and imports only the dependencies needed for them.
- [ ] Existing paths such as `/api/slot/spin`, `/api/scratch/buy`, `/api/wheel/spin`, `/api/guess/start`, and `/api/lottery/buy` remain registered when `app.domains.points.router.router` is included.
- [ ] Existing focused points boundary tests pass.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import/route compatibility check through `uv run python -c`.
- Run focused points public facade tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code/test slice, archive the Trellis task, and record the session journal.

## Technical Approach

Move the cohesive mini-game route block into `game_router.py` with its own `APIRouter()`. In `points/router.py`, import that router and call `router.include_router(game_router)` so bootstrap continues to include only `points.router` while the route table stays equivalent.

## Out of Scope

- Changing mini-game rules, costs, limits, randomization, or response payloads.
- Moving mini-game business logic out of route handlers into services in this slice.
- Changing point DAO compatibility exports.
- Refactoring non-game points routes such as config, transfer, red-packet, robbery, or PK endpoints.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- Existing bootstrap includes `app.domains.points.router.router` in `app/bootstrap/routes.py`; this slice should keep that integration point stable.
