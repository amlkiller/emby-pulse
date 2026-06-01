# Database Guidelines

> Database patterns and conventions for this project.

---

## Scenario: First-Stage Database Boundary

> Current layout note: this guideline was written while DAO/query modules still
> lived under transitional top-level `app.dao` and `app.queries` names. In the
> current checkout, the same boundary applies but most business DAO/query modules
> now live under `app.domains.<domain>.*_dao` and
> `app.domains.<domain>.*_queries`. Treat any `app.dao.*` / `app.queries.*`
> examples below as historical migration names unless the module still exists in
> this branch.

### 1. Scope / Trigger

- Trigger: database infrastructure refactor that starts removing `query_db()` from representative modules.
- Applies to new backend code that reads/writes EmbyPulse system data or playback reporting data.
- First-stage sample modules include `app/routers/history.py`, `app/routers/api_tokens.py`, `app/routers/notifications.py`, `app/routers/notify_rules.py`, `app/routers/pro.py`, `app/routers/notify_admin.py`, `app/routers/pwa.py`, `app/routers/audit.py`, `app/routers/risk.py`, `app/routers/clients.py`, `app/routers/calendar_notify.py`, `app/routers/webhook.py`, `app/services/report_service.py`, `app/routers/insight.py`, `app/routers/system_tools.py`, `app/services/risk_service.py`, `app/services/calendar_service.py`, `app/routers/views.py`, `app/routers/tasks.py`, `app/routers/dedupe.py`, `app/routers/system.py`, `app/routers/db_tools.py`, `app/routers/gaps.py`, `app/routers/bot.py`, `app/routers/stats.py`, `app/routers/auth.py`, `app/routers/messages.py`, `app/routers/media_request.py`, the low-risk config/account/log slice of `app/routers/points.py`, the user audit-log slice of `app/routers/users.py`, and the user-bot binding slice of `app/services/user_bot_service.py`.

### 2. Signatures

- `app.infra.db.system_store.system_store.fetch_all(sql: str, params=()) -> list[DataRow]`
- `app.infra.db.system_store.system_store.fetch_one(sql: str, params=()) -> DataRow | None`
- `app.infra.db.system_store.system_store.execute(sql: str, params=()) -> int`
- `app.infra.db.playback_store.playback_store.query(sql: str, params=(), one: bool = False) -> list[DataRow] | DataRow | None`
- `app.infra.db.playback_store.get_playback_column_name() -> str`
- `app.dao.notify_rule_dao.list_bot_notify_mutes() -> list[DataRow]`
- `app.dao.notify_rule_dao.is_bot_notify_muted(user_id, event_type) -> bool`
- `app.dao.notify_rule_dao.replace_bot_notify_mutes(playback_users, login_users) -> None`
- `app.dao.pro_license_dao.replace_license(license_key: str, machine_id: str, status: str = "pro") -> None`
- `app.dao.pro_license_dao.get_license_status() -> DataRow | None`
- `app.dao.notify_admin_dao.save_notify_rules(rules: dict) -> None`
- `app.dao.pwa_dao.get_pwa_config_values() -> dict`
- `app.dao.pwa_dao.save_pwa_config_value(key: str, value: str) -> None`
- `app.dao.audit_dao.list_user_audit_logs_since(start_datetime: str, limit: int) -> list[DataRow]`
- `app.dao.audit_dao.create_user_audit_log(...) -> None`
- `app.dao.audit_dao.list_user_audit_logs(page: int = 1, limit: int = 20, action: str = None, start_date: str = None, end_date: str = None, target_user_id: str = None) -> dict`
- `app.dao.audit_dao.get_user_audit_stats(start_date: str) -> dict`
- `app.dao.audit_dao.delete_user_audit_log(log_id: int) -> None`
- `app.dao.audit_dao.clear_user_audit_logs_before(cutoff_date: str) -> int`
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
- `app.dao.invitation_dao.get_available_registration_invitation(code: str) -> DataRow | None`
- `app.dao.invitation_dao.restore_invitation_code_usage(code: str) -> None`
- `app.dao.invitation_dao.claim_invitation_usage(code: str, used_by: str) -> bool`
- `app.dao.invitation_dao.save_code_registration_meta_and_finish_invitation(code: str, user_id: str, expire_date, allow_routes: str, block_routes: str) -> None`
- `app.dao.invitation_dao.renew_user_with_invitation_code(code: str, used_by: str, user_id: str) -> tuple[dict | None, str | None]`
- `app.dao.invitation_dao.create_invitation_codes(codes, days, created_at: str, template_user_id, code_type: str, routes: str, route_mode: str, req_free, req_free_count) -> None`
- `app.dao.invitation_dao.list_admin_invitations(code_type: str = "all") -> list[DataRow]`
- `app.dao.invitation_dao.list_invitation_usage_stats() -> list[DataRow]`
- `app.dao.invitation_dao.list_invitation_export_rows(code_type: str = "all") -> list[DataRow]`
- `app.dao.invitation_dao.delete_invitation_codes(codes) -> None`
- `app.dao.invitation_dao.claim_registration_invitation(code: str, used_by: str) -> tuple[DataRow | None, str | None]`
- `app.dao.invitation_dao.save_registered_user_meta(...) -> None`
- `app.dao.task_dao.ensure_task_config_defaults() -> None`
- `app.dao.task_dao.is_task_notify_enabled() -> bool`
- `app.dao.task_dao.set_task_notify_enabled(enabled: bool) -> None`
- `app.dao.task_dao.list_task_translations() -> list[DataRow]`
- `app.dao.task_dao.save_task_translation(original_name: str, translated_name: str) -> None`
- `app.dao.task_dao.delete_task_translation(original_name: str) -> None`
- `app.dao.user_dao.set_user_pinned(user_id: str, pinned: bool, created_at: str) -> None`
- `app.dao.user_dao.migrate_admin_disabled(disabled_user_ids, today: str) -> int | None`
- `app.dao.user_dao.list_users_with_expire_date_for_check() -> list[DataRow]`
- `app.dao.user_dao.list_all_user_meta() -> list[DataRow]`
- `app.dao.user_dao.get_user_meta(user_id: str) -> DataRow | None`
- `app.dao.user_dao.set_user_admin_disabled(user_id: str, disabled: bool) -> None`
- `app.dao.user_dao.save_user_admin_disabled(user_id: str, disabled: bool, created_at: str) -> None`
- `app.dao.user_dao.delete_user_meta(user_id: str) -> None`
- `app.dao.user_dao.delete_temp_account_by_emby_user(user_id: str) -> None`
- `app.dao.user_dao.get_user_policy_meta(user_id: str) -> DataRow | None`
- `app.dao.user_dao.save_user_expire_preserve(user_id: str, expire_date, created_at: str) -> None`
- `app.dao.user_dao.save_user_policy_meta(user_id: str, max_concurrent, is_vip, created_at: str) -> None`
- `app.dao.user_dao.save_user_routes_preserve(user_id: str, allow_routes: str, block_routes: str, created_at: str) -> None`
- `app.dao.user_dao.save_manage_user_meta(...) -> None`
- `app.dao.user_dao.create_user_meta(...) -> None`
- `app.dao.user_dao.sync_user_library_permissions(user_id: str, enable_all_folders: bool, enabled_folders) -> list | None`
- `app.dao.user_dao.get_user_library_settings(user_id: str) -> DataRow | None`
- `app.dao.user_dao.get_user_admin_enabled_folders(user_id: str) -> DataRow | None`
- `app.dao.user_dao.save_user_admin_enabled_folders(user_id: str, admin_enabled_folders: str) -> None`
- `app.dao.user_dao.save_user_hidden_libraries(user_id: str, hidden_libraries: str) -> None`
- `app.dao.user_dao.save_user_req_permission(user_id: str, req_free: int, req_free_count: int, created_at: str) -> None`
- `app.dao.user_dao.get_user_req_permission(user_id: str) -> dict`
- `app.dao.user_dao.list_users_with_expire_date() -> list[DataRow]`
- `app.dao.user_dao.get_user_points_expire(user_id: str) -> DataRow | None`
- `app.dao.user_dao.get_user_routes(user_id: str) -> DataRow | None`
- `app.dao.user_dao.save_user_expire(user_id: str, expire_date: str) -> None`
- `app.dao.user_dao.save_user_expire_routes(user_id: str, expire_date: str, allow_routes: str, block_routes: str) -> None`
- `app.dao.user_dao.list_user_tags() -> list[DataRow]`
- `app.dao.user_dao.create_user_tag(name: str, color: str) -> int`
- `app.dao.user_dao.delete_user_tag(tag_id: int) -> None`
- `app.dao.user_dao.delete_user_tag_by_name(tag_name: str) -> bool`
- `app.dao.user_dao.save_user_tags(user_id: str, tags: str, created_at: str) -> None`
- `app.dao.user_dao.get_user_tags(user_id: str) -> str`
- `app.dao.user_bot_dao.ensure_user_bot_tables() -> None`
- `app.dao.user_bot_dao.delete_user_binding(tg_user_id) -> None`
- `app.dao.user_bot_dao.get_binding_by_emby_id(emby_user_id) -> dict | None`
- `app.dao.user_bot_dao.get_binding(tg_user_id) -> dict | None`
- `app.dao.user_bot_dao.get_channel_binding(channel_id) -> DataRow | None`
- `app.dao.user_bot_dao.bind_channel(channel_id, tg_user_id, channel_title: str = "") -> None`
- `app.dao.user_bot_dao.unbind_channel(channel_id) -> None`
- `app.dao.user_bot_dao.list_bindings() -> list[dict]`
- `app.dao.user_bot_dao.list_tg_binding_names() -> list[DataRow]`
- `app.dao.user_bot_dao.list_emby_tg_user_bindings() -> list[DataRow]`
- `app.dao.user_bot_dao.count_bindings() -> int`
- `app.dao.user_bot_dao.create_registration_log(tg_user_id, emby_username, emby_user_id, reg_type: str = "open") -> None`
- `app.dao.user_bot_dao.record_bot_user(tg_user_id, tg_name: str = "") -> None`
- `app.dao.user_bot_dao.list_bot_users() -> list[dict]`
- `app.dao.user_bot_dao.bind_user(tg_user_id, emby_user_id, emby_username, init_password: str = "", tg_username: str = "", tg_display_name: str = "") -> None`
- `app.dao.user_bot_dao.get_tg_user_id_by_username(tg_username: str) -> str | None`
- `app.dao.user_bot_dao.get_binding_by_tg_user_or_username(identifier) -> dict | None`
- `app.dao.user_bot_dao.update_binding_init_password(tg_user_id, init_password: str) -> None`
- `app.dao.user_bot_dao.is_blacklisted(tg_user_id) -> bool`
- `app.dao.user_bot_dao.add_to_blacklist(tg_user_id, reason: str = "") -> None`
- `app.dao.user_bot_dao.search_whois_bindings(normalized: str) -> list[DataRow]`
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
- `app.dao.gap_dao.delete_gap_record_by_series_episode(series_id, season, episode) -> None`
- `app.dao.gap_dao.delete_cleared_gap_record(series_id, season, episode) -> bool`
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
- `app.dao.bot_service_dao.ensure_request_admin_messages_table() -> None`
- `app.dao.bot_service_dao.save_request_admin_message(tmdb_id, chat_id, message_id, is_caption, original_text) -> None`
- `app.dao.bot_service_dao.list_request_admin_messages(tmdb_id: int) -> list[DataRow]`
- `app.dao.bot_service_dao.delete_request_admin_messages(tmdb_id: int) -> None`
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
- `app.dao.message_dao.get_conversation_by_user(user_id: str) -> DataRow | None`
- `app.dao.message_dao.create_conversation(user_id: str, username: str, user_avatar=None) -> int`
- `app.dao.message_dao.insert_admin_message(conversation_id: int, sender_id: str, sender_name: str, content: str, last_message: str) -> None`
- `app.dao.message_dao.insert_user_message(user_id: str, username: str, user_avatar, content: str, last_message: str, notification_message: str) -> int`
- `app.dao.message_dao.get_local_user_remark_by_emby_id(user_id: str) -> DataRow | None`
- `app.dao.message_dao.add_notify_block(user_id: str) -> bool`
- `app.dao.message_dao.remove_notify_block(user_id: str) -> None`
- `app.dao.message_dao.ensure_mute_table() -> None`
- `app.dao.message_dao.upsert_user_mute(user_id: str, username: str, muted_until, reason: str, admin_id: str, admin_name: str) -> None`
- `app.dao.message_dao.ensure_announcement_tables() -> None`
- `app.dao.message_dao.list_announcements(active_only: bool = False) -> list[DataRow]`
- `app.dao.message_dao.update_announcement_fields(announcement_id: int, updates: dict) -> None`
- `app.dao.message_dao.send_broadcast_messages(user_entries, admin_id: str, admin_name: str, content: str) -> tuple[int, list]`
- `app.dao.media_request_dao.ensure_media_request_schema() -> None`
- `app.dao.media_request_dao.submit_new_media_request(...) -> dict`
- `app.dao.media_request_dao.list_my_requests(user_id: str) -> list[DataRow]`
- `app.dao.media_request_dao.list_user_recent_requests(user_id: str, limit: int = 10) -> list[DataRow]`
- `app.dao.media_request_dao.list_all_requests() -> list[DataRow]`
- `app.dao.media_request_dao.get_request_summary_by_tmdb(tmdb_id) -> DataRow | None`
- `app.dao.media_request_dao.list_pending_requests_by_tmdb(tmdb_id) -> list[DataRow]`
- `app.dao.media_request_dao.list_pending_sync_requests() -> list[DataRow]`
- `app.dao.media_request_dao.mark_sync_request_finished(tmdb_id, season=None) -> None`
- `app.dao.media_request_dao.update_media_request_status(tmdb_id, season, status, reject_reason=None) -> None`
- `app.dao.media_request_dao.get_pending_notify_data() -> tuple[int, list[DataRow], int, list[DataRow]]`
- `app.dao.media_request_dao.finish_media_requests_for_item(tmdb_id, season=None) -> tuple[list[DataRow], list[DataRow]]`
- `app.dao.media_request_dao.submit_update_request_record(...) -> dict`
- `app.dao.media_request_dao.submit_batch_update_request_records(...) -> dict`
- `app.dao.media_request_dao.claim_registration_invitation(code: str, used_by: str) -> tuple[DataRow | None, str | None]`
- `app.dao.media_request_dao.save_registered_user_meta(...) -> None`
- `app.dao.point_dao.get_point_config() -> dict`
- `app.dao.point_dao.ensure_lottery_table() -> None`
- `app.dao.point_dao.ensure_points_schema() -> None`
- `app.dao.point_dao.save_point_config_values(configs: dict) -> None`
- `app.dao.point_dao.list_user_points() -> list[DataRow]`
- `app.dao.point_dao.get_user_points_balance(user_id: str) -> int`
- `app.dao.point_dao.batch_update_user_points(user_ids, amount: int, reason: str, name_map: dict) -> int`
- `app.dao.point_dao.list_point_logs(user_id: str = None, page: int = 1, page_size: int = 50, action_type: str = None) -> dict`
- `app.dao.point_dao.get_user_points_info(user_id: str) -> dict`
- `app.dao.point_dao.list_user_point_logs(user_id: str, page: int = 1, page_size: int = 20) -> dict`
- `app.dao.point_dao.transfer_points(from_user_id: str, from_user_name: str, to_user_id: str, to_user_name: str, amount: int, target_exists=None) -> dict`
- `app.dao.point_dao.redeem_store_item(user_id: str, user_name: str, item_id: str) -> dict`
- `app.dao.point_dao.rob_points(from_user_id: str, from_user_name: str, to_user_id: str, to_user_name: str) -> dict`
- `app.dao.point_dao.save_red_packet_message_id(packet_id: int, message_id) -> None`
- `app.dao.point_dao.list_red_packet_logs(packet_id: int) -> list[dict]`
- `app.dao.point_dao.list_point_rank(limit: int = 10) -> list[DataRow]`
- `app.dao.point_dao.get_lottery_winning_numbers(draw_date: str) -> DataRow | None`
- `app.dao.point_dao.list_expired_pending_pk_invites_with_messages() -> list[DataRow]`
- `app.dao.point_dao.get_pending_pk_invitation(invite_id) -> DataRow | None`
- `app.dao.point_dao.set_pk_invitation_status(invite_id, status: str) -> None`
- `app.dao.point_dao.mark_pk_invitation_expired(invite_id) -> None`
- `app.dao.point_dao.get_latest_pending_pk_invitation_for_target(target_id: str) -> DataRow | None`
- `app.dao.point_dao.list_pending_pk_invitations_for_target(target_id: str) -> list[dict]`
- `app.dao.point_dao.reject_pending_pk_invitation(invite_id, target_id: str) -> dict`
- `app.dao.point_dao.clear_pk_invitations() -> int`
- `app.dao.point_dao.save_pk_invitation_message_id(invite_id, message_id) -> None`
- `app.dao.point_dao.create_pk_invitation(...) -> dict`
- `app.dao.point_dao.create_red_packet(total_amount: int, total_count: int, chat_id, creator_id: str, creator_name: str) -> dict`
- `app.dao.point_dao.grab_red_packet(packet_id: int, user_id: str, user_name: str, allow_creator: bool = True) -> dict`
- `app.dao.point_dao.perform_user_checkin(user_id: str, username: str) -> dict`
- `app.infra.db.local_playback_store.insert_webhook_playback_ip_record(...) -> None`
- `app.infra.db.local_playback_store.insert_bot_playback_history_record(...) -> None`
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
- `app.queries.stats_queries.get_user_last_play(user_id: str) -> DataRow | None`
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
- Good: `users.py` keeps admin/session checks and response payload assembly in the route while delegating `user_audit_logs` create/list/stats/delete/cleanup SQL to `audit_dao`.
- Good: `users.py` keeps invitation code generation, CSV rendering, invite-link assembly, and audit-log writes in the route while delegating `invitations` table CRUD/list/export reads to `invitation_dao`.
- Good: `users.py` keeps permission checks, response messages, and audit writes in the route while delegating user pinning, request permission, and tag CRUD persistence to `user_dao`.
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
- Good: `bot_service.py` keeps Emby availability/Policy checks, Telegram callback handling, message editing, notification dispatch, gap scan-state mutation, whois result formatting, and text rendering in the service while delegating request-admin message sync persistence, notify-rule/mute reads/bootstrap, media request/feedback status persistence, gap table/cache persistence, message reply/block persistence, playback read/write access, TG binding lookup, and user expiration metadata reads to DAO/query/infra boundaries.
- Good: `stats.py` keeps chart aggregation, media-server enrichment, and permission filtering in the route while delegating playback SQL execution and base user filters to `stats_queries`.
- Good: `auth.py` keeps password hashing, local/Emby login decisions, TOTP validation, session updates, and audit logging in the route while delegating login failure and `local_users` persistence to `auth_dao`.
- Good: `messages.py` keeps permission checks, Emby user lookups, content sanitization, bot notification delivery, and response assembly in the route while delegating message, mute, notification-block, announcement, and related user lookup tables to `message_dao`.
- Good: `media_request.py` keeps request validation, Emby/TMDB/MoviePilot calls, cache assembly, notification delivery, and response shaping in the route while delegating request, feedback, update, invitation, point, gap-cache, and user metadata persistence to `media_request_dao`.
- Good: `user_bot_service.py` keeps Telegram command parsing and response formatting in the service while delegating TG binding lookups and point robbery transactions to DAO boundaries.
- Good: `user_bot_service.py` keeps Telegram response assembly while delegating red-packet creation and message-id persistence to `point_dao`.
- Good: `user_bot_service.py` keeps Telegram response assembly and final-red-packet notification delivery while delegating red-packet grab transactions to `point_dao`.
- Good: `user_bot_service.py` keeps Telegram callback responses and message cleanup in the service while delegating PK invitation reads/status writes to `point_dao`.
- Good: `points.py` keeps admin/session checks, Emby user enrichment, pagination payload assembly, and later game workflows in the route while delegating point config, point schema bootstrap, point balances, batch updates, point log reads, red-packet log reads, point ranking reads, and daily check-in transactions to `point_dao`.
- Good: `points.py` keeps Emby user existence/name lookup in the route while delegating transfer fee calculation, balance mutation, transfer logs, and transfer transaction handling to `point_dao`.
- Good: `points.py` keeps Emby policy re-enable, sys notification writes, and response shaping in the route while delegating store-item lookup, point deduction, expiry update, purchase limit checks, and point-log writes to `point_dao`.
- Good: `points.py` keeps Emby target-user validation in the route while delegating robbery limits, cooldown, random success/counter logic, balance mutation, and robbery/point logs to `point_dao`.
- Good: `user_bot_service.py` keeps Telegram API calls, Emby account creation, in-memory caches, registration queueing, profile/request rendering, and bot command flow in the service while delegating invitation checks, binding, channel-binding, blacklist, bot-user, registration logs, registration metadata, profile/request reads, playback read queries, and base table bootstrap SQL to DAO/query boundaries.
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

- The `app.core.database` and `app.core.db_manager` compatibility shells have been removed; imports must target `app.infra.db.database`, `app.infra.db.db_manager`, DAO modules, or query service modules directly.
- `app.infra.db.schema_registry` is the new import point for schema metadata during migration.
- Existing schema definitions still delegate to `app.core.db_schemas` until ownership is fully moved.
- `app.infra.db.migration_service` is the new boundary for migration, health, backup, restore, and database-tool deep-check orchestration and currently delegates to existing implementations.

## Scenario: Schema Metadata Registry Boundary

### 1. Scope / Trigger

- Trigger: backend code that needs schema metadata such as system table names, playback table names, create SQL, alter SQL, or core table lists.
- Applies to `app/infra/db/**`, domain database tools, migration services, health checks, and repair helpers.

### 2. Signatures

- Import schema metadata from `app.infra.db.schema_registry`.
- Current exports: `SYSTEM_TABLES`, `PLAYBACK_TABLES`, `TABLE_SCHEMAS`, `TABLE_ALTERS`, `PLAYBACK_SCHEMA`, and `CORE_TABLES`.

### 3. Contracts

- `app.infra.db.schema_registry` is the only migration-time import point for schema metadata.
- During the transition, `schema_registry` may delegate to `app.core.db_schemas`; other app modules must not import `app.core.db_schemas` directly.
- Runtime modules must not keep local copies of `SYSTEM_TABLES` or `PLAYBACK_TABLES`; use the registry object so table lists cannot drift.
- This boundary does not authorize behavior changes to DDL, ALTER order, migration mode, or repair semantics.

### 4. Validation & Error Matrix

- New direct `from app.core.db_schemas import ...` outside `schema_registry` -> fail the schema boundary regression test.
- New local `SYSTEM_TABLES = [...]` / `PLAYBACK_TABLES = [...]` in `app/infra/db/database.py` -> fail the schema boundary regression test.
- Need a new schema metadata value -> add/export it through `schema_registry`, then update focused tests.

### 5. Good/Base/Bad Cases

- Good: `app.infra.db.database` imports `SYSTEM_TABLES` from `app.infra.db.schema_registry`.
- Good: `app.domains.system.system_tool_dao` imports `SYSTEM_TABLES` from `app.infra.db.schema_registry`.
- Base: `app.infra.db.schema_registry` temporarily re-exports values from `app.core.db_schemas`.
- Bad: `app.infra.db.db_manager` imports `TABLE_SCHEMAS` directly from `app.core.db_schemas`.
- Bad: `app.infra.db.database` defines its own `SYSTEM_TABLES` list.

### 6. Tests Required

- Focused boundary test: assert `schema_registry` is the only app module, besides `app/core/db_schemas.py` itself, that imports `app.core.db_schemas`.
- Focused identity test: assert `app.infra.db.database.SYSTEM_TABLES is app.infra.db.schema_registry.SYSTEM_TABLES`.
- Compile/import check changed database modules with `uv run --with-requirements requirements.txt`.
- Run the full pytest suite before completing a schema boundary batch.

### 7. Wrong vs Correct

#### Wrong

```python
from app.core.db_schemas import SYSTEM_TABLES
```

#### Correct

```python
from app.infra.db.schema_registry import SYSTEM_TABLES
```

---

## Common Mistakes

- Do not import removed compatibility modules such as `app.core.database` or `app.core.db_manager`.
- Do not import `app.core.db_schemas` directly outside `app.infra.db.schema_registry`.
- Do not copy schema metadata lists such as `SYSTEM_TABLES` into runtime modules.
- Do not add new `query_db()` usage in migrated modules.
- Do not hide playback API passthrough inside system database helpers.
- Do not mix route response changes into database access migration.
- Do not migrate plugin database access in the first stage; design the boundary so plugin state/config/log tables can migrate later.
