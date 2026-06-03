import sys
from pathlib import Path

from PIL import ImageFont


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _minimal_theme_config():
    return {
        "background": {"colors": [(15, 15, 20), (23, 20, 30)]},
        "colors": {
            "title": (255, 255, 255),
            "date": (220, 220, 230),
            "weekday": (150, 150, 160),
            "section_title": (255, 255, 255),
            "section_en": (130, 135, 150),
            "shadow": (10, 12, 18),
            "divider": (60, 65, 80),
            "placeholder_bg": [(45, 48, 58), (60, 60, 68)],
            "placeholder_text": (90, 95, 110),
            "rank_bg": (20, 22, 30),
            "rank_1": (255, 215, 0),
            "rank_2": (192, 192, 192),
            "rank_3": (205, 127, 50),
            "rank_other": (180, 185, 195),
            "name": (240, 240, 245),
            "duration": (130, 135, 150),
            "watermark": (80, 85, 100),
            "poster_radius": 12,
        },
        "decorations": [],
    }


def _period_context():
    return {
        "title": "观影日报",
        "subtitle": "MOVIE & TV DAILY REPORT",
        "date_label": "2026年06月02日",
        "weekday": "周二",
    }


def test_report_generator_film_strip_wrapper_preserves_poster_and_font_provider_chain(monkeypatch):
    from app.domains.reports import report_service

    calls = []
    generator = report_service.ReportGenerator()

    monkeypatch.setattr(
        generator,
        "_get_best_poster",
        lambda item_id, item_name, width, height, is_tv=False: calls.append(
            ("poster", item_id, item_name, width, height, is_tv)
        ) or "poster",
    )
    monkeypatch.setattr(
        report_service,
        "_get_font",
        lambda size: calls.append(("font", size)) or f"font-{size}",
    )

    def fake_draw_film_strip_layout(
        tv_list,
        movie_list,
        pc,
        theme_config,
        slogan,
        poster_provider,
        font_provider,
        default_font_provider,
    ):
        calls.append(("draw", tv_list, movie_list, pc, theme_config, slogan))
        assert poster_provider("item-1", "Show - S01E01", 170, 240, is_tv=True) == "poster"
        assert font_provider(72) == "font-72"
        assert default_font_provider() is not None
        return "rendered"

    monkeypatch.setattr(
        report_service.report_film_strip_poster_layout_service,
        "draw_film_strip_layout",
        fake_draw_film_strip_layout,
    )

    result = generator._draw_film_strip_layout(
        [{"ItemName": "Show - S01E01"}],
        [],
        {"title": "观影日报"},
        {"layout": "film_strip"},
        "Slogan",
    )

    assert result == "rendered"
    assert calls == [
        ("draw", [{"ItemName": "Show - S01E01"}], [], {"title": "观影日报"}, {"layout": "film_strip"}, "Slogan"),
        ("poster", "item-1", "Show - S01E01", 170, 240, True),
        ("font", 72),
    ]


def test_film_strip_layout_service_generates_jpeg_and_routes_tv_movie_poster_requests():
    from app.domains.reports import report_film_strip_poster_layout_service as service

    poster_calls = []

    def poster_provider(item_id, item_name, width, height, is_tv=False):
        poster_calls.append((item_id, item_name, width, height, is_tv))
        return None

    output = service.draw_film_strip_layout(
        tv_list=[{"ItemId": "ep1", "ItemName": "Show - S01E01", "SeriesName": "Show", "Duration": 3661}],
        movie_list=[{"ItemId": "m1", "ItemName": "Movie", "Duration": 59}],
        pc=_period_context(),
        theme_config=_minimal_theme_config(),
        slogan="Slogan",
        poster_provider=poster_provider,
        font_provider=lambda size: ImageFont.load_default(),
        default_font_provider=lambda: ImageFont.load_default(),
    )

    assert output.getvalue()[:2] == b"\xff\xd8"
    calls_by_item = {call[0]: call for call in poster_calls}
    assert calls_by_item["ep1"][:4] == ("ep1", "Show - S01E01", 170, 240)
    assert bool(calls_by_item["ep1"][4]) is True
    assert calls_by_item["m1"] == ("m1", "Movie", 170, 240, False)
