import datetime
import logging
import random
import re
from dataclasses import dataclass

from app.domains.reports.report_queries import list_report_ranked_items
from app.infra.config.report_settings import get_report_top_query_limit
from app.shared.time import get_period_range, get_weekday_cn


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger
_date_today_provider = lambda: datetime.date.today()
_random_provider = lambda: random
_get_period_range_provider = lambda: get_period_range
_get_weekday_cn_provider = lambda: get_weekday_cn
_get_plugin_config_provider = None
_get_report_top_query_limit_provider = lambda: get_report_top_query_limit
_list_report_ranked_items_provider = lambda: list_report_ranked_items


@dataclass
class DailyPosterData:
    tv_list: list
    movie_list: list
    pc: dict
    slogan: str


def set_dependency_providers(
    logger_provider=None,
    date_today_provider=None,
    random_provider=None,
    get_period_range_provider=None,
    get_weekday_cn_provider=None,
    get_plugin_config_provider=None,
    get_report_top_query_limit_provider=None,
    list_report_ranked_items_provider=None,
):
    global _logger_provider
    global _date_today_provider
    global _random_provider
    global _get_period_range_provider
    global _get_weekday_cn_provider
    global _get_plugin_config_provider
    global _get_report_top_query_limit_provider
    global _list_report_ranked_items_provider

    if logger_provider is not None:
        _logger_provider = logger_provider
    if date_today_provider is not None:
        _date_today_provider = date_today_provider
    if random_provider is not None:
        _random_provider = random_provider
    if get_period_range_provider is not None:
        _get_period_range_provider = get_period_range_provider
    if get_weekday_cn_provider is not None:
        _get_weekday_cn_provider = get_weekday_cn_provider
    if get_plugin_config_provider is not None:
        _get_plugin_config_provider = get_plugin_config_provider
    if get_report_top_query_limit_provider is not None:
        _get_report_top_query_limit_provider = get_report_top_query_limit_provider
    if list_report_ranked_items_provider is not None:
        _list_report_ranked_items_provider = list_report_ranked_items_provider


def _get_plugin_config(plugin_name):
    if _get_plugin_config_provider is not None:
        return _get_plugin_config_provider()(plugin_name)

    from app.plugins import get_plugin_config

    return get_plugin_config(plugin_name)


def _build_slogan(today):
    slogans = [
        "精选全球佳作，每日不可错过",
        "光影流转，记录每一刻精彩",
        "好片不停歇，追剧不设限",
        "你的观影足迹，我们的数据守护",
        "每一次播放，都是一次心动",
        "时光不老，影像长存",
        "用数据丈量热爱，以光影铭记时光",
        "影视剧集千千万，唯有热爱不可负",
        "一部好片，一段故事，一份记忆",
        "追剧有数据，热爱有依据",
        "荧幕背后的故事，数据会说话",
        "每个夜晚都有好剧相伴",
        "让每一次观影都值得被记录",
        "从数据中发现你的观影DNA",
        "好剧如酒，越品越有味道",
    ]
    random_module = _random_provider()
    random_module.seed(today.toordinal())
    return random_module.choice(slogans)


def _build_period_context(period, today):
    start_date, end_date, where_sql, title_text = _get_period_range_provider()(period)
    del title_text

    yesterday = today - datetime.timedelta(days=1)

    if period in ['yesterday', 'day', 'today', 'daily']:
        date_for_display = start_date or yesterday
        weekday = _get_weekday_cn_provider()(date_for_display)
        return {
            "title": "观影日报",
            "subtitle": "MOVIE & TV DAILY REPORT",
            "date_label": date_for_display.strftime("%Y年%m月%d日"),
            "sub_label": date_for_display.strftime("%m.%d"),
            "weekday": weekday,
            "where": where_sql,
        }
    if period in ['week', 'this_week']:
        end_display = (end_date - datetime.timedelta(days=1)) if end_date else today
        return {
            "title": "观影周报",
            "subtitle": "MOVIE & TV WEEKLY REPORT",
            "date_label": f"{start_date.strftime('%m.%d')} - {end_display.strftime('%m.%d')}",
            "sub_label": f"{start_date.strftime('%m.%d')}-{end_display.strftime('%m.%d')}",
            "weekday": "",
            "where": where_sql,
        }
    if period in ['last_week', 'weekly']:
        end_display = (end_date - datetime.timedelta(days=1)) if end_date else today
        return {
            "title": "观影周报",
            "subtitle": "MOVIE & TV WEEKLY REPORT",
            "date_label": f"{start_date.strftime('%m.%d')} - {end_display.strftime('%m.%d')}",
            "sub_label": f"{start_date.strftime('%m.%d')}-{end_display.strftime('%m.%d')}",
            "weekday": "",
            "where": where_sql,
        }
    if period in ['month', 'this_month']:
        return {
            "title": "观影月报",
            "subtitle": "MOVIE & TV MONTHLY REPORT",
            "date_label": today.strftime("%Y年%m月"),
            "sub_label": today.strftime("%m月"),
            "weekday": "",
            "where": where_sql,
        }
    if period in ['last_month', 'monthly']:
        return {
            "title": "观影月报",
            "subtitle": "MOVIE & TV MONTHLY REPORT",
            "date_label": start_date.strftime("%Y年%m月"),
            "sub_label": start_date.strftime("%m月"),
            "weekday": "",
            "where": where_sql,
        }
    if period in ['year', 'this_year', 'yearly']:
        return {
            "title": "观影年报",
            "subtitle": "MOVIE & TV YEARLY REPORT",
            "date_label": today.strftime("%Y年"),
            "sub_label": today.strftime("%Y年"),
            "weekday": "",
            "where": where_sql,
        }
    if period == 'last_year':
        return {
            "title": "观影年报",
            "subtitle": "MOVIE & TV YEARLY REPORT",
            "date_label": start_date.strftime("%Y年"),
            "sub_label": start_date.strftime("%Y年"),
            "weekday": "",
            "where": where_sql,
        }

    date_for_display = yesterday
    weekday = _get_weekday_cn_provider()(date_for_display)
    return {
        "title": "观影日报",
        "subtitle": "MOVIE & TV DAILY REPORT",
        "date_label": date_for_display.strftime("%Y年%m月%d日"),
        "sub_label": date_for_display.strftime("%m.%d"),
        "weekday": weekday,
        "where": where_sql,
    }


def _get_exclude_types():
    exclude_types = []
    try:
        view_report_config = _get_plugin_config("view_report")
        if view_report_config:
            config_exclude = view_report_config.get('exclude_types', [])
            if isinstance(config_exclude, str):
                config_exclude = [t.strip() for t in config_exclude.split(',') if t.strip()]
            if config_exclude:
                exclude_types = config_exclude
    except:
        pass
    return exclude_types


def _get_item_value(item, key, default=None):
    return item[key] if key in item.keys() else default


def _log_ranked_items_preview(all_tops):
    try:
        debug_list = []
        for t in all_tops[:10]:
            try:
                name = t['ItemName'] if 'ItemName' in t.keys() else (t[0] if len(t) > 0 else '未知')
                dur = t['Duration'] if 'Duration' in t.keys() else (t[3] if len(t) > 3 else 0)
                debug_list.append((name, dur))
            except:
                debug_list.append(('unknown', 0))
        _logger_provider().info(f"[海报生成] 查询结果前10条: {debug_list}")
    except Exception as e:
        _logger_provider().error(f"[海报生成] 调试日志错误: {e}")


def _prepare_ranked_lists(pc):
    exclude_types = _get_exclude_types()

    exclude_sql = ""
    if exclude_types:
        exclude_placeholders = ', '.join(['?' for _ in exclude_types])
        exclude_sql = f" AND ItemType NOT IN ({exclude_placeholders})"

    where = pc.get("where", "")
    top_limit = _get_report_top_query_limit_provider()()
    all_tops = _list_report_ranked_items_provider()(where, exclude_sql, exclude_types, top_limit)
    if not all_tops:
        return None, None

    _log_ranked_items_preview(all_tops)

    tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)
    tv_map = {}
    movie_list = []

    for item in all_tops:
        try:
            name = _get_item_value(item, 'ItemName', '')
            item_id = _get_item_value(item, 'ItemId')
            count = _get_item_value(item, 'C', 0)
            item_type = _get_item_value(item, 'ItemType', '')
        except (KeyError, TypeError):
            name = str(item[0]) if len(item) > 0 else ''
            item_id = item[1] if len(item) > 1 else None
            item_type = item[2] if len(item) > 2 else ''
            count = item[3] if len(item) > 3 else 0

        series_name = name
        is_tv = str(item_type) == 'Episode' or tv_pattern.search(name)
        if is_tv:
            parts = name.split(' - ')
            series_name = parts[0] if parts else name

        duration = item['Duration'] if 'Duration' in item.keys() else 0
        if duration is None:
            duration = 0
        item_dict = {'ItemName': name, 'SeriesName': series_name, 'ItemId': item_id, 'C': count, 'Duration': duration}

        if is_tv:
            existing = tv_map.get(series_name)
            if existing:
                existing['C'] += count
                existing['Duration'] += duration
                if duration > existing.get('_best_episode_duration', 0):
                    existing['ItemName'] = name
                    existing['ItemId'] = item_id
                    existing['_best_episode_duration'] = duration
            else:
                item_dict['_best_episode_duration'] = duration
                tv_map[series_name] = item_dict
        else:
            movie_list.append(item_dict)

    tv_list = list(tv_map.values())
    tv_list.sort(key=lambda x: x['Duration'], reverse=True)
    movie_list.sort(key=lambda x: x['Duration'], reverse=True)
    tv_list = tv_list[:5]
    movie_list = movie_list[:5]
    for item in tv_list:
        item.pop('_best_episode_duration', None)

    _logger_provider().info(f"[海报生成] 剧集列表排序后: {[(t['SeriesName'], t['Duration']) for t in tv_list]}")
    _logger_provider().info(f"[海报生成] 电影列表排序后: {[(m['ItemName'], m['Duration']) for m in movie_list]}")

    return tv_list, movie_list


def prepare_daily_poster_data(period='yesterday', tv_list=None, movie_list=None):
    today = _date_today_provider()
    slogan = _build_slogan(today)
    pc = _build_period_context(period, today)

    use_external_data = tv_list is not None or movie_list is not None
    if use_external_data:
        tv_list = tv_list or []
        movie_list = movie_list or []
        _logger_provider().info(f"[海报生成] 使用外部数据: 剧集{len(tv_list)}部, 电影{len(movie_list)}部")
    else:
        tv_list, movie_list = _prepare_ranked_lists(pc)
        if tv_list is None and movie_list is None:
            return None

    if not tv_list and not movie_list:
        return None

    return DailyPosterData(tv_list=tv_list, movie_list=movie_list, pc=pc, slogan=slogan)
