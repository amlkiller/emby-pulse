# Database Guidelines

> Database patterns and conventions for this project.

---

## Scenario: First-Stage Database Boundary

### 1. Scope / Trigger

- Trigger: database infrastructure refactor that starts removing `query_db()` from representative modules.
- Applies to new backend code that reads/writes EmbyPulse system data or playback reporting data.
- First-stage sample modules include `app/routers/history.py`, `app/routers/api_tokens.py`, `app/routers/notifications.py`, `app/routers/notify_rules.py`, `app/routers/pro.py`, `app/routers/notify_admin.py`, `app/routers/pwa.py`, `app/routers/audit.py`, `app/routers/risk.py`, `app/routers/clients.py`, `app/routers/calendar_notify.py`, `app/routers/webhook.py`, `app/services/report_service.py`, `app/routers/insight.py`, `app/routers/system_tools.py`, `app/services/risk_service.py`, `app/services/calendar_service.py`, `app/routers/views.py`, `app/routers/tasks.py`, `app/routers/dedupe.py`, `app/routers/system.py`, `app/routers/db_tools.py`, `app/routers/gaps.py`, `app/routers/bot.py`, `app/routers/stats.py`, `app/routers/auth.py`, `app/routers/messages.py`, `app/routers/media_request.py`, and the low-risk config/account/log slice of `app/routers/points.py`.

### 2. Signatures

- `app.infra.db.system_store.system_store.fetch_all(sql: str, params=()) -> list[DataRow]`
- `app.infra.db.system_store.system_store.fetch_one(sql: str, params=()) -> DataRow | None`
- `app.infra.db.system_store.system_store.execute(sql: str, params=()) -> int`
- `app.infra.db.playback_store.playback_store.query(sql: str, params=(), one: bool = False) -> list[DataRow] | DataRow | None`
- `app.infra.db.playback_store.get_playback_column_name() -> str`
- `app.dao.notify_rule_dao.list_bot_notify_mutes() -> list[DataRow]`
- `app.dao.notify_rule_dao.replace_bot_notify_mutes(playback_users, login_users) -> None`
- `app.dao.pro_license_dao.replace_license(license_key: str, machine_id: str, status: str = "pro") -> None`
- `app.dao.pro_license_dao.get_license_status() -> DataRow | None`
- `app.dao.notify_admin_dao.save_notify_rules(rules: dict) -> None`
- `app.dao.pwa_dao.get_pwa_config_values() -> dict`
- `app.dao.pwa_dao.save_pwa_config_value(key: str, value: str) -> None`
- `app.dao.audit_dao.list_user_audit_logs_since(start_datetime: str, limit: int) -> list[DataRow]`
- `app.dao.audit_dao.create_user_audit_log(...) -> None`
- `app.dao.risk_dao.list_risk_logs(limit: int = 200) -> list[DataRow]`
- `app.dao.risk_dao.count_recent_risk_actions() -> list[DataRow]`
- `app.dao.risk_dao.set_user_admin_disabled(user_id: str, disabled: bool, created_at: str = "") -> None`
- `app.dao.risk_dao.create_risk_log(user_id: str, username: str, action: str, reason: str) -> None`
- `app.dao.risk_dao.get_user_concurrent_policy(user_id: str) -> DataRow | None`
- `app.dao.risk_dao.get_tg_user_id_for_emby_user(user_id: str) -> str | None`
- `app.dao.client_dao.list_client_blacklist() -> list[DataRow]`
- `app.dao.client_dao.list_client_blacklist_names() -> list[DataRow]`
- `app.dao.client_dao.add_client_blacklist(app_name: str) -> None`
- `app.dao.client_dao.delete_client_blacklist(app_name: str) -> None`
- `app.dao.client_dao.list_client_whitelist() -> list[DataRow]`
- `app.dao.client_dao.list_client_whitelist_user_ids() -> list[DataRow]`
- `app.dao.client_dao.add_client_whitelist(user_id: str, user_name: str) -> None`
- `app.dao.client_dao.delete_client_whitelist(user_id: str) -> None`
- `app.dao.calendar_notify_dao.ensure_calendar_notify_config_table() -> None`
- `app.dao.calendar_notify_dao.get_calendar_notify_config() -> DataRow | None`
- `app.dao.calendar_notify_dao.save_calendar_notify_config(enabled, notify_time, channels, tg_chat_id, wecom_touser) -> None`
- `app.dao.calendar_notify_dao.mark_calendar_notify_sent() -> None`
- `app.dao.webhook_playback_dao.save_webhook_playback_ip_data(data, user_id, user_name, item, ip) -> None`
- `app.dao.insight_dao.save_insight_ignore(item_id: str, item_name: str) -> None`
- `app.dao.insight_dao.save_insight_ignores(items) -> None`
- `app.dao.insight_dao.delete_insight_ignores(item_ids) -> None`
- `app.dao.insight_dao.list_insight_ignores() -> list[DataRow]`
- `app.dao.insight_dao.list_insight_ignore_item_ids() -> list[DataRow]`
- `app.dao.system_tool_dao.check_system_table_integrity() -> dict`
- `app.dao.system_tool_dao.check_system_db_readwrite() -> dict`
- `app.dao.system_tool_dao.system_database_exists() -> bool`
- `app.dao.system_tool_dao.repair_core_system_tables() -> list[str]`
- `app.dao.system_tool_dao.get_dashboard_layout() -> Any | None`
- `app.dao.system_tool_dao.save_dashboard_layout(data) -> None`
- `app.dao.calendar_dao.mark_calendar_episode_ready(series_id, season, episode) -> None`
- `app.dao.calendar_dao.list_calendar_cache_rows(start_date: str, end_date: str) -> list[DataRow]`
- `app.dao.calendar_dao.replace_calendar_cache_items(week_data) -> None`
- `app.dao.calendar_dao.list_cached_calendar_series_ids() -> list[str]`
- `app.dao.calendar_dao.delete_calendar_cache_for_series(series_ids) -> int`
- `app.dao.calendar_dao.list_ended_series_tmdb_ids() -> set`
- `app.dao.calendar_dao.save_series_status(tmdb_id, series_name, status, checked_at: str) -> None`
- `app.dao.invitation_dao.get_invitation_by_code(code: str) -> DataRow | None`
- `app.dao.invitation_dao.restore_invitation_code_usage(code: str) -> None`
- `app.dao.invitation_dao.claim_registration_invitation(code: str, used_by: str) -> tuple[DataRow | None, str | None]`
- `app.dao.invitation_dao.save_registered_user_meta(...) -> None`
- `app.dao.task_dao.ensure_task_config_defaults() -> None`
- `app.dao.task_dao.is_task_notify_enabled() -> bool`
- `app.dao.task_dao.set_task_notify_enabled(enabled: bool) -> None`
- `app.dao.task_dao.list_task_translations() -> list[DataRow]`
- `app.dao.task_dao.save_task_translation(original_name: str, translated_name: str) -> None`
- `app.dao.task_dao.delete_task_translation(original_name: str) -> None`
- `app.dao.dedupe_dao.init_dedupe_tables(logger=None) -> None`
- `app.dao.dedupe_dao.list_dedupe_whitelist_group_keys() -> list[str]`
- `app.dao.dedupe_dao.DedupeResultWriter`
- `app.dao.dedupe_dao.list_dedupe_results() -> list[DataRow]`
- `app.dao.dedupe_dao.add_dedupe_whitelist_items(items) -> None`
- `app.dao.dedupe_dao.list_dedupe_whitelist() -> list[DataRow]`
- `app.dao.dedupe_dao.remove_dedupe_whitelist_items(group_keys) -> None`
- `app.dao.dedupe_dao.delete_dedupe_result_by_item_id(item_id: str) -> None`
- `app.dao.dedupe_dao.get_dedupe_config_values() -> dict`
- `app.dao.dedupe_dao.save_dedupe_config_values(config: dict) -> None`
- `app.dao.gap_dao.ensure_gap_tables(logger=None) -> None`
- `app.dao.gap_dao.add_gap_perfect_series(series_id, tmdb_id, series_name) -> None`
- `app.dao.gap_dao.get_gap_cache_interval_hours(default: int = 6) -> int`
- `app.dao.gap_dao.list_gap_records_for_lock() -> list[DataRow]`
- `app.dao.gap_dao.list_gap_perfect_series_ids() -> list[str]`
- `app.dao.gap_dao.get_gap_config_value(key: str) -> str | None`
- `app.dao.gap_dao.save_gap_scan_cache(results) -> None`
- `app.dao.gap_dao.load_gap_scan_cache() -> Any | None`
- `app.dao.gap_dao.list_ignored_series_ids() -> list[str]`
- `app.dao.gap_dao.save_gap_record_status(series_id, series_name, season, episode, status: int) -> None`
- `app.dao.gap_dao.list_gap_ignore_records() -> list[DataRow]`
- `app.dao.gap_dao.list_gap_perfect_records() -> list[DataRow]`
- `app.dao.gap_dao.get_gap_config_map() -> dict`
- `app.dao.bot_admin_dao.list_user_blacklist() -> list[DataRow]`
- `app.dao.bot_admin_dao.remove_user_blacklist(tg_user_id: str) -> None`
- `app.dao.bot_admin_dao.list_registration_logs(days: int = 7) -> list[DataRow]`
- `app.dao.bot_admin_dao.get_registration_stats() -> dict`
- `app.dao.bot_admin_dao.clear_registration_logs() -> None`
- `app.dao.bot_admin_dao.count_registration_logs() -> int`
- `app.dao.bot_admin_dao.list_tg_bindings_for_sync() -> list[DataRow]`
- `app.dao.bot_admin_dao.update_tg_binding_names(tg_user_id, username, display_name) -> None`
- `app.dao.bot_admin_dao.list_tg_bindings() -> list[DataRow]`
- `app.dao.bot_admin_dao.get_lottery_draw_result(draw_date: str) -> DataRow | None`
- `app.dao.bot_admin_dao.reset_lottery_draw(today: str, tomorrow: str) -> dict`
- `app.dao.bot_admin_dao.fix_lottery_pool(today: str, tomorrow: str) -> dict`
- `app.dao.bot_admin_dao.clear_active_scratch_card() -> dict`
- `app.dao.bot_admin_dao.get_lottery_pool_info(today: str, tomorrow: str) -> dict`
- `app.dao.bot_admin_dao.adjust_lottery_pool(today: str, tomorrow: str, init_pool: int) -> dict`
- `app.dao.auth_dao.ensure_local_users_table() -> None`
- `app.dao.auth_dao.get_login_failure(lock_key: str) -> DataRow | None`
- `app.dao.auth_dao.upsert_login_failure(lock_key: str, lock_type: str, failure_count: int, locked_until) -> None`
- `app.dao.auth_dao.count_enabled_local_users(role: str | None = None) -> int`
- `app.dao.auth_dao.list_local_users() -> list[DataRow]`
- `app.dao.auth_dao.create_local_user(username, password_hash, role, remark, permissions_json) -> None`
- `app.dao.auth_dao.update_local_user_fields(user_id: int, updates: dict, updated_at: str) -> None`
- `app.dao.auth_dao.get_local_user_for_login(username: str) -> DataRow | None`
- `app.dao.auth_dao.update_local_user_login(user_id: int, last_login_at: str, last_login_ip: str) -> None`
- `app.dao.auth_dao.enable_local_user_totp(user_id: int, secret: str) -> None`
- `app.dao.auth_dao.disable_local_user_totp(user_id: int) -> None`
- `app.dao.message_dao.ensure_msg_tables() -> None`
- `app.dao.message_dao.list_conversations(limit: int, offset: int) -> list[DataRow]`
- `app.dao.message_dao.get_or_create_conversation(user_id: str, username: str, user_avatar=None) -> tuple[int, dict]`
- `app.dao.message_dao.insert_admin_message(conversation_id: int, sender_id: str, sender_name: str, content: str, last_message: str) -> None`
- `app.dao.message_dao.insert_user_message(user_id: str, username: str, user_avatar, content: str, last_message: str, notification_message: str) -> int`
- `app.dao.message_dao.ensure_mute_table() -> None`
- `app.dao.message_dao.upsert_user_mute(user_id: str, username: str, muted_until, reason: str, admin_id: str, admin_name: str) -> None`
- `app.dao.message_dao.ensure_announcement_tables() -> None`
- `app.dao.message_dao.list_announcements(active_only: bool = False) -> list[DataRow]`
- `app.dao.message_dao.update_announcement_fields(announcement_id: int, updates: dict) -> None`
- `app.dao.message_dao.send_broadcast_messages(user_entries, admin_id: str, admin_name: str, content: str) -> tuple[int, list]`
- `app.dao.media_request_dao.ensure_media_request_schema() -> None`
- `app.dao.media_request_dao.submit_new_media_request(...) -> dict`
- `app.dao.media_request_dao.list_my_requests(user_id: str) -> list[DataRow]`
- `app.dao.media_request_dao.list_all_requests() -> list[DataRow]`
- `app.dao.media_request_dao.update_media_request_status(tmdb_id, season, status, reject_reason=None) -> None`
- `app.dao.media_request_dao.get_pending_notify_data() -> tuple[int, list[DataRow], int, list[DataRow]]`
- `app.dao.media_request_dao.submit_update_request_record(...) -> dict`
- `app.dao.media_request_dao.submit_batch_update_request_records(...) -> dict`
- `app.dao.media_request_dao.claim_registration_invitation(code: str, used_by: str) -> tuple[DataRow | None, str | None]`
- `app.dao.media_request_dao.save_registered_user_meta(...) -> None`
- `app.dao.point_dao.get_point_config() -> dict`
- `app.dao.point_dao.ensure_lottery_table() -> None`
- `app.dao.point_dao.ensure_points_schema() -> None`
- `app.dao.point_dao.save_point_config_values(configs: dict) -> None`
- `app.dao.point_dao.list_user_points() -> list[DataRow]`
- `app.dao.point_dao.batch_update_user_points(user_ids, amount: int, reason: str, name_map: dict) -> int`
- `app.dao.point_dao.list_point_logs(user_id: str = None, page: int = 1, page_size: int = 50, action_type: str = None) -> dict`
- `app.dao.point_dao.get_user_points_info(user_id: str) -> dict`
- `app.dao.point_dao.list_user_point_logs(user_id: str, page: int = 1, page_size: int = 20) -> dict`
- `app.dao.point_dao.list_red_packet_logs(packet_id: int) -> list[dict]`
- `app.dao.point_dao.list_point_rank(limit: int = 10) -> list[DataRow]`
- `app.dao.point_dao.perform_user_checkin(user_id: str, username: str) -> dict`
- `app.infra.db.local_playback_store.insert_webhook_playback_ip_record(...) -> None`
- `app.infra.db.perf_stats.get_query_perf_stats() -> dict`
- `app.queries.client_queries.count_playback_clients_by_app() -> list[DataRow]`
- `app.queries.client_queries.count_playback_devices(limit: int = 10) -> list[DataRow]`
- `app.queries.report_queries.build_report_base_filter(user_id_filter) -> tuple[str, list]`
- `app.queries.report_queries.count_report_plays(where_sql: str, params) -> int`
- `app.queries.report_queries.sum_report_duration(where_sql: str, params) -> int`
- `app.queries.report_queries.list_report_top_items(where_sql: str, params, limit: int = 8) -> list[DataRow]`
- `app.queries.report_queries.list_report_ranked_items(where_sql: str, exclude_sql: str, exclude_types, limit: int) -> list[DataRow]`
- `app.queries.stats_queries.build_stats_base_filter(user_id_filter) -> tuple[str, list]`
- `app.queries.stats_queries.query_stats(sql: str, params=(), one: bool = False) -> list[DataRow] | DataRow | None`
- `app.queries.system_tool_queries.get_latest_playback_date() -> str | None`
- `app.queries.system_tool_queries.diagnose_playback_database() -> dict`
- `app.infra.db.migration_service.full_health_check() -> dict`
- `app.infra.db.migration_service.ensure_tables() -> dict`
- `app.infra.db.migration_service.check_system_tables() -> dict`
- `app.infra.db.migration_service.check_old_db_tables() -> dict`
- `app.infra.db.migration_service.migrate_tables(mode="incremental", tables=None) -> dict`
- `app.infra.db.migration_service.backup_system_database() -> dict | None`
- `app.infra.db.migration_service.backup_existing_databases() -> dict`
- `app.infra.db.migration_service.deep_check_system_database() -> dict`
- Scenario modules live in `app/queries/*_queries.py` and `app/dao/*_dao.py` during the transition.

### 3. Contracts

- System database access must go through `system_store` or a DAO that wraps it.
- Playback reporting access must go through `playback_store` or a query service that wraps it.
- `playback_store` owns the SQLite/API data-source switch for `PlaybackActivity`.
- Local webhook fallback writes to `PlaybackActivity` must be isolated behind `app.infra.db.local_playback_store`, not route-local SQLite.
- Route modules should call scenario functions such as `history_queries` or `api_token_dao`, not open SQLite connections directly.
- Return rows use `DataRow`, which supports dict-style access, `.get()`, integer index access, and case-insensitive keys for compatibility with legacy callers.

### 4. Validation & Error Matrix

- Missing playback database file -> `playback_store.query(...)` returns `None` and logs the same user-facing warning style as the legacy path.
- Emby API passthrough failure -> `playback_store.query(...)` falls back to SQLite when possible.
- System database write failure -> DAO exception bubbles to the router, where existing `HTTPException(... safe_error_message(...))` handling is preserved.
- Empty SELECT result -> `fetch_all` returns `[]`; `fetch_one` returns `None`.

### 5. Good/Base/Bad Cases

- Good: `api_tokens.py` calls `api_token_dao.create_api_token_record(...)` and keeps HTTP response shape unchanged.
- Base: `history.py` calls `history_queries.count_history(...)` and still returns the same pagination payload.
- Good: `notifications.py` calls `notification_dao.list_notifications(...)` and preserves the `{"success", "unread_count", "items"}` response shape.
- Good: `notify_rules.py` calls `notify_rule_dao.replace_bot_notify_mutes(...)` and preserves the `{"playback": [], "login": []}` payload shape.
- Good: `pro.py` calls `pro_license_dao.replace_license(...)` and keeps system notification write failures non-blocking for activation.
- Good: `pwa.py` keeps its legacy `True`/`False` helper return behavior while delegating table creation and writes to `pwa_dao`.
- Good: `audit.py` keeps audit log merge/normalization in the route and delegates only `user_audit_logs` SQL to `audit_dao`.
- Good: `risk.py` keeps Emby API control and config updates in the route/service layer while delegating `risk_logs` and `users_meta` summary reads to `risk_dao`.
- Good: `clients.py` keeps media server device control and response assembly in the route while delegating blacklist/whitelist tables to `client_dao` and playback aggregates to `client_queries`.
- Good: `calendar_notify.py` keeps notification sending, scheduling, and channel-specific HTTP calls in the route/service layer while delegating `calendar_notify_config` reads/writes to `calendar_notify_dao`.
- Good: `webhook.py` keeps token validation, event parsing, and event-bus publishing in the route while delegating client-list reads to `client_dao` and local playback IP persistence to `webhook_playback_dao`.
- Good: `report_service.py` keeps poster rendering and media image fetching in the service while delegating playback aggregate SQL to `report_queries`.
- Good: `insight.py` keeps Emby library scanning and cache filtering in the route while delegating ignore-list persistence to `insight_dao`.
- Good: `system_tools.py` keeps weather/log/restart HTTP behavior in the route while delegating database health checks and playback recency SQL to DAO/query modules.
- Good: `risk_service.py` keeps Emby session control, event handling, and user messaging orchestration in the service while delegating `risk_logs`, `users_meta`, and `tg_user_bindings` access to DAOs.
- Good: `calendar_service.py` keeps Emby/TMDB API coordination and calendar aggregation in the service while delegating `tv_calendar_cache` and `tv_series_status` persistence to `calendar_dao`.
- Good: `views.py` keeps validation, Emby user creation, and template rendering in the route while delegating invitation transactions and `users_meta` writes to `invitation_dao`.
- Good: `tasks.py` keeps Emby scheduled-task polling and display-name assembly in the route while delegating task config and translation persistence to `task_dao`.
- Good: `dedupe.py` keeps Emby scan/delete orchestration and duplicate scoring in the route while delegating dedupe result, whitelist, and config persistence to `dedupe_dao`.
- Good: `system.py` keeps settings validation, external connectivity probes, and response assembly in the route while delegating database diagnostics, repair DDL, and dashboard layout persistence to DAO/query modules.
- Good: `db_tools.py` keeps admin permission checks, audit logging, and restore path validation in the route while delegating database health, migration, backup, restore, and deep-check operations to `migration_service`.
- Good: `gaps.py` keeps Emby/TMDB scanning, download handoff, and in-memory scan-state updates in the route while delegating gap tables, config, and scan cache persistence to `gap_dao`.
- Good: `bot.py` keeps bot settings validation, Telegram/WeCom HTTP calls, and admin response assembly in the route while delegating user-bot admin tables, registration logs, TG bindings, lottery, and scratch-card persistence to `bot_admin_dao`.
- Good: `stats.py` keeps chart aggregation, media-server enrichment, and permission filtering in the route while delegating playback SQL execution and base user filters to `stats_queries`.
- Good: `auth.py` keeps password hashing, local/Emby login decisions, TOTP validation, session updates, and audit logging in the route while delegating login failure and `local_users` persistence to `auth_dao`.
- Good: `messages.py` keeps permission checks, Emby user lookups, content sanitization, bot notification delivery, and response assembly in the route while delegating message, mute, notification-block, announcement, and related user lookup tables to `message_dao`.
- Good: `media_request.py` keeps request validation, Emby/TMDB/MoviePilot calls, cache assembly, notification delivery, and response shaping in the route while delegating request, feedback, update, invitation, point, gap-cache, and user metadata persistence to `media_request_dao`.
- Good: `points.py` keeps admin/session checks, Emby user enrichment, pagination payload assembly, and later game workflows in the route while delegating point config, point schema bootstrap, point balances, batch updates, point log reads, red-packet log reads, point ranking reads, and daily check-in transactions to `point_dao`.
- Bad: a router imports `query_db`, `SYSTEM_DB_PATH`, or `sqlite3` only to run route-local SQL.

### 6. Tests Required

- Compile/import check for new infra, query, DAO, and migrated router modules.
- Full existing pytest suite after representative migration.
- When adding a new migrated module, assert route response fields stay compatible with the pre-migration shape.

### 7. Wrong vs Correct

#### Wrong

```python
from app.core.database import query_db

rows = query_db("SELECT * FROM PlaybackActivity LIMIT 20")
```

#### Correct

```python
from app.queries.history_queries import fetch_history_rows

rows = fetch_history_rows(select_fields, where_sql, params, limit, offset)
```

#### Wrong

```python
import sqlite3
from app.core.database import SYSTEM_DB_PATH

conn = sqlite3.connect(SYSTEM_DB_PATH)
```

#### Correct

```python
from app.dao.api_token_dao import list_api_tokens

tokens = list_api_tokens(user_id)
```

---

## Migrations

- `app.infra.db.schema_registry` is the new import point for schema metadata during migration.
- Existing schema definitions still delegate to `app.core.db_schemas` until ownership is fully moved.
- `app.infra.db.migration_service` is the new boundary for migration, health, backup, restore, and database-tool deep-check orchestration and currently delegates to existing implementations.

---

## Common Mistakes

- Do not add new `query_db()` usage in migrated modules.
- Do not hide playback API passthrough inside system database helpers.
- Do not mix route response changes into database access migration.
- Do not migrate plugin database access in the first stage; design the boundary so plugin state/config/log tables can migrate later.
