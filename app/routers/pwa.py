"""
PWA 自定义图标和主题 API
"""
import sqlite3
import os
import io
import hashlib
import base64
import json
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List
import glob

router = APIRouter()

# 内置默认图标
DEFAULT_ICONS = [
    {"id": "default", "name": "默认图标", "url": "/static/img/logo-app-2.png"}
]

def get_pwa_config():
    """获取 PWA 配置"""
    try:
        from app.core.database import SYSTEM_DB_PATH
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 确保表存在
        c.execute('''
            CREATE TABLE IF NOT EXISTS pwa_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        c.execute("SELECT key, value FROM pwa_config")
        rows = c.fetchall()
        conn.close()
        
        config = {row[0]: row[1] for row in rows}
        return config
    except:
        return {}

def save_pwa_config(key: str, value: str):
    """保存 PWA 配置"""
    try:
        from app.core.database import SYSTEM_DB_PATH
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS pwa_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        c.execute("INSERT OR REPLACE INTO pwa_config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"保存 PWA 配置失败: {e}")
        return False

@router.get("/api/pwa/icon/{filename}")
async def get_pwa_icon(filename: str):
    """获取上传的 PWA 图标"""
    from fastapi.responses import FileResponse

    # 路径穿越防护
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    base_dir = os.path.abspath("data/pwa_icons")
    filepath = os.path.abspath(os.path.join(base_dir, filename))

    if not filepath.startswith(base_dir):
        raise HTTPException(status_code=400, detail="非法路径")

    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="图标不存在")

@router.get("/api/pwa/icons")
async def get_available_icons():
    """获取所有可用图标（内置 + 上传的）"""
    icons = list(DEFAULT_ICONS)
    
    # 获取上传的图标
    upload_dir = "data/pwa_icons"
    if os.path.exists(upload_dir):
        files = glob.glob(os.path.join(upload_dir, "*.png"))
        for filepath in files:
            filename = os.path.basename(filepath)
            icon_id = filename.replace(".png", "")
            icons.append({
                "id": icon_id,
                "name": icon_id.replace("custom_icon_", "自定义 "),
                "url": f"/api/pwa/icon/{filename}"
            })
    
    return {
        "status": "success",
        "icons": icons
    }

def get_user_icon(user_id: str) -> str:
    """获取用户选择的图标"""
    try:
        from app.core.database import SYSTEM_DB_PATH
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_pwa_icons (
                user_id TEXT PRIMARY KEY,
                icon_id TEXT
            )
        ''')
        
        c.execute("SELECT icon_id FROM user_pwa_icons WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        return row[0] if row else None
    except:
        return None

def set_user_icon(user_id: str, icon_id: str):
    """保存用户选择的图标"""
    try:
        from app.core.database import SYSTEM_DB_PATH
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_pwa_icons (
                user_id TEXT PRIMARY KEY,
                icon_id TEXT
            )
        ''')
        
        c.execute("INSERT OR REPLACE INTO user_pwa_icons (user_id, icon_id) VALUES (?, ?)", (user_id, icon_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"保存用户图标失败: {e}")
        return False

@router.get("/api/pwa/manifest.json")
async def get_dynamic_manifest(request: Request):
    """动态生成 PWA manifest"""
    config = get_pwa_config()
    
    # 使用管理员设置的默认图标
    selected_icon = config.get("default_icon") or "default"
    
    # 获取图标 URL
    icon_url = "/static/img/logo-app-2.png"
    
    # 检查是否是内置图标
    for icon in DEFAULT_ICONS:
        if icon["id"] == selected_icon:
            icon_url = icon["url"]
            break
    else:
        # 检查是否是上传的图标
        custom_icon_path = f"data/pwa_icons/{selected_icon}.png"
        if os.path.exists(custom_icon_path):
            icon_url = f"/api/pwa/icon/{selected_icon}.png"
    
    # 添加时间戳防止缓存
    import time
    cache_buster = f"?t={int(time.time())}"
    
    manifest = {
        "name": config.get("app_name", "用户中心 - EmbyPulse"),
        "short_name": config.get("app_short_name", "用户中心"),
        "start_url": "/request",
        "display": "standalone",
        "background_color": "#f8fafc",
        "theme_color": "#4f46e5",
        "icons": [
            {"src": icon_url + cache_buster, "sizes": "192x192", "type": "image/png"},
            {"src": icon_url + cache_buster, "sizes": "512x512", "type": "image/png"}
        ]
    }
    
    return JSONResponse(manifest)

@router.post("/api/pwa/upload_icon")
async def upload_custom_icon(request: Request, file: UploadFile = File(...)):
    """上传自定义 PWA 图标（管理员）"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 检查是否是管理员（兼容两种格式）
    is_admin = user.get("is_admin") or user.get("Policy", {}).get("IsAdministrator", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只支持图片文件")

    # 🔒 文件扩展名白名单
    ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
    filename_ext = os.path.splitext(file.filename or "")[1].lower()
    if filename_ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="不支持的扩展名（仅 png/jpg/jpeg/webp）")

    try:
        content = await file.read()

        # 🔒 大小限制（2MB）
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片不能超过 2MB")

        # 🔒 Magic bytes 校验（防止伪装文件类型）
        if not (
            content.startswith(b"\x89PNG\r\n\x1a\n")           # PNG
            or content.startswith(b"\xff\xd8\xff")              # JPEG
            or (content[:4] == b"RIFF" and content[8:12] == b"WEBP")  # WEBP
        ):
            raise HTTPException(status_code=400, detail="文件头校验失败")

        # 🔒 PIL 二次解析校验（防止恶意构造的图片）
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(content))
            img.verify()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="图片解析失败")

        upload_dir = "data/pwa_icons"
        os.makedirs(upload_dir, exist_ok=True)

        # 🔒 使用 hash 文件名，避免使用 timestamp 给攻击者可预测的命名
        digest = hashlib.sha256(content).hexdigest()[:24]
        filename = f"custom_icon_{digest}.png"
        filepath = os.path.join(upload_dir, filename)

        with open(filepath, "wb") as f:
            f.write(content)

        icon_url = f"/api/pwa/icon/{filename}"
        icon_id = filename.replace(".png", "")

        return {
            "status": "success",
            "message": "图标上传成功",
            "icon": {
                "id": icon_id,
                "name": icon_id.replace("custom_icon_", "自定义 "),
                "url": icon_url
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

@router.post("/api/pwa/set_default_icon")
async def set_default_icon(request: Request):
    """设置默认图标（管理员）"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    is_admin = user.get("is_admin") or user.get("Policy", {}).get("IsAdministrator", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    data = await request.json()
    icon_id = data.get("icon_id")
    
    save_pwa_config("default_icon", icon_id)
    
    return {
        "status": "success",
        "message": "已设置默认图标"
    }

@router.post("/api/pwa/set_app_name")
async def set_app_name(request: Request):
    """设置应用名称（管理员）"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    is_admin = user.get("is_admin") or user.get("Policy", {}).get("IsAdministrator", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    data = await request.json()
    app_name = data.get("app_name", "用户中心 - EmbyPulse")
    app_short_name = data.get("app_short_name", "用户中心")
    
    save_pwa_config("app_name", app_name)
    save_pwa_config("app_short_name", app_short_name)
    
    return {
        "status": "success",
        "message": "应用名称已更新"
    }

@router.delete("/api/pwa/delete_icon/{icon_id}")
async def delete_custom_icon(icon_id: str, request: Request):
    """删除自定义图标（管理员）"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    is_admin = user.get("is_admin") or user.get("Policy", {}).get("IsAdministrator", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    # 不能删除内置图标
    if icon_id in [icon["id"] for icon in DEFAULT_ICONS]:
        raise HTTPException(status_code=400, detail="不能删除内置图标")
    
    # 路径穿越防护
    if ".." in icon_id or "/" in icon_id or "\\" in icon_id:
        raise HTTPException(status_code=400, detail="非法图标 ID")

    base_dir = os.path.abspath("data/pwa_icons")
    filepath = os.path.abspath(os.path.join(base_dir, f"{icon_id}.png"))

    if not filepath.startswith(base_dir):
        raise HTTPException(status_code=400, detail="非法路径")

    if os.path.exists(filepath):
        os.remove(filepath)
        return {"status": "success", "message": "图标已删除"}
    else:
        raise HTTPException(status_code=404, detail="图标不存在")

@router.post("/api/pwa/set_user_icon")
async def set_user_icon_api(request: Request):
    """用户设置自己的图标（已弃用 - PWA 不支持用户个性化图标）"""
    raise HTTPException(status_code=400, detail="PWA 图标在安装时确定，无法为每个用户个性化。请联系管理员设置默认图标。")

@router.get("/api/pwa/user_icon")
async def get_user_icon_api(request: Request):
    """获取当前用户选择的图标（已弃用）"""
    return {"status": "success", "icon_id": None, "message": "PWA 图标由管理员统一设置"}

@router.get("/api/pwa/config")
async def get_pwa_config_api(request: Request):
    """获取当前 PWA 配置"""
    config = get_pwa_config()
    
    # 获取所有可用图标
    icons_res = await get_available_icons()
    icons = icons_res["icons"]
    
    return {
        "status": "success",
        "config": {
            "default_icon": config.get("default_icon", "default"),
            "app_name": config.get("app_name", "用户中心 - EmbyPulse"),
            "app_short_name": config.get("app_short_name", "用户中心")
        },
        "icons": icons
    }
