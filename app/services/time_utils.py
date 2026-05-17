"""
时间范围计算模块 - 统一各模块的时间范围定义
确保观影报告、海报、仪表盘排行榜数据一致
"""
import datetime
from typing import Tuple, Optional


def get_period_range(period: str) -> Tuple[datetime.date, datetime.date, str, str]:
    """
    获取时间范围的详细信息
    
    参数:
        period: 时间范围标识
            - yesterday: 昨天
            - day / today: 今天
            - week / this_week: 本周一至今天
            - last_week: 上周一至上周日
            - month / this_month: 本月1日至今天
            - last_month: 上月1日至上月最后一天
            - year / this_year: 今年1月1日至今天
            - last_year: 去年全年
            - all: 全量
    
    返回:
        (start_date, end_date, where_sql, title_text)
        - start_date: 起始日期（包含）
        - end_date: 结束日期（不包含，用于 WHERE 条件）
        - where_sql: SQLite WHERE 条件语句
        - title_text: 中文描述文本
    """
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    
    # 计算周相关日期
    days_since_monday = today.weekday()  # 0=周一
    this_monday = today - datetime.timedelta(days=days_since_monday)
    last_monday = this_monday - datetime.timedelta(days=7)
    last_sunday = last_monday + datetime.timedelta(days=6)
    
    # 计算月相关日期
    first_of_this_month = today.replace(day=1)
    last_of_last_month = first_of_this_month - datetime.timedelta(days=1)
    first_of_last_month = last_of_last_month.replace(day=1)
    
    # 计算年相关日期
    first_of_this_year = today.replace(month=1, day=1)
    first_of_last_year = (first_of_this_year - datetime.timedelta(days=1)).replace(month=1, day=1)
    last_of_last_year = first_of_this_year - datetime.timedelta(days=1)
    
    period_map = {
        # 日报相关
        'yesterday': {
            'start': yesterday,
            'end': today,
            'where': f"WHERE DateCreated >= '{yesterday.strftime('%Y-%m-%d')}' AND DateCreated < '{today.strftime('%Y-%m-%d')}'",
            'title': f"昨日日报 ({yesterday.strftime('%m-%d')})"
        },
        'day': {
            'start': today,
            'end': today + datetime.timedelta(days=1),  # 用于显示
            'where': f"WHERE DateCreated >= '{today.strftime('%Y-%m-%d')}'",
            'title': f"今日日报 ({today.strftime('%m-%d')})"
        },
        'today': {
            'start': today,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{today.strftime('%Y-%m-%d')}'",
            'title': f"今日日报 ({today.strftime('%m-%d')})"
        },
        
        # 周报相关
        'week': {
            'start': this_monday,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{this_monday.strftime('%Y-%m-%d')}'",
            'title': f"本周周报 ({this_monday.strftime('%m-%d')}~{today.strftime('%m-%d')})"
        },
        'this_week': {
            'start': this_monday,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{this_monday.strftime('%Y-%m-%d')}'",
            'title': f"本周周报 ({this_monday.strftime('%m-%d')}~{today.strftime('%m-%d')})"
        },
        'last_week': {
            'start': last_monday,
            'end': last_sunday + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{last_monday.strftime('%Y-%m-%d')}' AND DateCreated < '{(last_sunday + datetime.timedelta(days=1)).strftime('%Y-%m-%d')}'",
            'title': f"上周周报 ({last_monday.strftime('%m-%d')}~{last_sunday.strftime('%m-%d')})"
        },
        'weekly': {  # 别名，兼容海报
            'start': last_monday,
            'end': last_sunday + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{last_monday.strftime('%Y-%m-%d')}' AND DateCreated < '{(last_sunday + datetime.timedelta(days=1)).strftime('%Y-%m-%d')}'",
            'title': f"上周周报 ({last_monday.strftime('%m-%d')}~{last_sunday.strftime('%m-%d')})"
        },
        
        # 月报相关
        'month': {
            'start': first_of_this_month,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{first_of_this_month.strftime('%Y-%m-%d')}'",
            'title': f"本月月报 ({today.strftime('%Y年%m月')})"
        },
        'this_month': {
            'start': first_of_this_month,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{first_of_this_month.strftime('%Y-%m-%d')}'",
            'title': f"本月月报 ({today.strftime('%Y年%m月')})"
        },
        'last_month': {
            'start': first_of_last_month,
            'end': first_of_this_month,
            'where': f"WHERE DateCreated >= '{first_of_last_month.strftime('%Y-%m-%d')}' AND DateCreated < '{first_of_this_month.strftime('%Y-%m-%d')}'",
            'title': f"上月月报 ({first_of_last_month.strftime('%Y年%m月')})"
        },
        'monthly': {  # 别名，兼容海报
            'start': first_of_last_month,
            'end': first_of_this_month,
            'where': f"WHERE DateCreated >= '{first_of_last_month.strftime('%Y-%m-%d')}' AND DateCreated < '{first_of_this_month.strftime('%Y-%m-%d')}'",
            'title': f"上月月报 ({first_of_last_month.strftime('%Y年%m月')})"
        },
        
        # 年报相关
        'year': {
            'start': first_of_this_year,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{first_of_this_year.strftime('%Y-%m-%d')}'",
            'title': f"今年年报 ({today.strftime('%Y年')})"
        },
        'this_year': {
            'start': first_of_this_year,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{first_of_this_year.strftime('%Y-%m-%d')}'",
            'title': f"今年年报 ({today.strftime('%Y年')})"
        },
        'last_year': {
            'start': first_of_last_year,
            'end': first_of_this_year,
            'where': f"WHERE DateCreated >= '{first_of_last_year.strftime('%Y-%m-%d')}' AND DateCreated < '{first_of_this_year.strftime('%Y-%m-%d')}'",
            'title': f"去年年报 ({first_of_last_year.strftime('%Y年')})"
        },
        'yearly': {  # 别名，兼容海报
            'start': first_of_this_year,
            'end': today + datetime.timedelta(days=1),
            'where': f"WHERE DateCreated >= '{first_of_this_year.strftime('%Y-%m-%d')}'",
            'title': f"今年年报 ({today.strftime('%Y年')})"
        },
        
        # 全量
        'all': {
            'start': None,
            'end': None,
            'where': "",
            'title': "全量数据"
        },
    }
    
    config = period_map.get(period, period_map['yesterday'])
    return config['start'], config['end'], config['where'], config['title']


def get_period_days(period: str) -> int:
    """
    获取时间范围的天数（用于计算日均播放量）
    """
    start, end, _, _ = get_period_range(period)
    
    if start is None or end is None:
        return 1  # 全量数据默认1天
    
    delta = end - start
    return max(delta.days, 1)


def get_weekday_cn(date: datetime.date) -> str:
    """
    获取中文星期
    """
    weekday_map = {0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 4: "星期五", 5: "星期六", 6: "星期日"}
    return weekday_map.get(date.weekday(), "")


# 用于报告类型的 period 映射
REPORT_TYPE_PERIOD_MAP = {
    'daily': {
        'yesterday': 'yesterday',
        'today': 'day'
    },
    'weekly': {
        'last_week': 'last_week',
        'this_week': 'week'
    },
    'monthly': {
        'last_month': 'last_month',
        'this_month': 'month'
    },
}


def get_period_from_report_config(report_type: str, period_setting: str) -> str:
    """
    从报告类型和配置获取统一的 period 标识
    
    参数:
        report_type: daily / weekly / monthly
        period_setting: yesterday / today / last_week / this_week / last_month / this_month
    
    返回:
        统一的 period 标识（用于 get_period_range）
    """
    if report_type in REPORT_TYPE_PERIOD_MAP:
        return REPORT_TYPE_PERIOD_MAP[report_type].get(period_setting, period_setting)
    return period_setting