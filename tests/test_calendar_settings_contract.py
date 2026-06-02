import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeCfg:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.set_calls = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.set_calls.append((key, value))
        self.values[key] = value


def test_calendar_cache_ttl_defaults_for_empty_invalid_or_boolean_values(monkeypatch):
    from app.infra.config import calendar_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(calendar_settings, "cfg", FakeCfg({"calendar_cache_ttl": value}))

        assert calendar_settings.get_calendar_cache_ttl() == 86400


def test_calendar_cache_ttl_clamps_to_positive_integer(monkeypatch):
    from app.infra.config import calendar_settings

    for value, expected in (("1800", 1800), (1800, 1800), (1, 1)):
        monkeypatch.setattr(calendar_settings, "cfg", FakeCfg({"calendar_cache_ttl": value}))

        assert calendar_settings.get_calendar_cache_ttl() == expected

    for value in ("0", 0, "-25", -25):
        monkeypatch.setattr(calendar_settings, "cfg", FakeCfg({"calendar_cache_ttl": value}))

        assert calendar_settings.get_calendar_cache_ttl() == 1


def test_set_calendar_cache_ttl_persists_normalized_value(monkeypatch):
    from app.infra.config import calendar_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(calendar_settings, "cfg", fake_cfg)

    calendar_settings.set_calendar_cache_ttl("1800")
    calendar_settings.set_calendar_cache_ttl(0)
    calendar_settings.set_calendar_cache_ttl(True)
    calendar_settings.set_calendar_cache_ttl("not-a-number")

    assert fake_cfg.set_calls == [
        ("calendar_cache_ttl", 1800),
        ("calendar_cache_ttl", 1),
        ("calendar_cache_ttl", 86400),
        ("calendar_cache_ttl", 86400),
    ]


def test_calendar_public_url_preserves_existing_fallback_order(monkeypatch):
    from app.infra.config import calendar_settings

    monkeypatch.setattr(
        calendar_settings,
        "cfg",
        FakeCfg({
            "emby_public_url": "",
            "emby_public_host": "https://public.example",
            "emby_host": "http://internal.example",
        }),
    )

    assert calendar_settings.get_calendar_public_url() == "https://public.example"
