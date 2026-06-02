# Journal - amlkiller (Part 1)

> AI development session journal
> Started: 2026-05-29

---

2026-05-31: Started backend modular refactor. Split `app/main.py` into `app/bootstrap/*` modules for runtime prep, database init, logging, middleware, route registration, and user portal isolation. Verified with `uv run --with-requirements requirements.txt` syntax/import checks and `pytest` (68 passed). Updated backend directory-structure and error-handling specs to reflect the new bootstrap boundary.



## Session 1: Backend modular refactor

**Date**: 2026-05-31
**Task**: Backend modular refactor
**Branch**: `main`

### Summary

Split app/main.py into app/bootstrap modules, kept behavior stable, and documented the new bootstrap boundary.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4113e66` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

2026-06-01: Continued architecture refactor. Moved `user_backup` plugin DB access behind `app.dao.user_backup_dao`, moved history local IP lookup behind `app.infra.db.local_playback_store`, and moved startup session cleanup into `app.dao.session_dao`. Verified with `uv run --with-requirements requirements.txt` compile/import checks and full pytest (`68 passed, 4 warnings`).

Note for the next conversation: always use `uv run --with-requirements requirements.txt` for Python commands in this repo, and set `PYTHONIOENCODING=utf-8` on Windows when command output may include Chinese text.


## Session 2: Database boundary refactor wrap-up

**Date**: 2026-06-01
**Task**: Database boundary refactor wrap-up
**Branch**: `main`

### Summary

Completed the infra database boundary refactor, removed the legacy query_db facade, moved DB core and manager into infra, verified tests, and recorded the uv run convention in docs.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e632c2b` | (see git log) |
| `0b6fb0a` | (see git log) |
| `f1338d6` | (see git log) |
| `de62860` | (see git log) |
| `112b5c7` | (see git log) |
| `2f5372f` | (see git log) |
| `d3f2756` | (see git log) |
| `cf093c3` | (see git log) |
| `cb9f08b` | (see git log) |
| `6379ed1` | (see git log) |
| `d1315e0` | (see git log) |
| `5a4468d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: Gap schema bootstrap registry

**Date**: 2026-06-02
**Task**: Gap schema bootstrap registry
**Branch**: `main`

### Summary

Routed gap schema bootstrap through schema_registry, added focused regression tests, updated database schema guidance, and verified full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4e4aa55` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Dedupe schema bootstrap registry

**Date**: 2026-06-02
**Task**: Dedupe schema bootstrap registry
**Branch**: `main`

### Summary

Routed dedupe schema bootstrap through schema_registry, preserved legacy whitelist migration, added focused regression tests, updated database schema guidance, and verified full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0a4342f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: Notification schema bootstraps registry

**Date**: 2026-06-02
**Task**: Notification schema bootstraps registry
**Branch**: `main`

### Summary

Routed selected notification and message schema bootstraps through schema_registry, preserved the request admin message index and announcement table exclusion, added focused regression tests, updated database guidance, and verified full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `edfae01` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: User bot schema registry bootstrap

**Date**: 2026-06-02
**Task**: User bot schema registry bootstrap
**Branch**: `main`

### Summary

Routed user-bot registry-owned tables through schema_registry, added tg_user_bindings ALTER coverage, preserved local helper tables, and verified with focused schema tests plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e9ea546` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Auth local users schema registry bootstrap

**Date**: 2026-06-02
**Task**: Auth local users schema registry bootstrap
**Branch**: `main`

### Summary

Routed auth local_users schema bootstrap through schema_registry, added TOTP columns and safe ALTER coverage, guarded unsafe SQLite ALTERs, and verified with focused schema tests plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f094593` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Pro license schema registry bootstrap

**Date**: 2026-06-02
**Task**: Pro license schema registry bootstrap
**Branch**: `main`

### Summary

Routed sys_license bootstrap through schema_registry, added nullable device extension columns and safe ALTER coverage, preserved Pro status behavior, and verified with focused schema tests plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0e9e87e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: Batch Archive Completed PRDs

**Date**: 2026-06-02
**Task**: Batch Archive Completed PRDs
**Branch**: `main`

### Summary

Validated all active PRDs as complete, ran unified checks, and archived 29 completed tasks in one batch commit.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `629911c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: User Meta Schema Registry Bootstrap

**Date**: 2026-06-02
**Task**: User Meta Schema Registry Bootstrap
**Branch**: `main`

### Summary

Routed users_meta bootstrap and remaining non-plugin users_meta column consumers through the schema registry helper, added focused regression coverage, and updated database guidelines.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `68d7494` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: Calendar Notify Schema Registry Bootstrap

**Date**: 2026-06-02
**Task**: Calendar Notify Schema Registry Bootstrap
**Branch**: `main`

### Summary

Registered calendar_notify_config in the schema registry, routed its DAO bootstrap through the shared schema helper, restored database PLAYBACK_TABLES compatibility, and added focused regression coverage.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `163202d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: PWA schema registry bootstrap

**Date**: 2026-06-02
**Task**: PWA schema registry bootstrap
**Branch**: `main`

### Summary

Registered PWA config/icon tables in schema_registry, routed PWA DAO bootstraps through schema_bootstrap, added focused regression coverage, and updated backend database schema-boundary guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d562c0c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 13: Database init schema registry bootstrap

**Date**: 2026-06-02
**Task**: Database init schema registry bootstrap
**Branch**: `main`

### Summary

Routed simple registry-owned startup table creation in app.infra.db.database through schema_bootstrap, preserved local high-risk/unregistered DDL, added focused init-system-db regression coverage, and updated backend database schema-boundary guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e5e03f8` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 14: Point core schema registry bootstrap

**Date**: 2026-06-02
**Task**: Point core schema registry bootstrap
**Branch**: `main`

### Summary

Routed point_logs and point_config bootstraps through schema_bootstrap, preserved unregistered point game table DDL, added focused regression coverage, and updated backend database schema-boundary guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f5c9f32` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: Database init point core schema registry bootstrap

**Date**: 2026-06-02
**Task**: Database init point core schema registry bootstrap
**Branch**: `main`

### Summary

Routed init_db compatibility creation of point_logs and point_config through schema_bootstrap, added focused database-init compatibility coverage, and updated backend schema-boundary guidance while leaving high-risk legacy DDL local.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3b851d6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: Announcement schema registry bootstrap

**Date**: 2026-06-02
**Task**: Announcement schema registry bootstrap
**Branch**: `main`

### Summary

Registered announcements and announcement_reads in schema_registry, routed message_dao announcement bootstrap through schema_bootstrap, extended notification schema regression coverage, and updated backend schema-boundary guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `75ebe38` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: Database init message schema registry bootstrap

**Date**: 2026-06-02
**Task**: Database init message schema registry bootstrap
**Branch**: `main`

### Summary

Routed init_db late message-table compatibility creation for msg_conversations, msg_items, and msg_notify_block through schema_bootstrap, added focused database-init coverage, and updated backend schema-boundary guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `2319458` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 18: Database init compatibility simple schema registry bootstrap

**Date**: 2026-06-02
**Task**: Database init compatibility simple schema registry bootstrap
**Branch**: `main`

### Summary

Routed low-risk init_db compatibility simple tables through schema_bootstrap, preserved ALTER-sensitive local DDL for later slices, expanded database-init regression coverage, and updated backend schema-boundary guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6adfc43` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 19: Database init sys notifications schema registry bootstrap

**Date**: 2026-06-02
**Task**: Database init sys notifications schema registry bootstrap
**Branch**: `main`

### Summary

Routed init_db compatibility sys_notifications creation through schema_bootstrap, preserved registered is_cleared ALTER behavior, added focused database-init coverage, updated backend schema-boundary guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4a62cdd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 20: Plugin DAO schema registry bootstrap batch

**Date**: 2026-06-02
**Task**: Plugin DAO schema registry bootstrap batch
**Branch**: `main`

### Summary

Routed plugin_state, plugin_logs, and keep_alive_violations bootstrap paths through schema_bootstrap; preserved plugin log index and DAO behavior; added focused plugin DAO registry tests; updated backend schema-boundary guidance; verified focused checks and full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1dae17d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 21: Media feedback schema registry bootstrap

**Date**: 2026-06-02
**Task**: Media feedback schema registry bootstrap
**Branch**: `main`

### Summary

Routed media_feedback bootstrap through schema_bootstrap, registered its poster_path ALTER, preserved high-risk media_requests/request_users local migrations, added focused media-feedback registry coverage, updated backend schema-boundary guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `19f437c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 22: Auth and API token schema registry bootstrap

**Date**: 2026-06-02
**Task**: Auth and API token schema registry bootstrap
**Branch**: `main`

### Summary

Registered login_failures and api_tokens in schema_registry, routed database system initialization through schema_bootstrap while preserving lookup indexes, added focused init and DAO smoke coverage, updated backend schema-boundary guidance, and verified the full PRD batch with focused checks, compile, ruff, diff-check, and full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9026279` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 23: Point game schema registry bootstrap

**Date**: 2026-06-02
**Task**: Point game schema registry bootstrap
**Branch**: `main`

### Summary

Registered point game tables in schema_registry, routed database startup and point DAO bootstraps through schema_bootstrap, moved compatible point game ALTERs into TABLE_ALTERS, added focused registry/legacy-upgrade/game-DAO smoke coverage, updated backend database guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `5236379` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 24: Plugin private schema registry bootstrap

**Date**: 2026-06-02
**Task**: Plugin private schema registry bootstrap
**Branch**: `main`

### Summary

Registered plugin-private DAO tables in schema_registry, routed temp-account, season-poster, Emby-restart, and smart-collection bootstraps through schema_bootstrap, moved temp-account compatible ALTERs into TABLE_ALTERS, added focused registry/legacy-upgrade/DAO smoke coverage, updated backend database guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `fce8075` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 25: User bot helper schema registry bootstrap

**Date**: 2026-06-02
**Task**: User bot helper schema registry bootstrap
**Branch**: `main`

### Summary

Registered tg_bot_users and tg_channel_bindings in schema_registry, routed user-bot bootstrap through ensure_registered_table, added helper-table smoke coverage, updated backend database guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ccec28e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 26: User tags schema registry bootstrap

**Date**: 2026-06-02
**Task**: User tags schema registry bootstrap
**Branch**: `main`

### Summary

Registered user_tags in schema_registry, routed system database startup through ensure_registered_table, added user-tag DAO smoke coverage, updated backend database guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d3dca20` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 27: TV series status schema registry bootstrap

**Date**: 2026-06-02
**Task**: TV series status schema registry bootstrap
**Branch**: `main`

### Summary

Registered tv_series_status in schema_registry, routed system database startup through ensure_registered_table, added calendar-status DAO smoke coverage, updated backend database guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `056ab69` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 28: Compat sensitive schema registry bootstrap

**Date**: 2026-06-02
**Task**: Compat sensitive schema registry bootstrap
**Branch**: `main`

### Summary

Routed init_db compatibility creation for invitations, sys_license, and tg_user_bindings through ensure_registered_table, removed duplicate local DDL/ALTER copies, updated focused compatibility tests and backend database guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4b46379` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 29: Media request schema registry batch

**Date**: 2026-06-02
**Task**: Media request schema registry batch
**Branch**: `main`

### Summary

Routed media_requests and request_users bootstrap through schema registry while preserving legacy rebuild migrations; moved database init media request DDL to registry lists; added focused registry/bootstrap regression tests; verified focused tests, compileall, ruff, diff check, and full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `eb84646` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 30: Playback schema registry bootstrap

**Date**: 2026-06-02
**Task**: Playback schema registry bootstrap
**Branch**: `main`

### Summary

Centralized PlaybackActivity startup and local fallback bootstrap through the schema registry helper. Added registered playback compatible columns including ItemType, removed local playback DDL/ALTER copies, updated focused regression tests and database spec guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0096da8` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 31: Audit log schema registry bootstrap

**Date**: 2026-06-02
**Task**: Audit log schema registry bootstrap
**Branch**: `main`

### Summary

Registered audit_logs in the shared schema registry, routed audit logger bootstrap through ensure_registered_table while preserving local indexes, added focused DAO smoke and no-local-DDL regression tests, updated database spec guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8d4c862` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 32: Session schema registry bootstrap

**Date**: 2026-06-02
**Task**: Session schema registry bootstrap
**Branch**: `main`

### Summary

Registered sessions in the shared schema registry, routed session bootstrap through ensure_registered_table while preserving the expiry index, added focused session DAO smoke and no-local-DDL regression tests, updated database spec guidance, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `999a735` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 33: Gap service stop hook

**Date**: 2026-06-02
**Task**: Gap service stop hook
**Branch**: `main`

### Summary

Added a stoppable/restartable lifecycle hook for the bootstrap-started gap background refresh service, replaced long gap service sleeps with interruptible stop-event waits, registered the gaps bootstrap stop callback, added focused stop/restart tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6e19823` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 34: Dashboard cache stop hook

**Date**: 2026-06-02
**Task**: Dashboard cache stop hook
**Branch**: `main`

### Summary

Added a stoppable and restartable lifecycle hook for bootstrap-started dashboard cache tasks, saved and cancelled preload and refresh asyncio task handles, registered the dashboard-cache bootstrap stop callback, added focused cancel/restart and registry tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a588274` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 35: Season poster plugin lifecycle stop

**Date**: 2026-06-02
**Task**: Season poster plugin lifecycle stop
**Branch**: `main`

### Summary

Added reversible event-bus subscriptions for the season poster updater plugin, introduced EventBus.unsubscribe, guarded queued webhook handling when the plugin is disabled, documented event-driven plugin lifecycle expectations, added focused regression tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `898cd55` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 36: Bot admin message plugin lifecycle stop

**Date**: 2026-06-02
**Task**: Bot admin message plugin lifecycle stop
**Branch**: `main`

### Summary

Made Cloud115 and HDHive bot.admin_message subscriptions reversible on plugin disable, preserved duplicate-subscribe guards, fixed the HDHive request-search callback helper surfaced by lint by reusing the existing TMDB-select flow, added focused lifecycle/helper regression tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3b2cad6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 37: Risk monitor event subscription stop

**Date**: 2026-06-02
**Task**: Risk monitor event subscription stop
**Branch**: `main`

### Summary

Made the bootstrap-started risk monitor track and remove EventBus subscriptions on stop, preserved start idempotency and thread lifecycle behavior, added focused start/stop/restart subscription regression coverage, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ff830c1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 38: Notification bot event subscription stop

**Date**: 2026-06-02
**Task**: Notification bot event subscription stop
**Branch**: `main`

### Summary

Moved notification bot service EventBus subscriptions into reversible start/stop lifecycle hooks, replaced anonymous playback lambdas with stable handlers, preserved notification behavior, fixed the ColorTransfer HDR fallback surfaced by lint, added focused lifecycle/HDR tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `17bead7` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 39: Schema index fact-source convergence

**Date**: 2026-06-02
**Task**: Schema index fact-source convergence
**Branch**: `main`

### Summary

Centralized simple schema index DDL in TABLE_INDEXES, taught schema_bootstrap and repair paths to apply registered indexes with legacy-column guards, removed local index SQL from database and DAO bootstrap helpers, updated backend database specs, and verified compile, ruff, focused schema tests, diff check, and full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b76a84f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 40: Notification public service facade

**Date**: 2026-06-02
**Task**: Notification public service facade
**Branch**: `main`

### Summary

Added a narrow public notification service facade, migrated external domain and plugin callers away from direct bot_service.bot imports, preserved notification call arguments and return values, added delegation and boundary tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `dd0748f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 41: Users public service facade

**Date**: 2026-06-02
**Task**: Users public service facade
**Branch**: `main`

### Summary

Added a narrow public users service facade, migrated selected external domains and plugins away from direct users DAO/router cache imports, preserved cache and DAO call behavior, fixed a touched-file undefined user_bot_settings reference, added delegation and boundary tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `61b8813` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 42: Media requests public service facade

**Date**: 2026-06-02
**Task**: Media requests public service facade
**Branch**: `main`

### Summary

Added a narrow public media requests service facade, migrated selected notification bot callers away from direct media request DAO and gap internals, encapsulated gap scan-state mutation, added delegation and boundary tests, and verified focused checks plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e262912` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 43: Plugin scheduler lifecycle stop hooks

**Date**: 2026-06-02
**Task**: Plugin scheduler lifecycle stop hooks
**Branch**: `main`

### Summary

Added plugin shutdown cleanup through the bootstrap service registry, made remaining scheduler loops stop-event driven, and covered lifecycle shutdown/restart behavior with tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `119e58b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 44: System invitation public service facade

**Date**: 2026-06-02
**Task**: System invitation public service facade
**Branch**: `main`

### Summary

Added a system invitation public facade, moved points and notification user-bot invitation callers off the private system DAO, and covered the new boundary with facade and import tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ad827d1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 45: Playback public service facade for keep alive

**Date**: 2026-06-02
**Task**: Playback public service facade for keep alive
**Branch**: `main`

### Summary

Added a playback public facade for user play summaries, moved the keep-alive plugin off private playback stats queries, and covered the boundary with facade/import tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `57e7b80` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
