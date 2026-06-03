from fastapi import APIRouter, Request

from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_is_admin_user_provider = lambda: is_admin_user


def set_dependency_providers(*, media_api_provider=None, user_dao_provider=None, is_admin_user_provider=None):
    global _media_api_provider
    global _user_dao_provider
    global _is_admin_user_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider


@router.get("/api/manage/user/{user_id}")
def api_get_single_user(user_id: str, request: Request):
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        res = _media_api_provider().get(f"/Users/{user_id}", timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            policy = user_data.get('Policy', {})
            meta_row = _user_dao_provider().get_user_meta(user_id)

            return {
                "status": "success",
                "data": {
                    "Id": user_data['Id'], "Name": user_data['Name'],
                    "EnableAllFolders": policy.get('EnableAllFolders', True), "EnabledFolders": policy.get('EnabledFolders', []),
                    "ExcludedSubFolders": policy.get('ExcludedSubFolders', []), "EnableDownloading": policy.get('EnableContentDownloading', True),
                    "EnableVideoTranscoding": policy.get('EnableVideoPlaybackTranscoding', True), "EnableAudioTranscoding": policy.get('EnableAudioPlaybackTranscoding', True),
                    "MaxParentalRating": policy.get('MaxParentalRating'),
                    "BlockUnratedItems": policy.get('BlockUnratedItems', False),
                    "BlockedTags": ','.join(policy.get('BlockedTags', [])) if policy.get('BlockedTags') else "",
                    "MaxConcurrent": meta_row['max_concurrent'] if meta_row else None,
                    "IsVIP": bool(meta_row['is_vip']) if meta_row and meta_row['is_vip'] else False,
                    "Remark": meta_row['remark'] if meta_row and 'remark' in meta_row.keys() else "",
                    # 🔥 求片权限
                    "req_free": meta_row['req_free'] if meta_row and 'req_free' in meta_row.keys() else 0,
                    "req_free_count": meta_row['req_free_count'] if meta_row and 'req_free_count' in meta_row.keys() else -1
                }
            }
        return {"status": "error"}
    except:
        return {"status": "error"}
