import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def get(self, path, params=None, timeout=None):
        self.calls.append((path, params, timeout))
        if self.error:
            raise self.error
        if not self.responses:
            raise AssertionError(f"Unexpected media_api.get call: {path}")
        return self.responses.pop(0)


def _capture_bot():
    bot = bot_service.NotificationBot()
    sent_messages = []
    sent_photos = []
    image_calls = []

    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent_messages.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    bot.send_photo = lambda chat_id, photo, caption="", parse_mode="HTML", reply_markup=None, platform="all", wecom_photo_io=None: sent_photos.append(
        (chat_id, photo, caption, parse_mode, reply_markup, platform, wecom_photo_io)
    )

    def fake_download(item_id, img_type="Primary", image_tag=None):
        image_calls.append((item_id, img_type, image_tag))
        return {"Primary": None, "Backdrop": "backdrop-io"}.get(img_type)

    bot._download_emby_image = fake_download
    return bot, sent_messages, sent_photos, image_calls


def _search_params(keyword):
    return {
        "SearchTerm": keyword,
        "IncludeItemTypes": "Movie,Series",
        "Recursive": "true",
        "Fields": "ProductionYear,Type,Id",
        "Limit": 5,
    }


def test_extract_tech_info_legacy_wrapper_formats_video_details():
    bot = bot_service.NotificationBot()
    item = {
        "MediaSources": [
            {
                "Bitrate": 42_500_000,
                "MediaStreams": [
                    {
                        "Type": "Video",
                        "Width": 3840,
                        "VideoRange": "HDR10",
                        "DisplayTitle": "4K HEVC DOVI",
                    }
                ],
            }
        ]
    }

    assert bot._extract_tech_info(item) == "4K HDR DoVi | 42.5Mbps"
    assert bot._extract_tech_info({}) == "📼 未知"


def test_search_command_requires_keyword(monkeypatch):
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    bot, sent_messages, sent_photos, image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search", "tg")

    assert sent_messages == [("chat-1", "🔍 请使用: /search 关键词", "HTML", None, "tg")]
    assert sent_photos == []
    assert image_calls == []


def test_search_command_missing_admin_id(monkeypatch):
    media = FakeMediaApi()
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: None)
    bot, sent_messages, sent_photos, _image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search Alien", "wecom")

    assert media.calls == []
    assert sent_messages == [("chat-1", "❌ 错误: 无法获取 Emby 用户身份", "HTML", None, "wecom")]
    assert sent_photos == []


def test_search_command_non_200_and_empty_results(monkeypatch):
    media = FakeMediaApi(responses=[FakeResponse(status_code=500)])
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    bot, sent_messages, _sent_photos, _image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search Alien", "tg")

    assert media.calls == [("/Users/admin-1/Items", _search_params("Alien"), 10)]
    assert sent_messages == [("chat-1", "❌ 搜索失败", "HTML", None, "tg")]

    media = FakeMediaApi(responses=[FakeResponse(payload={"Items": []})])
    monkeypatch.setattr(bot_service, "media_api", media)
    bot, sent_messages, _sent_photos, _image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search Alien", "tg")

    assert media.calls == [("/Users/admin-1/Items", _search_params("Alien"), 10)]
    assert sent_messages == [("chat-1", "📭 未找到与 <b>Alien</b> 相关的资源", "HTML", None, "tg")]


def test_search_command_formats_movie_with_keyboard_and_image_fallback(monkeypatch):
    search_payload = {
        "Items": [
            {"Id": "m1", "Name": "Movie One", "Type": "Movie", "ProductionYear": 2026, "ServerId": "srv-1"},
            {"Id": "s2", "Name": "Series Two", "Type": "Series", "ProductionYear": 2025},
        ]
    }
    detail_payload = {
        "Name": "Movie One",
        "ProductionYear": 2026,
        "CommunityRating": 8.7,
        "Genres": ["科幻", "动作", "冒险", "忽略"],
        "Overview": "<p>这是一段剧情简介，包含 HTML。</p>",
        "MediaSources": [{"Bitrate": 12_000_000, "MediaStreams": [{"Type": "Video", "Width": 1920}]}],
    }
    media = FakeMediaApi(responses=[FakeResponse(payload=search_payload), FakeResponse(payload=detail_payload)])
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "emby.example")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "http://fallback.example")
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "cover-url")
    bot, sent_messages, sent_photos, image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search Movie", "tg")

    assert media.calls == [
        ("/Users/admin-1/Items", _search_params("Movie"), 10),
        ("/Users/admin-1/Items/m1", {"Fields": "Overview,CommunityRating,Genres,MediaSources"}, 8),
    ]
    assert image_calls == [("m1", "Primary", None), ("m1", "Backdrop", None)]
    assert sent_messages == []
    assert sent_photos == [
        (
            "chat-1",
            "backdrop-io",
            (
                "🎬 <b>Movie One</b> (2026)\n"
                "⭐️ 8.7  |  🎭 科幻 / 动作 / 冒险\n"
                "💿 1080P | 12.0Mbps\n\n"
                "📝 <b>剧情简介：</b>\n"
                "这是一段剧情简介，包含 HTML。\n"
                "\n🔎 <b>其他结果：</b>\n"
                "📺 Series Two (2025)"
            ),
            "HTML",
            {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": "https://emby.example/web/index.html#!/item?id=m1&serverId=srv-1"}]]},
            "tg",
            "backdrop-io",
        )
    ]


def test_search_command_formats_series_with_sample_tech_info(monkeypatch):
    search_payload = {"Items": [{"Id": "series-1", "Name": "Series One", "Type": "Series", "ServerId": "srv-1"}]}
    detail_payload = {
        "Name": "Series One",
        "CommunityRating": "N/A",
        "Genres": [],
        "Overview": "",
        "RecursiveItemCount": 12,
    }
    sample_payload = {
        "Items": [
            {
                "MediaSources": [
                    {"Bitrate": 5_500_000, "MediaStreams": [{"Type": "Video", "Width": 1280, "DisplayTitle": "720p"}]}
                ]
            }
        ]
    }
    media = FakeMediaApi(
        responses=[FakeResponse(payload=search_payload), FakeResponse(payload=detail_payload), FakeResponse(payload=sample_payload)]
    )
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "")
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "cover-url")
    bot, sent_messages, sent_photos, image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search Series", "wecom")

    assert media.calls == [
        ("/Users/admin-1/Items", _search_params("Series"), 10),
        ("/Users/admin-1/Items/series-1", {"Fields": "Overview,CommunityRating,Genres,RecursiveItemCount"}, 5),
        (
            "/Users/admin-1/Items",
            {"ParentId": "series-1", "Recursive": "true", "IncludeItemTypes": "Episode", "Limit": 1, "Fields": "MediaSources"},
            5,
        ),
    ]
    assert image_calls == [("series-1", "Primary", None), ("series-1", "Backdrop", None)]
    assert sent_messages == []
    assert sent_photos == [
        (
            "chat-1",
            "backdrop-io",
            (
                "📺 <b>Series One</b> \n"
                "⭐️ N/A  |  🎭 未分类\n"
                "💿 📊 共 12 集 | 720P | 5.5Mbps\n\n"
                "📝 <b>剧情简介：</b>\n"
                "暂无简介"
            ),
            "HTML",
            None,
            "wecom",
            "backdrop-io",
        )
    ]


def test_search_command_exception_fallback(monkeypatch):
    media = FakeMediaApi(error=RuntimeError("media down"))
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    bot, sent_messages, sent_photos, _image_calls = _capture_bot()

    bot._cmd_search("chat-1", "/search Alien", "tg")

    assert media.calls == [("/Users/admin-1/Items", _search_params("Alien"), 10)]
    assert sent_messages == [("chat-1", "❌ 搜索时发生错误", "HTML", None, "tg")]
    assert sent_photos == []
