from app.bot.user_bot import user_bot_account_commands_service
from app.bot.user_bot import user_bot_basic_commands_service
from app.bot.user_bot import user_bot_binding_service
from app.bot.user_bot import user_bot_callback_dispatcher_service
from app.bot.user_bot import user_bot_channel_commands_service
from app.bot.user_bot import user_bot_code_commands_service
from app.bot.user_bot import user_bot_concurrency_service
from app.bot.user_bot import user_bot_dice_pk_commands_service
from app.bot.user_bot import user_bot_game_commands_service
from app.bot.user_bot import user_bot_lottery_draw_service
from app.bot.user_bot import user_bot_menu_service
from app.bot.user_bot import user_bot_message_cleanup_service
from app.bot.user_bot import user_bot_message_dispatcher_service
from app.bot.user_bot import user_bot_new_chat_member_service
from app.bot.user_bot import user_bot_open_registration_service
from app.bot.user_bot import user_bot_open_reg_notify_service
from app.bot.user_bot import user_bot_password_commands_service
from app.bot.user_bot import user_bot_pk_callback_service
from app.bot.user_bot import user_bot_pk_invitation_commands_service
from app.bot.user_bot import user_bot_points_commands_service
from app.bot.user_bot import user_bot_points_game_commands_service
from app.bot.user_bot import user_bot_polling_service
from app.bot.user_bot import user_bot_registration_quota_service
from app.bot.user_bot import user_bot_request_commands_service
from app.bot.user_bot import user_bot_restriction_service
from app.bot.user_bot import user_bot_scheduler_service
from app.bot.user_bot import user_bot_scratch_commands_service
from app.bot.user_bot import user_bot_service
from app.bot.user_bot import user_bot_service_info_commands_service
from app.bot.user_bot import user_bot_shop_commands_service
from app.bot.user_bot import user_bot_telegram_service
from app.bot.user_bot import user_bot_transfer_commands_service


_SERVICE_MODULES = [
    user_bot_account_commands_service,
    user_bot_basic_commands_service,
    user_bot_binding_service,
    user_bot_callback_dispatcher_service,
    user_bot_channel_commands_service,
    user_bot_code_commands_service,
    user_bot_concurrency_service,
    user_bot_dice_pk_commands_service,
    user_bot_game_commands_service,
    user_bot_lottery_draw_service,
    user_bot_menu_service,
    user_bot_message_cleanup_service,
    user_bot_message_dispatcher_service,
    user_bot_new_chat_member_service,
    user_bot_open_registration_service,
    user_bot_open_reg_notify_service,
    user_bot_password_commands_service,
    user_bot_pk_callback_service,
    user_bot_pk_invitation_commands_service,
    user_bot_points_commands_service,
    user_bot_points_game_commands_service,
    user_bot_polling_service,
    user_bot_registration_quota_service,
    user_bot_request_commands_service,
    user_bot_restriction_service,
    user_bot_scheduler_service,
    user_bot_scratch_commands_service,
    user_bot_service_info_commands_service,
    user_bot_shop_commands_service,
    user_bot_telegram_service,
    user_bot_transfer_commands_service,
]


_REAL_ATTRS = {
    "_add_to_blacklist": (user_bot_binding_service, "add_to_blacklist"),
    "_batch_flush_loop": (user_bot_registration_quota_service, "batch_flush_loop"),
    "_bind_channel": (user_bot_binding_service, "bind_channel"),
    "_bind_user": (user_bot_binding_service, "bind_user"),
    "_check_emby_account": (user_bot_binding_service, "check_emby_account"),
    "_check_user_in_chat": (user_bot_restriction_service, "check_user_in_chat"),
    "_check_user_restrictions": (user_bot_restriction_service, "check_user_restrictions"),
    "_clear_restriction_cache": (user_bot_restriction_service, "clear_restriction_cache"),
    "_delete_messages_later": (user_bot_message_cleanup_service, "delete_messages_later"),
    "_do_code_register": (user_bot_code_commands_service, "do_code_register"),
    "_do_register": (user_bot_open_registration_service, "do_register"),
    "_edit": (user_bot_telegram_service, "edit"),
    "_enter_reg_queue": (user_bot_service.user_bot_registration_queue_service, "enter_reg_queue"),
    "_flush_batch_used": (user_bot_registration_quota_service, "flush_batch_used"),
    "_format_restriction_message": (user_bot_restriction_service, "format_restriction_message"),
    "_get_all_bot_users": (user_bot_binding_service, "get_all_bot_users"),
    "_get_binding": (user_bot_binding_service, "get_binding"),
    "_get_binding_by_emby_id": (user_bot_binding_service, "get_binding_by_emby_id"),
    "_get_channel_binding": (user_bot_binding_service, "get_channel_binding"),
    "_get_username_lock": (user_bot_concurrency_service, "get_username_lock"),
    "_handle_pk_accept_callback": (user_bot_pk_callback_service, "_handle_pk_accept_callback"),
    "_handle_pk_reject_callback": (user_bot_pk_callback_service, "_handle_pk_reject_callback"),
    "_handle_scratch": (user_bot_scratch_commands_service, "_handle_scratch"),
    "_inc_batch_used": (user_bot_registration_quota_service, "inc_batch_used"),
    "_invalidate_users_cache_after_code_registration": (user_bot_service, "_invalidate_users_cache_after_code_registration"),
    "_is_blacklisted": (user_bot_binding_service, "is_blacklisted"),
    "_leave_reg_queue": (user_bot_service.user_bot_registration_queue_service, "leave_reg_queue"),
    "_load_batch_used_from_cfg": (user_bot_registration_quota_service, "load_batch_used_from_cfg"),
    "_main_menu_keyboard": (user_bot_menu_service, "main_menu_keyboard"),
    "_rate_check": (user_bot_concurrency_service, "rate_check"),
    "_record_bot_user": (user_bot_binding_service, "record_bot_user"),
    "_refresh_user_count_cache_locked": (user_bot_registration_quota_service, "refresh_user_count_cache_locked"),
    "_release_quota_slot": (user_bot_registration_quota_service, "release_quota_slot"),
    "_reply": (user_bot_telegram_service, "reply"),
    "_reserve_quota_slot": (user_bot_registration_quota_service, "reserve_quota_slot"),
    "_restore_invitation_code": (user_bot_code_commands_service, "restore_invitation_code"),
    "_scratch_draw_result": (user_bot_scratch_commands_service, "_scratch_draw_result"),
    "_send": (user_bot_telegram_service, "send"),
    "_send_code_registration_notifications": (user_bot_service, "_send_code_registration_notifications"),
    "_send_open_reg_closed_notify": (user_bot_open_reg_notify_service, "send_open_reg_closed_notify"),
    "_start_batch_flush_thread": (user_bot_registration_quota_service, "start_batch_flush_thread"),
    "_stop_batch_flush_thread": (user_bot_registration_quota_service, "stop_batch_flush_thread"),
    "_submit_request": (user_bot_request_commands_service, "_submit_request"),
    "_submit_task": (user_bot_service.user_bot_registration_queue_service, "submit_task"),
    "_tg_api": (user_bot_telegram_service, "tg_api"),
    "_unbind_channel": (user_bot_binding_service, "unbind_channel"),
    "_unbind_user": (user_bot_binding_service, "unbind_user"),
    "_update_scratch_message": (user_bot_scratch_commands_service, "_update_scratch_message"),
    "cmd_bind": (user_bot_basic_commands_service, "cmd_bind"),
    "cmd_bind_channel": (user_bot_channel_commands_service, "cmd_bind_channel"),
    "cmd_calendar": (user_bot_service_info_commands_service, "cmd_calendar"),
    "cmd_check": (user_bot_code_commands_service, "cmd_check"),
    "cmd_checkin": (user_bot_points_commands_service, "cmd_checkin"),
    "cmd_code": (user_bot_code_commands_service, "cmd_code"),
    "cmd_grab": (user_bot_game_commands_service, "cmd_grab"),
    "cmd_help": (user_bot_basic_commands_service, "cmd_help"),
    "cmd_library": (user_bot_service_info_commands_service, "cmd_library"),
    "cmd_lottery": (user_bot_game_commands_service, "cmd_lottery"),
    "cmd_myrequests": (user_bot_request_commands_service, "cmd_myrequests"),
    "cmd_password": (user_bot_password_commands_service, "cmd_password"),
    "cmd_pk": (user_bot_dice_pk_commands_service, "cmd_pk"),
    "cmd_pk_accept": (user_bot_pk_invitation_commands_service, "cmd_pk_accept"),
    "cmd_pk_invite": (user_bot_pk_invitation_commands_service, "cmd_pk_invite"),
    "cmd_pk_reject": (user_bot_pk_invitation_commands_service, "cmd_pk_reject"),
    "cmd_points": (user_bot_points_commands_service, "cmd_points"),
    "cmd_profile": (user_bot_account_commands_service, "cmd_profile"),
    "cmd_rank": (user_bot_points_game_commands_service, "cmd_rank"),
    "cmd_redpacket": (user_bot_transfer_commands_service, "cmd_redpacket"),
    "cmd_redeem_callback": (user_bot_shop_commands_service, "cmd_redeem_callback"),
    "cmd_register": (user_bot_basic_commands_service, "cmd_register"),
    "cmd_renew": (user_bot_code_commands_service, "cmd_renew"),
    "cmd_request": (user_bot_request_commands_service, "cmd_request"),
    "cmd_request_callback": (user_bot_request_commands_service, "cmd_request_callback"),
    "cmd_rob": (user_bot_points_game_commands_service, "cmd_rob"),
    "cmd_scratch": (user_bot_scratch_commands_service, "cmd_scratch"),
    "cmd_server": (user_bot_service_info_commands_service, "cmd_server"),
    "cmd_shop": (user_bot_shop_commands_service, "cmd_shop"),
    "cmd_start": (user_bot_basic_commands_service, "cmd_start"),
    "cmd_transfer": (user_bot_transfer_commands_service, "cmd_transfer"),
    "cmd_unbind": (user_bot_account_commands_service, "cmd_unbind"),
    "cmd_unbind_channel": (user_bot_channel_commands_service, "cmd_unbind_channel"),
    "cmd_unbind_confirm": (user_bot_account_commands_service, "cmd_unbind_confirm"),
    "do_lottery_draw": (user_bot_lottery_draw_service, "do_lottery_draw"),
    "get_users_list_cached": (user_bot_registration_quota_service, "get_users_list_cached"),
}


_PROVIDER_NAMES = {
    "_add_to_blacklist": "add_to_blacklist_provider",
    "_bind_channel": "bind_channel_provider",
    "_bind_user": "bind_user_provider",
    "_check_emby_account": "check_emby_account_provider",
    "_check_user_in_chat": "check_user_in_chat_provider",
    "_check_user_restrictions": "check_user_restrictions_provider",
    "_clear_restriction_cache": "clear_restriction_cache_provider",
    "_delete_messages_later": "delete_messages_later_provider",
    "_do_code_register": "do_code_register_provider",
    "_do_register": "do_register_provider",
    "_edit": "edit_provider",
    "_enter_reg_queue": "enter_reg_queue_provider",
    "_format_restriction_message": "format_restriction_message_provider",
    "_get_all_bot_users": "get_all_bot_users_provider",
    "_get_binding": "get_binding_provider",
    "_get_binding_by_emby_id": "get_binding_by_emby_id_provider",
    "_get_channel_binding": "get_channel_binding_provider",
    "_get_username_lock": "get_username_lock_provider",
    "_handle_pk_accept_callback": "handle_pk_accept_callback_provider",
    "_handle_pk_reject_callback": "handle_pk_reject_callback_provider",
    "_handle_scratch": "handle_scratch_provider",
    "_invalidate_users_cache_after_code_registration": "invalidate_users_cache_provider",
    "_is_blacklisted": "is_blacklisted_provider",
    "_leave_reg_queue": "leave_reg_queue_provider",
    "_main_menu_keyboard": "main_menu_keyboard_provider",
    "_rate_check": "rate_check_provider",
    "_record_bot_user": "record_bot_user_provider",
    "_refresh_user_count_cache_locked": "refresh_user_count_cache_locked_provider",
    "_release_quota_slot": "release_quota_slot_provider",
    "_reply": "reply_provider",
    "_reserve_quota_slot": "reserve_quota_slot_provider",
    "_restore_invitation_code": "restore_invitation_code_provider",
    "_scratch_draw_result": "scratch_draw_result_provider",
    "_send": "send_provider",
    "_send_code_registration_notifications": "send_registration_notifications_provider",
    "_send_open_reg_closed_notify": "send_open_reg_closed_notify_provider",
    "_submit_request": "submit_request_provider",
    "_submit_task": "submit_task_provider",
    "_tg_api": "tg_api_provider",
    "_unbind_channel": "unbind_channel_provider",
    "_unbind_user": "unbind_user_provider",
    "_update_scratch_message": "update_scratch_message_provider",
    "cmd_bind": "cmd_bind_provider",
    "cmd_bind_channel": "cmd_bind_channel_provider",
    "cmd_calendar": "cmd_calendar_provider",
    "cmd_check": "cmd_check_provider",
    "cmd_checkin": "cmd_checkin_provider",
    "cmd_code": "cmd_code_provider",
    "cmd_grab": "cmd_grab_provider",
    "cmd_help": "cmd_help_provider",
    "cmd_library": "cmd_library_provider",
    "cmd_lottery": "cmd_lottery_provider",
    "cmd_myrequests": "cmd_myrequests_provider",
    "cmd_password": "cmd_password_provider",
    "cmd_pk": "cmd_pk_provider",
    "cmd_pk_accept": "cmd_pk_accept_provider",
    "cmd_pk_invite": "cmd_pk_invite_provider",
    "cmd_pk_reject": "cmd_pk_reject_provider",
    "cmd_points": "cmd_points_provider",
    "cmd_profile": "cmd_profile_provider",
    "cmd_rank": "cmd_rank_provider",
    "cmd_redpacket": "cmd_redpacket_provider",
    "cmd_redeem_callback": "cmd_redeem_callback_provider",
    "cmd_register": "cmd_register_provider",
    "cmd_request": "cmd_request_provider",
    "cmd_rob": "cmd_rob_provider",
    "cmd_scratch": "cmd_scratch_provider",
    "cmd_server": "cmd_server_provider",
    "cmd_shop": "cmd_shop_provider",
    "cmd_start": "cmd_start_provider",
    "cmd_transfer": "cmd_transfer_provider",
    "cmd_unbind": "cmd_unbind_provider",
    "do_lottery_draw": "do_lottery_draw_provider",
    "get_users_list_cached": "get_users_list_cached_provider",
}


_SIMPLE_PROVIDER_NAMES = {
    "datetime": "datetime_provider",
    "get_hidden_users": "get_hidden_users_provider",
    "get_media_server_main_public_url": "media_server_main_public_url_provider",
    "get_media_server_user_routes": "get_media_server_user_routes_provider",
    "get_safe_proxies": "get_safe_proxies_provider",
    "get_user_bot_allowed_groups": "allowed_groups_provider",
    "get_user_bot_allow_routes": "allow_routes_provider",
    "get_user_bot_block_routes": "block_routes_provider",
    "get_user_bot_group_commands": "group_commands_provider",
    "get_user_bot_group_enabled": "group_enabled_provider",
    "get_user_bot_max_reg": "max_reg_provider",
    "get_user_bot_portal_url": "portal_url_provider",
    "get_user_bot_reg_days": "reg_days_provider",
    "get_user_bot_reg_quota": "reg_quota_provider",
    "get_user_bot_reg_quota_mode": "reg_quota_mode_provider",
    "get_user_bot_registration_batch_used": "get_registration_batch_used_provider",
    "get_user_bot_required_channels": "required_channels_provider",
    "get_user_bot_required_groups": "required_groups_provider",
    "get_user_bot_restriction_cache_ttl": "restriction_cache_ttl_provider",
    "get_user_bot_template_user": "template_user_provider",
    "get_user_bot_token": "token_provider",
    "get_user_bot_welcome_msg": "welcome_msg_provider",
    "invitation_dao": "invitation_dao_provider",
    "is_user_bot_open_reg_enabled": "open_reg_enabled_provider",
    "is_user_bot_open_reg_notify_group_enabled": "notify_group_enabled_provider",
    "is_user_bot_open_reg_notify_user_enabled": "notify_user_enabled_provider",
    "is_user_bot_restriction_enabled": "restriction_enabled_provider",
    "logger": "logger_provider",
    "media_api": "media_api_provider",
    "media_request_dao": "media_request_dao_provider",
    "network_client": "network_client_provider",
    "point_dao": "point_dao_provider",
    "random": "random_provider",
    "safe_error_message": "safe_error_message_provider",
    "secrets": "secrets_provider",
    "set_user_bot_open_reg_enabled": "set_open_reg_enabled_provider",
    "set_user_bot_registration_batch_used": "set_registration_batch_used_provider",
    "stats_queries": "stats_queries_provider",
    "telegram_client": "telegram_client_provider",
    "threading": "threading_provider",
    "time": "time_provider",
    "tmdb_client": "tmdb_client_provider",
    "user_bot_dao": "user_bot_dao_provider",
    "user_dao": "user_dao_provider",
    "validate_password_strength": "validate_password_strength_provider",
}


_RETURN_CALLABLE_ATTRS = {
    "get_hidden_users",
    "get_media_server_main_public_url",
    "get_media_server_user_routes",
    "get_safe_proxies",
    "get_user_bot_group_commands",
    "get_user_bot_group_enabled",
    "get_user_bot_portal_url",
    "get_user_bot_registration_batch_used",
    "get_user_bot_required_channels",
    "get_user_bot_required_groups",
    "get_user_bot_restriction_cache_ttl",
    "get_user_bot_token",
    "get_users_list_cached",
    "is_user_bot_restriction_enabled",
    "safe_error_message",
    "set_user_bot_open_reg_enabled",
    "set_user_bot_registration_batch_used",
    "validate_password_strength",
}


_DIRECT_VALUE_ATTRS = {
    "_get_all_bot_users",
}


class BoundaryUserBot:
    def _on_message(self, msg):
        return user_bot_message_dispatcher_service.handle_message(msg)

    def _on_new_chat_members(self, chat_id, new_members, group_name=""):
        return user_bot_new_chat_member_service.handle_new_chat_members(chat_id, new_members, group_name)


class UserBotWorkerBoundary:
    def __init__(self):
        object.__setattr__(self, "_overrides", {})
        object.__setattr__(self, "_provider_params", {
            module: set(module.set_dependency_providers.__kwdefaults__ or {})
            for module in _SERVICE_MODULES
            if hasattr(module, "set_dependency_providers")
        })

    def __getattr__(self, name):
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        if name == "UserBot":
            return BoundaryUserBot
        if name == "user_bot":
            return BoundaryUserBot()
        if name in _REAL_ATTRS:
            module, attr = _REAL_ATTRS[name]
            return getattr(module, attr)
        if hasattr(user_bot_service, name):
            return getattr(user_bot_service, name)
        for module in _SERVICE_MODULES:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        overrides = object.__getattribute__(self, "_overrides")
        overrides[name] = value
        self._wire_provider(name, value)
        self._wire_state(name, value)

    def _wire_provider(self, name, value):
        provider_name = _PROVIDER_NAMES.get(name) or _SIMPLE_PROVIDER_NAMES.get(name)
        if provider_name is None:
            return
        provider_value = self._provider_value(name, value)
        provider_params = object.__getattribute__(self, "_provider_params")
        for module, params in provider_params.items():
            if provider_name in params:
                module.set_dependency_providers(**{provider_name: provider_value})

        if name == "get_user_bot_token":
            user_bot_telegram_service.set_dependency_providers(get_token_provider=lambda: value)
            user_bot_new_chat_member_service.set_dependency_providers(user_bot_token_provider=value)
            user_bot_message_cleanup_service.set_dependency_providers(token_provider=value)
        if name == "get_safe_proxies":
            user_bot_message_cleanup_service.set_dependency_providers(safe_proxies_provider=value)
            user_bot_telegram_service.set_dependency_providers(get_safe_proxies_provider=lambda: value)
            user_bot_polling_service.set_dependency_providers(get_safe_proxies_provider=lambda: value)
            user_bot_request_commands_service.set_dependency_providers(get_safe_proxies_provider=lambda: value)
        if name == "get_user_bot_allowed_groups":
            user_bot_message_dispatcher_service.set_dependency_providers(allowed_groups_provider=lambda: value)
        if name == "get_user_bot_portal_url":
            user_bot_menu_service.set_dependency_providers(portal_url_provider=value)
            user_bot_request_commands_service.set_dependency_providers(portal_url_provider=lambda: value)
        if name == "get_media_server_user_routes":
            user_bot_service_info_commands_service.set_dependency_providers(get_media_server_user_routes_provider=lambda: value)
        if name == "datetime":
            user_bot_pk_callback_service.set_dependency_providers(datetime_provider=lambda: value)

    def _provider_value(self, name, value):
        if name in _DIRECT_VALUE_ATTRS:
            return value
        if name in _RETURN_CALLABLE_ATTRS:
            return lambda: value
        if name.startswith("get_") or name.startswith("is_") or name.startswith("set_"):
            return value
        if name == "get_user_bot_token":
            return value
        return lambda: value

    def _wire_state(self, name, value):
        if name == "_user_state":
            for module in (
                user_bot_basic_commands_service,
                user_bot_code_commands_service,
                user_bot_message_dispatcher_service,
                user_bot_open_registration_service,
                user_bot_password_commands_service,
                user_bot_callback_dispatcher_service,
            ):
                module.set_dependency_providers(user_state_provider=lambda value=value: value)
            user_bot_service._user_state = value
        elif name in {"_binding_cache", "_blacklist_cache", "_emby_account_cache", "_cache_lock"}:
            user_bot_binding_service.set_dependency_providers(**{f"{name[1:]}_provider": lambda value=value: value})
            setattr(user_bot_service, name, value)
        elif name in {"_BINDING_CACHE_TTL", "_BLACKLIST_CACHE_TTL", "_EMBY_ACCOUNT_CACHE_TTL"}:
            provider_name = {
                "_BINDING_CACHE_TTL": "binding_cache_ttl_provider",
                "_BLACKLIST_CACHE_TTL": "blacklist_cache_ttl_provider",
                "_EMBY_ACCOUNT_CACHE_TTL": "emby_account_cache_ttl_provider",
            }[name]
            user_bot_binding_service.set_dependency_providers(**{provider_name: lambda value=value: value})
            setattr(user_bot_service, name, value)
        elif name in {"_rate_limit", "_username_locks", "_username_locks_lock", "_USERNAME_LOCK_MAX_SIZE"}:
            provider_name = {
                "_rate_limit": "rate_limit_provider",
                "_username_locks": "username_locks_provider",
                "_username_locks_lock": "username_locks_lock_provider",
                "_USERNAME_LOCK_MAX_SIZE": "username_lock_max_size_provider",
            }[name]
            user_bot_concurrency_service.set_dependency_providers(**{provider_name: lambda value=value: value})
            setattr(user_bot_service, name, value)
        elif name in {
            "_quota_lock",
            "_quota_reserved",
            "_user_count_cache",
            "_batch_used_lock",
            "_batch_used_mem",
            "_batch_used_dirty",
            "_batch_flush_stop",
            "_batch_flush_thread",
        }:
            self._wire_quota_state(name, value)
            setattr(user_bot_service, name, value)
        elif name in {"_restriction_cache", "_restriction_cache_lock"}:
            provider_name = {
                "_restriction_cache": "restriction_cache_provider",
                "_restriction_cache_lock": "restriction_cache_lock_provider",
            }[name]
            user_bot_restriction_service.set_dependency_providers(**{provider_name: lambda value=value: value})
            setattr(user_bot_service, name, value)

    def _wire_quota_state(self, name, value):
        provider_name = {
            "_quota_lock": "quota_lock_provider",
            "_quota_reserved": "get_quota_reserved_provider",
            "_user_count_cache": "user_count_cache_provider",
            "_batch_used_lock": "batch_used_lock_provider",
            "_batch_used_mem": "get_batch_used_mem_provider",
            "_batch_used_dirty": "get_batch_used_dirty_provider",
            "_batch_flush_stop": "batch_flush_stop_provider",
            "_batch_flush_thread": "get_batch_flush_thread_provider",
        }[name]
        kwargs = {provider_name: lambda name=name: object.__getattribute__(self, "_overrides").get(name)}
        callback_name = {
            "_quota_reserved": "set_quota_reserved_callback",
            "_batch_used_mem": "set_batch_used_mem_callback",
            "_batch_used_dirty": "set_batch_used_dirty_callback",
            "_batch_flush_thread": "set_batch_flush_thread_callback",
        }.get(name)
        if callback_name:
            kwargs[callback_name] = lambda new_value, name=name: self._set_state_value(name, new_value)
        user_bot_registration_quota_service.set_dependency_providers(**kwargs)
        if name == "_quota_lock":
            user_bot_open_registration_service.set_dependency_providers(
                quota_lock_provider=lambda name=name: object.__getattribute__(self, "_overrides").get(name)
            )
        elif name == "_user_count_cache":
            user_bot_open_registration_service.set_dependency_providers(
                user_count_cache_provider=lambda name=name: object.__getattribute__(self, "_overrides").get(name)
            )

    def _set_state_value(self, name, value):
        object.__getattribute__(self, "_overrides")[name] = value
        setattr(user_bot_service, name, value)
        setattr(user_bot_registration_quota_service, name, value)


user_bot_worker_boundary = UserBotWorkerBoundary()
