import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


class FakeLock:
    def __init__(self):
        self.entered = 0
        self.exited = 0
        self.depth = 0

    def __enter__(self):
        self.entered += 1
        self.depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.depth -= 1
        self.exited += 1


def _make_daemon():
    from app.bot.notification_bot import bot_service

    daemon = bot_service.SystemDaemon()
    daemon.library_lock = FakeLock()
    daemon.library_queue = []
    return daemon


def _patch_dependencies(monkeypatch, *, max_queue=300):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    monkeypatch.setattr(bot_service, "get_library_notify_queue_max", lambda: max_queue)
    monkeypatch.setattr(bot_service, "logger", logger)
    return logger


def test_library_queue_appends_item_under_configured_limit(monkeypatch):
    logger = _patch_dependencies(monkeypatch, max_queue=3)
    daemon = _make_daemon()
    item = {"Id": "item-1", "Name": "Movie"}

    daemon.add_library_task(item)

    assert daemon.library_queue == [item]
    assert logger.warnings == []
    assert daemon.library_lock.entered == 1
    assert daemon.library_lock.exited == 1
    assert daemon.library_lock.depth == 0


def test_library_queue_skips_duplicate_item_id(monkeypatch):
    logger = _patch_dependencies(monkeypatch, max_queue=3)
    daemon = _make_daemon()
    first = {"Id": "item-1", "Name": "First"}
    duplicate = {"Id": "item-1", "Name": "Duplicate"}
    daemon.library_queue = [first]

    daemon.add_library_task(duplicate)

    assert daemon.library_queue == [first]
    assert logger.warnings == []
    assert daemon.library_lock.entered == 1
    assert daemon.library_lock.exited == 1


def test_library_queue_drops_oldest_and_logs_when_at_capacity(monkeypatch):
    logger = _patch_dependencies(monkeypatch, max_queue=2)
    daemon = _make_daemon()
    second = {"Id": "item-2", "Name": "Second"}
    new_item = {"Id": "item-3", "Name": "Third"}
    daemon.library_queue = [{"Id": "item-1", "Name": "First"}, second]

    daemon.add_library_task(new_item)

    assert daemon.library_queue == [second, new_item]
    assert logger.warnings == ["[入库通知] 队列已满，丢弃最旧项目: First"]
    assert daemon.library_lock.entered == 1
    assert daemon.library_lock.exited == 1


def test_library_queue_drop_log_falls_back_to_id(monkeypatch):
    logger = _patch_dependencies(monkeypatch, max_queue=1)
    daemon = _make_daemon()
    daemon.library_queue = [{"Id": "old-id"}]

    daemon.add_library_task({"Id": "new-id"})

    assert daemon.library_queue == [{"Id": "new-id"}]
    assert logger.warnings == ["[入库通知] 队列已满，丢弃最旧项目: old-id"]


def test_library_queue_missing_item_id_uses_existing_dedupe_semantics(monkeypatch):
    logger = _patch_dependencies(monkeypatch, max_queue=3)
    daemon = _make_daemon()
    existing = {"Name": "No Id"}
    daemon.library_queue = [existing]

    daemon.add_library_task({"Name": "Also No Id"})

    assert daemon.library_queue == [existing]
    assert logger.warnings == []
    assert daemon.library_lock.entered == 1
    assert daemon.library_lock.exited == 1
