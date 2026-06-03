import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []

    def info(self, message):
        self.infos.append(message)


def _message(
    text,
    *,
    chat_id=10,
    chat_type="private",
    message_id=20,
    from_user=None,
    chat_extra=None,
    sender_chat=None,
    new_chat_members=None,
    entities=None,
):
    msg = {
        "text": text,
        "chat": {"id": chat_id, "type": chat_type, **(chat_extra or {})},
        "message_id": message_id,
        "entities": entities or [],
    }
    if from_user is not None:
        msg["from"] = from_user
    if sender_chat is not None:
        msg["sender_chat"] = sender_chat
    if new_chat_members is not None:
        msg["new_chat_members"] = new_chat_members
    return msg


def _user(tg_user_id="tg1", first_name="Alice", last_name="", username="alice"):
    return {
        "id": tg_user_id,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
    }


def _reset_message_dispatcher_state(monkeypatch, *, binding=None):
    from app.bot.user_bot import user_bot_message_dispatcher_service
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    calls = []
    sent = []
    cleanup = []
    user_state = {}
    logger = FakeLogger()

    monkeypatch.setattr(user_bot_service, "logger", logger)
    monkeypatch.setattr(user_bot_service, "_get_channel_binding", lambda channel_id: None)
    monkeypatch.setattr(
        user_bot_service,
        "_send",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)),
    )
    monkeypatch.setattr(user_bot_service, "_rate_check", lambda tg_user_id, cooldown=3: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_group_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "")
    monkeypatch.setattr(user_bot_service, "get_user_bot_group_commands", lambda: "")
    monkeypatch.setattr(
        user_bot_service,
        "_delete_messages_later",
        lambda chat_id, message_ids, delay_seconds=30: cleanup.append((chat_id, message_ids, delay_seconds)),
    )
    monkeypatch.setattr(
        user_bot_service,
        "_get_binding",
        lambda tg_user_id: binding,
    )
    monkeypatch.setattr(user_bot_service, "_check_user_restrictions", lambda tg_user_id: {"passed": True})
    monkeypatch.setattr(user_bot_service, "_format_restriction_message", lambda result: "restriction text")
    monkeypatch.setattr(user_bot_service, "_user_state", user_state)
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding=None: {"binding": binding})
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda binding: True)
    monkeypatch.setattr(user_bot_service, "_unbind_user", lambda tg_user_id: calls.append(("unbind", tg_user_id)))
    monkeypatch.setattr(
        user_bot_service,
        "_do_register",
        lambda chat_id, tg_user_id, custom_name, tg_username="", tg_display_name="": calls.append(
            ("register", chat_id, tg_user_id, custom_name, tg_username, tg_display_name)
        ),
    )
    monkeypatch.setattr(
        user_bot_service,
        "_do_code_register",
        lambda chat_id, tg_user_id, custom_name, code, days, tpl_id, routes=None, route_mode=None, tg_username="", tg_display_name="": calls.append(
            ("code_register", chat_id, tg_user_id, custom_name, code, days, tpl_id, routes, route_mode, tg_username, tg_display_name)
        ),
    )
    monkeypatch.setattr(
        user_bot_service,
        "cmd_points",
        lambda chat_id, tg_user_id, msg_id=None, is_group=False: calls.append(("points", chat_id, tg_user_id, msg_id, is_group))
        or {"result": {"message_id": 99}},
    )
    monkeypatch.setattr(
        user_bot_service,
        "cmd_server",
        lambda chat_id, tg_user_id, msg_id=None: calls.append(("server", chat_id, tg_user_id, msg_id)),
    )

    monkeypatch.setattr(user_bot_message_dispatcher_service, "_logger_provider", lambda: user_bot_service.logger)
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_get_channel_binding_provider",
        lambda: user_bot_service._get_channel_binding,
    )
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_send_provider", lambda: user_bot_service._send)
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_rate_check_provider", lambda: user_bot_service._rate_check)
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_group_enabled_provider",
        lambda: user_bot_service.get_user_bot_group_enabled,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_allowed_groups_provider",
        lambda: user_bot_service.get_user_bot_allowed_groups,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_group_commands_provider",
        lambda: user_bot_service.get_user_bot_group_commands,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_delete_messages_later_provider",
        lambda: user_bot_service._delete_messages_later,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_get_binding_provider",
        lambda: user_bot_service._get_binding,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_check_user_restrictions_provider",
        lambda: user_bot_service._check_user_restrictions,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_format_restriction_message_provider",
        lambda: user_bot_service._format_restriction_message,
    )
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_user_state_provider", lambda: user_bot_service._user_state)
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_main_menu_keyboard_provider",
        lambda: user_bot_service._main_menu_keyboard,
    )
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_check_emby_account_provider",
        lambda: user_bot_service._check_emby_account,
    )
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_unbind_user_provider", lambda: user_bot_service._unbind_user)
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_do_register_provider", lambda: user_bot_service._do_register)
    monkeypatch.setattr(
        user_bot_message_dispatcher_service,
        "_do_code_register_provider",
        lambda: user_bot_service._do_code_register,
    )
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_cmd_points_provider", lambda: user_bot_service.cmd_points)
    monkeypatch.setattr(user_bot_message_dispatcher_service, "_cmd_server_provider", lambda: user_bot_service.cmd_server)

    return user_bot_service, sent, cleanup, calls, user_state, logger


def test_message_dispatcher_preserves_group_points_cleanup_through_legacy_wrappers(monkeypatch):
    user_bot_service, sent, cleanup, calls, _user_state, _logger = _reset_message_dispatcher_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "10")
    monkeypatch.setattr(user_bot_service, "get_user_bot_group_commands", lambda: "points")

    user_bot_service.user_bot._on_message(
        _message(
            "/points",
            chat_type="supergroup",
            chat_extra={"title": "Group"},
            from_user=_user(),
        )
    )

    assert calls == [("points", "10", "tg1", None, True)]
    assert cleanup == [("10", [99, 20], 30)]
    assert sent == []


def test_message_dispatcher_preserves_unbound_register_name_state(monkeypatch):
    user_bot_service, sent, cleanup, calls, user_state, _logger = _reset_message_dispatcher_state(monkeypatch)
    user_state["tg1"] = {"action": "register_name"}

    user_bot_service.user_bot._on_message(
        _message(
            "NewUser",
            from_user=_user(first_name="Alice", last_name="Lee", username="alice_lee"),
        )
    )

    assert user_state == {}
    assert calls == [("register", "10", "tg1", "NewUser", "alice_lee", "Alice Lee")]
    assert sent == []
    assert cleanup == []


def test_message_dispatcher_preserves_bound_private_server_command(monkeypatch):
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}
    user_bot_service, sent, cleanup, calls, _user_state, _logger = _reset_message_dispatcher_state(
        monkeypatch,
        binding=binding,
    )

    user_bot_service.user_bot._on_message(_message("/server", from_user=_user()))

    assert calls == [("server", "10", "tg1", None)]
    assert sent == []
    assert cleanup == []


def test_message_dispatcher_preserves_unbound_channel_identity_notice(monkeypatch):
    user_bot_service, sent, cleanup, calls, _user_state, _logger = _reset_message_dispatcher_state(monkeypatch)

    user_bot_service.user_bot._on_message(
        _message(
            "/points",
            chat_type="supergroup",
            from_user=None,
            sender_chat={"id": -100, "title": "Channel A"},
        )
    )

    assert calls == []
    assert cleanup == []
    assert len(sent) == 1
    assert sent[0][0] == "10"
    assert "Channel A" in sent[0][1]
    assert "/bind_channel -100" in sent[0][1]
