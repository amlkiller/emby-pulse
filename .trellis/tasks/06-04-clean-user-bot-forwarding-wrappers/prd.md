# Clean user bot forwarding wrappers

## Goal

Clean `app/bot/user_bot/user_bot_service.py` so call sites point at the service function that does the real work when the existing function only redirects to another function.

## Requirements

* Remove only middle-layer wrappers whose body only forwards to another function and adds no validation, branching, orchestration, state access, compatibility contract, or other behavior.
* Update internal call sites and dependency providers to point directly at the real worker function.
* Preserve direct accessors for `cfg`, `os`, environment variables, module variables, or local state.
* Preserve wrappers that encode lifecycle compatibility or additional semantic contracts.
* Keep changes scoped to the user bot service boundary and directly affected tests/callers.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer keeps no-op forwarding wrappers where callers can use the real worker directly.
* [ ] Accessors that read config, OS/env, or module variables remain intact.
* [ ] Relevant tests pass or are updated only when their assertions targeted removed redirect wrappers.

## Definition of Done

* Relevant backend guidelines checked.
* Focused tests run for user bot service boundaries.
* No unrelated refactors or formatting churn.

## Out of Scope

* Moving business logic between service modules.
* Removing public compatibility functions that are imported by other modules.
* Cleaning accessors that directly expose configuration, OS/env, or module variables.

## Technical Notes

* Target file: `app/bot/user_bot/user_bot_service.py`.
* User requested Chinese-specific rule: "真正干活的函数在哪里，调用方就指向哪里；不保留没有额外语义、没有校验、没有编排逻辑的中间包装。只清理函数只转发到另一个函数的重定向包装；但不清理直接读 cfg/os/env/变量 的 accessor。"
