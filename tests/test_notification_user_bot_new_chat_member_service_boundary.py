import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _patch_dependencies(monkeypatch, *, token="12345:token", welcome_msg=""):
    from app.domains.notifications import user_bot_service

    sent = []
    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: token)
    monkeypatch.setattr(user_bot_service, "get_user_bot_welcome_msg", lambda: welcome_msg)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    return sent


def test_new_chat_member_service_sends_custom_welcome_for_matching_bot(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = _patch_dependencies(monkeypatch, welcome_msg="custom hello")
    bot = user_bot_service.UserBot()

    bot._on_new_chat_members("chat-1", [{"is_bot": True, "id": "12345"}], "Group A")

    assert sent == [("chat-1", "custom hello", None)]


def test_new_chat_member_service_sends_default_welcome_when_custom_empty(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = _patch_dependencies(monkeypatch, welcome_msg="")
    bot = user_bot_service.UserBot()

    bot._on_new_chat_members("chat-2", [{"is_bot": True, "id": 12345}], "Group B")

    assert sent == [
        (
            "chat-2",
            "👋 你好！我是 EmbyPulse 用户机器人，已加入 <b>Group B</b>\n\n"
            "✅ 发送 /checkin 或 /签到 获取积分\n"
            "✅ 发送 /help 查看群内可用指令\n\n"
            "💡 更多功能请私聊机器人使用",
            None,
        )
    ]


def test_new_chat_member_service_ignores_non_matching_members(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = _patch_dependencies(monkeypatch, welcome_msg="custom hello")
    bot = user_bot_service.UserBot()

    bot._on_new_chat_members(
        "chat-3",
        [
            {"is_bot": False, "id": "12345"},
            {"is_bot": True, "id": "99999"},
        ],
        "Group C",
    )

    assert sent == []


def test_new_chat_member_service_stops_after_first_matching_bot(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = _patch_dependencies(monkeypatch, token="12345", welcome_msg="custom hello")
    bot = user_bot_service.UserBot()

    bot._on_new_chat_members(
        "chat-4",
        [
            {"is_bot": True, "id": ""},
            {"is_bot": True, "id": ""},
        ],
        "Group D",
    )

    assert sent == [("chat-4", "custom hello", None)]
