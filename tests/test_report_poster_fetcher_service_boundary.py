import io
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


def _jpeg_bytes(color=(40, 80, 120), size=(12, 18)):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


def test_report_generator_legacy_wrapper_fetches_emby_poster_through_lazy_provider(monkeypatch):
    from app.domains.reports import report_service

    calls = []
    image_bytes = _jpeg_bytes()

    class FakeMediaApi:
        def get(self, path, params=None, timeout=None):
            calls.append((path, params, timeout))
            return FakeResponse(content=image_bytes)

    monkeypatch.setattr(report_service, "HAS_PIL", True)
    monkeypatch.setattr(report_service, "media_api", FakeMediaApi())

    poster = report_service.ReportGenerator()._fetch_emby_poster("item-1", width=20, height=30)

    assert poster.size == (20, 30)
    assert calls == [
        (
            "/Items/item-1/Images/Primary",
            {"maxHeight": 60, "maxWidth": 40, "quality": 85},
            5,
        )
    ]


def test_report_generator_get_best_poster_uses_tv_series_poster_first(monkeypatch):
    from app.domains.reports import report_service

    calls = []
    image_bytes = _jpeg_bytes(color=(120, 80, 40))

    class FakeMediaApi:
        def get(self, path, params=None, timeout=None):
            calls.append((path, params, timeout))
            if path == "/Users":
                return FakeResponse(payload=[{"Id": "user-1"}])
            if path == "/Users/user-1/Items/episode-1":
                return FakeResponse(payload={"SeriesId": "series-1"})
            return FakeResponse(content=image_bytes)

    monkeypatch.setattr(report_service, "HAS_PIL", True)
    monkeypatch.setattr(report_service, "media_api", FakeMediaApi())

    poster = report_service.ReportGenerator()._get_best_poster(
        "episode-1",
        "Show - S01E01",
        width=24,
        height=36,
        is_tv=True,
    )

    assert poster.size == (24, 36)
    assert calls == [
        ("/Users", None, 3),
        ("/Users/user-1/Items/episode-1", None, 3),
        (
            "/Items/series-1/Images/Primary",
            {"maxHeight": 72, "maxWidth": 48, "quality": 85},
            5,
        ),
    ]


def test_report_generator_get_best_poster_preserves_method_monkeypatch_chain(monkeypatch):
    from app.domains.reports import report_service

    generator = report_service.ReportGenerator()
    calls = []

    def fake_get_series_id(item_id, item_name):
        calls.append(("series", item_id, item_name))
        return "series-1"

    def fake_fetch_emby_poster(item_id, width=120, height=160):
        calls.append(("emby", item_id, width, height))
        return "series-poster"

    def fake_fetch_tmdb_poster(*args, **kwargs):
        raise AssertionError("TMDB fallback should not run when series poster exists")

    monkeypatch.setattr(generator, "_get_series_id", fake_get_series_id)
    monkeypatch.setattr(generator, "_fetch_emby_poster", fake_fetch_emby_poster)
    monkeypatch.setattr(generator, "_fetch_tmdb_poster", fake_fetch_tmdb_poster)

    poster = generator._get_best_poster("episode-1", "Show - S01E01", width=24, height=36, is_tv=True)

    assert poster == "series-poster"
    assert calls == [
        ("series", "episode-1", "Show - S01E01"),
        ("emby", "series-1", 24, 36),
    ]


def test_report_generator_tmdb_fallback_uses_tv_search_when_movie_has_no_poster(monkeypatch):
    from app.domains.reports import report_service

    calls = []
    image_bytes = _jpeg_bytes(color=(80, 120, 40))

    class FakeTmdbClient:
        api_key = "tmdb-key"

        def search_movie(self, clean_name, proxies=None, timeout=None):
            calls.append(("search_movie", clean_name, proxies, timeout))
            return FakeResponse(payload={"results": []})

        def search_tv(self, clean_name, proxies=None, timeout=None):
            calls.append(("search_tv", clean_name, proxies, timeout))
            return FakeResponse(payload={"results": [{"poster_path": "/poster.jpg"}]})

    class FakeNetworkClient:
        def get(self, url, proxies=None, timeout=None):
            calls.append(("download", url, proxies, timeout))
            return FakeResponse(content=image_bytes)

    fake_logger = SimpleNamespace(info=lambda *args, **kwargs: None, debug=lambda *args, **kwargs: None)

    monkeypatch.setattr(report_service, "HAS_PIL", True)
    monkeypatch.setattr(report_service, "tmdb_client", FakeTmdbClient())
    monkeypatch.setattr(report_service, "network_client", FakeNetworkClient())
    monkeypatch.setattr(report_service, "logger", fake_logger)

    poster = report_service.ReportGenerator()._fetch_tmdb_poster("Movie - Cut", width=28, height=42)

    assert poster.size == (28, 42)
    assert calls == [
        ("search_movie", "Movie", None, 5),
        ("search_tv", "Movie", None, 5),
        ("download", "https://image.tmdb.org/t/p/w500/poster.jpg", None, 8),
    ]


def test_report_generator_poster_fetch_returns_none_when_pil_disabled(monkeypatch):
    from app.domains.reports import report_service

    class FailMediaApi:
        def get(self, *args, **kwargs):
            raise AssertionError("media API should not be called when PIL is disabled")

    monkeypatch.setattr(report_service, "HAS_PIL", False)
    monkeypatch.setattr(report_service, "media_api", FailMediaApi())

    assert report_service.ReportGenerator()._fetch_emby_poster("item-1") is None
