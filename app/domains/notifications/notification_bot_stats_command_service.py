import datetime
import re
import traceback

from app.core.config import REPORT_COVER_URL
from app.domains.reports.report_service import HAS_PIL, report_gen
from app.infra.db.playback_filters import get_base_filter
from app.infra.db.playback_store import playback_store


_base_filter_provider = lambda: get_base_filter
_playback_store_provider = lambda: playback_store
_report_gen_provider = lambda: report_gen
_has_pil_provider = lambda: HAS_PIL
_report_cover_url_provider = lambda: REPORT_COVER_URL
_logger_provider = lambda: _NullLogger()


class _NullLogger:
    def error(self, message):
        pass


def set_dependency_providers(
    *,
    base_filter_provider=None,
    playback_store_provider=None,
    report_gen_provider=None,
    has_pil_provider=None,
    report_cover_url_provider=None,
    logger_provider=None,
):
    global _base_filter_provider
    global _playback_store_provider
    global _report_gen_provider
    global _has_pil_provider
    global _report_cover_url_provider
    global _logger_provider

    if base_filter_provider is not None:
        _base_filter_provider = base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if report_gen_provider is not None:
        _report_gen_provider = report_gen_provider
    if has_pil_provider is not None:
        _has_pil_provider = has_pil_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _get_view_report_config():
    try:
        from app.plugins import get_plugin_config

        return get_plugin_config("view_report")
    except Exception:
        return None


def cmd_stats(bot, chat_id, period='day', platform="tg"):
    from app.shared.time import get_period_range, get_period_days, get_weekday_cn

    where, params = _base_filter_provider()('all')
    titles = {'day': '今日日报', 'yesterday': '昨日日报', 'week': '本周周报', 'month': '本月月报', 'year': '年度报告'}
    title_cn = titles.get(period, '数据报表')

    start_date, end_date, period_where, _ = get_period_range(period)
    if period_where:
        where += " " + period_where.replace("WHERE", "AND")

    days = get_period_days(period)

    today = datetime.date.today()
    if period == 'yesterday':
        date_str = start_date.strftime("%m-%d")
        weekday = get_weekday_cn(start_date)
    elif period == 'day':
        date_str = today.strftime("%m-%d")
        weekday = get_weekday_cn(today)
    elif period == 'week':
        end_display = today
        date_str = f"{start_date.strftime('%m-%d')} ~ {end_display.strftime('%m-%d')}"
        weekday = ""
    elif period == 'month':
        date_str = today.strftime("%Y年%m月")
        weekday = ""
    elif period == 'year':
        date_str = today.strftime("%Y年")
        weekday = ""
    else:
        date_str = ""
        weekday = ""

    exclude_types = []
    content_limit = 10
    view_report_config = _get_view_report_config()
    if view_report_config:
        config_exclude = view_report_config.get('exclude_types', [])
        if isinstance(config_exclude, str):
            config_exclude = [t.strip() for t in config_exclude.split(',') if t.strip()]
        if config_exclude:
            exclude_types = config_exclude
        try:
            content_limit = int(view_report_config.get('top_content_limit') or 10)
        except (ValueError, TypeError):
            content_limit = 10

    exclude_sql = ""
    if exclude_types:
        exclude_placeholders = ', '.join(['?' for _ in exclude_types])
        exclude_sql = f" AND ItemType NOT IN ({exclude_placeholders})"
        if isinstance(params, (list, tuple)):
            params = tuple(params) + tuple(exclude_types)
        else:
            params = tuple(exclude_types)

    try:
        store = _playback_store_provider()
        plays_res = store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}{exclude_sql}", params)
        if not plays_res:
            raise Exception("DB Error")
        plays = plays_res[0]['c']
        dur_res = store.query(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}{exclude_sql}", params)
        dur = dur_res[0]['c'] if dur_res and dur_res[0]['c'] else 0
        hours_str = f"{dur / 3600:.1f}"
        users_res = store.query(f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where}{exclude_sql}", params)
        users = users_res[0]['c'] if users_res else 0

        avg_plays_str = f"{plays / days:.1f}" if days > 0 else str(plays)

        top_users = store.query(f"SELECT UserId, SUM(PlayDuration) as t FROM PlaybackActivity {where}{exclude_sql} GROUP BY UserId ORDER BY t DESC LIMIT 5", params)
        user_str = ""
        if top_users:
            for i, u in enumerate(top_users):
                name = bot._get_username(u['UserId'])
                h = u['t'] / 3600
                h_str = f"{h:.1f}"
                prefix = ['🥇','🥈','🥉'][i] if i < 3 else f"{i+1}."
                user_str += f"{prefix} {name} ({h_str}h)\n"
        else:
            user_str = "暂无数据\n"

        all_content = store.query(f"SELECT ItemName, ItemId, ItemType, COUNT(*) as C, COALESCE(SUM(PlayDuration), 0) as Duration FROM PlaybackActivity {where}{exclude_sql} GROUP BY ItemName ORDER BY Duration DESC LIMIT 100", params)

        tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)
        tv_list = []
        movie_list = []

        for item in all_content or []:
            name = item['ItemName'] if item['ItemName'] else ''
            series_name = name.split(' - ')[0] if ' - ' in name else name
            duration = item['Duration'] if item['Duration'] else 0
            count = item['C'] if item['C'] else 0
            item_id = item['ItemId'] if item['ItemId'] else None

            if tv_pattern.search(name) or item['ItemType'] == 'Episode':
                existing = [t for t in tv_list if t['SeriesName'] == series_name]
                if not existing and len(tv_list) < content_limit:
                    tv_list.append({'SeriesName': series_name, 'ItemName': name, 'ItemId': item_id, 'C': count, 'Duration': duration})
                elif existing:
                    existing[0]['C'] += count
                    existing[0]['Duration'] += duration
            else:
                if len(movie_list) < content_limit:
                    movie_list.append({'ItemName': name, 'ItemId': item_id, 'C': count, 'Duration': duration})

        tv_list.sort(key=lambda x: x['Duration'], reverse=True)
        movie_list.sort(key=lambda x: x['Duration'], reverse=True)

        tv_str = ""
        for i, item in enumerate(tv_list):
            d = item['Duration']
            h = int(d // 3600)
            m = int((d % 3600) // 60)
            if h > 0:
                dur_str = f"{h} 小时 {m} 分钟"
            else:
                dur_str = f"{m} 分钟"
            tv_str += f"{i+1}. {item['SeriesName']}\n播放次数: {item['C']} 时长: {dur_str}\n"

        movie_str = ""
        for i, item in enumerate(movie_list):
            d = item['Duration']
            h = int(d // 3600)
            m = int((d % 3600) // 60)
            if h > 0:
                dur_str = f"{h} 小时 {m} 分钟"
            else:
                dur_str = f"{m} 分钟"
            movie_str += f"{i+1}. {item['ItemName']}\n播放次数: {item['C']} 时长: {dur_str}\n"

        title_display = f"{title_cn}"
        if date_str:
            title_display = f"{title_cn}\n📅 {date_str}"
            if weekday:
                title_display += f" {weekday}"

        if _has_pil_provider():
            date_line = f"📅 {date_str}" if date_str else ""
            weekday_line = f" {weekday}" if weekday else ""

            caption_parts = [
                f"📊 <b>EmbyPulse {title_cn}</b>",
                f"{date_line}{weekday_line}",
                "",
                "📈 <b>数据大盘</b>",
                f"▶️ 总播放量：{plays} 次",
                f"⏱️ 活跃时长：{hours_str} 小时",
                f"👥 活跃人数：{users} 人",
            ]

            if period in ['week', 'month']:
                caption_parts.append(f"📊 日均播放：{avg_plays_str} 次")

            caption_parts.extend([
                "",
                f"🏆 <b>活跃用户 Top {len(top_users) if top_users else 5}</b>",
                user_str.strip(),
            ])

            if tv_str:
                caption_parts.extend([
                    "",
                    f"📺 <b>剧集排名</b>",
                    tv_str.strip()
                ])

            if movie_str:
                caption_parts.extend([
                    "",
                    f"🎬 <b>电影排名</b>",
                    movie_str.strip()
                ])

            caption = "\n".join(caption_parts)
            poster = _report_gen_provider().generate_daily_poster(period, tv_list, movie_list)
            if poster:
                bot.send_photo(chat_id, poster, caption.strip(), platform=platform)
                return

        caption = (f"📊 <b>EmbyPulse {title_display}</b>\n\n"
                   f"📈 <b>数据大盘</b>\n"
                   f"▶️ 总播放量：{plays} 次\n"
                   f"⏱️ 活跃时长：{hours_str} 小时\n"
                   f"👥 活跃人数：{users} 人\n\n"
                   f"🏆 <b>活跃用户 Top 5</b>\n"
                   f"{user_str}\n"
                   f"🔥 <b>热门内容 Top 10</b>\n"
                   f"{tv_str or movie_str or '暂无数据'}")
        bot.send_photo(chat_id, _report_cover_url_provider(), caption.strip(), platform=platform)
    except Exception as e:
        _logger_provider().error(f"[Bot] _cmd_stats error: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, f"❌ 统计失败: {str(e)}", platform=platform)
