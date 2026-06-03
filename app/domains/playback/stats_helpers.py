import logging
import re
import time

from fastapi import Request

from app.domains.users import public_service as user_service
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_stats_cache = {
    "overview": {"data": None, "expires": 0},
    "plays": {"data": None, "expires": 0},
    "users": {"data": None, "expires": 0},
}
STATS_CACHE_TTL = 300  # 5 分钟缓存


def get_cached_stats(key: str):
    """获取缓存的统计数据"""
    if key in _stats_cache:
        cache = _stats_cache[key]
        if cache["data"] and time.time() < cache["expires"]:
            return cache["data"]
    return None


def set_cached_stats(key: str, data):
    """设置统计数据缓存"""
    _stats_cache[key] = {
        "data": data,
        "expires": time.time() + STATS_CACHE_TTL,
    }


def check_login(request: Request) -> bool:
    """检查用户是否登录（公共API，支持管理端和用户端）"""
    # 管理端登录：session 中有 user
    # 用户端登录：session 中有 req_user
    return request.session.get("user") is not None or request.session.get("req_user") is not None


def require_admin_login(request: Request):
    """要求管理员登录"""
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    return None


def get_clean_name(item_name, item_type):
    if not item_name:
        return "未知内容"
    item_name = str(item_name)
    if str(item_type) != "Episode":
        return item_name.split(" - ")[0]

    parts = [p.strip() for p in item_name.split(" - ")]
    series_name = parts[0]
    season_num = None

    cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    for part in parts[1:]:
        m1 = re.search(r"(?:S|Season\s*)0*(\d+)", part, re.I)
        if m1:
            season_num = int(m1.group(1))
            break
        m2 = re.search(r"第\s*(\d+)\s*季", part)
        if m2:
            season_num = int(m2.group(1))
            break
        m3 = re.search(r"第\s*([一二三四五六七八九十]+)\s*季", part)
        if m3:
            season_num = cn_map.get(m3.group(1), 1)
            break

    if season_num is not None:
        return f"{series_name} - 第 {season_num} 季"
    m_f1 = re.search(r"(?:S|Season\s*)0*(\d+)", item_name, re.I)
    if m_f1:
        return f"{series_name} - 第 {int(m_f1.group(1))} 季"
    m_f2 = re.search(r"第\s*([一二三四五六七八九十]+)\s*季", item_name)
    if m_f2:
        return f"{series_name} - 第 {cn_map.get(m_f2.group(1), 1)} 季"
    m_f3 = re.search(r"第\s*(\d+)\s*季", item_name)
    if m_f3:
        return f"{series_name} - 第 {int(m_f3.group(1))} 季"

    return series_name


def resolve_poster_ids(items_list):
    if not items_list:
        return
    ids = ",".join(list(set([str(x["ItemId"]) for x in items_list if x.get("ItemId")])))
    if not ids:
        return

    try:
        # 🚀 替换为 media_api
        logger.debug(f"[resolve_poster_ids] 查询 ItemIds: {ids[:100]}...")
        res = media_api.get("/Items", params={"Ids": ids}, timeout=5)
        logger.debug(f"[resolve_poster_ids] 状态码: {res.status_code}")
        if res.status_code == 200:
            emby_items = res.json().get("Items", [])
            logger.debug(f"[resolve_poster_ids] 返回 Items 数量: {len(emby_items)}")
            id_map = {}
            for e in emby_items:
                best_id = e.get("SeriesId") or e.get("SeasonId") or e.get("Id")
                id_map[str(e.get("Id"))] = best_id
            logger.debug(f"[resolve_poster_ids] ID 映射数量: {len(id_map)}")
            for x in items_list:
                orig_id = str(x.get("ItemId"))
                if orig_id in id_map:
                    # 🔥 不修改原始 ItemId，而是添加 PosterId 用于显示海报
                    x["PosterId"] = id_map[orig_id]
                    x["smart_poster"] = f"/api/proxy/smart_image?item_id={id_map[orig_id]}&type=Primary"
        else:
            logger.warning(f"[resolve_poster_ids] 请求失败: {res.text[:200]}")
    except Exception as e:
        logger.error(f"[resolve_poster_ids] 异常: {e}")


def get_admin_user_id():
    try:
        # 🚀 替换为 media_api
        res = media_api.get("/Users", timeout=5)
        if res.status_code == 200:
            users = res.json()
            for u in users:
                if u.get("Policy", {}).get("IsAdministrator"):
                    return u["Id"]
            if users:
                return users[0]["Id"]
    except Exception:
        pass
    return None


def get_user_map_local():
    user_map = {}
    try:
        # 🚀 替换为 media_api
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                user_map[u["Id"]] = u["Name"]
    except Exception:
        pass
    return user_map
