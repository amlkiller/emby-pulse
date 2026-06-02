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


def test_playback_data_mode_defaults_to_sqlite_for_empty_or_invalid_values(monkeypatch):
    from app.infra.config import db_settings

    for value in (None, "", "  ", "mysql", 0):
        monkeypatch.setattr(db_settings, "cfg", FakeCfg({"playback_data_mode": value}))

        assert db_settings.get_playback_data_mode() == "sqlite"


def test_playback_data_mode_normalizes_supported_values(monkeypatch):
    from app.infra.config import db_settings

    for value, expected in (
        ("sqlite", "sqlite"),
        (" SQLITE ", "sqlite"),
        ("api", "api"),
        (" API ", "api"),
    ):
        monkeypatch.setattr(db_settings, "cfg", FakeCfg({"playback_data_mode": value}))

        assert db_settings.get_playback_data_mode() == expected


def test_set_playback_data_mode_persists_canonical_value(monkeypatch):
    from app.infra.config import db_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(db_settings, "cfg", fake_cfg)

    db_settings.set_playback_data_mode(" API ")
    db_settings.set_playback_data_mode("unsupported")

    assert fake_cfg.set_calls == [
        ("playback_data_mode", "api"),
        ("playback_data_mode", "sqlite"),
    ]


def test_slow_query_ms_defaults_for_empty_invalid_or_boolean_values(monkeypatch):
    from app.infra.config import db_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(db_settings, "cfg", FakeCfg({"slow_query_ms": value}))

        assert db_settings.get_slow_query_ms() == 800


def test_slow_query_ms_clamps_to_positive_integer(monkeypatch):
    from app.infra.config import db_settings

    for value, expected in (("250", 250), (250, 250), (1, 1)):
        monkeypatch.setattr(db_settings, "cfg", FakeCfg({"slow_query_ms": value}))

        assert db_settings.get_slow_query_ms() == expected

    for value in ("0", 0, "-25", -25):
        monkeypatch.setattr(db_settings, "cfg", FakeCfg({"slow_query_ms": value}))

        assert db_settings.get_slow_query_ms() == 1
