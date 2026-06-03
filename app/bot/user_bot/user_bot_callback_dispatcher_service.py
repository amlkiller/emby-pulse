_rate_check_provider = lambda: (lambda tg_user_id, cooldown=3: True)
_tg_api_provider = lambda: (lambda method, data=None, token=None: None)
_check_user_restrictions_provider = lambda: (lambda tg_user_id: {"passed": True})
_format_restriction_message_provider = lambda: (lambda check_result: "")
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_edit_provider = lambda: (lambda chat_id, message_id, text, reply_markup=None: None)
_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_add_to_blacklist_provider = lambda: (lambda tg_user_id, reason="": None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_user_state_provider = lambda: {}
_cmd_register_provider = lambda: (lambda chat_id, tg_user_id, tg_name: None)
_cmd_library_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_server_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_checkin_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None, is_group=False, group_name="", user_msg_id=None: None)
_cmd_points_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None, is_group=False: None)
_cmd_profile_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_cmd_shop_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_handle_pk_accept_callback_provider = lambda: (lambda chat_id, tg_user_id, invite_id, cq_id, msg_id: None)
_handle_pk_reject_callback_provider = lambda: (lambda chat_id, tg_user_id, invite_id, cq_id, msg_id: None)
_cmd_redeem_callback_provider = lambda: (lambda chat_id, tg_user_id, item_id, cq_id: None)
_cmd_request_callback_provider = lambda: (lambda chat_id, tg_user_id, media_type, tmdb_id, cq_id: None)
_submit_request_provider = lambda: (lambda chat_id, tg_user_id, media_type, tmdb_id, season: None)
_cmd_myrequests_provider = lambda: (lambda chat_id, tg_user_id, msg_id=None: None)
_handle_scratch_provider = lambda: (lambda chat_id, tg_user_id, card_id, slot_number, tg_name="": None)


def set_dependency_providers(
    *,
    rate_check_provider=None,
    tg_api_provider=None,
    check_user_restrictions_provider=None,
    format_restriction_message_provider=None,
    send_provider=None,
    edit_provider=None,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    add_to_blacklist_provider=None,
    main_menu_keyboard_provider=None,
    user_state_provider=None,
    cmd_register_provider=None,
    cmd_library_provider=None,
    cmd_server_provider=None,
    cmd_checkin_provider=None,
    cmd_points_provider=None,
    cmd_profile_provider=None,
    cmd_shop_provider=None,
    handle_pk_accept_callback_provider=None,
    handle_pk_reject_callback_provider=None,
    cmd_redeem_callback_provider=None,
    cmd_request_callback_provider=None,
    submit_request_provider=None,
    cmd_myrequests_provider=None,
    handle_scratch_provider=None,
):
    global _rate_check_provider
    global _tg_api_provider
    global _check_user_restrictions_provider
    global _format_restriction_message_provider
    global _send_provider
    global _edit_provider
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _add_to_blacklist_provider
    global _main_menu_keyboard_provider
    global _user_state_provider
    global _cmd_register_provider
    global _cmd_library_provider
    global _cmd_server_provider
    global _cmd_checkin_provider
    global _cmd_points_provider
    global _cmd_profile_provider
    global _cmd_shop_provider
    global _handle_pk_accept_callback_provider
    global _handle_pk_reject_callback_provider
    global _cmd_redeem_callback_provider
    global _cmd_request_callback_provider
    global _submit_request_provider
    global _cmd_myrequests_provider
    global _handle_scratch_provider

    if rate_check_provider is not None:
        _rate_check_provider = rate_check_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if check_user_restrictions_provider is not None:
        _check_user_restrictions_provider = check_user_restrictions_provider
    if format_restriction_message_provider is not None:
        _format_restriction_message_provider = format_restriction_message_provider
    if send_provider is not None:
        _send_provider = send_provider
    if edit_provider is not None:
        _edit_provider = edit_provider
    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if check_emby_account_provider is not None:
        _check_emby_account_provider = check_emby_account_provider
    if unbind_user_provider is not None:
        _unbind_user_provider = unbind_user_provider
    if add_to_blacklist_provider is not None:
        _add_to_blacklist_provider = add_to_blacklist_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if user_state_provider is not None:
        _user_state_provider = user_state_provider
    if cmd_register_provider is not None:
        _cmd_register_provider = cmd_register_provider
    if cmd_library_provider is not None:
        _cmd_library_provider = cmd_library_provider
    if cmd_server_provider is not None:
        _cmd_server_provider = cmd_server_provider
    if cmd_checkin_provider is not None:
        _cmd_checkin_provider = cmd_checkin_provider
    if cmd_points_provider is not None:
        _cmd_points_provider = cmd_points_provider
    if cmd_profile_provider is not None:
        _cmd_profile_provider = cmd_profile_provider
    if cmd_shop_provider is not None:
        _cmd_shop_provider = cmd_shop_provider
    if handle_pk_accept_callback_provider is not None:
        _handle_pk_accept_callback_provider = handle_pk_accept_callback_provider
    if handle_pk_reject_callback_provider is not None:
        _handle_pk_reject_callback_provider = handle_pk_reject_callback_provider
    if cmd_redeem_callback_provider is not None:
        _cmd_redeem_callback_provider = cmd_redeem_callback_provider
    if cmd_request_callback_provider is not None:
        _cmd_request_callback_provider = cmd_request_callback_provider
    if submit_request_provider is not None:
        _submit_request_provider = submit_request_provider
    if cmd_myrequests_provider is not None:
        _cmd_myrequests_provider = cmd_myrequests_provider
    if handle_scratch_provider is not None:
        _handle_scratch_provider = handle_scratch_provider


def handle_callback(cq):
    data = cq.get("data", "")
    chat_id = str(cq["message"]["chat"]["id"])
    msg_id = cq["message"]["message_id"]
    tg_user_id = str(cq["from"]["id"])
    tg_name = cq["from"].get("first_name", "用户")
    cq_id = cq["id"]

    if not _rate_check_provider()(tg_user_id, cooldown=1):
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        return

    restriction_check = _check_user_restrictions_provider()(tg_user_id)
    if not restriction_check["passed"]:
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先关注频道/加入群聊", "show_alert": True})
        _send_provider()(chat_id, _format_restriction_message_provider()(restriction_check))
        return

    binding = _get_binding_provider()(tg_user_id)

    if data == "ub_menu_bind":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _edit_provider()(
            chat_id,
            msg_id,
            "📝 <b>绑定账号</b>\n\n请发送命令（用户名和密码用空格隔开）：\n<code>/bind 用户名 密码</code>\n\n⚠️ 密码仅用于验证身份，不会被存储",
            reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
        )
        return
    if data == "ub_menu_register":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _cmd_register_provider()(chat_id, tg_user_id, tg_name)
        return
    if data == "ub_menu_code":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _edit_provider()(
            chat_id,
            msg_id,
            "🎟️ <b>注册码激活</b>\n\n请发送命令：\n<code>/code 你的注册码</code>",
            reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
        )
        return
    if data == "ub_back_menu":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _user_state_provider().pop(tg_user_id, None)
        binding = _get_binding_provider()(tg_user_id)
        if binding:
            _edit_provider()(
                chat_id,
                msg_id,
                f"👋 欢迎回来，<b>{binding['emby_username']}</b>！\n\n🎬 EmbyPulse 用户自助服务\n请选择你需要的服务：",
                reply_markup=_main_menu_keyboard_provider()(binding),
            )
        else:
            _edit_provider()(
                chat_id,
                msg_id,
                f"👋 你好 <b>{tg_name}</b>！\n\n🎬 这是 <b>EmbyPulse</b> 用户自助服务机器人\n\n请先完成绑定或注册：",
                reply_markup=_main_menu_keyboard_provider()(None),
            )
        return
    if data == "ub_cancel_state":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "已取消"})
        _user_state_provider().pop(tg_user_id, None)
        binding = _get_binding_provider()(tg_user_id)
        _edit_provider()(chat_id, msg_id, "❌ 已取消操作", reply_markup=_main_menu_keyboard_provider()(binding))
        return

    if data == "ub_menu_library":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _cmd_library_provider()(chat_id, tg_user_id, msg_id=msg_id)
        return

    if data == "ub_menu_server":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "检测中..."})
        _cmd_server_provider()(chat_id, tg_user_id, msg_id=msg_id)
        return

    if not binding:
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先绑定账号", "show_alert": True})
        return

    if not _check_emby_account_provider()(binding):
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _unbind_user_provider()(tg_user_id)
        _edit_provider()(chat_id, msg_id, "⚠️ 你的 Emby 账号已被管理员删除，绑定已自动解除。", reply_markup=_main_menu_keyboard_provider()(None))
        return

    if data == "ub_menu_checkin":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "签到中..."})
        _cmd_checkin_provider()(chat_id, tg_user_id, msg_id=msg_id)
    elif data == "ub_menu_points":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _cmd_points_provider()(chat_id, tg_user_id, msg_id=msg_id)
    elif data == "ub_menu_profile":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _cmd_profile_provider()(chat_id, tg_user_id, msg_id=msg_id)
    elif data == "ub_menu_shop":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _cmd_shop_provider()(chat_id, tg_user_id, msg_id=msg_id)
    elif data == "ub_menu_request":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _edit_provider()(
            chat_id,
            msg_id,
            "🎬 <b>求片功能</b>\n\n请发送命令：\n<code>/request 影视名称</code>\n\n例如：<code>/request 沙丘</code>",
            reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
        )
    elif data == "ub_menu_password":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _edit_provider()(
            chat_id,
            msg_id,
            "🔐 <b>修改密码</b>\n\n请发送命令（当前密码和新密码用空格隔开）：\n<code>/password 当前密码 新密码</code>\n\n例如：<code>/password 当前密码 NewPass1</code>\n\n⚠️ 新密码至少 8 位，需包含小写字母 + 大写字母或数字",
            reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
        )
    elif data == "ub_menu_renew":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _edit_provider()(
            chat_id,
            msg_id,
            "🎟️ <b>续期功能</b>\n\n请发送命令：\n<code>/renew 你的续期码</code>",
            reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
        )
    elif data == "ub_menu_unbind":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _edit_provider()(
            chat_id,
            msg_id,
            f"🔓 <b>确认解绑？</b>\n\n当前绑定：<b>{binding['emby_username']}</b>\n\n解绑后将无法使用签到、商城等功能。",
            reply_markup={"inline_keyboard": [[{"text": "✅ 确认解绑", "callback_data": "ub_unbind_confirm"}, {"text": "❌ 取消", "callback_data": "ub_back_menu"}]]},
        )
    elif data == "ub_unbind_confirm":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "已解绑"})
        _unbind_user_provider()(tg_user_id)
        _add_to_blacklist_provider()(tg_user_id, "用户主动解绑")
        _edit_provider()(chat_id, msg_id, "✅ 已成功解绑账号。\n\n如需重新使用，请联系管理员或使用注册码注册。", reply_markup=_main_menu_keyboard_provider()(None))
    elif data.startswith("pk_accept:"):
        invite_id = data.split(":")[1]
        _handle_pk_accept_callback_provider()(chat_id, tg_user_id, invite_id, cq_id, msg_id)
    elif data.startswith("pk_reject:"):
        invite_id = data.split(":")[1]
        _handle_pk_reject_callback_provider()(chat_id, tg_user_id, invite_id, cq_id, msg_id)
    elif data.startswith("ub_redeem_"):
        item_id = data.replace("ub_redeem_", "")
        _cmd_redeem_callback_provider()(chat_id, tg_user_id, item_id, cq_id)
    elif data.startswith("ub_req_"):
        parts = data.split("_")
        if len(parts) >= 4:
            media_type = parts[2]
            tmdb_id = parts[3]
            _cmd_request_callback_provider()(chat_id, tg_user_id, media_type, tmdb_id, cq_id)
    elif data.startswith("ub_reqsn_"):
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "提交中..."})
        parts = data.split("_")
        if len(parts) >= 4:
            try:
                tmdb_id = parts[2]
                season = int(parts[3])
                if season > 0:
                    _submit_request_provider()(chat_id, tg_user_id, "tv", tmdb_id, season)
                else:
                    _send_provider()(chat_id, "❌ 无效的季数选择")
            except (ValueError, IndexError):
                _send_provider()(chat_id, "❌ 求片参数错误，请重新选择")
    elif data == "ub_menu_myrequests":
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        _cmd_myrequests_provider()(chat_id, tg_user_id, msg_id=msg_id)
    elif data.startswith("scratch_"):
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
        parts = data.split("_")
        if len(parts) >= 3:
            if parts[1] == "done":
                _send_provider()(chat_id, "❌ 这个格子已经被刮过了")
            else:
                card_id = int(parts[1])
                slot_number = int(parts[2])
                _handle_scratch_provider()(chat_id, tg_user_id, card_id, slot_number, tg_name)
    else:
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
