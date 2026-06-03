import io
import re
import datetime
import logging
import math
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.core.config import THEMES
from app.domains.reports.report_assets import HAS_PIL, POSTER_THEMES, _get_font, _load_font, get_theme_list
from app.domains.reports import report_poster_fetcher_service
from app.domains.reports.report_queries import (
    build_report_base_filter,
    count_report_plays,
    list_report_ranked_items,
    list_report_top_items,
    sum_report_duration,
)
from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.report_settings import get_report_top_query_limit

logger = logging.getLogger("uvicorn")

if HAS_PIL:
    from PIL import Image, ImageDraw, ImageFont

report_poster_fetcher_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    tmdb_client_provider=lambda: tmdb_client,
    network_client_provider=lambda: network_client,
    has_pil_provider=lambda: HAS_PIL,
    logger_provider=lambda: logger,
)

def get_user_map_internal():
    user_map = {}
    try:
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                user_map[u['Id']] = u['Name']
    except Exception:
        pass
    return user_map


class ReportGenerator:
    def __init__(self):
        if HAS_PIL:
            self._init_fonts()

    def _init_fonts(self):
        self.font_title = _get_font(28)
        self.font_section = _get_font(18)
        self.font_rank = _get_font(20)
        self.font_name = _get_font(14)
        self.font_count = _get_font(12)
        self.font_footer = _get_font(12)
        self.font_large = _get_font(32)
        self.font_medium = _get_font(20)
        self.font_small = _get_font(16)

    def draw_rounded_rect(self, draw, xy, color, radius=15):
        if not HAS_PIL: return
        draw.rounded_rectangle(xy, radius=radius, fill=color)

    def generate_report(self, user_id, period, theme_name="black_gold"):
        if not HAS_PIL: return None
        theme = THEMES.get(theme_name, THEMES["black_gold"])
        width, height = 800, 1200

        where_base, params = build_report_base_filter(user_id)
        date_filter = ""
        title_period = "全量"

        if period == 'week':
            date_filter = " AND DateCreated > date('now', '-7 days')"
            title_period = "本周观影周报"
        elif period == 'month':
            date_filter = " AND DateCreated > date('now', '-30 days')"
            title_period = "本月观影月报"
        elif period == 'year':
            date_filter = " AND DateCreated > date('now', '-1 year')"
            title_period = "年度观影报告"
        elif period == 'day':
            date_filter = " AND DateCreated > date('now', 'start of day')"
            title_period = "今日日报"
        elif period == 'yesterday':
            date_filter = " AND DateCreated >= date('now', '-1 day', 'start of day') AND DateCreated < date('now', 'start of day')"
            yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%m-%d")
            title_period = f"昨日日报 ({yesterday_str})"
        else:
            title_period = "全量观影报告"

        full_where = where_base + date_filter

        plays = count_report_plays(full_where, params)

        dur = sum_report_duration(full_where, params)
        hours = round(dur / 3600, 1)

        user_name = "Emby Server"
        if user_id != 'all': user_name = get_user_map_internal().get(user_id, "User")

        top_list = []
        if plays > 0:
            top_list = list_report_top_items(full_where, params)

        try:
            font_lg = _get_font(60)
            font_md = _get_font(40)
            font_sm = _get_font(28)
            font_xs = _get_font(22)
        except:
            font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

        img = Image.new('RGB', (width, height), theme['bg'])
        draw = ImageDraw.Draw(img)

        draw.text((40, 60), user_name, font=font_lg, fill=theme['text'])
        draw.text((40, 140), f"{title_period}", font=font_sm, fill=theme['text'])

        self.draw_rounded_rect(draw, (40, 220, 390, 370), theme['card'])
        draw.text((70, 250), str(plays), font=font_lg, fill=theme['highlight'])
        draw.text((70, 320), "播放次数", font=font_sm, fill=theme['text'])

        self.draw_rounded_rect(draw, (410, 220, 760, 370), theme['card'])
        draw.text((440, 250), str(hours), font=font_lg, fill=theme['highlight'])
        draw.text((440, 320), "专注时长(H)", font=font_sm, fill=theme['text'])

        list_y = 420
        draw.text((40, list_y), "🏆 内容风云榜", font=font_md, fill=theme['text'])
        item_y = list_y + 70

        if top_list:
            for i, item in enumerate(top_list):
                self.draw_rounded_rect(draw, (40, item_y, 760, item_y+60), theme['card'], radius=10)
                raw_name = item.get('ItemName') or '未知内容'
                name = str(raw_name)[:20]
                draw.text((60, item_y+15), str(i+1), font=font_sm, fill=theme['highlight'])
                draw.text((120, item_y+15), name, font=font_sm, fill=theme['text'])
                item_y += 70
        else:
            draw.text((300, item_y+50), "暂无数据", font=font_md, fill=(100,100,100))

        draw.text((250, 1150), "Generated by EmbyPulse", font=font_xs, fill=(80, 80, 80))

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        return output

    def _get_series_id(self, item_id, item_name):
        return report_poster_fetcher_service.report_poster_fetcher.get_series_id(item_id, item_name)

    def _fetch_emby_poster(self, item_id, width=120, height=160):
        return report_poster_fetcher_service.report_poster_fetcher.fetch_emby_poster(item_id, width, height)

    def _fetch_tmdb_poster(self, item_name, width=120, height=160, is_tv=False):
        return report_poster_fetcher_service.report_poster_fetcher.fetch_tmdb_poster(item_name, width, height, is_tv=is_tv)

    def _get_best_poster(self, item_id, item_name, width=120, height=160, is_tv=False):
        poster = None
        if is_tv and item_id:
            series_id = self._get_series_id(item_id, item_name)
            if series_id:
                poster = self._fetch_emby_poster(series_id, width, height)
        if not poster and item_id:
            poster = self._fetch_emby_poster(item_id, width, height)
        if not poster:
            poster = self._fetch_tmdb_poster(item_name, width, height, is_tv=is_tv)
        return poster

    def generate_daily_poster(self, period='yesterday', tv_list=None, movie_list=None, theme='cinema'):
        """生成观影TOP榜海报 - 支持多主题
        
        参数:
            period: 时间范围标识
            tv_list: 外部传入的剧集列表（可选，包含 SeriesName, ItemId, Duration）
            movie_list: 外部传入的电影列表（可选，包含 ItemName, ItemId, Duration）
            theme: 主题ID，可选: cinema, neon, minimal, sunset, ocean, forest
        
        当 tv_list 和 movie_list 都传入时，使用外部数据（确保与文字报告一致）
        否则自行查询数据库（向后兼容）
        """
        if not HAS_PIL:
            return None
        
        # 获取主题配置
        theme_config = POSTER_THEMES.get(theme, POSTER_THEMES['cinema'])
        colors = theme_config['colors']
        
        self._init_fonts()
        
        # 🔥 如果外部传入数据，直接使用，跳过查询逻辑
        use_external_data = tv_list is not None or movie_list is not None
        
        # 多样化标语库 - 每次随机选择不重复
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
            "好剧如酒，越品越有味道"
        ]
        # 使用日期作为随机种子，确保同一天生成相同标语
        random.seed(datetime.date.today().toordinal())
        slogan = random.choice(slogans)
        
        # 🔥 使用统一的时间计算模块
        from app.shared.time import get_period_range, get_weekday_cn
        start_date, end_date, where_sql, title_text = get_period_range(period)
        
        # 构建海报显示配置
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        
        # 根据时间范围类型生成显示文本
        if period in ['yesterday', 'day', 'today', 'daily']:
            date_for_display = start_date or yesterday
            weekday = get_weekday_cn(date_for_display)
            pc = {
                "title": "观影日报",
                "subtitle": "MOVIE & TV DAILY REPORT",
                "date_label": date_for_display.strftime("%Y年%m月%d日"),
                "sub_label": date_for_display.strftime("%m.%d"),
                "weekday": weekday,
                "where": where_sql
            }
        elif period in ['week', 'this_week']:
            end_display = (end_date - datetime.timedelta(days=1)) if end_date else today
            pc = {
                "title": "观影周报",
                "subtitle": "MOVIE & TV WEEKLY REPORT",
                "date_label": f"{start_date.strftime('%m.%d')} - {end_display.strftime('%m.%d')}",
                "sub_label": f"{start_date.strftime('%m.%d')}-{end_display.strftime('%m.%d')}",
                "weekday": "",
                "where": where_sql
            }
        elif period in ['last_week', 'weekly']:
            end_display = (end_date - datetime.timedelta(days=1)) if end_date else today
            pc = {
                "title": "观影周报",
                "subtitle": "MOVIE & TV WEEKLY REPORT",
                "date_label": f"{start_date.strftime('%m.%d')} - {end_display.strftime('%m.%d')}",
                "sub_label": f"{start_date.strftime('%m.%d')}-{end_display.strftime('%m.%d')}",
                "weekday": "",
                "where": where_sql
            }
        elif period in ['month', 'this_month']:
            pc = {
                "title": "观影月报",
                "subtitle": "MOVIE & TV MONTHLY REPORT",
                "date_label": today.strftime("%Y年%m月"),
                "sub_label": today.strftime("%m月"),
                "weekday": "",
                "where": where_sql
            }
        elif period in ['last_month', 'monthly']:
            pc = {
                "title": "观影月报",
                "subtitle": "MOVIE & TV MONTHLY REPORT",
                "date_label": start_date.strftime("%Y年%m月"),
                "sub_label": start_date.strftime("%m月"),
                "weekday": "",
                "where": where_sql
            }
        elif period in ['year', 'this_year', 'yearly']:
            pc = {
                "title": "观影年报",
                "subtitle": "MOVIE & TV YEARLY REPORT",
                "date_label": today.strftime("%Y年"),
                "sub_label": today.strftime("%Y年"),
                "weekday": "",
                "where": where_sql
            }
        elif period == 'last_year':
            pc = {
                "title": "观影年报",
                "subtitle": "MOVIE & TV YEARLY REPORT",
                "date_label": start_date.strftime("%Y年"),
                "sub_label": start_date.strftime("%Y年"),
                "weekday": "",
                "where": where_sql
            }
        else:
            # 默认使用昨天
            date_for_display = yesterday
            weekday = get_weekday_cn(date_for_display)
            pc = {
                "title": "观影日报",
                "subtitle": "MOVIE & TV DAILY REPORT",
                "date_label": date_for_display.strftime("%Y年%m月%d日"),
                "sub_label": date_for_display.strftime("%m.%d"),
                "weekday": weekday,
                "where": where_sql
            }

        # 🔥 如果外部传入数据，直接使用，不再查询数据库
        if use_external_data:
            # 使用外部传入的数据
            tv_list = tv_list or []
            movie_list = movie_list or []
            logger.info(f"[海报生成] 使用外部数据: 剧集{len(tv_list)}部, 电影{len(movie_list)}部")
        else:
            # 向后兼容：自行查询数据库
            # 读取观影报告插件的排除类型配置（默认不排除）
            exclude_types = []
            try:
                from app.plugins import get_plugin_config
                view_report_config = get_plugin_config("view_report")
                if view_report_config:
                    config_exclude = view_report_config.get('exclude_types', [])
                    if isinstance(config_exclude, str):
                        config_exclude = [t.strip() for t in config_exclude.split(',') if t.strip()]
                    if config_exclude:
                        exclude_types = config_exclude
            except:
                pass
            
            # 构建排除类型 SQL
            exclude_sql = ""
            if exclude_types:
                exclude_placeholders = ', '.join(['?' for _ in exclude_types])
                exclude_sql = f" AND ItemType NOT IN ({exclude_placeholders})"

            # 🔥 从 pc 字典获取 where 条件
            where = pc.get("where", "")

            top_limit = get_report_top_query_limit()
            all_tops = list_report_ranked_items(where, exclude_sql, exclude_types, top_limit)
            if not all_tops:
                return None
            
            # 调试日志：打印查询结果前10条
            try:
                debug_list = []
                for t in all_tops[:10]:
                    try:
                        name = t['ItemName'] if 'ItemName' in t.keys() else (t[0] if len(t) > 0 else '未知')
                        dur = t['Duration'] if 'Duration' in t.keys() else (t[3] if len(t) > 3 else 0)
                        debug_list.append((name, dur))
                    except:
                        debug_list.append(('unknown', 0))
                logger.info(f"[海报生成] 查询结果前10条: {debug_list}")
            except Exception as e:
                logger.error(f"[海报生成] 调试日志错误: {e}")

            tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)
            tv_map = {}
            movie_list = []
            
            for item in all_tops:
                try:
                    name = item['ItemName'] if 'ItemName' in item.keys() else ''
                    item_id = item['ItemId'] if 'ItemId' in item.keys() else None
                    count = item['C'] if 'C' in item.keys() else 0
                    item_type = item['ItemType'] if 'ItemType' in item.keys() else ''
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

            # 先完整聚合同一剧集，再取 TOP，避免前 100 条单集数据导致剧集总榜被截断。
            tv_list = list(tv_map.values())
            tv_list.sort(key=lambda x: x['Duration'], reverse=True)
            movie_list.sort(key=lambda x: x['Duration'], reverse=True)
            tv_list = tv_list[:5]
            movie_list = movie_list[:5]
            for item in tv_list:
                item.pop('_best_episode_duration', None)
            
            # 调试日志：打印排序后的列表
            logger.info(f"[海报生成] 剧集列表排序后: {[(t['SeriesName'], t['Duration']) for t in tv_list]}")
            logger.info(f"[海报生成] 电影列表排序后: {[(m['ItemName'], m['Duration']) for m in movie_list]}")

        if not tv_list and not movie_list:
            return None

        # ========== 根据布局类型生成海报 ==========
        layout = theme_config.get('layout', 'film_strip')
        
        if layout == 'text_list':
            return self._draw_text_list_layout(tv_list, movie_list, pc, theme_config, slogan)
        elif layout == 'card_grid':
            return self._draw_card_grid_layout(tv_list, movie_list, pc, theme_config, slogan)
        elif layout == 'waterfall':
            return self._draw_waterfall_layout(tv_list, movie_list, pc, theme_config, slogan)
        elif layout == 'hero_poster':
            return self._draw_hero_poster_layout(tv_list, movie_list, pc, theme_config, slogan)
        else:
            # 默认使用 film_strip 布局
            return self._draw_film_strip_layout(tv_list, movie_list, pc, theme_config, slogan)

    def _draw_film_strip_layout(self, tv_list, movie_list, pc, theme_config, slogan):
        """电影胶片横排布局"""
        colors = theme_config['colors']
        bg_config = theme_config['background']
        bg_colors = bg_config['colors']
        decorations = theme_config.get('decorations', [])
        
        W = 1080
        padding = 60
        
        # ========== 加载字体 ==========
        try:
            font_title = _get_font(72)          # 主标题
            font_subtitle = _get_font(22)       # 英文副标题
            font_date = _get_font(36)           # 日期
            font_weekday = _get_font(28)        # 星期
            font_section_cn = _get_font(36)     # 板块中文标题
            font_section_en = _get_font(18)     # 板块英文标题
            font_rank = _get_font(48)           # 排名数字
            font_name = _get_font(24)           # 剧名/电影名
            font_count = _get_font(18)          # 播放次数
            font_watermark = _get_font(20)      # 水印
        except:
            font_title = font_subtitle = font_date = font_weekday = font_section_cn = font_section_en = font_rank = font_name = font_count = font_watermark = ImageFont.load_default()
        
        # ========== 计算所需高度 ==========
        header_h = 200       # 报头区域
        section_h = 380      # 每个榜单区域（标题60 + 封面240 + 名称80）
        footer_h = 60        # 页脚
        
        num_sections = (1 if tv_list else 0) + (1 if movie_list else 0)
        H = header_h + num_sections * section_h + footer_h + 40
        
        # ========== 创建画布 - 应用主题背景 ==========
        bg_config = theme_config['background']
        bg_colors = bg_config['colors']
        
        img = Image.new('RGB', (W, H), bg_colors[0])
        draw = ImageDraw.Draw(img)
        
        # 绘制背景渐变
        for y in range(H):
            ratio = y / H
            r = int(bg_colors[0][0] + ratio * (bg_colors[1][0] - bg_colors[0][0]))
            g = int(bg_colors[0][1] + ratio * (bg_colors[1][1] - bg_colors[0][1]))
            b = int(bg_colors[0][2] + ratio * (bg_colors[1][2] - bg_colors[0][2]))
            draw.line([(0, y), (W, y)], fill=(r, g, b))
        
        # 绘制主题装饰
        decorations = theme_config.get('decorations', [])
        
        if 'film_holes' in decorations:
            # 电影胶片孔装饰
            hole_w, hole_h = 12, 18
            for i in range(0, H, 35):
                draw.rounded_rectangle([(15, i+8), (15 + hole_w, i+8 + hole_h)], radius=3, 
                                       fill=colors['shadow'], outline=colors['divider'])
                draw.rounded_rectangle([(W - 15 - hole_w, i+8), (W - 15, i+8 + hole_h)], radius=3, 
                                       fill=colors['shadow'], outline=colors['divider'])
        
        if 'spotlight' in decorations:
            # 顶部聚光灯效果
            for r in range(500, 0, -5):
                draw.ellipse([(-150, -250), (r*2-150, r*2-250)], 
                            fill=(bg_colors[1][0]+20, bg_colors[1][1]+15, bg_colors[1][2]+25))
            for r in range(400, 0, -4):
                draw.ellipse([(W-100, -200), (W+r*2-100, r*2-200)], 
                            fill=(bg_colors[1][0]+15, bg_colors[1][1]+10, bg_colors[1][2]+20))
        
        if 'bottom_glow' in decorations:
            # 底部光晕
            for r in range(300, 0, -4):
                draw.ellipse([(W//2 - r, H - 100), (W//2 + r, H + r)], 
                            fill=(bg_colors[1][0]+5, bg_colors[1][1]+3, bg_colors[1][2]+8))
        
        effects = theme_config.get('effects', {})
        
        if 'neon_grid' in decorations:
            # 霓虹网格
            grid_color = effects.get('grid_color', (80, 40, 120))
            for x in range(0, W, 80):
                draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
            for y in range(0, H, 80):
                draw.line([(0, y), (W, y)], fill=grid_color, width=1)
        
        if 'sun_glow' in decorations:
            # 日落太阳光晕
            sun_y = effects.get('sun_y', 100)
            glow_color = effects.get('glow_color', (255, 150, 50))
            for r in range(200, 0, -5):
                opacity = r / 200
                draw.ellipse([(W//2 - r, sun_y - r), (W//2 + r, sun_y + r)], 
                            fill=(int(glow_color[0]*opacity), int(glow_color[1]*opacity), int(glow_color[2]*opacity)))
        
        if 'wave_lines' in decorations:
            # 海洋波浪线
            wave_color = effects.get('wave_color', (30, 80, 120))
            for i in range(5):
                wave_y = H - 50 - i * 20
                for x in range(0, W, 10):
                    y_offset = int(math.sin(x * 0.05 + i) * 8)
                    draw.line([(x, wave_y + y_offset), (x + 10, wave_y + y_offset)], fill=wave_color, width=2)
        
        # ========== 顶部报头区域 ==========
        current_y = 50
        
        draw.text((padding, current_y), pc['title'], font=font_title, fill=colors['title'])
        current_y += 85
        
        date_text = pc['date_label']
        weekday_text = pc['weekday']
        draw.text((padding, current_y), date_text, font=font_date, fill=colors['date'])
        draw.text((padding + 320, current_y + 6), weekday_text, font=font_weekday, fill=colors['weekday'])
        
        draw.text((W - padding - 300, 60), pc['subtitle'], font=font_subtitle, fill=(120, 125, 140))
        draw.text((W - padding - 260, 90), slogan, font=font_count, fill=(100, 105, 120))
        
        current_y += 55
        draw.line([(padding, current_y), (W - padding, current_y)], fill=(60, 65, 80), width=2)
        current_y += 30
        
        # ========== 绘制封面排行区域的函数 ==========
        # 🔥 tv_pattern 在整个函数范围内定义
        tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)
        
        def draw_rank_section(cn_title, en_title, items, y_start):
            y = y_start
            
            # 板块标题：左侧中文 + 右侧英文
            draw.text((padding, y), cn_title, font=font_section_cn, fill=colors['section_title'])
            en_bbox = draw.textbbox((0, 0), en_title, font=font_section_en)
            en_w = en_bbox[2] - en_bbox[0]
            draw.text((W - padding - en_w, y + 10), en_title, font=font_section_en, fill=colors['section_en'])
            y += 60
            
            # 封面参数 - 更大的封面
            poster_w, poster_h = 170, 240
            gap = 15
            total_width = 5 * poster_w + 4 * gap
            start_x = (W - total_width) // 2
            
            # 层次偏移（上下错落，更有动感）
            offsets = [0, 12, -8, 10, -5]
            
            # 辅助函数：安全获取值
            def get_val(item, key, default=None):
                try:
                    return item[key] if key in item.keys() else default
                except:
                    return item.get(key, default) if hasattr(item, 'get') else default
            
            # 并行获取封面（优化性能）
            def fetch_poster_for_item(idx, item):
                item_id = get_val(item, 'ItemId')
                item_name = get_val(item, 'ItemName', '')
                is_tv = "剧集" in cn_title and tv_pattern.search(item_name)
                poster = self._get_best_poster(item_id, item_name, poster_w, poster_h, is_tv=is_tv)
                return idx, poster
            
            # 并行获取最多5个封面
            posters = {}
            items_to_process = items[:5]
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(fetch_poster_for_item, i, item) for i, item in enumerate(items_to_process)]
                for future in as_completed(futures, timeout=30):
                    try:
                        idx, poster = future.result()
                        posters[idx] = poster
                    except Exception as e:
                        logger.warning(f"[海报生成] 封面获取失败: {e}")
            
            # 获取海报圆角半径
            poster_radius = colors.get('poster_radius', 12)
            
            # 绘制封面和排名
            for i, item in enumerate(items[:5]):
                poster = posters.get(i)
                
                x = start_x + i * (poster_w + gap)
                poster_y = y + offsets[i]
                
                # 封面阴影
                shadow_offset = 6
                for s in range(3):
                    draw.rounded_rectangle(
                        [(x + shadow_offset + s, poster_y + shadow_offset + s), 
                         (x + poster_w + shadow_offset - s, poster_y + poster_h + shadow_offset - s)],
                        radius=poster_radius, fill=colors['shadow']
                    )
                
                if poster:
                    # 圆角封面
                    mask = Image.new('L', (poster_w, poster_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle([(0, 0), (poster_w, poster_h)], radius=poster_radius, fill=255)
                    
                    resized = poster.resize((poster_w, poster_h), Image.LANCZOS)
                    rounded = Image.new('RGBA', (poster_w, poster_h), (0, 0, 0, 0))
                    rounded.paste(resized, (0, 0))
                    rounded.putalpha(mask)
                    
                    img.paste(rounded.convert('RGB'), (x, poster_y), rounded.split()[3])
                else:
                    # 占位封面 - 渐变效果
                    placeholder_bg = colors['placeholder_bg']
                    for py in range(poster_h):
                        ratio = py / poster_h
                        r = int(placeholder_bg[0][0] + ratio * (placeholder_bg[1][0] - placeholder_bg[0][0]))
                        g = int(placeholder_bg[0][1] + ratio * (placeholder_bg[1][1] - placeholder_bg[0][1]))
                        b = int(placeholder_bg[0][2] + ratio * (placeholder_bg[1][2] - placeholder_bg[0][2]))
                        draw.line([(x, poster_y + py), (x + poster_w, poster_y + py)], fill=(r, g, b))
                    draw.rounded_rectangle([(x, poster_y), (x + poster_w, poster_y + poster_h)], radius=poster_radius, outline=colors['divider'], width=1)
                    draw.text((x + poster_w//2 - 36, poster_y + poster_h//2), "暂无封面", font=font_count, fill=colors['placeholder_text'])
                
                # 排名数字
                rank_text = str(i + 1)
                rank_x = x + 10
                rank_y = poster_y + 10
                
                # 排名颜色（金银铜）
                if i == 0:
                    rank_color = colors['rank_1']
                elif i == 1:
                    rank_color = colors['rank_2']
                elif i == 2:
                    rank_color = colors['rank_3']
                else:
                    rank_color = colors['rank_other']
                
                # 排名背景圆
                rank_size = 50
                draw.ellipse([(rank_x, rank_y), (rank_x + rank_size, rank_y + rank_size)], fill=colors['rank_bg'])
                draw.ellipse([(rank_x, rank_y), (rank_x + rank_size, rank_y + rank_size)], outline=rank_color, width=3)
                
                # 排名数字
                rank_bbox = draw.textbbox((0, 0), rank_text, font=font_rank)
                rank_w = rank_bbox[2] - rank_bbox[0]
                rank_h = rank_bbox[3] - rank_bbox[1]
                draw.text((rank_x + (rank_size - rank_w) // 2, rank_y + (rank_size - rank_h) // 2 - 5), 
                         rank_text, font=font_rank, fill=rank_color)
                
                # 剧名/电影名 - 封面下方
                name_y = poster_y + poster_h + 15
                name_text = get_val(item, 'SeriesName') or get_val(item, 'ItemName') or '未知'
                if len(name_text) > 8:
                    name_text = name_text[:8] + '...'
                
                # 名称居中
                name_bbox = draw.textbbox((0, 0), name_text, font=font_name)
                name_w = name_bbox[2] - name_bbox[0]
                name_x = x + (poster_w - name_w) // 2
                draw.text((name_x, name_y), name_text, font=font_name, fill=colors['name'])
                
                # 播放时长
                duration = get_val(item, 'Duration') or 0
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                if hours > 0:
                    duration_text = f"{hours}h{minutes}m"
                else:
                    duration_text = f"{minutes}分钟"
                count_bbox = draw.textbbox((0, 0), duration_text, font=font_count)
                count_w = count_bbox[2] - count_bbox[0]
                count_x = x + (poster_w - count_w) // 2
                draw.text((count_x, name_y + 32), duration_text, font=font_count, fill=colors['duration'])
            
            # 返回下一个区域的起始Y坐标
            return y + poster_h + max(offsets) + 70
        
        # ========== 热播剧集 TOP 5 ==========
        if tv_list:
            current_y = draw_rank_section("热门剧集 TOP 5", "TV SHOWS TOP 5", tv_list, current_y)
        
        # ========== 热门电影 TOP 5 ==========
        if movie_list:
            current_y = draw_rank_section("热门电影 TOP 5", "MOVIES TOP 5", movie_list, current_y)
        
        # ========== 底部页脚 ==========
        footer_y = current_y + 10
        draw.line([(padding, footer_y), (W - padding, footer_y)], fill=colors['divider'], width=1)
        
        watermark_text = "By Emby Pulse"
        bbox = draw.textbbox((0, 0), watermark_text, font=font_watermark)
        watermark_w = bbox[2] - bbox[0]
        draw.text(((W - watermark_w) // 2, footer_y + 15), watermark_text, font=font_watermark, fill=colors['watermark'])
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        return output

    def _draw_text_list_layout(self, tv_list, movie_list, pc, theme_config, slogan):
        """简约文字榜单布局 - 无需封面"""
        colors = theme_config['colors']
        bg_config = theme_config['background']
        bg_colors = bg_config['colors']
        
        W = 800
        padding = 50
        
        # 加载字体
        try:
            font_title = _get_font(48)
            font_date = _get_font(24)
            font_section = _get_font(28)
            font_rank = _get_font(32)
            font_name = _get_font(22)
            font_duration = _get_font(18)
            font_watermark = _get_font(16)
        except:
            font_title = font_date = font_section = font_rank = font_name = font_duration = font_watermark = ImageFont.load_default()
        
        # 计算高度
        header_h = 140
        row_h = 55
        section_title_h = 50
        footer_h = 50
        
        # 至少5个剧集 + 5个电影
        num_tv = min(len(tv_list) if tv_list else 0, 5)
        num_movie = min(len(movie_list) if movie_list else 0, 5)
        num_sections = (1 if tv_list else 0) + (1 if movie_list else 0)
        H = header_h + (num_tv + num_movie) * row_h + num_sections * section_title_h + footer_h + 40
        
        # 创建画布
        img = Image.new('RGB', (W, H), bg_colors[0])
        draw = ImageDraw.Draw(img)
        
        # 绘制背景渐变
        for y in range(H):
            ratio = y / H
            r = int(bg_colors[0][0] + ratio * (bg_colors[1][0] - bg_colors[0][0]))
            g = int(bg_colors[0][1] + ratio * (bg_colors[1][1] - bg_colors[0][1]))
            b = int(bg_colors[0][2] + ratio * (bg_colors[1][2] - bg_colors[0][2]))
            draw.line([(0, y), (W, y)], fill=(r, g, b))
        
        # 绘制报头
        y = 40
        draw.text((padding, y), pc['title'], font=font_title, fill=colors['title'])
        y += 60
        draw.text((padding, y), f"{pc['date_label']} {pc.get('weekday', '')}", font=font_date, fill=colors['date'])
        y += 45
        
        # 绘制分割线
        draw.line([(padding, y), (W - padding, y)], fill=colors['divider'], width=1)
        y += 20
        
        def draw_list_section(title, items, start_y, max_items=5):
            draw.text((padding, start_y), title, font=font_section, fill=colors['section_title'])
            start_y += 45
            
            for i, item in enumerate(items[:max_items]):
                # 行背景
                if i % 2 == 0:
                    draw.rounded_rectangle([(padding - 10, start_y), (W - padding + 10, start_y + row_h - 5)], 
                                          radius=8, fill=colors.get('row_bg', (250, 252, 255)))
                
                # 排名
                rank = i + 1
                rank_color = colors['rank_1'] if rank == 1 else colors['rank_2'] if rank == 2 else colors['rank_3'] if rank == 3 else colors['rank_other']
                draw.text((padding + 10, start_y + 12), f"TOP {rank}", font=font_rank, fill=rank_color)
                
                # 名称
                name = item.get('SeriesName') or item.get('ItemName') or '未知'
                if len(name) > 18:
                    name = name[:18] + '...'
                draw.text((padding + 100, start_y + 15), name, font=font_name, fill=colors['name'])
                
                # 时长
                duration = item.get('Duration', 0) or 0
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                dur_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                draw.text((W - padding - 80, start_y + 15), dur_text, font=font_duration, fill=colors['duration'])
                
                start_y += row_h
            
            return start_y + 15
        
        # 绘制剧集榜单
        if tv_list:
            y = draw_list_section("热门剧集 TOP 5", tv_list, y, 5)
        
        # 绘制电影榜单
        if movie_list:
            y = draw_list_section("热门电影 TOP 5", movie_list, y, 5)
        
        # 底部
        draw.line([(padding, y), (W - padding, y)], fill=colors['divider'], width=1)
        watermark = "By Emby Pulse"
        bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) // 2, y + 15), watermark, font=font_watermark, fill=colors['watermark'])
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        return output

    def _draw_card_grid_layout(self, tv_list, movie_list, pc, theme_config, slogan):
        """现代卡片网格布局 - 分上下两排，剧集5个 + 电影5个"""
        colors = theme_config['colors']
        bg_config = theme_config['background']
        bg_colors = bg_config['colors']
        
        W = 1200  # 加宽以容纳5个卡片
        padding = 40
        
        # 加载字体
        try:
            font_title = _get_font(48)
            font_date = _get_font(24)
            font_section = _get_font(32)
            font_rank = _get_font(22)
            font_name = _get_font(18)
            font_duration = _get_font(14)
            font_watermark = _get_font(16)
        except:
            font_title = font_date = font_section = font_rank = font_name = font_duration = font_watermark = ImageFont.load_default()
        
        # 卡片参数 - 竖版海报比例
        card_w = 200
        card_h = 320
        card_gap = 15
        poster_w, poster_h = 180, 250
        
        # 计算数量 - 自动裁切
        tv_count = min(len(tv_list) if tv_list else 0, 5)
        movie_count = min(len(movie_list) if movie_list else 0, 5)
        
        header_h = 100
        section_title_h = 50
        row_h = card_h + 30
        footer_h = 50
        
        # 根据实际内容计算高度
        num_rows = (1 if tv_count > 0 else 0) + (1 if movie_count > 0 else 0)
        H = header_h + num_rows * (row_h + section_title_h) + footer_h + 60
        
        # 创建画布
        img = Image.new('RGB', (W, H), bg_colors[0])
        draw = ImageDraw.Draw(img)
        
        # 绘制背景渐变
        for y in range(H):
            ratio = y / H
            r = int(bg_colors[0][0] + ratio * (bg_colors[1][0] - bg_colors[0][0]))
            g = int(bg_colors[0][1] + ratio * (bg_colors[1][1] - bg_colors[0][1]))
            b = int(bg_colors[0][2] + ratio * (bg_colors[1][2] - bg_colors[0][2]))
            draw.line([(0, y), (W, y)], fill=(r, g, b))
        
        # 绘制报头
        y = 30
        draw.text((padding, y), pc['title'], font=font_title, fill=colors['title'])
        draw.text((W - padding - 250, y + 15), f"{pc['date_label']}", font=font_date, fill=colors['date'])
        
        y = header_h
        
        def draw_card_row(title, items, start_y, is_tv=False):
            """绘制一行卡片"""
            draw.text((padding, start_y), title, font=font_section, fill=colors['section_title'])
            start_y += 45
            
            # 计算起始位置（居中）
            num_cards = min(len(items) if items else 0, 5)
            total_width = num_cards * card_w + (num_cards - 1) * card_gap
            start_x = (W - total_width) // 2
            
            for i, item in enumerate(items[:5]):
                card_x = start_x + i * (card_w + card_gap)
                card_y = start_y
                
                # 卡片背景
                card_bg = colors.get('card_bg', (255, 255, 255))
                draw.rounded_rectangle([(card_x, card_y), (card_x + card_w, card_y + card_h)], 
                                      radius=16, fill=card_bg)
                
                # 排名 - 金银铜圆点
                rank = i + 1
                rank_colors = [colors['rank_1'], colors['rank_2'], colors['rank_3']]
                dot_color = rank_colors[rank - 1] if rank <= 3 else colors['rank_other']
                dot_r = 12
                draw.ellipse([(card_x + 8, card_y + 8), (card_x + 8 + dot_r * 2, card_y + 8 + dot_r * 2)], fill=dot_color)
                draw.text((card_x + 8 + dot_r - 5, card_y + 8 + dot_r - 8), str(rank), font=font_name, fill=(0, 0, 0))
                
                # 获取封面
                item_id = item.get('ItemId')
                item_name = item.get('ItemName', '')
                poster = self._get_best_poster(item_id, item_name, poster_w, poster_h, is_tv=is_tv)
                
                # 绘制封面
                poster_x = card_x + (card_w - poster_w) // 2
                poster_y = card_y + 40
                
                if poster:
                    # 不拉伸，保持比例居中
                    orig_w, orig_h = poster.size
                    ratio = min(poster_w / orig_w, poster_h / orig_h)
                    new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
                    resized = poster.resize((new_w, new_h), Image.LANCZOS)
                    
                    # 居中绘制
                    paste_x = poster_x + (poster_w - new_w) // 2
                    paste_y = poster_y + (poster_h - new_h) // 2
                    
                    # 创建圆角遮罩
                    mask = Image.new('L', (new_w, new_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle([(0, 0), (new_w, new_h)], radius=10, fill=255)
                    rounded = Image.new('RGBA', (new_w, new_h), (0, 0, 0, 0))
                    rounded.paste(resized, (0, 0))
                    rounded.putalpha(mask)
                    img.paste(rounded.convert('RGB'), (paste_x, paste_y), rounded.split()[3])
                else:
                    draw.rounded_rectangle([(poster_x, poster_y), (poster_x + poster_w, poster_y + poster_h)], 
                                          radius=10, fill=colors['placeholder_bg'][0])
                    draw.text((poster_x + poster_w//2 - 30, poster_y + poster_h//2), "暂无封面", 
                             font=font_duration, fill=colors['placeholder_text'])
                
                # 名称
                name = item.get('SeriesName') or item.get('ItemName') or '未知'
                if len(name) > 10:
                    name = name[:10] + '...'
                name_bbox = draw.textbbox((0, 0), name, font=font_name)
                name_w = name_bbox[2] - name_bbox[0]
                draw.text((card_x + (card_w - name_w) // 2, card_y + card_h - 28), name, font=font_name, fill=colors['name'])
            
            return start_y + card_h + 45
        
        # 绘制剧集卡片行
        if tv_list:
            y = draw_card_row("热门剧集 TOP 5", tv_list, y, is_tv=True)
        
        # 绘制电影卡片行
        if movie_list:
            y = draw_card_row("热门电影 TOP 5", movie_list, y, is_tv=False)
        
        # 底部
        draw.line([(padding, y), (W - padding, y)], fill=colors['divider'], width=1)
        watermark = "By Emby Pulse"
        bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) // 2, y + 15), watermark, font=font_watermark, fill=colors['watermark'])
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        return output

    def _draw_waterfall_layout(self, tv_list, movie_list, pc, theme_config, slogan):
        """瀑布流布局 - 交错排列，美观现代"""
        colors = theme_config['colors']
        bg_config = theme_config['background']
        bg_colors = bg_config['colors']
        
        W = 1000
        padding = 40
        
        # 加载字体
        try:
            font_title = _get_font(48)
            font_date = _get_font(22)
            font_rank = _get_font(18)
            font_name = _get_font(16)
            font_duration = _get_font(14)
            font_watermark = _get_font(16)
        except:
            font_title = font_date = font_rank = font_name = font_duration = font_watermark = ImageFont.load_default()
        
        # 海报参数
        poster_w = 170
        poster_h = 240
        card_gap = 20
        
        # 计算需要的行数
        tv_count = min(len(tv_list) if tv_list else 0, 5)
        movie_count = min(len(movie_list) if movie_list else 0, 5)
        
        # 计算高度
        header_h = 120
        row_h = poster_h + 50  # 海报 + 名称
        num_rows = max(tv_count, movie_count)
        H = header_h + num_rows * (poster_h + 60) + 80
        
        # 创建画布
        img = Image.new('RGB', (W, H), bg_colors[0])
        draw = ImageDraw.Draw(img)
        
        # 绘制背景渐变
        for y in range(H):
            ratio = y / H
            r = int(bg_colors[0][0] + ratio * (bg_colors[1][0] - bg_colors[0][0]))
            g = int(bg_colors[0][1] + ratio * (bg_colors[1][1] - bg_colors[0][1]))
            b = int(bg_colors[0][2] + ratio * (bg_colors[1][2] - bg_colors[0][2]))
            draw.line([(0, y), (W, y)], fill=(r, g, b))
        
        # 绘制报头
        y = 35
        draw.text((padding, y), pc['title'], font=font_title, fill=colors['title'])
        draw.text((W - padding - 200, y + 15), pc['date_label'], font=font_date, fill=colors['date'])
        y = header_h
        
        # 左列标题
        if tv_list:
            draw.text((padding, y), "📺 热门剧集", font=font_name, fill=colors['section_title'])
        # 右列标题
        if movie_list:
            draw.text((W // 2 + 30, y), "🎬 热门电影", font=font_name, fill=colors['section_title'])
        y += 35
        
        # 绘制瀑布流
        left_x = padding
        right_x = W // 2 + 30
        
        for i in range(max(tv_count, movie_count)):
            row_y = y + i * (poster_h + 60)
            
            # 左列 - 剧集
            if i < tv_count and tv_list:
                item = tv_list[i]
                self._draw_waterfall_card(img, draw, item, left_x, row_y, poster_w, poster_h, 
                                         colors, font_rank, font_name, i + 1, is_tv=True)
            
            # 右列 - 电影
            if i < movie_count and movie_list:
                item = movie_list[i]
                self._draw_waterfall_card(img, draw, item, right_x, row_y, poster_w, poster_h, 
                                         colors, font_rank, font_name, i + 1, is_tv=False)
        
        # 底部
        footer_y = y + num_rows * (poster_h + 60) + 10
        draw.line([(padding, footer_y), (W - padding, footer_y)], fill=colors['divider'], width=1)
        watermark = "By Emby Pulse"
        bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) // 2, footer_y + 15), watermark, font=font_watermark, fill=colors['watermark'])
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        return output
    
    def _draw_waterfall_card(self, img, draw, item, x, y, w, h, colors, font_rank, font_name, rank, is_tv=False):
        """绘制瀑布流卡片"""
        item_id = item.get('ItemId')
        item_name = item.get('ItemName', '')
        
        # 获取封面
        poster = self._get_best_poster(item_id, item_name, w, h, is_tv=is_tv)
        
        # 卡片背景
        card_bg = colors.get('card_bg', (30, 30, 38))
        draw.rounded_rectangle([(x, y), (x + w, y + h + 35)], radius=12, fill=card_bg)
        
        # 绘制封面
        if poster:
            # 不拉伸，保持比例
            orig_w, orig_h = poster.size
            ratio = min(w / orig_w, h / orig_h)
            new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
            resized = poster.resize((new_w, new_h), Image.LANCZOS)
            
            # 居中
            paste_x = x + (w - new_w) // 2
            paste_y = y + (h - new_h) // 2
            
            # 圆角
            mask = Image.new('L', (new_w, new_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (new_w, new_h)], radius=8, fill=255)
            rounded = Image.new('RGBA', (new_w, new_h), (0, 0, 0, 0))
            rounded.paste(resized, (0, 0))
            rounded.putalpha(mask)
            img.paste(rounded.convert('RGB'), (paste_x, paste_y), rounded.split()[3])
        else:
            draw.rounded_rectangle([(x + 5, y + 5), (x + w - 5, y + h - 5)], 
                                  radius=8, fill=colors['placeholder_bg'][0])
        
        # 排名 - 金银铜圆点（简洁美观）
        rank_colors = [colors['rank_1'], colors['rank_2'], colors['rank_3']]
        dot_color = rank_colors[rank - 1] if rank <= 3 else colors['rank_other']
        dot_r = 14
        draw.ellipse([(x + 8, y + 8), (x + 8 + dot_r * 2, y + 8 + dot_r * 2)], fill=dot_color)
        draw.text((x + 8 + dot_r - 5, y + 8 + dot_r - 8), str(rank), font=font_name, fill=(0, 0, 0))
        
        # 名称
        name = item.get('SeriesName') or item.get('ItemName') or '未知'
        if len(name) > 10:
            name = name[:10] + '...'
        name_bbox = draw.textbbox((0, 0), name, font=font_name)
        name_w = name_bbox[2] - name_bbox[0]
        draw.text((x + (w - name_w) // 2, y + h + 8), name, font=font_name, fill=colors['name'])

    def _draw_hero_poster_layout(self, tv_list, movie_list, pc, theme_config, slogan):
        """宣传海报布局 - 分上下两栏，每栏5个"""
        colors = theme_config['colors']
        bg_config = theme_config['background']
        bg_colors = bg_config['colors']
        
        W = 1100
        padding = 40
        
        # 加载字体
        try:
            font_title = _get_font(48)
            font_date = _get_font(22)
            font_section = _get_font(30)
            font_rank = _get_font(20)
            font_name = _get_font(18)
            font_duration = _get_font(14)
            font_watermark = _get_font(16)
        except:
            font_title = font_date = font_section = font_rank = font_name = font_duration = font_watermark = ImageFont.load_default()
        
        # 海报参数
        poster_w, poster_h = 180, 250
        poster_gap = 15
        
        # 计算数量 - 自动裁切
        tv_count = min(len(tv_list) if tv_list else 0, 5)
        movie_count = min(len(movie_list) if movie_list else 0, 5)
        
        header_h = 100
        section_h = 50
        row_h = poster_h + 40
        footer_h = 50
        
        # 根据实际内容计算高度
        num_rows = (1 if tv_count > 0 else 0) + (1 if movie_count > 0 else 0)
        H = header_h + num_rows * (section_h + row_h) + footer_h + 60
        
        # 创建画布
        img = Image.new('RGB', (W, H), bg_colors[0])
        draw = ImageDraw.Draw(img)
        
        # 绘制背景渐变
        for y in range(H):
            ratio = y / H
            r = int(bg_colors[0][0] + ratio * (bg_colors[1][0] - bg_colors[0][0]))
            g = int(bg_colors[0][1] + ratio * (bg_colors[1][1] - bg_colors[0][1]))
            b = int(bg_colors[0][2] + ratio * (bg_colors[1][2] - bg_colors[0][2]))
            draw.line([(0, y), (W, y)], fill=(r, g, b))
        
        # 绘制报头
        y = 30
        draw.text((padding, y), pc['title'], font=font_title, fill=colors['title'])
        draw.text((W - padding - 180, y + 15), pc['date_label'], font=font_date, fill=colors['date'])
        y = header_h
        
        def draw_poster_row(title, items, start_y, is_tv=False):
            """绘制一行海报"""
            draw.text((padding, start_y), title, font=font_section, fill=colors['section_title'])
            start_y += 45
            
            # 计算5个海报的总宽度
            num_items = min(len(items) if items else 0, 5)
            if num_items == 0:
                return start_y
            
            total_width = num_items * poster_w + (num_items - 1) * poster_gap
            start_x = (W - total_width) // 2
            
            for i, item in enumerate(items[:5]):
                poster_x = start_x + i * (poster_w + poster_gap)
                poster_y = start_y
                
                item_id = item.get('ItemId')
                item_name = item.get('ItemName', '')
                
                # 获取封面
                poster = self._get_best_poster(item_id, item_name, poster_w, poster_h, is_tv=is_tv)
                
                # 绘制卡片背景
                draw.rounded_rectangle([(poster_x - 5, poster_y - 5), 
                                       (poster_x + poster_w + 5, poster_y + poster_h + 35)], 
                                      radius=12, fill=colors.get('card_bg', (30, 30, 35)))
                
                if poster:
                    # 不拉伸，保持比例
                    orig_w, orig_h = poster.size
                    ratio = min(poster_w / orig_w, poster_h / orig_h)
                    new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
                    resized = poster.resize((new_w, new_h), Image.LANCZOS)
                    
                    # 居中
                    paste_x = poster_x + (poster_w - new_w) // 2
                    paste_y = poster_y + (poster_h - new_h) // 2
                    
                    # 圆角
                    mask = Image.new('L', (new_w, new_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle([(0, 0), (new_w, new_h)], radius=8, fill=255)
                    rounded = Image.new('RGBA', (new_w, new_h), (0, 0, 0, 0))
                    rounded.paste(resized, (0, 0))
                    rounded.putalpha(mask)
                    img.paste(rounded.convert('RGB'), (paste_x, paste_y), rounded.split()[3])
                else:
                    draw.rounded_rectangle([(poster_x, poster_y), (poster_x + poster_w, poster_y + poster_h)], 
                                          radius=8, fill=colors['placeholder_bg'][0])
                    draw.text((poster_x + poster_w//2 - 30, poster_y + poster_h//2), "暂无封面", 
                             font=font_duration, fill=colors['placeholder_text'])
                
                # 排名 - 金银铜圆点
                rank = i + 1
                rank_colors = [colors['rank_1'], colors['rank_2'], colors['rank_3']]
                dot_color = rank_colors[rank - 1] if rank <= 3 else colors['rank_other']
                dot_r = 14
                draw.ellipse([(poster_x + 8, poster_y + 8), (poster_x + 8 + dot_r * 2, poster_y + 8 + dot_r * 2)], fill=dot_color)
                draw.text((poster_x + 8 + dot_r - 5, poster_y + 8 + dot_r - 8), str(rank), font=font_name, fill=(0, 0, 0))
                
                # 名称
                name = item.get('SeriesName') or item.get('ItemName') or '未知'
                if len(name) > 10:
                    name = name[:10] + '...'
                name_bbox = draw.textbbox((0, 0), name, font=font_name)
                name_w = name_bbox[2] - name_bbox[0]
                draw.text((poster_x + (poster_w - name_w) // 2, poster_y + poster_h + 10), 
                         name, font=font_name, fill=colors['name'])
            
            return start_y + poster_h + 50
        
        # 绘制剧集海报行
        if tv_list:
            y = draw_poster_row("热门剧集 TOP 5", tv_list, y, is_tv=True)
        
        # 绘制电影海报行
        if movie_list:
            y = draw_poster_row("热门电影 TOP 5", movie_list, y, is_tv=False)
        
        # 底部
        draw.line([(padding, y), (W - padding, y)], fill=colors['divider'], width=1)
        watermark = "By Emby Pulse"
        bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) // 2, y + 15), watermark, font=font_watermark, fill=colors['watermark'])
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        return output


report_gen = ReportGenerator()
