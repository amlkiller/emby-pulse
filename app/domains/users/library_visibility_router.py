import logging
from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security_utils import safe_error_message
from app.domains.users import user_dao
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_logger_provider = lambda: logging


class HiddenLibrariesModel(BaseModel):
    hidden_libraries: List[str] = []  # 要隐藏的媒体库 Guid 列表


def set_dependency_providers(*, media_api_provider=None, user_dao_provider=None, logger_provider=None):
    global _media_api_provider
    global _user_dao_provider
    global _logger_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


@router.get("/api/user/libraries")
def api_get_user_libraries(request: Request):
    """获取所有媒体库 + 用户隐藏状态（过滤掉管理员已隐藏的）"""
    user = request.session.get("req_user")
    if not user or not user.get("Id"):
        return {"status": "error", "message": "请先登录"}
    user_id = user["Id"]

    try:
        media = _media_api_provider()
        dao = _user_dao_provider()

        # 获取所有媒体库
        libs_res = media.get("/Library/VirtualFolders", timeout=5)
        if libs_res.status_code != 200:
            return {"status": "error", "message": "媒体服务器无法连接"}
        libs = libs_res.json()
        all_guids = [lib["Guid"] for lib in libs if "Guid" in lib]

        # 获取用户当前权限
        user_res = media.get(f"/Users/{user_id}", timeout=5)
        if user_res.status_code != 200:
            return {"status": "error", "message": "用户信息获取失败"}
        user_data = user_res.json()
        policy = user_data.get("Policy", {})
        enabled_folders = policy.get("EnabledFolders", [])

        # 🔥 从本地数据库获取管理员初始设置的媒体库权限
        row = dao.get_user_library_settings(user_id)
        admin_enabled_folders_str = row["admin_enabled_folders"] if row and row["admin_enabled_folders"] else None
        user_hidden_str = row["hidden_libraries"] if row and row["hidden_libraries"] else None

        # 🔥 解析管理员允许的媒体库
        if admin_enabled_folders_str:
            admin_enabled_folders = set(g.strip() for g in admin_enabled_folders_str.split(",") if g.strip())
        else:
            admin_enabled_folders = None

        # 🔥 解析用户自己隐藏的媒体库
        if user_hidden_str:
            user_hidden_folders = set(g.strip() for g in user_hidden_str.split(",") if g.strip())
        else:
            user_hidden_folders = set()

        # 🔥 实时检测管理员是否又隐藏了新的媒体库
        # 如果当前 enabled_folders + 用户隐藏的 < admin_enabled_folders，说明管理员又隐藏了
        if admin_enabled_folders is not None:
            # 计算管理员当前允许的媒体库（从当前权限推断）
            # 当前 enabled_folders = 管理员允许的 - 用户隐藏的
            # 所以管理员当前允许的 = enabled_folders + 用户隐藏的（且在 admin_enabled_folders 中）
            current_admin_allowed = set(enabled_folders) | (user_hidden_folders & admin_enabled_folders)

            # 如果 current_admin_allowed 比 admin_enabled_folders 少，说明管理员又隐藏了新的
            if current_admin_allowed < admin_enabled_folders:
                # 更新 admin_enabled_folders
                admin_enabled_folders = current_admin_allowed
                try:
                    dao.save_user_admin_enabled_folders(user_id, ",".join(admin_enabled_folders))
                except:
                    pass

        # 构建返回数据（过滤掉管理员已隐藏的媒体库）
        result = []
        for lib in libs:
            guid = lib.get("Guid")
            name = lib.get("Name", "未知")

            # 🔥 如果管理员限制了媒体库，且该媒体库不在管理员允许列表中，则跳过
            if admin_enabled_folders is not None and guid not in admin_enabled_folders:
                continue  # 管理员已隐藏，不展示给用户

            # 判断用户是否自己隐藏了该媒体库
            is_hidden = guid in user_hidden_folders
            result.append({
                "id": guid,
                "name": name,
                "hidden": is_hidden,
            })

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/user/hidden_libraries")
def api_update_hidden_libraries(data: HiddenLibrariesModel, request: Request):
    """更新用户隐藏的媒体库，同步到 Emby 权限"""
    user = request.session.get("req_user")
    if not user or not user.get("Id"):
        return {"status": "error", "message": "请先登录"}
    user_id = user["Id"]

    try:
        media = _media_api_provider()
        dao = _user_dao_provider()

        # 获取所有媒体库
        libs_res = media.get("/Library/VirtualFolders", timeout=5)
        if libs_res.status_code != 200:
            return {"status": "error", "message": "媒体服务器无法连接"}
        libs = libs_res.json()
        all_guids = [lib["Guid"] for lib in libs if "Guid" in lib]

        # 🔥 获取管理员设置的默认权限
        row = dao.get_user_admin_enabled_folders(user_id)
        admin_enabled_folders_str = row["admin_enabled_folders"] if row and row["admin_enabled_folders"] else None

        # 🔥 解析管理员允许的媒体库
        if admin_enabled_folders_str:
            admin_enabled_folders = [g.strip() for g in admin_enabled_folders_str.split(",") if g.strip()]
        else:
            # 没有记录，说明管理员允许全部
            admin_enabled_folders = None

        # 🔥 计算用户可操作的媒体库范围
        if admin_enabled_folders is not None:
            # 用户只能操作管理员允许的媒体库
            user_available_guids = [g for g in all_guids if g in admin_enabled_folders]
        else:
            # 管理员允许全部，用户可以操作所有媒体库
            user_available_guids = all_guids

        # 🔥 计算用户选择隐藏的媒体库
        hidden_guids = [g for g in data.hidden_libraries if g in user_available_guids]
        enabled_guids = [g for g in user_available_guids if g not in hidden_guids]

        # 🔥 同步到 Emby，让播放器生效
        user_res = media.get(f"/Users/{user_id}", timeout=5)
        if user_res.status_code == 200:
            policy = user_res.json().get("Policy", {})
            policy["EnableAllFolders"] = False
            policy["EnabledFolders"] = enabled_guids
            media.post(f"/Users/{user_id}/Policy", json=policy, timeout=5)

        # 保存到本地数据库
        try:
            dao.save_user_hidden_libraries(user_id, ",".join(hidden_guids))
        except Exception as e:
            _logger_provider().warning(f"保存隐藏媒体库到本地失败: {e}")

        return {"status": "success", "message": "设置已保存"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
