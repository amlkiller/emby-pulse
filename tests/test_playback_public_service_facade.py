import ast
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeStatsQueries:
    def __init__(self):
        self.calls = []

    def get_user_play_summary(self, user_id, start_str, end_str):
        self.calls.append(("get_user_play_summary", user_id, start_str, end_str))
        return {"total_dur": 3600, "active_days": 2}


def test_playback_public_service_delegates_and_returns(monkeypatch):
    from app.domains.playback import public_service

    stats_queries = FakeStatsQueries()
    monkeypatch.setattr(public_service, "stats_queries", stats_queries)

    assert public_service.get_user_play_summary("u1", "2026-05-01", "2026-06-01") == {
        "total_dur": 3600,
        "active_days": 2,
    }
    assert stats_queries.calls == [
        ("get_user_play_summary", "u1", "2026-05-01", "2026-06-01"),
    ]


def test_keep_alive_plugin_does_not_import_private_playback_query_modules():
    path = _REPO_ROOT / "app/plugins/keep_alive/plugin.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename="app/plugins/keep_alive/plugin.py")
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "app.domains.playback.stats_queries":
            violations.append(f"app/plugins/keep_alive/plugin.py:{node.lineno}")
        if node.module == "app.domains.playback":
            imported_names = {alias.name for alias in node.names}
            if "stats_queries" in imported_names or "*" in imported_names:
                violations.append(f"app/plugins/keep_alive/plugin.py:{node.lineno}")

    assert violations == []
