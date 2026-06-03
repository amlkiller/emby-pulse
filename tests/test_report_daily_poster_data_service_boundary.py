import datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


def _reset_daily_poster_data_service(monkeypatch, *, today=None, ranked_items=None, plugin_config=None):
    from app.domains.reports import report_daily_poster_data_service as service

    logger = FakeLogger()
    calls = []
    today = today or datetime.date(2026, 6, 3)

    def fake_get_period_range(period):
        calls.append(("period", period))
        return (
            datetime.date(2026, 6, 2),
            datetime.date(2026, 6, 3),
            "DateCreated >= ?",
            "unused title",
        )

    def fake_get_weekday_cn(value):
        calls.append(("weekday", value))
        return "周二"

    def fake_get_plugin_config(plugin_name):
        calls.append(("plugin_config", plugin_name))
        return plugin_config

    def fake_get_top_limit():
        calls.append(("top_limit",))
        return 50

    def fake_list_ranked_items(where, exclude_sql, exclude_types, top_limit):
        calls.append(("ranked_items", where, exclude_sql, exclude_types, top_limit))
        return ranked_items or []

    monkeypatch.setattr(service, "_logger_provider", lambda: logger)
    monkeypatch.setattr(service, "_date_today_provider", lambda: today)
    monkeypatch.setattr(service, "_get_period_range_provider", lambda: fake_get_period_range)
    monkeypatch.setattr(service, "_get_weekday_cn_provider", lambda: fake_get_weekday_cn)
    monkeypatch.setattr(service, "_get_plugin_config_provider", lambda: fake_get_plugin_config)
    monkeypatch.setattr(service, "_get_report_top_query_limit_provider", lambda: fake_get_top_limit)
    monkeypatch.setattr(service, "_list_report_ranked_items_provider", lambda: fake_list_ranked_items)
    return service, logger, calls


def test_prepare_daily_poster_data_uses_external_lists_without_query(monkeypatch):
    tv_list = [{"SeriesName": "Show", "Duration": 120}]

    service, logger, calls = _reset_daily_poster_data_service(monkeypatch, ranked_items=[{"ItemName": "ignored"}])

    data = service.prepare_daily_poster_data("yesterday", tv_list=tv_list, movie_list=None)

    assert data.tv_list is tv_list
    assert data.movie_list == []
    assert data.pc == {
        "title": "观影日报",
        "subtitle": "MOVIE & TV DAILY REPORT",
        "date_label": "2026年06月02日",
        "sub_label": "06.02",
        "weekday": "周二",
        "where": "DateCreated >= ?",
    }
    assert data.slogan
    assert ("ranked_items", "DateCreated >= ?", "", [], 50) not in calls
    assert logger.infos[-1] == "[海报生成] 使用外部数据: 剧集1部, 电影0部"


def test_prepare_daily_poster_data_groups_internal_ranked_items_and_parses_excludes(monkeypatch):
    ranked_items = [
        {"ItemName": "Show - S01E01", "ItemId": "ep1", "C": 1, "ItemType": "Episode", "Duration": 100},
        {"ItemName": "Show - S01E02", "ItemId": "ep2", "C": 2, "ItemType": "Episode", "Duration": 300},
        {"ItemName": "Movie A", "ItemId": "m1", "C": 3, "ItemType": "Movie", "Duration": 200},
        {"ItemName": "Movie B", "ItemId": "m2", "C": 4, "ItemType": "Movie", "Duration": None},
    ]
    plugin_config = {"exclude_types": "Trailer, Clip,  "}

    service, logger, calls = _reset_daily_poster_data_service(
        monkeypatch,
        ranked_items=ranked_items,
        plugin_config=plugin_config,
    )

    data = service.prepare_daily_poster_data("week")

    assert data.tv_list == [
        {"ItemName": "Show - S01E02", "SeriesName": "Show", "ItemId": "ep2", "C": 3, "Duration": 400}
    ]
    assert data.movie_list == [
        {"ItemName": "Movie A", "SeriesName": "Movie A", "ItemId": "m1", "C": 3, "Duration": 200},
        {"ItemName": "Movie B", "SeriesName": "Movie B", "ItemId": "m2", "C": 4, "Duration": 0},
    ]
    assert ("ranked_items", "DateCreated >= ?", " AND ItemType NOT IN (?, ?)", ["Trailer", "Clip"], 50) in calls
    assert ("plugin_config", "view_report") in calls
    assert logger.errors == []
    assert any("查询结果前10条" in message for message in logger.infos)
    assert logger.infos[-2] == "[海报生成] 剧集列表排序后: [('Show', 400)]"
    assert logger.infos[-1] == "[海报生成] 电影列表排序后: [('Movie A', 200), ('Movie B', 0)]"


def test_prepare_daily_poster_data_returns_none_when_internal_query_empty(monkeypatch):
    service, _logger, _calls = _reset_daily_poster_data_service(monkeypatch, ranked_items=[])

    assert service.prepare_daily_poster_data("yesterday") is None


def test_report_generator_daily_poster_delegates_to_data_service_and_keeps_layout_wrapper(monkeypatch):
    from app.domains.reports import report_daily_poster_data_service
    from app.domains.reports import report_service

    data = report_daily_poster_data_service.DailyPosterData(
        tv_list=[{"SeriesName": "Show", "Duration": 100}],
        movie_list=[{"ItemName": "Movie", "Duration": 200}],
        pc={"title": "观影日报"},
        slogan="Slogan",
    )
    calls = []

    monkeypatch.setattr(report_service, "HAS_PIL", True)
    monkeypatch.setattr(report_service.ReportGenerator, "_init_fonts", lambda self: calls.append(("fonts",)))
    monkeypatch.setattr(
        report_service.report_daily_poster_data_service,
        "prepare_daily_poster_data",
        lambda period, tv_list=None, movie_list=None: calls.append(("prepare", period, tv_list, movie_list)) or data,
    )
    monkeypatch.setattr(
        report_service.ReportGenerator,
        "_draw_text_list_layout",
        lambda self, tv, movies, pc, theme_config, slogan: calls.append(
            ("draw", tv, movies, pc, theme_config["layout"], slogan)
        ) or "image-bytes",
    )

    result = report_service.ReportGenerator().generate_daily_poster(
        period="week",
        tv_list=[{"external": "tv"}],
        movie_list=None,
        theme="list",
    )

    assert result == "image-bytes"
    assert calls == [
        ("fonts",),
        ("fonts",),
        ("prepare", "week", [{"external": "tv"}], None),
        ("draw", data.tv_list, data.movie_list, data.pc, "text_list", "Slogan"),
    ]
