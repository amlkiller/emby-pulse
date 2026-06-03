# Refactor Notification Announcements Router

## Goal

Reduce `app/domains/notifications/messages.py` by extracting the announcement management and user announcement routes into a domain-local module while preserving existing route URLs, response shapes, permissions, sanitization, and DAO behavior.

## Requirements

- Add `app/domains/notifications/announcements_router.py` for the announcement Pydantic models and route handlers currently defined in `messages.py`.
- Move these routes without changing their URL paths or HTTP methods:
  - `GET /api/announcements`
  - `POST /api/announcements`
  - `PUT /api/announcements/{ann_id}`
  - `DELETE /api/announcements/{ann_id}`
  - `POST /api/announcements/{ann_id}/view`
  - `GET /api/user/announcements`
  - `POST /api/user/announcements/{ann_id}/read`
- Keep compatibility exports from `app.domains.notifications.messages` for:
  - `AnnouncementModel`
  - `AnnouncementUpdateModel`
  - `get_announcements`
  - `create_announcement`
  - `update_announcement`
  - `delete_announcement`
  - `increment_announcement_view`
  - `user_get_announcements`
  - `mark_announcement_read`
- Include the new announcement router from `messages.py` so bootstrap route mounting remains unchanged.
- Do not change route response dict shapes, session checks, admin permission behavior, HTML sanitization, DAO calls, or announcement table bootstrap behavior.

## Acceptance Criteria

- [ ] `messages.py` no longer contains the announcement route handler bodies.
- [ ] `announcements_router.py` owns announcement models and handlers with the same behavior.
- [ ] `messages.router` still exposes the announcement URLs through `router.include_router(...)`.
- [ ] Existing tests pass, including notification public-auth boundary tests and schema bootstrap tests.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import and route compatibility check through `uv run python -c`.
- Run focused notification messages/schema tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code slice, archive the Trellis task, and record the session journal.

## Technical Approach

Use the same compatibility-preserving child-router pattern used by recent domain splits: create a sibling router module, import its public names back into the original large module, and include the child router from the existing parent router to preserve bootstrap wiring.

## Out of Scope

- Refactoring conversation, mute, bot notification, or broadcast message routes.
- Changing notification DAO schema ownership.
- Changing message bot settings or notification delivery behavior.
- Reworking `app/bootstrap/routes.py`.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- `app/bootstrap/routes.py` mounts `app.domains.notifications.messages.router`, so the child router should be included from `messages.py` rather than mounted separately in bootstrap.
