from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login, get_user_map_local
from app.domains.playback.stats_queries import build_stats_base_filter
from app.infra.clients.media_server_client import media_api
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_playback_store_provider = lambda: playback_store
_get_user_map_local_provider = lambda: get_user_map_local
_media_api_provider = lambda: media_api


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    playback_store_provider=None,
    get_user_map_local_provider=None,
    media_api_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _playback_store_provider
    global _get_user_map_local_provider
    global _media_api_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if get_user_map_local_provider is not None:
        _get_user_map_local_provider = get_user_map_local_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider


@router.get("/api/stats/recent")
def api_recent_activity(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where, params = _build_stats_base_filter_provider()(user_id)
        results = _playback_store_provider().query(f"SELECT DateCreated, UserId, ItemId, ItemName, ItemType FROM PlaybackActivity {where} ORDER BY DateCreated DESC LIMIT 50", params)
        if not results: return {"status": "success", "data": []}
        user_map = _get_user_map_local_provider()()

        # 🔥 批量获取 ImageTag（减少 API 调用）
        item_ids = [row['ItemId'] for row in results]
        image_tags = {}
        if item_ids:
            try:
                # 批量查询 Emby 获取 ImageTags
                res = _media_api_provider().get("/Items", params={
                    "Ids": ",".join(item_ids[:50]),  # 最多50个
                    "Fields": "ImageTags"
                }, timeout=5)
                if res.status_code == 200:
                    for item in res.json().get("Items", []):
                        tag = item.get("ImageTags", {}).get("Primary", "")
                        if tag:
                            image_tags[item.get("Id")] = tag[:8]
            except:
                pass

        data = []
        for row in results:
            item = dict(row)
            item['UserName'] = user_map.get(item['UserId'], "User")
            item['DisplayName'] = item.get('ItemName') or '未知记录'
            item['ImageTag'] = image_tags.get(item['ItemId'], "")  # 🔥 添加 ImageTag
            if not is_admin:
                item.pop('UserId', None)  # 🔒 非管理员不暴露原始 UserId
            data.append(item)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": []}
