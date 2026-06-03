import logging

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.media_requests import community_cache_service
from app.domains.playback import stats as playback_stats
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_media_api_provider = lambda: media_api
_playback_stats_provider = lambda: playback_stats
_logger_provider = lambda: logging.getLogger("uvicorn")
_get_cache_provider = lambda: community_cache_service._get_cache
_set_cache_provider = lambda: community_cache_service._set_cache
_cache_ttl_top_provider = lambda: community_cache_service.COMMUNITY_CACHE_TTL_TOP
_cache_ttl_latest_provider = lambda: community_cache_service.COMMUNITY_CACHE_TTL_LATEST
_safe_error_message_provider = lambda: safe_error_message


def _check_user_exists(user_id: str) -> bool:
    """检查 Emby 用户是否仍然存在"""
    if not user_id:
        return False
    try:
        media = _media_api_provider()
        if media and media.host and media.api_key:
            res = media.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True  # 网络异常时不误判，允许继续操作


_check_user_exists_provider = lambda: _check_user_exists


def set_dependency_providers(
    *,
    media_api_provider=None,
    playback_stats_provider=None,
    logger_provider=None,
    check_user_exists_provider=None,
    get_cache_provider=None,
    set_cache_provider=None,
    cache_ttl_top_provider=None,
    cache_ttl_latest_provider=None,
    safe_error_message_provider=None,
):
    global _media_api_provider
    global _playback_stats_provider
    global _logger_provider
    global _check_user_exists_provider
    global _get_cache_provider
    global _set_cache_provider
    global _cache_ttl_top_provider
    global _cache_ttl_latest_provider
    global _safe_error_message_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if playback_stats_provider is not None:
        _playback_stats_provider = playback_stats_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if check_user_exists_provider is not None:
        _check_user_exists_provider = check_user_exists_provider
    if get_cache_provider is not None:
        _get_cache_provider = get_cache_provider
    if set_cache_provider is not None:
        _set_cache_provider = set_cache_provider
    if cache_ttl_top_provider is not None:
        _cache_ttl_top_provider = cache_ttl_top_provider
    if cache_ttl_latest_provider is not None:
        _cache_ttl_latest_provider = cache_ttl_latest_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


@router.get("/api/requests/safe_top")
def get_safe_top_media(category: str, request: Request):
    check_user_exists = _check_user_exists_provider()
    get_cache = _get_cache_provider()
    set_cache = _set_cache_provider()
    cache_ttl_top = _cache_ttl_top_provider()
    playback = _playback_stats_provider()
    media = _media_api_provider()
    logger = _logger_provider()
    safe_error = _safe_error_message_provider()

    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    # 检查 Emby 账号是否仍然存在
    if not check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}

    uid = user["Id"]
    logger.debug(f"[热播榜] 用户 {uid} 请求 {category} 榜单")

    # 🔥 尝试从缓存获取全局热播榜数据
    cache_key = f"safe_top_{category}"
    global_items = get_cache(cache_key)
    logger.debug(f"[热播榜] 缓存命中: {global_items is not None}, 数据量: {len(global_items) if global_items else 0}")

    if not global_items:
        try:
            logger.debug(f"[热播榜] 调用 api_top_movies 获取数据...")
            global_res = playback.api_top_movies(user_id="all", category=category, sort_by="count")
            logger.debug(f"[热播榜] api_top_movies 返回状态: {global_res.get('status')}, 数据量: {len(global_res.get('data', []))}")
            global_items = global_res.get("data", [])

            if global_items:
                # 🔥 缓存全局数据（不过滤用户权限）
                set_cache(cache_key, global_items[:50], cache_ttl_top)
                logger.debug(f"[热播榜] 已缓存 {len(global_items[:50])} 条数据")
            else:
                logger.warning(f"[热播榜] api_top_movies 返回空数据，未缓存")
        except Exception as e:
            logger.error(f"[热播榜] 数据获取失败: {e}")
            return {"status": "error", "data": [], "error": safe_error(e)}

    if not global_items:
        logger.warning(f"[热播榜] 最终数据为空")
        return {"status": "success", "data": []}

    # 🔥 用户权限过滤（这部分很快，不需要缓存）
    try:
        candidate_items = global_items[:50]
        item_ids = ",".join([str(i["ItemId"]) for i in candidate_items])
        logger.debug(f"[热播榜] 待过滤 ItemIds 数量: {len(candidate_items)}, 总长度: {len(item_ids)}")

        # 🔥 尝试不同的 API 调用方式
        # 方式1: 不带 Recursive 参数
        res1 = media.get(f"/Users/{uid}/Items", params={"Ids": item_ids}, timeout=5)
        items1 = res1.json().get("Items", [])
        logger.debug(f"[热播榜] 方式1 结果: 状态码 {res1.status_code}, Items 数量 {len(items1)}")

        # 方式2: 使用 /Items 而不是 /Users/{uid}/Items
        res2 = media.get("/Items", params={"Ids": item_ids, "UserId": uid}, timeout=5)
        items2 = res2.json().get("Items", [])
        logger.debug(f"[热播榜] 方式2 结果: 状态码 {res2.status_code}, Items 数量 {len(items2)}")

        # 使用能返回数据的方式
        emby_items = items1 if items1 else items2
        if not emby_items:
            logger.warning(f"[热播榜] 两种方式都返回空")
            return {"status": "success", "data": []}

        allowed_ids = {str(item["Id"]) for item in emby_items}
        logger.debug(f"[热播榜] 用户有权限的 Item 数量: {len(allowed_ids)}")

        safe_top_10 = [i for i in candidate_items if str(i["ItemId"]) in allowed_ids][:10]
        logger.debug(f"[热播榜] 过滤后剩余: {len(safe_top_10)} 条")

        return {"status": "success", "data": safe_top_10, "from_cache": True}
    except Exception as e:
        logger.error(f"[热播榜] 权限过滤失败: {e}")
        return {"status": "error", "data": [], "error": safe_error(e)}


@router.get("/api/requests/safe_latest")
def get_safe_latest(limit: int = 15, request: Request = None):
    check_user_exists = _check_user_exists_provider()
    get_cache = _get_cache_provider()
    set_cache = _set_cache_provider()
    cache_ttl_latest = _cache_ttl_latest_provider()
    playback = _playback_stats_provider()
    media = _media_api_provider()
    logger = _logger_provider()

    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    # 检查 Emby 账号是否仍然存在
    if not check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}

    uid = user["Id"]

    # 🔥 尝试从缓存获取全局最新数据
    cache_key = "safe_latest"
    global_items = get_cache(cache_key)

    if not global_items:
        try:
            global_res = playback.api_latest_media(limit=40)
            global_items = global_res.get("data", [])

            if global_items:
                # 🔥 缓存全局数据
                set_cache(cache_key, global_items, cache_ttl_latest)
        except Exception as e:
            print(f"最新数据获取失败: {e}")
            return {"status": "error", "data": []}

    if not global_items:
        return {"status": "success", "data": []}

    # 🔥 用户权限过滤
    try:
        item_ids = ",".join([str(i.get("Id") or i.get("ItemId")) for i in global_items])
        logger.debug(f"[最新收录] 待过滤 ItemIds 数量: {len(global_items)}")

        # 🔥 尝试不同的 API 调用方式
        # 方式1: 不带 Recursive
        emby_res1 = media.get(f"/Users/{uid}/Items", params={"Ids": item_ids}, timeout=5).json()
        items1 = emby_res1.get("Items", [])
        logger.debug(f"[最新收录] 方式1 结果: {len(items1)} 条")

        # 方式2: 带 UserId 参数
        emby_res2 = media.get("/Items", params={"Ids": item_ids, "UserId": uid}, timeout=5).json()
        items2 = emby_res2.get("Items", [])
        logger.debug(f"[最新收录] 方式2 结果: {len(items2)} 条")

        emby_items = items1 if items1 else items2
        if not emby_items:
            logger.warning(f"[最新收录] 两种方式都返回空")
            return {"status": "success", "data": []}

        allowed_ids = {str(item["Id"]) for item in emby_items}

        safe_items = []
        for i in global_items:
            i_id = str(i.get("Id") or i.get("ItemId"))
            if i_id in allowed_ids:
                safe_items.append(i)

        logger.debug(f"[最新收录] 过滤后剩余: {len(safe_items)} 条")

        return {"status": "success", "data": safe_items[:limit], "from_cache": True}
    except Exception as e:
        logger.error(f"[最新收录] 权限过滤失败: {e}")
        return {"status": "error", "data": []}
