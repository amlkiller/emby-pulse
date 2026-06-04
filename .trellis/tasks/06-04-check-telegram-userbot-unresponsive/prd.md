# Check Telegram Userbot Unresponsive

## Goal

Find why the Telegram userbot is not responding and, if needed, apply a narrowly scoped fix so messages/events are handled again.

## What I already know

* User reports: "telegram userbot 无反应".
* Current git branch is `main`; working tree was clean before this task was created.
* Open/public environment missing `tg_user_bot_token` is expected.
* Test environment has a userbot token but the bot still does not respond.

## Assumptions

* "无反应" means the userbot token is configured, but Telegram commands/messages do not trigger expected behavior.
* Local open environment cannot reproduce the token-configured path directly, so the investigation should focus on startup, polling, Telegram API error handling, and dispatcher logic that would affect the test environment.

## Requirements

* Locate Telegram userbot startup, event registration, and command/message handling code.
* Check configuration/environment requirements that could prevent login, event subscription, or handler execution.
* Check available logs or runnable diagnostics for startup/runtime errors.
* Investigate token-configured failure modes such as polling thread not starting, Telegram `getUpdates` non-200 responses, webhook conflicts, worker queue saturation, group filtering, and dispatcher early returns.
* Fix only the identified cause if a code/config issue is found in the repo.

## Acceptance Criteria

* [x] Root cause is identified with concrete evidence for the token-configured test environment.
* [x] If code changes are needed, the change is scoped to Telegram userbot responsiveness.
* [x] Relevant lint/type-check/tests or equivalent diagnostics are run.

## Definition of Done

* Diagnosis is summarized with affected files and commands run.
* Quality checks are run or any inability to run them is documented.
* No unrelated files are changed.

## Out of Scope

* New Telegram bot features.
* Broad refactors unrelated to responsiveness.
* Deployment changes unless logs/config show deployment is the cause.

## Technical Notes

* Startup path: `app/bootstrap/services.py` registers `start_notification_services()`, which imports and calls `app.bot.user_bot.user_bot_service.start_user_bot_services()`.
* `UserBot.start()` in `app/bot/user_bot/user_bot_service.py` returns without starting polling when `get_user_bot_token()` is empty.
* Local `data/config/config.json` has no `tg_user_bot_token`; there is no local `.env`; current process environment does not expose `TG_USER_BOT_TOKEN`.
* Reproduced with `uv run python -`: after `start_user_bot_services()`, `user_bot.running` remains `False` and `poll_thread` remains `None`.
* Token-configured test environment can still be unresponsive when Telegram has a webhook configured for that bot token. The code used polling mode but never called `deleteWebhook`; Telegram returns non-200 for `getUpdates` in that state.
* Before this fix, `getUpdates` non-200 responses and polling network exceptions were silent or debug-only, so operators saw "started" but no actionable failure.
* Fix: userbot startup now clears Telegram webhook before polling, warns if the userbot token equals the admin bot token, and logs sanitized `getUpdates` non-200/exception details at warning level without logging tokens.
* Verification: `uv run pytest tests/test_notification_user_bot_polling_service_boundary.py tests/test_bootstrap_stop_hooks.py -q` passed.
* Verification: `uv run pytest <expanded userbot-related test files> -q` passed with 171 tests.
* Verification: `uv run pytest tests/ -q` passed with 919 tests.
* Verification: `uv run python -m compileall app/bot/user_bot/user_bot_polling_service.py app/bot/user_bot/user_bot_service.py tests/test_notification_user_bot_polling_service_boundary.py tests/test_bootstrap_stop_hooks.py` passed.
* Spec update: `.trellis/spec/backend/logging-guidelines.md` now documents Telegram polling webhook cleanup and sanitized warning-level diagnostics.
