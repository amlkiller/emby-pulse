import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeReportQueries:
    def __init__(self):
        self.calls = []

    def count_report_plays(self, where_sql, params):
        self.calls.append(("count_report_plays", where_sql, params))
        return 12

    def sum_report_duration(self, where_sql, params):
        self.calls.append(("sum_report_duration", where_sql, params))
        return 3600

    def count_report_distinct_users(self, where_sql, params):
        self.calls.append(("count_report_distinct_users", where_sql, params))
        return 3

    def list_report_top_users(self, where_sql, params, limit):
        self.calls.append(("list_report_top_users", where_sql, params, limit))
        return [{"UserId": "u1", "t": 1200}]

    def list_report_content_items(self, where_sql, params, limit):
        self.calls.append(("list_report_content_items", where_sql, params, limit))
        return [{"ItemName": "Movie", "Duration": 1200}]


class FakeReportGenerator:
    def __init__(self):
        self.calls = []

    def generate_daily_poster(self, period, tv_list, movie_list, theme):
        self.calls.append(("generate_daily_poster", period, tv_list, movie_list, theme))
        return "poster-result"


def test_reports_public_service_delegates_and_returns(monkeypatch):
    from app.domains.reports import public_service

    report_queries = FakeReportQueries()
    report_gen = FakeReportGenerator()
    report_service = SimpleNamespace(HAS_PIL=True, report_gen=report_gen)
    monkeypatch.setattr(public_service, "report_queries", report_queries)
    monkeypatch.setattr(public_service, "report_service", report_service)

    where_sql = "WHERE UserId = ?"
    params = ["u1"]

    assert public_service.count_report_plays(where_sql, params) == 12
    assert public_service.sum_report_duration(where_sql, params) == 3600
    assert public_service.count_report_distinct_users(where_sql, params) == 3
    assert public_service.list_report_top_users(where_sql, params, 5) == [{"UserId": "u1", "t": 1200}]
    assert public_service.list_report_content_items(where_sql, params, 10) == [
        {"ItemName": "Movie", "Duration": 1200}
    ]
    assert public_service.has_pillow_support() is True
    assert public_service.generate_daily_poster("weekly", ["tv"], ["movie"], "cinema") == "poster-result"
    assert public_service.generate_daily_poster("daily", ["show"], ["film"]) == "poster-result"

    assert report_queries.calls == [
        ("count_report_plays", where_sql, params),
        ("sum_report_duration", where_sql, params),
        ("count_report_distinct_users", where_sql, params),
        ("list_report_top_users", where_sql, params, 5),
        ("list_report_content_items", where_sql, params, 10),
    ]
    assert report_gen.calls == [
        ("generate_daily_poster", "weekly", ["tv"], ["movie"], "cinema"),
        ("generate_daily_poster", "daily", ["show"], ["film"], "cinema"),
    ]


def test_view_report_plugin_does_not_import_private_report_modules():
    path = _REPO_ROOT / "app/plugins/view_report/plugin.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename="app/plugins/view_report/plugin.py")
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module in {
            "app.domains.reports.report_queries",
            "app.domains.reports.report_service",
        }:
            violations.append(f"app/plugins/view_report/plugin.py:{node.lineno}")

    assert violations == []


def test_notification_bot_service_does_not_import_private_report_modules():
    path = _REPO_ROOT / "app/domains/notifications/bot_service.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel_path)
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.reports.report_service":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.reports" and (
                "report_service" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.reports.report_service" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_notification_bot_stats_uses_report_public_facade_methods():
    path = _REPO_ROOT / "app/domains/notifications/bot_service.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel_path)
    cmd_stats = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_cmd_stats"
    )
    report_calls = set()

    for node in ast.walk(cmd_stats):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "report_service"
        ):
            report_calls.add(func.attr)

    assert {"has_pillow_support", "generate_daily_poster"}.issubset(report_calls)
