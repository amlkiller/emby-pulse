import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeCfg:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_report_top_query_limit_defaults_for_empty_invalid_or_boolean_values(monkeypatch):
    from app.infra.config import report_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(report_settings, "cfg", FakeCfg({"report_top_query_limit": value}))

        assert report_settings.get_report_top_query_limit() == 300


def test_report_top_query_limit_clamps_to_positive_integer(monkeypatch):
    from app.infra.config import report_settings

    for value, expected in (("500", 500), (500, 500), (1, 1)):
        monkeypatch.setattr(report_settings, "cfg", FakeCfg({"report_top_query_limit": value}))

        assert report_settings.get_report_top_query_limit() == expected

    for value in ("0", 0, "-25", -25):
        monkeypatch.setattr(report_settings, "cfg", FakeCfg({"report_top_query_limit": value}))

        assert report_settings.get_report_top_query_limit() == 1


def test_dashboard_cache_ttl_defaults_for_empty_invalid_or_boolean_values(monkeypatch):
    from app.infra.config import stats_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(stats_settings, "cfg", FakeCfg({"dashboard_cache_ttl": value}))

        assert stats_settings.get_dashboard_cache_ttl() == 300


def test_dashboard_cache_ttl_clamps_to_positive_integer(monkeypatch):
    from app.infra.config import stats_settings

    for value, expected in (("600", 600), (600, 600), (1, 1)):
        monkeypatch.setattr(stats_settings, "cfg", FakeCfg({"dashboard_cache_ttl": value}))

        assert stats_settings.get_dashboard_cache_ttl() == expected

    for value in ("0", 0, "-25", -25):
        monkeypatch.setattr(stats_settings, "cfg", FakeCfg({"dashboard_cache_ttl": value}))

        assert stats_settings.get_dashboard_cache_ttl() == 1
