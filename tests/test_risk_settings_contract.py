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


def test_risk_integer_settings_default_and_clamp(monkeypatch):
    from app.infra.config import risk_settings

    monkeypatch.setattr(
        risk_settings,
        "cfg",
        FakeCfg({
            "max_devices": "not-a-number",
            "default_max_concurrent": "",
        }),
    )

    assert risk_settings.get_max_devices() == 10
    assert risk_settings.get_default_max_concurrent() == 2

    monkeypatch.setattr(
        risk_settings,
        "cfg",
        FakeCfg({
            "max_devices": "-5",
            "default_max_concurrent": 0,
        }),
    )

    assert risk_settings.get_max_devices() == 1
    assert risk_settings.get_default_max_concurrent() == 1


def test_risk_boolean_settings_normalize_common_values(monkeypatch):
    from app.infra.config import risk_settings

    monkeypatch.setattr(
        risk_settings,
        "cfg",
        FakeCfg({
            "enable_risk_control": "false",
            "enable_risk_sys_notification": "1",
        }),
    )

    assert risk_settings.is_risk_control_enabled() is False
    assert risk_settings.is_risk_sys_notification_enabled() is True

    monkeypatch.setattr(
        risk_settings,
        "cfg",
        FakeCfg({
            "enable_risk_control": 0,
            "enable_risk_sys_notification": "off",
        }),
    )

    assert risk_settings.is_risk_control_enabled() is False
    assert risk_settings.is_risk_sys_notification_enabled() is False


def test_risk_violation_action_is_supported_value(monkeypatch):
    from app.infra.config import risk_settings

    for action in ("warn_only", "warn_user", "auto_ban"):
        monkeypatch.setattr(risk_settings, "cfg", FakeCfg({"violation_action": action}))
        assert risk_settings.get_violation_action() == action

    monkeypatch.setattr(risk_settings, "cfg", FakeCfg({"violation_action": "delete_user"}))

    assert risk_settings.get_violation_action() == "warn_only"


def test_risk_setting_writers_normalize_values(monkeypatch):
    from app.infra.config import risk_settings

    fake_cfg = FakeCfg()
    monkeypatch.setattr(risk_settings, "cfg", fake_cfg)

    risk_settings.set_risk_control_enabled(1)
    risk_settings.set_default_max_concurrent(0)
    risk_settings.set_violation_action("unsupported")
    risk_settings.set_risk_sys_notification_enabled("")

    assert fake_cfg.set_calls == [
        ("enable_risk_control", True),
        ("default_max_concurrent", 1),
        ("violation_action", "warn_only"),
        ("enable_risk_sys_notification", False),
    ]
