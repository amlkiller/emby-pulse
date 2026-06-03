import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security_utils import safe_error_message
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user


router = APIRouter()


# 预定义标签颜色
TAG_COLORS = {
    'red': {'bg': 'bg-red-100', 'text': 'text-red-700', 'dark_bg': 'dark:bg-red-500/20', 'dark_text': 'dark:text-red-400'},
    'orange': {'bg': 'bg-orange-100', 'text': 'text-orange-700', 'dark_bg': 'dark:bg-orange-500/20', 'dark_text': 'dark:text-orange-400'},
    'yellow': {'bg': 'bg-yellow-100', 'text': 'text-yellow-700', 'dark_bg': 'dark:bg-yellow-500/20', 'dark_text': 'dark:text-yellow-400'},
    'green': {'bg': 'bg-green-100', 'text': 'text-green-700', 'dark_bg': 'dark:bg-green-500/20', 'dark_text': 'dark:text-green-400'},
    'blue': {'bg': 'bg-blue-100', 'text': 'text-blue-700', 'dark_bg': 'dark:bg-blue-500/20', 'dark_text': 'dark:text-blue-400'},
    'purple': {'bg': 'bg-purple-100', 'text': 'text-purple-700', 'dark_bg': 'dark:bg-purple-500/20', 'dark_text': 'dark:text-purple-400'},
    'pink': {'bg': 'bg-pink-100', 'text': 'text-pink-700', 'dark_bg': 'dark:bg-pink-500/20', 'dark_text': 'dark:text-pink-400'},
    'gray': {'bg': 'bg-gray-100', 'text': 'text-gray-700', 'dark_bg': 'dark:bg-gray-500/20', 'dark_text': 'dark:text-gray-400'},
}


@router.get("/api/manage/tags")
def api_get_tags(request: Request):
    """获取所有标签"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        rows = user_dao.list_user_tags()
        tags = [{"id": r['id'], "name": r['name'], "color": r['color'] or 'blue'} for r in rows]
        return {"status": "success", "data": tags}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


class TagCreateModel(BaseModel):
    name: str
    color: str = 'blue'


@router.post("/api/manage/tags")
def api_create_tag(data: TagCreateModel, request: Request):
    """创建标签"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        tag_id = user_dao.create_user_tag(data.name.strip(), data.color)
        return {"status": "success", "data": {"id": tag_id, "name": data.name.strip(), "color": data.color}}
    except ValueError:
        return {"status": "error", "message": "标签已存在"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.delete("/api/manage/tags/{tag_id}")
def api_delete_tag(tag_id: int, request: Request):
    """删除标签（通过ID）"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        user_dao.delete_user_tag(tag_id)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.delete("/api/manage/tags/name/{tag_name}")
def api_delete_tag_by_name(tag_name: str, request: Request):
    """删除标签（通过名称）"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        deleted = user_dao.delete_user_tag_by_name(tag_name)
        if not deleted:
            return {"status": "error", "message": "标签不存在"}
        return {"status": "success", "message": f"标签 '{tag_name}' 已删除"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


class UserTagsUpdateModel(BaseModel):
    user_id: str
    tags: str  # 逗号分隔的标签名


@router.post("/api/manage/user/tags")
def api_update_user_tags(data: UserTagsUpdateModel, request: Request):
    """更新用户标签"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        user_dao.save_user_tags(data.user_id, data.tags, datetime.datetime.now().isoformat())
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/manage/user/tags")
def api_get_user_tags(user_id: str, request: Request):
    """获取用户标签"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        return {"status": "success", "data": user_dao.get_user_tags(user_id)}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
