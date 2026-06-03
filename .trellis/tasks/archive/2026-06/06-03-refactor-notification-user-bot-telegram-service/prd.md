# Refactor notification user bot telegram service

## Goal

Split user bot Telegram API and message send/edit/reply helpers out of `app/domains/notifications/user_bot_service.py` into a focused notification domain service while preserving existing behavior and compatibility wrappers.

## Requirements

* Move implementation for `_tg_api`, `_send`, `_edit`, and `_reply` into `app/domains/notifications/user_bot_telegram_service.py`.
* Keep legacy functions in `user_bot_service.py` so existing callers and tests can continue to monkeypatch `_tg_api`, `_send`, `_edit`, `_reply`, `telegram_client`, `get_user_bot_token`, `get_safe_proxies`, and logger dependencies.
* Preserve token fallback behavior, proxy lookup, timeout value, non-200 handling, JSON response behavior, sendMessage payload shape, editMessageText fallback-to-send behavior, and reply routing based on `msg_id`.
* Configure the new service through provider callbacks that read `user_bot_service.py` globals at call time.
* Add focused boundary tests proving old wrappers observe legacy monkeypatches and dependency patches.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns implementation bodies for Telegram API/send/edit/reply helpers.
* [ ] New `user_bot_telegram_service.py` owns implementation and exposes provider configuration.
* [ ] New boundary tests cover token fallback, missing token skip, proxy/client call shape, `_send` payloads, `_edit` fallback behavior, and `_reply` routing through old `user_bot_service.*` globals.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused Telegram helper boundary tests.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Use the provider compatibility pattern from recent notification user bot splits. The new service should default to direct infrastructure dependencies but be configured by `user_bot_service.py` with lambdas that read old module globals at request time.

## Out of Scope

* Rewriting bot polling, command routing, registration, restriction, quota, or binding logic.
* Changing Telegram message text, parse mode, timeout, or proxy behavior.
* Changing admin bot Telegram helpers in `bot_service.py`.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
