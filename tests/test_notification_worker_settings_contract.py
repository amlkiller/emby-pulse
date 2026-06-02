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


def test_coerce_positive_int_respects_optional_maximum():
    from app.infra.config.coercion import coerce_positive_int

    assert coerce_positive_int("12", 8, minimum=2, maximum=32) == 12
    assert coerce_positive_int("1", 8, minimum=2, maximum=32) == 2
    assert coerce_positive_int("99", 8, minimum=2, maximum=32) == 32
    assert coerce_positive_int("bad", 8, minimum=2, maximum=32) == 8
    assert coerce_positive_int(True, 8, minimum=2, maximum=32) == 8


def test_bot_worker_count_preserves_default_and_bounds(monkeypatch):
    from app.infra.config import bot_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(bot_settings, "cfg", FakeCfg({"bot_worker_count": value}))

        assert bot_settings.get_bot_worker_count() == 8

    for value, expected in (("12", 12), (12, 12), (1, 2), ("1", 2), (99, 32), ("99", 32)):
        monkeypatch.setattr(bot_settings, "cfg", FakeCfg({"bot_worker_count": value}))

        assert bot_settings.get_bot_worker_count() == expected


def test_library_notify_queue_max_preserves_default_and_bounds(monkeypatch):
    from app.infra.config import bot_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(bot_settings, "cfg", FakeCfg({"library_notify_queue_max": value}))

        assert bot_settings.get_library_notify_queue_max() == 300

    for value, expected in (("120", 120), (120, 120), (1, 50), ("1", 50), (9999, 2000), ("9999", 2000)):
        monkeypatch.setattr(bot_settings, "cfg", FakeCfg({"library_notify_queue_max": value}))

        assert bot_settings.get_library_notify_queue_max() == expected


def test_user_bot_worker_count_preserves_default_and_bounds(monkeypatch):
    from app.infra.config import user_bot_settings

    for value in (None, "", "not-a-number", True, False):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_worker_count": value}))

        assert user_bot_settings.get_user_bot_worker_count() == 16

    for value, expected in (("12", 12), (12, 12), (1, 4), ("1", 4), (99, 50), ("99", 50)):
        monkeypatch.setattr(user_bot_settings, "cfg", FakeCfg({"user_bot_worker_count": value}))

        assert user_bot_settings.get_user_bot_worker_count() == expected
