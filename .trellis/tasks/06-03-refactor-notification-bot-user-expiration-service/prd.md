# Refactor Notification Bot User Expiration Service

## Goal

Continue the architecture-audit refactor by extracting `SystemDaemon._check_user_expiration()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve the scheduled user-expiration disable behavior and keep the legacy `SystemDaemon._check_user_expiration()` entry point.

## Requirements

* Add a notification-domain module responsible for notification daemon user-expiration checks.
* Move `_check_user_expiration()` implementation into the new module.
* Keep `SystemDaemon._check_user_expiration()` as a compatibility wrapper.
* Preserve lookup through `user_dao.list_users_with_expire_date()`.
* Preserve early return when no users are returned.
* Preserve the current date comparison using `datetime.datetime.now().strftime("%Y-%m-%d")`.
* Preserve row fields `user_id` and `expire_date`.
* Preserve expiration condition `u["expire_date"] < today`.
* Preserve media server lookup through `media_api.get(f"/Users/{user_id}", timeout=5)`.
* Preserve the `status_code == 200` guard before reading the policy.
* Preserve full policy read and mutation: `policy = response.json().get("Policy", {})`, then only set `policy["IsDisabled"] = True` when not already disabled.
* Preserve policy write through `media_api.post(f"/Users/{user_id}/Policy", json=policy, timeout=5)`.
* Preserve swallowed per-user exceptions and swallowed outer exceptions.
* Use lazy providers for legacy globals so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving user-expiration handling into a new domain-local module.
* [ ] `SystemDaemon._check_user_expiration()` delegates to the new service.
* [ ] Empty user lists skip media server side effects.
* [ ] Unexpired users are skipped.
* [ ] Expired users with an enabled policy are disabled while preserving other policy fields.
* [ ] Already disabled users are not posted again.
* [ ] Non-200 media responses are skipped.
* [ ] Per-user and outer exceptions remain swallowed.
* [ ] Focused user-expiration tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added for the extracted user-expiration boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_user_expiration_service.py` with `check_user_expiration()`. Configure providers from `bot_service.py` for user DAO, media API, datetime, and logger if needed. Keep `SystemDaemon._check_user_expiration()` as a thin wrapper so scheduler behavior and legacy monkeypatching still work.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains daemon-scheduled user-expiration business logic mixed into the daemon class.

**Decision**: Extract only the user-expiration check in this slice. Leave scheduler timing and other daemon library workflows for later slices.

**Consequences**: The expiration check becomes independently testable and `bot_service.py` shrinks without changing scheduling or media/user DAO contracts.

## Out of Scope

* Changing expiration date semantics.
* Changing media server policy update behavior.
* Changing scheduler timing.
* Changing user DAO contracts.
* Adding new logs or notifications.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
