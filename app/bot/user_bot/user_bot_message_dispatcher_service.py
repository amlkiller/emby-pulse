import logging

from app.infra.config.user_bot_settings import (
    get_user_bot_allowed_groups,
    get_user_bot_group_commands,
    get_user_bot_group_enabled,
)


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger
_get_channel_binding_provider = lambda: (lambda channel_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_rate_check_provider = lambda: (lambda tg_user_id, cooldown=3: True)
_group_enabled_provider = lambda: get_user_bot_group_enabled
_allowed_groups_provider = lambda: get_user_bot_allowed_groups
_group_commands_provider = lambda: get_user_bot_group_commands
_delete_messages_later_provider = lambda: (lambda chat_id, message_ids, delay_seconds=30: None)
_new_chat_members_handler_provider = lambda: (lambda chat_id, new_members, group_name: None)
_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_user_restrictions_provider = lambda: (lambda tg_user_id: {"passed": True})
_format_restriction_message_provider = lambda: (lambda check_result: "")
_user_state_provider = lambda: {}
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_do_register_provider = lambda: (lambda chat_id, tg_user_id, custom_name, tg_username="", tg_display_name="": None)
_do_code_register_provider = lambda: (
    lambda chat_id,
    tg_user_id,
    custom_name,
    code,
    days,
    tpl_id,
    routes=None,
    route_mode=None,
    tg_username="",
    tg_display_name="": None
)

_cmd_checkin_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None, is_group=False, group_name="", user_msg_id=None: None)
_cmd_points_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None, is_group=False: None)
_cmd_rank_provider = lambda: (lambda chat_id, tg_user_id, is_group=False: None)
_cmd_transfer_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, entities=None: None)
_cmd_rob_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, entities=None: None)
_cmd_pk_invite_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, entities=None, user_msg_id=None: None)
_cmd_redpacket_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None: None)
_cmd_grab_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None: None)
_cmd_pk_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None: None)
_cmd_lottery_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, user_msg_id=None: None)
_cmd_scratch_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None: None)
_cmd_check_provider = lambda: (lambda chat_id, tg_user_id: None)
_cmd_start_provider = lambda: (lambda chat_id, tg_user_id, tg_name: None)
_cmd_help_provider = lambda: (lambda chat_id, tg_user_id: None)
_cmd_bind_channel_provider = lambda: (lambda chat_id, tg_user_id, args: None)
_cmd_bind_provider = lambda: (lambda chat_id, tg_user_id, args, tg_username="", tg_display_name="": None)
_cmd_register_provider = lambda: (lambda chat_id, tg_user_id, tg_name: None)
_cmd_code_provider = lambda: (lambda chat_id, tg_user_id, args: None)
_cmd_unbind_channel_provider = lambda: (lambda chat_id, tg_user_id, args: None)
_cmd_unbind_provider = lambda: (lambda chat_id, tg_user_id: None)
_cmd_profile_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_renew_provider = lambda: (lambda chat_id, tg_user_id, args: None)
_cmd_calendar_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_shop_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_request_provider = lambda: (lambda chat_id, tg_user_id, args: None)
_cmd_myrequests_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_server_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_library_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_password_provider = lambda: (lambda chat_id, tg_user_id, args: None)
_cmd_pk_accept_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False: None)
_cmd_pk_reject_provider = lambda: (lambda chat_id, tg_user_id, text, is_group=False: None)


def set_dependency_providers(
    *,
    logger_provider=None,
    get_channel_binding_provider=None,
    send_provider=None,
    rate_check_provider=None,
    group_enabled_provider=None,
    allowed_groups_provider=None,
    group_commands_provider=None,
    delete_messages_later_provider=None,
    new_chat_members_handler_provider=None,
    get_binding_provider=None,
    check_user_restrictions_provider=None,
    format_restriction_message_provider=None,
    user_state_provider=None,
    main_menu_keyboard_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    do_register_provider=None,
    do_code_register_provider=None,
    cmd_checkin_provider=None,
    cmd_points_provider=None,
    cmd_rank_provider=None,
    cmd_transfer_provider=None,
    cmd_rob_provider=None,
    cmd_pk_invite_provider=None,
    cmd_redpacket_provider=None,
    cmd_grab_provider=None,
    cmd_pk_provider=None,
    cmd_lottery_provider=None,
    cmd_scratch_provider=None,
    cmd_check_provider=None,
    cmd_start_provider=None,
    cmd_help_provider=None,
    cmd_bind_channel_provider=None,
    cmd_bind_provider=None,
    cmd_register_provider=None,
    cmd_code_provider=None,
    cmd_unbind_channel_provider=None,
    cmd_unbind_provider=None,
    cmd_profile_provider=None,
    cmd_renew_provider=None,
    cmd_calendar_provider=None,
    cmd_shop_provider=None,
    cmd_request_provider=None,
    cmd_myrequests_provider=None,
    cmd_server_provider=None,
    cmd_library_provider=None,
    cmd_password_provider=None,
    cmd_pk_accept_provider=None,
    cmd_pk_reject_provider=None,
):
    global _logger_provider
    global _get_channel_binding_provider
    global _send_provider
    global _rate_check_provider
    global _group_enabled_provider
    global _allowed_groups_provider
    global _group_commands_provider
    global _delete_messages_later_provider
    global _new_chat_members_handler_provider
    global _get_binding_provider
    global _check_user_restrictions_provider
    global _format_restriction_message_provider
    global _user_state_provider
    global _main_menu_keyboard_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _do_register_provider
    global _do_code_register_provider
    global _cmd_checkin_provider
    global _cmd_points_provider
    global _cmd_rank_provider
    global _cmd_transfer_provider
    global _cmd_rob_provider
    global _cmd_pk_invite_provider
    global _cmd_redpacket_provider
    global _cmd_grab_provider
    global _cmd_pk_provider
    global _cmd_lottery_provider
    global _cmd_scratch_provider
    global _cmd_check_provider
    global _cmd_start_provider
    global _cmd_help_provider
    global _cmd_bind_channel_provider
    global _cmd_bind_provider
    global _cmd_register_provider
    global _cmd_code_provider
    global _cmd_unbind_channel_provider
    global _cmd_unbind_provider
    global _cmd_profile_provider
    global _cmd_renew_provider
    global _cmd_calendar_provider
    global _cmd_shop_provider
    global _cmd_request_provider
    global _cmd_myrequests_provider
    global _cmd_server_provider
    global _cmd_library_provider
    global _cmd_password_provider
    global _cmd_pk_accept_provider
    global _cmd_pk_reject_provider

    if logger_provider is not None:
        _logger_provider = logger_provider
    if get_channel_binding_provider is not None:
        _get_channel_binding_provider = get_channel_binding_provider
    if send_provider is not None:
        _send_provider = send_provider
    if rate_check_provider is not None:
        _rate_check_provider = rate_check_provider
    if group_enabled_provider is not None:
        _group_enabled_provider = group_enabled_provider
    if allowed_groups_provider is not None:
        _allowed_groups_provider = allowed_groups_provider
    if group_commands_provider is not None:
        _group_commands_provider = group_commands_provider
    if delete_messages_later_provider is not None:
        _delete_messages_later_provider = delete_messages_later_provider
    if new_chat_members_handler_provider is not None:
        _new_chat_members_handler_provider = new_chat_members_handler_provider
    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if check_user_restrictions_provider is not None:
        _check_user_restrictions_provider = check_user_restrictions_provider
    if format_restriction_message_provider is not None:
        _format_restriction_message_provider = format_restriction_message_provider
    if user_state_provider is not None:
        _user_state_provider = user_state_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if check_emby_account_provider is not None:
        _check_emby_account_provider = check_emby_account_provider
    if unbind_user_provider is not None:
        _unbind_user_provider = unbind_user_provider
    if do_register_provider is not None:
        _do_register_provider = do_register_provider
    if do_code_register_provider is not None:
        _do_code_register_provider = do_code_register_provider
    if cmd_checkin_provider is not None:
        _cmd_checkin_provider = cmd_checkin_provider
    if cmd_points_provider is not None:
        _cmd_points_provider = cmd_points_provider
    if cmd_rank_provider is not None:
        _cmd_rank_provider = cmd_rank_provider
    if cmd_transfer_provider is not None:
        _cmd_transfer_provider = cmd_transfer_provider
    if cmd_rob_provider is not None:
        _cmd_rob_provider = cmd_rob_provider
    if cmd_pk_invite_provider is not None:
        _cmd_pk_invite_provider = cmd_pk_invite_provider
    if cmd_redpacket_provider is not None:
        _cmd_redpacket_provider = cmd_redpacket_provider
    if cmd_grab_provider is not None:
        _cmd_grab_provider = cmd_grab_provider
    if cmd_pk_provider is not None:
        _cmd_pk_provider = cmd_pk_provider
    if cmd_lottery_provider is not None:
        _cmd_lottery_provider = cmd_lottery_provider
    if cmd_scratch_provider is not None:
        _cmd_scratch_provider = cmd_scratch_provider
    if cmd_check_provider is not None:
        _cmd_check_provider = cmd_check_provider
    if cmd_start_provider is not None:
        _cmd_start_provider = cmd_start_provider
    if cmd_help_provider is not None:
        _cmd_help_provider = cmd_help_provider
    if cmd_bind_channel_provider is not None:
        _cmd_bind_channel_provider = cmd_bind_channel_provider
    if cmd_bind_provider is not None:
        _cmd_bind_provider = cmd_bind_provider
    if cmd_register_provider is not None:
        _cmd_register_provider = cmd_register_provider
    if cmd_code_provider is not None:
        _cmd_code_provider = cmd_code_provider
    if cmd_unbind_channel_provider is not None:
        _cmd_unbind_channel_provider = cmd_unbind_channel_provider
    if cmd_unbind_provider is not None:
        _cmd_unbind_provider = cmd_unbind_provider
    if cmd_profile_provider is not None:
        _cmd_profile_provider = cmd_profile_provider
    if cmd_renew_provider is not None:
        _cmd_renew_provider = cmd_renew_provider
    if cmd_calendar_provider is not None:
        _cmd_calendar_provider = cmd_calendar_provider
    if cmd_shop_provider is not None:
        _cmd_shop_provider = cmd_shop_provider
    if cmd_request_provider is not None:
        _cmd_request_provider = cmd_request_provider
    if cmd_myrequests_provider is not None:
        _cmd_myrequests_provider = cmd_myrequests_provider
    if cmd_server_provider is not None:
        _cmd_server_provider = cmd_server_provider
    if cmd_library_provider is not None:
        _cmd_library_provider = cmd_library_provider
    if cmd_password_provider is not None:
        _cmd_password_provider = cmd_password_provider
    if cmd_pk_accept_provider is not None:
        _cmd_pk_accept_provider = cmd_pk_accept_provider
    if cmd_pk_reject_provider is not None:
        _cmd_pk_reject_provider = cmd_pk_reject_provider


def _arg_after_command(text):
    return text.split(None, 1)[1] if len(text.split()) > 1 else ""


def handle_message(msg):
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat", {})
    chat_id = str(chat["id"])
    chat_type = chat.get("type", "")

    sender_chat = msg.get("sender_chat")
    from_user = msg.get("from")

    if sender_chat and not from_user:
        channel_id = str(sender_chat["id"])
        channel_title = sender_chat.get("title", "频道")
        _logger_provider().info(f"[UserBot] 频道身份消息: channel_id={channel_id}, title={channel_title}, text={text[:50]}")

        channel_binding = _get_channel_binding_provider()(channel_id)
        if channel_binding:
            tg_user_id = channel_binding["bound_tg_user_id"]
            _logger_provider().info(f"[UserBot] 频道绑定用户: tg_user_id={tg_user_id}")
        else:
            _send_provider()(chat_id, f"❌ 频道 <b>{channel_title}</b> 未绑定账号\n\n💡 请先私聊机器人发送 /bind_channel {channel_id} 绑定频道")
            return
    else:
        if not from_user:
            _logger_provider().info("[UserBot] 消息缺少 from 字段，跳过")
            return

        tg_user_id = str(from_user["id"])

    tg_name = from_user.get("first_name", "用户") if from_user else "频道用户"
    tg_last_name = msg["from"].get("last_name", "")
    tg_display_name = f"{tg_name} {tg_last_name}".strip() if tg_last_name else tg_name
    group_name = chat.get("title", "")
    user_msg_id = msg.get("message_id")
    entities = msg.get("entities", [])

    if chat_type == "channel":
        return

    if not _rate_check_provider()(tg_user_id):
        return

    if chat_type in ["group", "supergroup"]:
        if not _group_enabled_provider()():
            return

        allowed_groups = _allowed_groups_provider()()
        if allowed_groups:
            allowed_list = [g.strip() for g in allowed_groups.split("\n") if g.strip()]
            if chat_id not in allowed_list and f"@{chat.get('username', '')}" not in allowed_list:
                return

        group_commands = _group_commands_provider()()
        allowed_cmds = [c.strip().lower() for c in group_commands.split(",") if c.strip()]
        _logger_provider().info(f"[群聊] allowed_cmds={allowed_cmds}, text={text}")

        cmd = text.split()[0].lower().lstrip("/") if text else ""
        cmd_name = cmd.split("@")[0] if "@" in cmd else cmd
        _logger_provider().info(f"[群聊] cmd={cmd}, cmd_name={cmd_name}")

        if cmd_name in ["checkin", "签到", "qd"] and "checkin" in allowed_cmds:
            _cmd_checkin_provider()(chat_id, tg_user_id, is_group=True, group_name=group_name, user_msg_id=user_msg_id)
            return
        elif cmd_name in ["help", "帮助"] and "help" in allowed_cmds:
            result = _send_provider()(
                chat_id,
                "🤖 <b>群内可用指令</b>\n\n"
                "✅ /checkin 或 /签到 - 每日签到获取积分\n"
                "✅ /points 或 /积分 - 查看积分余额\n"
                "✅ /rank 或 /排行 - 积分排行榜\n"
                "✅ /transfer 或 /转赠 - 转赠积分\n"
                "✅ /rob 或 /打劫 - 打劫好友积分\n"
                "✅ /hb 或 /红包 - 发积分红包\n"
                "✅ /grab 或 /抢 - 抢红包\n\n"
                "💡 更多功能请私聊机器人使用",
            )
            if result and user_msg_id:
                bot_msg_id = result.get("result", {}).get("message_id")
                if bot_msg_id:
                    _delete_messages_later_provider()(chat_id, [bot_msg_id, user_msg_id], 30)
            return
        elif cmd_name in ["points", "积分", "jf"] and "points" in allowed_cmds:
            result = _cmd_points_provider()(chat_id, tg_user_id, is_group=True, msg_id=None)
            if result and user_msg_id:
                bot_msg_id = result.get("result", {}).get("message_id")
                if bot_msg_id:
                    _delete_messages_later_provider()(chat_id, [bot_msg_id, user_msg_id], 30)
            return
        elif cmd_name in ["rank", "排行", "ph"] and "rank" in allowed_cmds:
            result = _cmd_rank_provider()(chat_id, tg_user_id, is_group=True)
            if result and user_msg_id:
                bot_msg_id = result.get("result", {}).get("message_id")
                if bot_msg_id:
                    _delete_messages_later_provider()(chat_id, [bot_msg_id, user_msg_id], 30)
            return
        elif cmd_name in ["transfer", "转赠", "zz"] and "transfer" in allowed_cmds:
            _cmd_transfer_provider()(chat_id, tg_user_id, text, is_group=True, entities=entities)
            return
        elif cmd_name in ["rob", "打劫", "dj"] and "rob" in allowed_cmds:
            _cmd_rob_provider()(chat_id, tg_user_id, text, is_group=True, entities=entities)
            return
        elif cmd_name in ["upk", "用户pk"] and "upk" in allowed_cmds:
            _cmd_pk_invite_provider()(chat_id, tg_user_id, text, is_group=True, entities=entities, user_msg_id=user_msg_id)
            return
        elif cmd_name in ["hb", "红包", "redpacket"] and "redpacket" in allowed_cmds:
            _cmd_redpacket_provider()(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
            return
        elif cmd_name in ["grab", "抢", "q"] and "grab" in allowed_cmds:
            _cmd_grab_provider()(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
            return
        elif cmd_name in ["pk", "PK", "骰子", "tz"] and "pk" in allowed_cmds:
            _cmd_pk_provider()(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
            return
        elif cmd_name in ["lottery", "彩票", "cp"] and "lottery" in allowed_cmds:
            _logger_provider().info("[彩票] 群聊命令匹配成功，调用 cmd_lottery")
            _cmd_lottery_provider()(chat_id, tg_user_id, text, is_group=True, user_msg_id=user_msg_id)
            return
        elif cmd_name in ["scratch", "刮刮乐", "ggl"] and "scratch" in allowed_cmds:
            _cmd_scratch_provider()(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
            return
        else:
            if "new_chat_members" in msg:
                _new_chat_members_handler_provider()(chat_id, msg.get("new_chat_members", []), group_name)
                return
            return

    binding = _get_binding_provider()(tg_user_id)

    if text.startswith("/check") or text.startswith("/验证"):
        _cmd_check_provider()(chat_id, tg_user_id)
        return

    restriction_check = _check_user_restrictions_provider()(tg_user_id)
    if not restriction_check["passed"]:
        _send_provider()(chat_id, _format_restriction_message_provider()(restriction_check))
        return

    if text.startswith("/start"):
        _cmd_start_provider()(chat_id, tg_user_id, tg_name)
        return
    if text.startswith("/help") or text.startswith("/帮助"):
        _cmd_help_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/menu") or text.startswith("/菜单"):
        _cmd_start_provider()(chat_id, tg_user_id, tg_name)
        return
    if text.startswith("/bind_channel"):
        _cmd_bind_channel_provider()(chat_id, tg_user_id, _arg_after_command(text))
        return
    if text.startswith("/bind") or text.startswith("/绑定"):
        _cmd_bind_provider()(chat_id, tg_user_id, _arg_after_command(text), tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name)
        return
    if text.startswith("/register") or text.startswith("/注册"):
        _cmd_register_provider()(chat_id, tg_user_id, tg_name)
        return
    if text.startswith("/code") or text.startswith("/注册码"):
        _cmd_code_provider()(chat_id, tg_user_id, _arg_after_command(text))
        return

    if not binding:
        state = _user_state_provider().get(tg_user_id)
        if state and state.get("action") == "register_name" and not text.startswith("/"):
            del _user_state_provider()[tg_user_id]
            _do_register_provider()(chat_id, tg_user_id, text, tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name)
            return
        if state and state.get("action") == "code_input_name" and not text.startswith("/"):
            del _user_state_provider()[tg_user_id]
            _do_code_register_provider()(
                chat_id,
                tg_user_id,
                text,
                state.get("code"),
                state.get("days"),
                state.get("tpl_id"),
                state.get("routes"),
                state.get("route_mode"),
                tg_username=msg["from"].get("username", ""),
                tg_display_name=tg_display_name,
            )
            return
        _send_provider()(chat_id, "🔒 请先绑定或注册账号后才能使用此功能", reply_markup=_main_menu_keyboard_provider()(None))
        return

    if not _check_emby_account_provider()(binding):
        _unbind_user_provider()(tg_user_id)
        _send_provider()(chat_id, "⚠️ 你的 Emby 账号已被管理员删除，绑定已自动解除。", reply_markup=_main_menu_keyboard_provider()(None))
        return

    if text.startswith("/unbind_channel"):
        _cmd_unbind_channel_provider()(chat_id, tg_user_id, _arg_after_command(text))
        return
    if text.startswith("/unbind") or text.startswith("/解绑"):
        _cmd_unbind_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/profile") or text.startswith("/个人中心"):
        _cmd_profile_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/renew") or text.startswith("/续期"):
        _cmd_renew_provider()(chat_id, tg_user_id, _arg_after_command(text))
        return
    if text.startswith("/checkin") or text.startswith("/签到"):
        _cmd_checkin_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/calendar") or text.startswith("/今日更新"):
        _cmd_calendar_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/points") or text.startswith("/积分"):
        _cmd_points_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/shop") or text.startswith("/商城"):
        _cmd_shop_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/request") or text.startswith("/求片"):
        _cmd_request_provider()(chat_id, tg_user_id, _arg_after_command(text))
        return
    if text.startswith("/myrequests") or text.startswith("/我的求片"):
        _cmd_myrequests_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/server") or text.startswith("/服务器"):
        _cmd_server_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/library") or text.startswith("/媒体库"):
        _cmd_library_provider()(chat_id, tg_user_id)
        return
    if text.startswith("/password") or text.startswith("/密码"):
        _cmd_password_provider()(chat_id, tg_user_id, _arg_after_command(text))
        return
    if text.startswith("/pk ") or text.startswith("/PK "):
        _cmd_pk_provider()(chat_id, tg_user_id, text, tg_name=tg_display_name)
        return
    if text.startswith("/骰子") or text.startswith("/tz"):
        _cmd_pk_provider()(chat_id, tg_user_id, text, tg_name=tg_display_name)
        return
    if text.startswith("/upk") or text.startswith("/用户pk") or text.startswith("/用户PK"):
        _cmd_pk_invite_provider()(chat_id, tg_user_id, text, entities=entities)
        return
    if text.startswith("/lottery") or text.startswith("/彩票") or text.startswith("/cp"):
        _cmd_lottery_provider()(chat_id, tg_user_id, text)
        return
    if text.startswith("/scratch") or text.startswith("/刮刮乐") or text.startswith("/ggl"):
        _cmd_scratch_provider()(chat_id, tg_user_id, text, tg_name=tg_display_name)
        return
    if text.startswith("/rob") or text.startswith("/打劫") or text.startswith("/dj"):
        _cmd_rob_provider()(chat_id, tg_user_id, text, entities=entities)
        return
    if text.startswith("/upk") or text.startswith("/用户pk") or text.startswith("/用户PK"):
        _cmd_pk_invite_provider()(chat_id, tg_user_id, text, entities=entities)
        return
    if text.startswith("/accept") or text.startswith("/接受"):
        _cmd_pk_accept_provider()(chat_id, tg_user_id, text)
        return
    if text.startswith("/reject") or text.startswith("/拒绝"):
        _cmd_pk_reject_provider()(chat_id, tg_user_id, text)
        return

    if not text.startswith("/"):
        state = _user_state_provider().get(tg_user_id)
        if state and state.get("action") == "register_name":
            del _user_state_provider()[tg_user_id]
            _do_register_provider()(chat_id, tg_user_id, text, tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name)
            return
        _send_provider()(chat_id, "💡 请从菜单中选择服务，或发送 /help 查看命令列表", reply_markup=_main_menu_keyboard_provider()(binding))
