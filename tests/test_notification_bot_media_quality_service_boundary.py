from app.domains.notifications import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


def test_get_admin_id_prefers_admin_user(monkeypatch):
    class FakeMediaApi:
        def get(self, path, **kwargs):
            assert path == "/Users"
            return FakeResponse(
                payload=[
                    {"Id": "user-1", "Policy": {"IsAdministrator": False}},
                    {"Id": "admin-1", "Policy": {"IsAdministrator": True}},
                ],
            )

    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi())

    assert bot_service.get_admin_id() == "admin-1"


def test_get_admin_id_falls_back_to_first_user_and_handles_failure(monkeypatch):
    class FakeMediaApi:
        def __init__(self, response):
            self.response = response

        def get(self, path, **kwargs):
            assert path == "/Users"
            return self.response

    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi(FakeResponse(payload=[{"Id": "user-1"}])))
    assert bot_service.get_admin_id() == "user-1"

    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi(FakeResponse(status_code=500, payload=[])))
    assert bot_service.get_admin_id() is None


def test_get_media_quality_info_parses_filename_first(monkeypatch):
    class FakeMediaApi:
        def get(self, path, **kwargs):
            assert path == "/Users/admin/Items/item-1"
            return FakeResponse(
                payload={
                    "MediaSources": [
                        {
                            "Path": "/movies/Movie.2026.REMUX.2160p.HDR10+.HEVC.DTS-HD.MA.mkv",
                        }
                    ]
                }
            )

    fake_logger = FakeLogger()
    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi())
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin")

    result = bot_service.get_media_quality_info("item-1")

    assert result == {
        "quality": "REMUX 4K HDR10+",
        "video_codec": "HEVC",
        "audio_codec": "DTS-HD MA",
        "resolution": "3840×2160",
        "hdr": "HDR10+",
        "quality_icon": "✨",
    }
    assert fake_logger.infos


def test_get_media_quality_info_uses_stream_fallback_and_legacy_monkeypatch(monkeypatch):
    class FakeMediaApi:
        def get(self, path, **kwargs):
            assert path == "/Users/admin/Items/item-1"
            return FakeResponse(
                payload={
                    "MediaStreams": [
                        {
                            "Type": "Video",
                            "Width": 1920,
                            "Height": 1080,
                            "BitRate": 8000000,
                            "Codec": "hevc",
                            "ColorTransfer": "arib-std-b67",
                        },
                        {
                            "Type": "Audio",
                            "Codec": "eac3",
                            "Channels": 6,
                        },
                    ]
                }
            )

    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi())
    monkeypatch.setattr(bot_service, "logger", FakeLogger())
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin")

    result = bot_service.get_media_quality_info("item-1")

    assert result["quality"] == "1080p HLG"
    assert result["resolution"] == "1920×1080"
    assert result["hdr"] == "HLG"
    assert result["video_codec"] == "HEVC"
    assert result["audio_codec"] == "E-AC3 5.1"
    assert result["quality_icon"] == "✨"


def test_get_media_quality_info_returns_empty_without_admin_or_item(monkeypatch):
    fake_logger = FakeLogger()

    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: None)

    assert bot_service.get_media_quality_info("item-1") == {
        "quality": "",
        "video_codec": "",
        "audio_codec": "",
        "resolution": "",
        "hdr": "",
        "quality_icon": "",
    }
    assert fake_logger.warnings == []

    class FakeMediaApi:
        def get(self, path, **kwargs):
            return FakeResponse(status_code=404, payload={})

    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi())
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin")

    assert bot_service.get_media_quality_info("item-1") == {
        "quality": "",
        "video_codec": "",
        "audio_codec": "",
        "resolution": "",
        "hdr": "",
        "quality_icon": "",
    }
    assert fake_logger.warnings == ["[媒体质量] 获取 item item-1 失败"]
