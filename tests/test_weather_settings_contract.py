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


def test_weather_source_defaults_for_empty_invalid_or_boolean_values(monkeypatch):
    from app.infra.config import weather_settings

    for value in (None, "", "  ", "openweather", 0, True, False):
        monkeypatch.setattr(weather_settings, "cfg", FakeCfg({"weather_source": value}))

        assert weather_settings.get_weather_source() == "wttr"


def test_weather_source_normalizes_supported_values(monkeypatch):
    from app.infra.config import weather_settings

    for value, expected in (
        ("wttr", "wttr"),
        (" WTTR ", "wttr"),
        ("qweather", "qweather"),
        (" QWeather ", "qweather"),
        ("amap", "amap"),
        (" AMAP ", "amap"),
    ):
        monkeypatch.setattr(weather_settings, "cfg", FakeCfg({"weather_source": value}))

        assert weather_settings.get_weather_source() == expected


def test_set_weather_source_persists_canonical_value(monkeypatch):
    from app.infra.config import weather_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(weather_settings, "cfg", fake_cfg)

    weather_settings.set_weather_source(" QWeather ")
    weather_settings.set_weather_source("AMAP")
    weather_settings.set_weather_source("unsupported")
    weather_settings.set_weather_source(True)

    assert fake_cfg.set_calls == [
        ("weather_source", "qweather"),
        ("weather_source", "amap"),
        ("weather_source", "wttr"),
        ("weather_source", "wttr"),
    ]


def test_weather_qweather_host_preserves_runtime_and_raw_contract(monkeypatch):
    from app.infra.config import weather_settings

    fake_cfg = FakeCfg({"weather_qweather_host": " https://devapi.qweather.com/ "})
    monkeypatch.setattr(weather_settings, "cfg", fake_cfg)

    assert weather_settings.get_weather_qweather_host() == "https://devapi.qweather.com"
    assert weather_settings.get_weather_qweather_host_raw() == " https://devapi.qweather.com/ "
