import re
from typing import Optional

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.playback.stats_helpers import check_login, get_user_map_local
from app.infra.clients.media_server_client import media_api
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_media_api_provider = lambda: media_api
_playback_store_provider = lambda: playback_store
_get_user_map_local_provider = lambda: get_user_map_local
_logger_provider = lambda: None
_re_provider = lambda: re
_safe_error_message_provider = lambda: safe_error_message


def set_dependency_providers(
    *,
    check_login_provider=None,
    media_api_provider=None,
    playback_store_provider=None,
    get_user_map_local_provider=None,
    logger_provider=None,
    re_provider=None,
    safe_error_message_provider=None,
):
    global _check_login_provider
    global _media_api_provider
    global _playback_store_provider
    global _get_user_map_local_provider
    global _logger_provider
    global _re_provider
    global _safe_error_message_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if get_user_map_local_provider is not None:
        _get_user_map_local_provider = get_user_map_local_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if re_provider is not None:
        _re_provider = re_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


def _logger():
    logger = _logger_provider()
    if logger is None:
        import logging

        return logging.getLogger("uvicorn")
    return logger


@router.get("/api/stats/item_detail")
def api_item_detail(request: Request, item_id: str, item_name: Optional[str] = None):
    """获取媒体详情（谁在看、播放历史）"""
    if not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：非管理员只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    current_user_id = None
    if not is_admin:
        current_user_id = (req_user or admin_user).get("Id")

    logger = _logger()
    re_module = _re_provider()

    try:
        # 1. 获取媒体基础信息
        item_info = None
        item_type = None
        series_name = None
        series_id = None
        try:
            res = _media_api_provider().get(f"/Users/{request.session.get('user', {}).get('Id', '')}/Items/{item_id}")
            logger.info(f"[item_detail] Emby API status: {res.status_code}")
            if res.status_code == 200:
                item_info = res.json()
                item_type = item_info.get('Type')
                logger.info(f"[item_detail] item_type: {item_type}, item_name: {item_info.get('Name')}")
                # 🔥 如果是剧集，获取剧名和剧集ID
                if item_type == 'Episode':
                    # 尝试多个可能的字段名
                    series_name = item_info.get('SeriesName') or item_info.get('Series') or item_info.get('SeriesName')
                    series_id = item_info.get('SeriesId') or item_info.get('SeriesItemId')
                    logger.info(f"[item_detail] Episode detected, series_name: {series_name}, series_id: {series_id}")
        except Exception as e:
            logger.error(f"[item_detail] 获取媒体信息失败: {e}")

        # 🔥 如果 Emby API 失败，从 item_name 提取剧名和季
        if not series_name and item_name:
            # 从 "年少有为 - s01e05 - 第 5 集" 提取 "年少有为 - 第 1 季"
            # 或从 "纯真年代的爱情 - 第 1 季" 保留原样
            parts = item_name.split(' - ')
            if len(parts) >= 2:
                # 第一部分是剧名
                name_part = parts[0].strip()
                # 查找季信息
                season_part = None
                for p in parts[1:]:
                    # 匹配 "第 X 季" 或 "S01" 格式
                    m = re_module.search(r'第\s*\d+\s*季', p)
                    if m:
                        season_part = m.group()
                        break
                    m = re_module.search(r'S(\d+)', p, re_module.I)
                    if m:
                        season_num = int(m.group(1))
                        season_part = f"第 {season_num} 季"
                        break
                if season_part:
                    series_name = f"{name_part} - {season_part}"
                else:
                    series_name = name_part
            else:
                series_name = parts[0].strip()
            logger.info(f"[item_detail] 从 item_name 提取: {series_name}")

        # 2. 获取播放统计
        rows = []

        # 🔥 如果是剧集，始终按剧名查询所有集数
        if series_name or item_name:
            search_name = series_name or item_name
            # 提取剧名（去掉集数信息）
            # 例如 "逐玉 - s01e01 - 第 1 集" -> "逐玉"
            clean_name = search_name.split(' - ')[0].strip()
            # 去掉可能的季数信息
            clean_name = re_module.sub(r'\s*S\d+.*', '', clean_name, flags=re_module.I)
            clean_name = re_module.sub(r'\s*第.*季.*', '', clean_name)
            clean_name = clean_name.strip()
            logger.info(f"[item_detail] 按剧名查询: '{clean_name}' (原始: '{search_name}')")

            if is_admin:
                sql_by_name = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemName LIKE ?
                    ORDER BY DateCreated DESC
                    LIMIT 500
                """
                rows = _playback_store_provider().query(sql_by_name, [f"%{clean_name}%"])
            else:
                sql_by_name = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemName LIKE ? AND UserId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 500
                """
                rows = _playback_store_provider().query(sql_by_name, [f"%{clean_name}%", current_user_id])
            logger.info(f"[item_detail] 按剧名查询结果: {len(rows) if rows else 0} 条")
        else:
            # 🔥 电影等其他类型，按 ItemId 查询
            if is_admin:
                sql_by_id = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 100
                """
                rows = _playback_store_provider().query(sql_by_id, [item_id])
            else:
                sql_by_id = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemId = ? AND UserId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 100
                """
                rows = _playback_store_provider().query(sql_by_id, [item_id, current_user_id])
            logger.info(f"[item_detail] 按 ItemId 查询结果: {len(rows) if rows else 0} 条")

        if not rows:
            return {"status": "error", "message": "无播放记录"}

        # 🔥 获取用户 ID 到用户名的映射
        user_map = _get_user_map_local_provider()()

        # 3. 统计数据
        total_plays = len(rows)
        total_time = sum(r.get('PlayDuration') or 0 for r in rows)

        # 用户统计 - 通过 UserId 查找用户名
        user_stats = {}
        for r in rows:
            uid = r.get('UserId') or 'unknown'
            if uid not in user_stats:
                # 🔥 优先从 user_map 获取用户名
                user_name = user_map.get(uid) or r.get('UserName') or '未知用户'
                user_stats[uid] = {
                    'UserId': uid,
                    'UserName': user_name,
                    'PlayCount': 0,
                    'TotalTime': 0
                }
            user_stats[uid]['PlayCount'] += 1
            user_stats[uid]['TotalTime'] += r.get('PlayDuration') or 0

        # 按播放次数排序
        top_users = sorted(user_stats.values(), key=lambda x: x['PlayCount'], reverse=True)[:10]

        # 4. 最近播放历史
        recent_plays = []
        for r in rows[:20]:
            uid = r.get('UserId')
            # 🔥 优先从 user_map 获取用户名
            user_name = user_map.get(uid) or r.get('UserName') or '未知用户'
            recent_plays.append({
                'UserName': user_name,
                'PlayDuration': r.get('PlayDuration') or 0,
                'DateCreated': r.get('DateCreated')
            })

        # 5. 时间分布（按天）
        time_distribution = {}
        for r in rows:
            if r.get('DateCreated'):
                day = r['DateCreated'][:10]  # YYYY-MM-DD
                if day not in time_distribution:
                    time_distribution[day] = {'plays': 0, 'time': 0}
                time_distribution[day]['plays'] += 1
                time_distribution[day]['time'] += r.get('PlayDuration') or 0

        # 按日期排序，取最近30天
        sorted_days = sorted(time_distribution.items(), key=lambda x: x[0], reverse=True)[:30]

        return {
            "status": "success",
            "data": {
                "ItemInfo": {
                    "Id": series_id or item_id,
                    "Name": series_name or (item_info.get('Name') if item_info else rows[0]['ItemName']),
                    "Type": item_info.get('Type') if item_info else rows[0]['ItemType'],
                    "Overview": item_info.get('Overview') if item_info else None,
                    "ProductionYear": item_info.get('ProductionYear') if item_info else None,
                    "CommunityRating": item_info.get('CommunityRating') if item_info else None,
                    "Genres": item_info.get('Genres') if item_info else None,
                } if item_info else {
                    "Id": item_id,
                    "Name": series_name or rows[0]['ItemName'],
                    "Type": rows[0]['ItemType'],
                    "Overview": None,
                    "ProductionYear": None,
                    "CommunityRating": None,
                    "Genres": None
                },
                "Stats": {
                    "TotalPlays": total_plays,
                    "TotalTime": total_time,
                    "TotalTimeHours": round(total_time / 3600, 1)
                },
                "TopUsers": top_users,
                "RecentPlays": recent_plays,
                "TimeDistribution": dict(sorted_days)
            }
        }
    except Exception as e:
        logger.error(f"[api_item_detail] 异常: {e}")
        return {"status": "error", "message": _safe_error_message_provider()(e)}
