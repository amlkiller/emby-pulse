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


def test_image_proxy_max_bytes_defaults_for_empty_invalid_or_boolean_values(monkeypatch):
    from app.infra.config import image_proxy_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(image_proxy_settings, "cfg", FakeCfg({"image_proxy_max_bytes": value}))

        assert image_proxy_settings.get_image_proxy_max_bytes() == 10 * 1024 * 1024


def test_image_proxy_max_bytes_returns_positive_integer(monkeypatch):
    from app.infra.config import image_proxy_settings

    for value, expected in (
        ("2097152", 2 * 1024 * 1024),
        (2097152, 2 * 1024 * 1024),
        (1, 1),
    ):
        monkeypatch.setattr(image_proxy_settings, "cfg", FakeCfg({"image_proxy_max_bytes": value}))

        assert image_proxy_settings.get_image_proxy_max_bytes() == expected


def test_image_proxy_max_bytes_clamps_zero_and_negative_values(monkeypatch):
    from app.infra.config import image_proxy_settings

    for value in ("0", 0, "-25", -25):
        monkeypatch.setattr(image_proxy_settings, "cfg", FakeCfg({"image_proxy_max_bytes": value}))

        assert image_proxy_settings.get_image_proxy_max_bytes() == 1
