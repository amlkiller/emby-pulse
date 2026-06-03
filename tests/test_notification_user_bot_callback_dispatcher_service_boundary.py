import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _callback(data):
    return {
        "id": "cq-1",
        "data": data,
        "message": {"chat": {"id": 10}, "message_id": 20},
        "from": {"id": "tg1", "first_name": "Alice"},
    }


def _reset_dispatcher_state(monkeypatch, binding=None):
    from app.bot.user_bot import user_bot_service

    tg_calls = []
    edits = []
    sent = []
    command_calls = []
    user_state = {"tg1": {"action": "register_name"}}

    monkeypatch.setattr(user_bot_service, "_rate_check", lambda tg_user_id, cooldown=3: True)
    monkeypatch.setattr(user_bot_service, "_check_user_restrictions", lambda tg_user_id: {"passed": True})
    monkeypatch.setattr(user_bot_service, "_format_restriction_message", lambda result: "restriction text")
    monkeypatch.setattr(user_bot_service, "_tg_api", lambda method, data=None, token=None: tg_calls.append((method, data, token)))
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_edit", lambda chat_id, msg_id, text, reply_markup=None: edits.append((chat_id, msg_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda binding: True)
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding=None: {"binding": binding})
    monkeypatch.setattr(user_bot_service, "_user_state", user_state)
    monkeypatch.setattr(user_bot_service, "cmd_checkin", lambda chat_id, tg_user_id, msg_id=None, **kwargs: command_calls.append(("checkin", chat_id, tg_user_id, msg_id, kwargs)))
    monkeypatch.setattr(user_bot_service, "_submit_request", lambda chat_id, tg_user_id, media_type, tmdb_id, season: command_calls.append(("submit_request", chat_id, tg_user_id, media_type, tmdb_id, season)))
    monkeypatch.setattr(user_bot_service, "_handle_scratch", lambda chat_id, tg_user_id, card_id, slot_number, tg_name="": command_calls.append(("scratch", chat_id, tg_user_id, card_id, slot_number, tg_name)))

    return user_bot_service, tg_calls, edits, sent, command_calls, user_state


def test_callback_dispatcher_preserves_unbound_back_menu_and_state_clear(monkeypatch):
    from app.bot.user_bot import user_bot_callback_dispatcher_service

    _user_bot_service, tg_calls, edits, sent, command_calls, user_state = _reset_dispatcher_state(monkeypatch)

    user_bot_callback_dispatcher_service.handle_callback(_callback("ub_back_menu"))

    assert user_state == {}
    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq-1"}, None)]
    assert edits == [(
        "10",
        20,
        "👋 你好 <b>Alice</b>！\n\n🎬 这是 <b>EmbyPulse</b> 用户自助服务机器人\n\n请先完成绑定或注册：",
        {"binding": None},
    )]
    assert sent == []
    assert command_calls == []


def test_callback_dispatcher_preserves_bound_checkin_button(monkeypatch):
    from app.bot.user_bot import user_bot_callback_dispatcher_service

    binding = {"emby_user_id": "u1", "emby_username": "Alice"}
    _user_bot_service, tg_calls, edits, sent, command_calls, _user_state = _reset_dispatcher_state(monkeypatch, binding=binding)

    user_bot_callback_dispatcher_service.handle_callback(_callback("ub_menu_checkin"))

    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "签到中..."}, None)]
    assert command_calls == [("checkin", "10", "tg1", 20, {})]
    assert edits == []
    assert sent == []


def test_callback_dispatcher_preserves_pattern_callbacks(monkeypatch):
    from app.bot.user_bot import user_bot_callback_dispatcher_service

    binding = {"emby_user_id": "u1", "emby_username": "Alice"}
    _user_bot_service, tg_calls, _edits, sent, command_calls, _user_state = _reset_dispatcher_state(monkeypatch, binding=binding)

    user_bot_callback_dispatcher_service.handle_callback(_callback("ub_reqsn_123_2"))
    user_bot_callback_dispatcher_service.handle_callback(_callback("scratch_77_3"))
    user_bot_callback_dispatcher_service.handle_callback(_callback("scratch_done_77_3"))

    assert tg_calls == [
        ("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "提交中..."}, None),
        ("answerCallbackQuery", {"callback_query_id": "cq-1"}, None),
        ("answerCallbackQuery", {"callback_query_id": "cq-1"}, None),
    ]
    assert command_calls == [
        ("submit_request", "10", "tg1", "tv", "123", 2),
        ("scratch", "10", "tg1", 77, 3, "Alice"),
    ]
    assert sent == [("10", "❌ 这个格子已经被刮过了", None)]
