"""
观影报告插件 - 主插件类
支持日报/周报/月报/年报的定时推送和手动生成
"""
import logging
import datetime
import threading
import time
import re
from fastapi import Request
from fastapi.responses import Response
from app.plugins.base import PluginBase
from app.routers.auth import is_admin_user  # 🔒 管理员鉴权
from app.infra.clients.media_server_client import media_api
from app.infra.config.user_visibility_settings import get_hidden_users
from app.queries.report_queries import (
    count_report_distinct_users,
    count_report_plays,
    list_report_content_items,
    list_report_top_users,
    sum_report_duration,
)

logger = logging.getLogger("uvicorn")

# 用户映射表缓存（有效期5分钟）
_user_map_cache = {}
_user_map_cache_time = None
USER_MAP_CACHE_TTL = 300  # 5分钟

# 媒体库列表缓存（有效期10分钟）
_libraries_cache = []
_libraries_cache_time = None
LIBRARIES_CACHE_TTL = 600  # 10分钟


class ViewReportPlugin(PluginBase):
    id = "view_report"
    name = "观影报告"
    description = "自动生成日报/周报/月报/年报，支持自定义推送时间和报告内容"
    icon = "fa-chart-line"
    icon_color = "from-blue-500 to-purple-500"
    version = "1.0.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self.scheduler_thread = None
        self.scheduler_running = False
        self.last_check = {}  # 记录每种报告类型上次检查的时间

    def on_enable(self):
        """启用插件"""
        self.log("观影报告插件已启用", notify=False)
        self._start_scheduler()

    def on_disable(self):
        """禁用插件"""
        self.log("观影报告插件已禁用", notify=False)
        self._stop_scheduler()

    def get_config_schema(self):
        """配置项定义 - 仅保留基础设置，报告配置移到面板"""
        # 获取媒体库列表用于配置
        libraries = self._get_libraries()
        library_options = [{"value": lib['id'], "label": lib['name']} for lib in libraries]
        
        return [
            {"key": "top_users_limit", "label": "用户排行数量", "type": "text", "default": "10",
             "hint": "文字报告中显示的用户排行数量", "group": "基础设置"},
            {"key": "top_content_limit", "label": "内容排行数量", "type": "text", "default": "10",
             "hint": "文字报告中显示的内容排行数量", "group": "基础设置"},
            {"key": "exclude_types", "label": "排除媒体类型", "type": "multiselect",
             "options": [
                 {"value": "Audio", "label": "🎵 音乐"},
                 {"value": "MusicVideo", "label": "🎬 MV"},
                 {"value": "Book", "label": "📚 书籍"},
                 {"value": "Photo", "label": "📷 照片"},
                 {"value": "Trailer", "label": "🎞️ 预告片"},
                 {"value": "LiveTvChannel", "label": "📺 直播频道"},
             ],
             "default": ["Audio", "MusicVideo"],
             "hint": "排除的音乐和其他媒体类型，不参与统计", "group": "基础设置"},
            {"key": "exclude_libraries", "label": "排除媒体库", "type": "multiselect",
             "options": library_options,
             "default": [],
             "hint": "排除的媒体库，不参与排行统计", "group": "基础设置"},
        ]
    
    def get_report_config_schema(self, report_type: str) -> list:
        """获取特定报告类型的配置项"""
        period_options = {
            'daily': [{"value": "yesterday", "label": "昨天"}, {"value": "today", "label": "今天"}],
            'weekly': [{"value": "last_week", "label": "上周"}, {"value": "this_week", "label": "本周"}],
            'monthly': [{"value": "last_month", "label": "上月"}, {"value": "this_month", "label": "本月"}]
        }
        default_cron = {'daily': '0 9 * * *', 'weekly': '0 9 * * 1', 'monthly': '0 9 1 * *'}
        default_period = {'daily': 'yesterday', 'weekly': 'last_week', 'monthly': 'last_month'}
        
        # 主题选项
        theme_options = [
            {"value": "cinema", "label": "🎞️ 电影胶片"},
            {"value": "neon", "label": "💜 霓虹都市"},
            {"value": "sunset", "label": "🌅 日落橙"},
            {"value": "ocean", "label": "🌊 深海蓝"},
            {"value": "forest", "label": "🌲 森林绿"},
            {"value": "waterfall", "label": "🎪 瀑布流"},
            {"value": "grid", "label": "📱 卡片网格"},
            {"value": "list", "label": "📝 简约榜单"},
            {"value": "poster", "label": "🎬 宣传海报"},
        ]
        
        schema = [
            {"key": f"{report_type}_enabled", "label": f"启用{report_type == 'daily' and '日报' or report_type == 'weekly' and '周报' or '月报'}", "type": "toggle", "default": False},
            {"key": f"{report_type}_period", "label": "统计范围", "type": "select", "default": default_period.get(report_type),
             "options": period_options.get(report_type, [])},
            {"key": f"{report_type}_cron", "label": "推送时间", "type": "text", "default": default_cron.get(report_type)},
            {"key": f"{report_type}_poster", "label": "生成海报", "type": "toggle", "default": True},
            {"key": f"{report_type}_theme", "label": "海报主题", "type": "select", "default": "cinema",
             "options": theme_options},
            {"key": f"{report_type}_channels", "label": "推送渠道", "type": "multiselect",
             "options": [{"value": "telegram", "label": "Telegram"}, {"value": "wecom", "label": "企业微信"}],
             "default": ["telegram", "wecom"]},
            {"key": f"{report_type}_push_channels", "label": "推送到频道", "type": "toggle", "default": False},
            {"key": f"{report_type}_show_stats", "label": "显示统计数据", "type": "toggle", "default": True},
        ]
        if report_type in ['weekly', 'monthly']:
            schema.append({"key": f"{report_type}_show_avg_daily", "label": "显示日均播放", "type": "toggle", "default": True})
        schema.extend([
            {"key": f"{report_type}_show_top_users", "label": "显示用户排行", "type": "toggle", "default": True},
            {"key": f"{report_type}_show_top_tv", "label": "显示剧集排行", "type": "toggle", "default": True},
            {"key": f"{report_type}_show_top_movies", "label": "显示电影排行", "type": "toggle", "default": True},
        ])
        return schema

    def _start_scheduler(self):
        """启动调度器"""
        if self.scheduler_running:
            return
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info(f"[{self.name}] 调度器已启动")

    def _stop_scheduler(self):
        """停止调度器"""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info(f"[{self.name}] 调度器已停止")

    def _scheduler_loop(self):
        """调度循环 - 每分钟检查一次"""
        while self.scheduler_running:
            try:
                now = datetime.datetime.now()
                now_str = now.strftime("%Y-%m-%d %H:%M")
                
                config = self._get_config()
                
                for report_type in ['daily', 'weekly', 'monthly']:
                    if config.get(f'{report_type}_enabled'):
                        cron_expr = config.get(f'{report_type}_cron', self._get_default_cron(report_type))
                        if self._should_trigger(report_type, cron_expr, now):
                            self.log(f"触发 {self._get_report_name(report_type)} 推送", notify=False)
                            self._send_report_async(report_type)
                
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"[{self.name}] 调度器异常: {e}")
                time.sleep(60)

    def _get_default_cron(self, report_type: str) -> str:
        """获取默认 cron 表达式"""
        defaults = {
            'daily': '0 9 * * *',
            'weekly': '0 9 * * 1',
            'monthly': '0 9 1 * *'
        }
        return defaults.get(report_type, '0 9 * * *')

    def _should_trigger(self, report_type: str, cron_expr: str, now: datetime.datetime) -> bool:
        """检查是否应该触发报告（不依赖 croniter）"""
        try:
            # 如果 cron_expr 为空或无效，使用默认值
            if not cron_expr or not cron_expr.strip():
                cron_expr = self._get_default_cron(report_type)
            
            # 解析 cron 表达式：分 时 日 月 周
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                # 不打印错误日志，静默使用默认值
                cron_expr = self._get_default_cron(report_type)
                parts = cron_expr.split()
            
            minute, hour, day_of_month, month, day_of_week = parts
            current_minute_start = now.replace(second=0, microsecond=0)
            last_run_key = f"last_run_{report_type}"
            last_run = self.last_check.get(last_run_key)
            
            # 检查是否匹配
            matches = True
            
            # 分钟检查
            if minute != '*':
                try:
                    if int(minute) != now.minute:
                        matches = False
                except ValueError:
                    pass
            
            # 小时检查
            if matches and hour != '*':
                try:
                    if int(hour) != now.hour:
                        matches = False
                except ValueError:
                    pass
            
            # 日期检查
            if matches and day_of_month != '*':
                try:
                    if int(day_of_month) != now.day:
                        matches = False
                except ValueError:
                    pass
            
            # 月份检查
            if matches and month != '*':
                try:
                    if int(month) != now.month:
                        matches = False
                except ValueError:
                    pass
            
            # 星期检查 (0=周日, 1-6=周一到周六)
            if matches and day_of_week != '*':
                try:
                    # Python weekday: 0=周一, 6=周日; cron: 0=周日, 1-6=周一到周六
                    python_weekday = now.weekday()  # 0=周一, 6=周日
                    cron_weekday = int(day_of_week)  # 0=周日, 1-6=周一到周六
                    # 转换：如果 cron 是 0（周日），对应 Python weekday 6
                    if cron_weekday == 0:
                        if python_weekday != 6:
                            matches = False
                    else:
                        if python_weekday != cron_weekday - 1:
                            matches = False
                except ValueError:
                    pass
            
            # 如果匹配且不在同一分钟内重复触发
            if matches:
                current_str = current_minute_start.strftime("%Y-%m-%d %H:%M")
                if last_run != current_str:
                    self.last_check[last_run_key] = current_str
                    return True
            
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 解析 cron 表达式失败: {cron_expr}, 错误: {e}")
            return False

    def _send_report_async(self, report_type: str):
        """异步发送报告"""
        def _send():
            try:
                self.generate_and_send(report_type)
            except Exception as e:
                self.log(f"发送 {report_type} 失败: {e}", level="error")
        
        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def _get_report_name(self, report_type: str) -> str:
        """获取报告中文名称"""
        names = {
            'daily': '日报',
            'weekly': '周报',
            'monthly': '月报'
        }
        return names.get(report_type, report_type)

    def _get_period_filter(self, report_type: str) -> tuple:
        """获取时间范围过滤条件 - 使用统一的时间计算模块"""
        config = self._get_config()
        
        # 🔥 从配置获取 period 设置
        if report_type == 'daily':
            period_setting = config.get('daily_period', 'yesterday')
        elif report_type == 'weekly':
            period_setting = config.get('weekly_period', 'last_week')
        elif report_type == 'monthly':
            period_setting = config.get('monthly_period', 'last_month')
        else:
            period_setting = 'yesterday'
        
        # 🔥 使用统一的时间计算模块
        from app.services.time_utils import get_period_range, get_period_from_report_config
        
        period = get_period_from_report_config(report_type, period_setting)
        start_date, end_date, where_sql, title_text = get_period_range(period)
        
        # 格式化日期字符串
        if report_type == 'daily':
            date_str = (start_date or datetime.date.today()).strftime("%Y-%m-%d")
        elif report_type == 'weekly':
            if start_date and end_date:
                date_str = f"{start_date.strftime('%m-%d')} ~ {(end_date - datetime.timedelta(days=1)).strftime('%m-%d')}"
            else:
                date_str = ""
        elif report_type == 'monthly':
            if start_date:
                date_str = start_date.strftime("%Y年%m月")
            else:
                date_str = ""
        else:
            date_str = ""
        
        return where_sql, title_text, date_str

    def _get_user_map(self) -> dict:
        """批量获取用户映射表（带5分钟缓存）"""
        global _user_map_cache, _user_map_cache_time
        
        now = time.time()
        # 检查缓存是否有效
        if _user_map_cache and _user_map_cache_time and (now - _user_map_cache_time) < USER_MAP_CACHE_TTL:
            return _user_map_cache
        
        try:
            res = media_api.get("/Users", timeout=3)
            if res.status_code == 200:
                user_map = {u['Id']: u['Name'] for u in res.json()}
                _user_map_cache = user_map
                _user_map_cache_time = now
                logger.info(f"[观影报告] 批量获取用户映射: {len(user_map)} 个用户")
                return user_map
        except Exception as e:
            logger.warning(f"[观影报告] 获取用户映射失败: {e}")
        
        return {}

    def _get_libraries(self) -> list:
        """获取媒体库列表（带10分钟缓存），包含路径信息"""
        global _libraries_cache, _libraries_cache_time
        
        now = time.time()
        # 检查缓存是否有效
        if _libraries_cache and _libraries_cache_time and (now - _libraries_cache_time) < LIBRARIES_CACHE_TTL:
            return _libraries_cache
        
        try:
            res = media_api.get("/Library/VirtualFolders", timeout=5)
            if res.status_code == 200:
                libraries = []
                for lib in res.json():
                    lib_id = lib.get("ItemId") or lib.get("Id")
                    lib_name = lib.get("Name", "未命名")
                    # 🔥 获取媒体库的路径列表
                    locations = lib.get("Locations", []) or []
                    if lib_id:
                        libraries.append({
                            "id": lib_id, 
                            "name": lib_name,
                            "locations": locations  # 路径列表
                        })
                _libraries_cache = libraries
                _libraries_cache_time = now
                logger.info(f"[观影报告] 获取媒体库列表: {len(libraries)} 个")
                return libraries
        except Exception as e:
            logger.warning(f"[观影报告] 获取媒体库列表失败: {e}")
        
        return []

    def _get_item_library(self, item_id: str, libraries: list) -> str:
        """通过路径匹配获取媒体项所属的媒体库ID"""
        if not item_id or not libraries:
            return None
        
        try:
            # 获取用户ID
            res = media_api.get("/Users", timeout=3)
            if res.status_code != 200:
                return None
            users = res.json()
            user_id = users[0]['Id'] if users else None
            if not user_id:
                return None
            
            # 获取媒体项详情
            item_res = media_api.get(f"/Users/{user_id}/Items/{item_id}", timeout=3)
            if item_res.status_code != 200:
                return None
            
            item_data = item_res.json()
            item_path = item_data.get("Path", "")
            
            if not item_path:
                return None
            
            # 🔥 通过路径匹配判断属于哪个媒体库
            for lib in libraries:
                lib_id = lib.get("id")
                lib_locations = lib.get("locations", [])
                for loc in lib_locations:
                    if item_path.startswith(loc):
                        return lib_id
            
            return None
        except Exception as e:
            logger.debug(f"[观影报告] 获取媒体项库ID失败: {e}")
        
        return None

    def _query_stats(self, report_type: str) -> dict:
        """查询统计数据"""
        config = self._get_config()
        where, title, date_str = self._get_period_filter(report_type)
        
        # 获取排除的媒体类型（默认不排除任何类型）
        exclude_types = config.get('exclude_types', [])
        if isinstance(exclude_types, str):
            exclude_types = [t.strip() for t in exclude_types.split(',') if t.strip()]
        # 如果配置为空或 None，使用空列表
        if not exclude_types:
            exclude_types = []
        
        # 🔥 获取排行黑名单用户（与机器人命令一致）
        hidden_users = get_hidden_users()
        
        # 调试日志
        logger.info(f"[观影报告] exclude_types 配置: {exclude_types}, hidden_users: {hidden_users}")
        
        # 构建排除类型 SQL
        exclude_sql = ""
        exclude_params = []
        if exclude_types:
            exclude_placeholders = ', '.join(['?' for _ in exclude_types])
            exclude_sql += f" AND ItemType NOT IN ({exclude_placeholders})"
            exclude_params.extend(exclude_types)
        
        # 🔥 构建黑名单用户排除 SQL
        if hidden_users:
            hidden_placeholders = ', '.join(['?' for _ in hidden_users])
            exclude_sql += f" AND UserId NOT IN ({hidden_placeholders})"
            exclude_params.extend(hidden_users)
        report_where = f"{where}{exclude_sql}"
        report_params = tuple(exclude_params) if exclude_params else ()
        
        # 计算天数（用于日均播放量）- 使用统一的时间计算
        from app.services.time_utils import get_period_days, get_period_from_report_config
        
        if report_type == 'daily':
            period_setting = config.get('daily_period', 'yesterday')
        elif report_type == 'weekly':
            period_setting = config.get('weekly_period', 'last_week')
        elif report_type == 'monthly':
            period_setting = config.get('monthly_period', 'last_month')
        else:
            period_setting = 'yesterday'
        
        period = get_period_from_report_config(report_type, period_setting)
        days = get_period_days(period)
        
        # 排行数量 - 处理空字符串或无效值
        try:
            users_limit = int(config.get('top_users_limit') or 5)
        except (ValueError, TypeError):
            users_limit = 5
        try:
            content_limit = int(config.get('top_content_limit') or 5)
        except (ValueError, TypeError):
            content_limit = 5
        
        # 根据报告类型调整排行数量
        if report_type == 'weekly':
            users_limit = min(users_limit, 10)
            content_limit = min(content_limit, 10)
        elif report_type == 'monthly':
            users_limit = min(users_limit, 10)
            content_limit = min(content_limit, 10)
        
        # 总播放量（排除指定类型和黑名单用户）
        total_plays = count_report_plays(report_where, report_params)
        
        # 总播放时长（排除指定类型和黑名单用户）
        total_duration = sum_report_duration(report_where, report_params)
        # 🔥 使用标准四舍五入（与 JavaScript toFixed 一致）
        total_hours = round(total_duration / 3600, 1)
        
        # 活跃用户数（排除指定类型和黑名单用户）
        active_users = count_report_distinct_users(report_where, report_params)
        
        # 日均播放量
        avg_daily_plays = round(total_plays / days, 1) if days > 0 else total_plays
        
        # 🔥 批量获取用户映射表（一次请求替代多次）
        user_map = self._get_user_map()
        
        # 活跃用户排行（排除指定类型和黑名单用户）
        top_users_res = list_report_top_users(report_where, report_params, users_limit)
        top_users_list = []
        for i, u in enumerate(top_users_res or []):
            # 🔥 使用批量获取的映射表
            user_id = u['UserId']
            name = user_map.get(user_id, user_id[:8] if len(user_id) > 8 else user_id)
            # 🔥 使用格式化字符串，确保四舍五入与前端一致
            h_str = f"{u['t'] / 3600:.1f}"
            medal = ['🥇', '🥈', '🥉'][i] if i < 3 else f"{i+1}."
            top_users_list.append(f"{medal} {name} ({h_str}h)")
        top_users_str = "\n".join(top_users_list) if top_users_list else "暂无数据"
        
        # 热门内容 - 区分剧集和电影（按时长排序，排除指定类型和黑名单用户）
        # 🔥 增加查询数量，为媒体库过滤预留空间
        query_limit = max(200, content_limit * 10)
        all_content = list_report_content_items(report_where, report_params, query_limit)
        
        # 🔥 获取排除的媒体库配置
        exclude_libraries = config.get('exclude_libraries', [])
        if isinstance(exclude_libraries, str):
            exclude_libraries = [l.strip() for l in exclude_libraries.split(',') if l.strip()]
        
        # 🔥 批量获取媒体项的库ID（通过路径匹配）
        item_library_cache = {}
        if exclude_libraries and all_content:
            # 获取媒体库列表（包含路径）
            libraries = self._get_libraries()
            
            # 收集所有唯一的 ItemId
            item_ids = list(set(item['ItemId'] for item in all_content if item.get('ItemId')))
            
            # 批量查询
            for item_id in item_ids[:50]:
                lib_id = self._get_item_library(item_id, libraries)
                if lib_id:
                    item_library_cache[item_id] = lib_id
        
        # 分离剧集和电影，并合并同一剧集的不同集
        tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)
        tv_list = []
        movie_list = []
        
        for item in all_content or []:
            # 🔥 检查是否在排除的媒体库中
            if exclude_libraries:
                item_id = item.get('ItemId')
                lib_id = item_library_cache.get(item_id)
                if lib_id and lib_id in exclude_libraries:
                    continue  # 跳过该媒体库的内容
            
            name = item['ItemName'] if item['ItemName'] else ''
            # 提取剧集名称（去掉集数后缀）
            series_name = name.split(' - ')[0] if ' - ' in name else name
            
            if tv_pattern.search(name) or item['ItemType'] == 'Episode':
                # 检查是否已存在同一剧集
                existing = [t for t in tv_list if t.get('SeriesName') == series_name]
                if not existing and len(tv_list) < content_limit:
                    # 添加 SeriesName 字段用于合并判断
                    item_dict = dict(item)
                    item_dict['SeriesName'] = series_name
                    tv_list.append(item_dict)
                elif existing:
                    # 合并时长和播放次数
                    existing[0]['C'] += item['C'] if 'C' in item.keys() else 0
                    existing[0]['Duration'] += item['Duration'] if 'Duration' in item.keys() else 0
            else:
                if len(movie_list) < content_limit:
                    movie_list.append(dict(item))
            
            # 当两个列表都满了才停止
            if len(tv_list) >= content_limit and len(movie_list) >= content_limit:
                break
        
        # 重新按时长排序（合并后顺序可能变化）
        tv_list.sort(key=lambda x: x['Duration'] if 'Duration' in x.keys() else 0, reverse=True)
        movie_list.sort(key=lambda x: x['Duration'] if 'Duration' in x.keys() else 0, reverse=True)
        
        # 格式化剧集排行（与机器人命令格式一致）
        top_tv_str = ""
        for i, item in enumerate(tv_list):
            name = item.get('SeriesName') or item.get('ItemName') or '未知'
            name = name[:20]
            d = item['Duration'] if 'Duration' in item.keys() else 0
            h = int(d // 3600)
            m = int((d % 3600) // 60)
            if h > 0:
                dur_str = f"{h} 小时 {m} 分钟"
            else:
                dur_str = f"{m} 分钟"
            count = item['C'] if 'C' in item.keys() else 0
            top_tv_str += f"{i+1}. {name}\n播放次数: {count} 时长: {dur_str}\n"
        if not top_tv_str:
            top_tv_str = "暂无数据"
        
        # 格式化电影排行（与机器人命令格式一致）
        top_movies_str = ""
        for i, item in enumerate(movie_list):
            name = (item['ItemName'] or '未知')[:20]
            d = item['Duration'] if 'Duration' in item.keys() else 0
            h = int(d // 3600)
            m = int((d % 3600) // 60)
            if h > 0:
                dur_str = f"{h} 小时 {m} 分钟"
            else:
                dur_str = f"{m} 分钟"
            count = item['C'] if 'C' in item.keys() else 0
            top_movies_str += f"{i+1}. {name}\n播放次数: {count} 时长: {dur_str}\n"
        if not top_movies_str:
            top_movies_str = "暂无数据"
        
        return {
            'total_plays': total_plays,
            'total_hours': total_hours,
            'active_users': active_users,
            'avg_daily_plays': avg_daily_plays,
            'top_users': top_users_str,
            'top_users_count': len(top_users_list),
            'top_tv': top_tv_str.strip(),
            'top_movies': top_movies_str.strip(),
            'title': title,
            'date_str': date_str,
            'days': days,
            # 🔥 原始数据列表，供海报使用
            'tv_list_raw': tv_list,
            'movie_list_raw': movie_list
        }

    def _render_template(self, report_type: str, stats: dict) -> str:
        """渲染报告模板"""
        config = self._get_config()
        
        # 构建报告内容
        lines = []
        lines.append(f"📊 <b>EmbyPulse {stats['title']}</b>")
        lines.append(f"📅 {stats['date_str']}")
        lines.append("")
        
        # 数据大盘
        show_stats = config.get(f'{report_type}_show_stats', True)
        if show_stats:
            lines.append("📈 <b>数据大盘</b>")
            lines.append(f"▶️ 总播放量：{stats['total_plays']} 次")
            lines.append(f"⏱️ 活跃时长：{stats['total_hours']} 小时")
            lines.append(f"👥 活跃人数：{stats['active_users']} 人")
            # 日均播放量（仅周报/月报/年报显示）
            if report_type in ['weekly', 'monthly', 'yearly']:
                show_avg = config.get(f'{report_type}_show_avg_daily', True)
                if show_avg:
                    lines.append(f"📊 日均播放：{stats['avg_daily_plays']} 次")
            lines.append("")
        
        # 用户排行
        show_users = config.get(f'{report_type}_show_top_users', True)
        if show_users:
            lines.append(f"🏆 <b>活跃用户 Top {stats['top_users_count']}</b>")
            lines.append(stats['top_users'])
            lines.append("")
        
        # 剧集排行
        show_tv = config.get(f'{report_type}_show_top_tv', True)
        if show_tv and stats.get('top_tv'):
            lines.append("📺 <b>剧集排名</b>")
            lines.append(stats['top_tv'])
            lines.append("")
        
        # 电影排行
        show_movies = config.get(f'{report_type}_show_top_movies', True)
        if show_movies and stats.get('top_movies'):
            lines.append("🎬 <b>电影排名</b>")
            lines.append(stats['top_movies'])
        
        return "\n".join(lines)

    def _generate_poster(self, report_type: str, stats: dict, theme: str = None):
        """生成海报图片 - 支持主题选择"""
        try:
            from app.services.report_service import report_gen, HAS_PIL
            if not HAS_PIL:
                return None
            
            config = self._get_config()
            
            # 获取主题配置
            if theme is None:
                theme = config.get(f'{report_type}_theme', 'cinema')
            
            # 根据 report_type 和配置的 period 决定海报时间范围
            if report_type == 'daily':
                period = config.get('daily_period', 'yesterday')  # yesterday 或 today
            elif report_type == 'weekly':
                weekly_period = config.get('weekly_period', 'last_week')
                period = 'week' if weekly_period == 'this_week' else 'weekly'  # weekly = 上周, week = 本周
            elif report_type == 'monthly':
                monthly_period = config.get('monthly_period', 'last_month')
                period = 'month' if monthly_period == 'this_month' else 'monthly'  # monthly = 上月, month = 本月
            elif report_type == 'yearly':
                period = 'yearly'  # 年报
            else:
                period = 'yesterday'
            
            # 使用 stats 中的原始数据生成海报，确保数据一致性
            tv_list = stats.get('tv_list_raw', [])
            movie_list = stats.get('movie_list_raw', [])
            
            poster = report_gen.generate_daily_poster(period, tv_list, movie_list, theme)
            return poster
        except Exception as e:
            logger.error(f"[{self.name}] 生成海报失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def generate_report(self, report_type: str) -> dict:
        """生成报告（供预览和外部调用）"""
        stats = self._query_stats(report_type)
        text = self._render_template(report_type, stats)
        
        config = self._get_config()
        poster_enabled = config.get(f'{report_type}_poster', True)
        poster = None
        if poster_enabled:
            poster = self._generate_poster(report_type, stats)
        
        return {
            'type': report_type,
            'title': stats['title'],
            'date_str': stats['date_str'],
            'text': text,
            'stats': stats,
            'has_poster': poster is not None
        }

    def generate_and_send(self, report_type: str):
        """生成并发送报告"""
        config = self._get_config()
        
        # 查询统计数据
        stats = self._query_stats(report_type)
        self.log(f"查询统计完成: 播放{stats['total_plays']}次, 时长{stats['total_hours']}h", notify=False)
        
        # 如果没有播放数据，跳过发送
        if stats['total_plays'] == 0:
            self.log(f"{self._get_report_name(report_type)}：无播放数据，跳过发送", notify=False)
            return
        
        # 渲染文本
        text = self._render_template(report_type, stats)
        self.log(f"文本渲染完成，长度: {len(text)}", notify=False)
        
        # 生成海报
        poster_enabled = config.get(f'{report_type}_poster', True)
        poster = None
        if poster_enabled:
            poster = self._generate_poster(report_type, stats)
            self.log(f"海报生成: {'成功' if poster else '失败或无数据'}", notify=False)
        
        # 获取推送渠道 - 支持字符串和列表两种格式
        channels = config.get(f'{report_type}_channels')
        if channels is None:
            channels = ['telegram', 'wecom']
        elif isinstance(channels, str):
            channels = [c.strip() for c in channels.split(',') if c.strip()]
        elif not isinstance(channels, list):
            channels = ['telegram', 'wecom']
        
        # 额外推送渠道：频道推送
        push_to_channels = config.get(f'{report_type}_push_channels', False)
        
        self.log(f"推送渠道: {channels}, 频道推送: {push_to_channels}", notify=False)
        
        # 发送
        try:
            from app.services.bot_service import bot
            self.log(f"bot 实例: {bot}, 类型: {type(bot)}", notify=False)
            
            # 判断是否需要发送到企微和TG
            send_to_tg = 'telegram' in channels
            send_to_wecom = 'wecom' in channels
            
            if poster:
                if send_to_tg and send_to_wecom:
                    # 同时发送两个渠道
                    bot.send_photo("sys_notify", poster, text, platform="all")
                    self.log("发送到 telegram 和企业微信 成功", notify=False)
                elif send_to_tg:
                    # 只发送TG
                    bot.send_photo("sys_notify", poster, text, platform="tg")
                    self.log("发送到 telegram 成功", notify=False)
                elif send_to_wecom:
                    # 只发送企微
                    bot.send_photo("sys_notify", poster, text, platform="wecom")
                    self.log("发送到企业微信 成功", notify=False)
                
                # 推送到频道
                if push_to_channels:
                    try:
                        bot.send_to_channels(poster, text)
                        self.log("发送到频道 成功", notify=False)
                    except Exception as e:
                        logger.error(f"[{self.name}] 推送到频道失败: {e}")
            else:
                if send_to_tg and send_to_wecom:
                    bot.send_message("sys_notify", text, platform="all")
                    self.log("发送到 telegram 和企业微信 成功", notify=False)
                elif send_to_tg:
                    bot.send_message("sys_notify", text, platform="tg")
                    self.log("发送到 telegram 成功", notify=False)
                elif send_to_wecom:
                    bot.send_message("sys_notify", text, platform="wecom")
                    self.log("发送到企业微信 成功", notify=False)
                
                # 推送到频道（纯文本）
                if push_to_channels:
                    try:
                        bot.send_to_channels(None, text)
                        self.log("发送到频道 成功", notify=False)
                    except Exception as e:
                        logger.error(f"[{self.name}] 推送到频道失败: {e}")
            
            self.log(f"{self._get_report_name(report_type)} 已发送 (播放: {stats['total_plays']}次, 时长: {stats['total_hours']}h)", notify=True)
        except Exception as e:
            logger.error(f"[{self.name}] generate_and_send 异常: {e}")
            import traceback
            traceback.print_exc()
            self.log(f"发送 {self._get_report_name(report_type)} 失败: {e}", level="error")

    # ========== API 方法 ==========
    
    def api_preview(self, report_type: str) -> dict:
        """预览报告（API 调用）"""
        return self.generate_report(report_type)
    
    def api_send(self, report_type: str) -> dict:
        """手动发送报告（API 调用）"""
        try:
            logger.info(f"[{self.name}] api_send 开始: report_type={report_type}")
            self.log(f"开始生成 {self._get_report_name(report_type)}...", notify=False)
            
            # 先检查是否有播放数据
            stats = self._query_stats(report_type)
            logger.info(f"[{self.name}] 统计数据: 播放{stats['total_plays']}次, 时长{stats['total_hours']}h")
            self.log(f"统计数据: 播放{stats['total_plays']}次, 时长{stats['total_hours']}h", notify=False)
            
            if stats['total_plays'] == 0:
                logger.info(f"[{self.name}] 无播放数据，返回")
                return {'success': False, 'message': f'{self._get_report_name(report_type)}：无播放数据'}
            
            logger.info(f"[{self.name}] 调用 generate_and_send")
            self.generate_and_send(report_type)
            logger.info(f"[{self.name}] generate_and_send 完成")
            return {'success': True, 'message': f'{self._get_report_name(report_type)} 已发送'}
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"[{self.name}] 发送报告失败:\n{error_detail}")
            self.log(f"发送失败: {str(e)}", level="error", notify=False)
            return {'success': False, 'message': f'{str(e)}'}
    
    def api_get_schedule_status(self) -> dict:
        """获取调度状态"""
        config = self._get_config()
        status = {}
        for report_type in ['daily', 'weekly', 'monthly', 'yearly']:
            enabled = config.get(f'{report_type}_enabled', False)
            cron = config.get(f'{report_type}_cron', self._get_default_cron(report_type))
            last_run = self.last_check.get(f"last_run_{report_type}", "从未运行")
            status[report_type] = {
                'enabled': enabled,
                'cron': cron,
                'last_run': last_run
            }
        return status


# 创建插件实例
plugin = ViewReportPlugin()


@plugin.router.get("/config")
async def get_config(request: Request):
    """获取插件配置"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    from app.plugins import get_plugin_config
    return {
        "status": "success",
        "data": {
            "schema": plugin.get_config_schema(),
            "values": get_plugin_config(plugin.id)
        }
    }


@plugin.router.get("/report_config/{report_type}")
async def get_report_config(request: Request, report_type: str):
    """获取特定报告类型的配置"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    if report_type not in ['daily', 'weekly', 'monthly']:
        return {"status": "error", "message": "无效的报告类型"}
    
    from app.plugins import get_plugin_config
    all_config = get_plugin_config(plugin.id)
    schema = plugin.get_report_config_schema(report_type)
    
    # 提取该报告类型的配置值
    values = {}
    for field in schema:
        key = field['key']
        values[key] = all_config.get(key, field.get('default'))
    
    # 获取调度状态
    status = plugin.api_get_schedule_status().get(report_type, {})
    
    return {
        "status": "success",
        "data": {
            "schema": schema,
            "values": values,
            "status": status
        }
    }


@plugin.router.post("/report_config/{report_type}")
async def update_report_config(report_type: str, request: Request):
    """更新特定报告类型的配置"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    if report_type not in ['daily', 'weekly', 'monthly']:
        return {"status": "error", "message": "无效的报告类型"}
    
    from app.plugins import get_plugin_config, save_plugin_config
    
    try:
        data = await request.json()
    except:
        return {"status": "error", "message": "无效的请求数据"}
    
    # 获取现有配置并合并
    current_config = get_plugin_config(plugin.id)
    
    # 处理渠道列表格式
    for key, value in data.items():
        if key.endswith('_channels') and isinstance(value, list):
            data[key] = ','.join(value)
        # 🔥 处理排除媒体库列表
        elif key == 'exclude_libraries' and isinstance(value, list):
            data[key] = ','.join(value)
    
    current_config.update(data)
    save_plugin_config(plugin.id, current_config)
    
    return {"status": "success", "message": "配置已更新"}


@plugin.router.post("/config")
async def update_config(request: Request):
    """更新插件配置"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    from app.plugins import save_plugin_config
    
    # 直接获取 JSON body，避免 Pydantic 验证问题
    try:
        data = await request.json()
    except:
        return {"status": "error", "message": "无效的请求数据"}
    
    config = {}
    
    # 处理所有配置项
    for key, value in data.items():
        # 处理渠道列表：支持字符串和数组两种格式
        if key.endswith('_channels') and isinstance(value, str):
            # 前端可能发送 "telegram,wecom" 或 "['telegram','wecom']"
            if value.startswith('['):
                try:
                    import json
                    value = json.loads(value)
                    value = ','.join(value)
                except:
                    pass
            config[key] = value
        elif key.endswith('_channels') and isinstance(value, list):
            config[key] = ','.join(value)
        # 🔥 处理排除媒体库列表
        elif key == 'exclude_libraries' and isinstance(value, list):
            config[key] = ','.join(value)
        elif key == 'exclude_libraries' and isinstance(value, str) and value.startswith('['):
            try:
                import json
                value = json.loads(value)
                config[key] = ','.join(value) if isinstance(value, list) else value
            except:
                config[key] = value
        else:
            config[key] = value
    
    # 直接保存配置，不合并
    save_plugin_config(plugin.id, config)
    
    # 配置已保存到缓存，调度器会在下次检查时读取新配置，无需重启
    
    return {"status": "success", "message": "配置已更新", "data": {"values": config}}


@plugin.router.get("/preview/{report_type}")
async def preview_report(request: Request, report_type: str):
    """预览报告"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    if report_type not in ['daily', 'weekly', 'monthly']:
        return {"success": False, "message": "无效的报告类型"}
    try:
        result = plugin.api_preview(report_type)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}


@plugin.router.get("/preview/{report_type}/poster")
async def preview_poster(request: Request, report_type: str, theme: str = 'cinema'):
    """预览海报图片 - 支持主题选择"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    if report_type not in ['daily', 'weekly', 'monthly']:
        return {"success": False, "message": "无效的报告类型"}
    try:
        from app.services.report_service import report_gen, HAS_PIL
        if not HAS_PIL:
            return {"success": False, "message": "Pillow 未安装"}
        
        # 使用统一数据源：先查询统计数据
        stats = plugin._query_stats(report_type)
        if stats['total_plays'] == 0:
            return {"success": False, "message": "无播放数据"}
        
        # 根据 report_type 和配置决定 period
        config = plugin._get_config()
        if report_type == 'daily':
            period = config.get('daily_period', 'yesterday')
        elif report_type == 'weekly':
            weekly_period = config.get('weekly_period', 'last_week')
            period = 'week' if weekly_period == 'this_week' else 'weekly'
        elif report_type == 'monthly':
            monthly_period = config.get('monthly_period', 'last_month')
            period = 'month' if monthly_period == 'this_month' else 'monthly'
        else:
            period = 'yesterday'
        
        # 使用 stats 中的原始数据生成海报
        tv_list = stats.get('tv_list_raw', [])
        movie_list = stats.get('movie_list_raw', [])
        
        poster = report_gen.generate_daily_poster(period, tv_list, movie_list, theme)
        if poster:
            return Response(content=poster.read(), media_type="image/jpeg")
        return {"success": False, "message": "海报生成失败"}
    except Exception as e:
        logger.error(f"[ViewReport] preview_poster error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


@plugin.router.post("/send/{report_type}")
async def send_report(request: Request, report_type: str):
    """手动发送报告"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    if report_type not in ['daily', 'weekly', 'monthly']:
        return {"success": False, "message": "无效的报告类型"}
    
    # 检查插件是否启用
    if not plugin.enabled:
        return {"success": False, "message": "插件未启用，请先启用插件"}
    
    try:
        result = plugin.api_send(report_type)
        return result
    except Exception as e:
        logger.error(f"[ViewReport] API send_report error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


@plugin.router.get("/status")
async def get_status(request: Request):
    """获取调度状态"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    try:
        return {"success": True, "data": plugin.api_get_schedule_status()}
    except Exception as e:
        return {"success": False, "message": str(e)}


@plugin.router.get("/logs")
async def get_logs(request: Request, limit: int = 50):
    """获取插件日志"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    try:
        logs = plugin.get_logs(limit)
        return {"status": "success", "data": logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@plugin.router.delete("/logs")
async def clear_logs(request: Request):
    """清空插件日志"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    try:
        plugin.clear_logs()
        return {"status": "success", "message": "日志已清空"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
