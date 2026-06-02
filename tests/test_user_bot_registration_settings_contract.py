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


def test_user_bot_reg_quota_mode_returns_supported_canonical_values(monkeypatch):
    from app.infra.config import user_bot_settings

    for value, expected in (("total", "total"), (" TOTAL ", "total"), ("batch", "batch"), (" Batch ", "batch")):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_reg_quota_mode": value}))

        assert user_bot_settings.get_user_bot_reg_quota_mode() == expected

    for value in (None, "", "daily", 0):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_reg_quota_mode": value}))

        assert user_bot_settings.get_user_bot_reg_quota_mode() == "total"


def test_user_bot_reg_quota_mode_writer_persists_canonical_value(monkeypatch):
    from app.infra.config import user_bot_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(user_bot_settings, "cfg", fake_cfg)

    user_bot_settings.set_user_bot_reg_quota_mode(" Batch ")
    user_bot_settings.set_user_bot_reg_quota_mode("unsupported")

    assert fake_cfg.set_calls == [
        ("user_bot_reg_quota_mode", "batch"),
        ("user_bot_reg_quota_mode", "total"),
    ]


def test_user_bot_route_mode_returns_supported_canonical_values(monkeypatch):
    from app.infra.config import user_bot_settings

    for value, expected in (("block", "block"), (" BLOCK ", "block"), ("allow", "allow"), (" Allow ", "allow")):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_route_mode": value}))

        assert user_bot_settings.get_user_bot_route_mode() == expected

    for value in (None, "", "deny", 0):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_route_mode": value}))

        assert user_bot_settings.get_user_bot_route_mode() == "block"


def test_user_bot_route_mode_writer_persists_canonical_value(monkeypatch):
    from app.infra.config import user_bot_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(user_bot_settings, "cfg", fake_cfg)

    user_bot_settings.set_user_bot_route_mode(" Allow ")
    user_bot_settings.set_user_bot_route_mode("unsupported")

    assert fake_cfg.set_calls == [
        ("user_bot_route_mode", "allow"),
        ("user_bot_route_mode", "block"),
    ]


def test_user_bot_registration_non_negative_integer_settings(monkeypatch):
    from app.infra.config import user_bot_settings

    for key, getter in (
        ("user_bot_reg_batch_used", user_bot_settings.get_user_bot_registration_batch_used),
        ("user_bot_reg_quota", user_bot_settings.get_user_bot_reg_quota),
        ("user_bot_max_reg", user_bot_settings.get_user_bot_max_reg),
    ):
        for value in (None, "", "not-a-number", True, False):
            monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({key: value}))
            assert getter() == 0

        for value, expected in (("12", 12), (12, 12), (0, 0), ("0", 0), (-5, 0), ("-5", 0)):
            monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({key: value}))
            assert getter() == expected


def test_user_bot_registration_batch_used_writer_normalizes(monkeypatch):
    from app.infra.config import user_bot_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(user_bot_settings, "cfg", fake_cfg)

    user_bot_settings.set_user_bot_registration_batch_used("12")
    user_bot_settings.set_user_bot_registration_batch_used(-5)
    user_bot_settings.set_user_bot_registration_batch_used(True)

    assert fake_cfg.set_calls == [
        ("user_bot_reg_batch_used", 12),
        ("user_bot_reg_batch_used", 0),
        ("user_bot_reg_batch_used", 0),
    ]


def test_user_bot_reg_days_is_positive_integer(monkeypatch):
    from app.infra.config import user_bot_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_reg_days": value}))

        assert user_bot_settings.get_user_bot_reg_days() == 30

    for value, expected in (("45", 45), (45, 45), (1, 1), (0, 1), ("0", 1), (-5, 1), ("-5", 1)):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_reg_days": value}))

        assert user_bot_settings.get_user_bot_reg_days() == expected
