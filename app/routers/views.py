import os
import requests
import json
import re
import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.core.config import cfg
from app.dao.invitation_dao import (
    claim_registration_invitation,
    get_invitation_by_code,
    restore_invitation_code_usage,
    save_registered_user_meta,
)
from app.dao.notification_dao import add_system_notification
from app.core.media_adapter import media_api
from app.core.security_utils import validate_redirect_url
from app.core.security import validate_password_strength
from app.routers.auth import check_permission, PAGE_PERMISSION_MAP
import logging
import random

logger = logging.getLogger("uvicorn")
templates = Jinja2Templates(directory="templates", autoescape=True)
router = APIRouter()

from app.main import APP_VERSION
from app.core.security_utils import safe_error_message

def check_login(request: Request):
    user = request.session.get("user")
    # 只要有用户信息就认为已登录（包括子账号）
    if user:
        return True
    return False

def get_first_allowed_page(request: Request) -> str:
    """获取用户有权限访问的第一个页面路径"""
    user = request.session.get("user", {})
    
    # Emby 账号或 admin 角色拥有全部权限，返回首页
    if user.get("auth_type") == "emby" or user.get("role") == "admin":
        return "/"
    
    # 子账号检查权限列表
    permissions = user.get("permissions", [])
    if isinstance(permissions, str):
        try:
            permissions = json.loads(permissions)
        except:
            permissions = []
    
    # 如果有 "all" 权限，返回首页
    if "all" in permissions:
        return "/"
    
    # 按优先级返回第一个有权限的页面
    # 权限 ID 到页面路径的反向映射
    perm_to_path = {v: k for k, v in PAGE_PERMISSION_MAP.items()}
    
    # 定义页面优先级顺序
    priority_pages = ['dashboard', 'content', 'users', 'requests_admin', 'clients', 'settings']
    
    for perm in priority_pages:
        if perm in permissions and perm in perm_to_path:
            return perm_to_path[perm]
    
    # 如果优先级页面都没有权限，返回第一个有权限的页面
    for perm in permissions:
        if perm in perm_to_path:
            return perm_to_path[perm]
    
    # 没有任何权限，返回空
    return ""

def check_page_permission(request: Request, path: str):
    """检查页面访问权限，无权限返回重定向响应或错误页面"""
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    # 兼容性处理：旧 session 格式没有 auth_type 和 role 字段
    # 旧版本 session 结构：
    #   - Emby 账号: {id, name, is_admin: true, server_id}
    #   - 本地账号: {id, name, is_admin: true/false, role, permissions} (如果有 role 字段)
    if user.get("auth_type") is None and user.get("role") is None:
        # 检查是否有 server_id 字段 - 有则是旧版本 Emby 管理员
        if user.get("server_id"):
            user["auth_type"] = "emby"
            user["role"] = "admin"
            user["permissions"] = []
            request.session["user"] = user
            return None
        # 检查 is_admin 字段 - 旧版本管理员
        elif user.get("is_admin") == True:
            user["auth_type"] = "emby"  # 旧版本只有 Emby 管理员
            user["role"] = "admin"
            user["permissions"] = []
            request.session["user"] = user
            return None
        else:
            # 无法确定权限，需要重新登录
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
    
    # 修复 is_admin 与 role 不一致的情况（用户角色被修改后 session 未更新）
    # 以 role 为准，重新计算 is_admin
    actual_is_admin = user.get("role") == "admin"
    if user.get("is_admin") != actual_is_admin:
        user["is_admin"] = actual_is_admin
        request.session["user"] = user
    
    # Emby 账号或 admin 角色拥有全部权限，跳过检查
    if user.get("auth_type") == "emby" or user.get("role") == "admin":
        return None
    
    # 子账号检查权限
    perm_id = PAGE_PERMISSION_MAP.get(path)
    if perm_id and not check_permission(request, perm_id):
        # 没有权限，返回错误提示页面
        import html as _html
        user_name = _html.escape(str(user.get("name", "用户")))
        return HTMLResponse(
            content=f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>无访问权限 - EmbyPulse</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            color: #fff;
            overflow: hidden;
        }}
        .bg-animation {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image: 
                radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255, 119, 115, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(79, 70, 229, 0.1) 0%, transparent 40%);
            pointer-events: none;
        }}
        .container {{
            position: relative;
            z-index: 1;
            text-align: center;
            padding: 60px 40px;
            max-width: 480px;
        }}
        .icon-wrapper {{
            width: 140px;
            height: 140px;
            margin: 0 auto 32px;
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(239, 68, 68, 0.05) 100%);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px solid rgba(239, 68, 68, 0.3);
            animation: pulse 2s ease-in-out infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.2); }}
            50% {{ transform: scale(1.02); box-shadow: 0 0 40px 10px rgba(239, 68, 68, 0.1); }}
        }}
        .icon {{
            font-size: 64px;
            filter: drop-shadow(0 4px 8px rgba(239, 68, 68, 0.3));
        }}
        h1 {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 16px;
            background: linear-gradient(135deg, #fff 0%, #e0e0e0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .user-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            font-size: 14px;
            color: rgba(255, 255, 255, 0.7);
            margin-bottom: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .user-badge span {{
            color: #a5b4fc;
            font-weight: 500;
        }}
        .message {{
            font-size: 16px;
            color: rgba(255, 255, 255, 0.6);
            line-height: 1.6;
            margin-bottom: 40px;
        }}
        .buttons {{
            display: flex;
            gap: 16px;
            justify-content: center;
            flex-wrap: wrap;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 14px 28px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            text-decoration: none;
            transition: all 0.2s ease;
            cursor: pointer;
            border: none;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            color: #fff;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
        }}
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.3);
        }}
        .footer {{
            position: fixed;
            bottom: 24px;
            left: 0;
            right: 0;
            text-align: center;
            font-size: 12px;
            color: rgba(255, 255, 255, 0.3);
        }}
        .footer a {{
            color: rgba(255, 255, 255, 0.5);
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="bg-animation"></div>
    <div class="container">
        <div class="icon-wrapper">
            <div class="icon">⛔</div>
        </div>
        <h1>无访问权限</h1>
        <div class="user-badge">
            当前账号：<span>{user_name}</span>
        </div>
        <p class="message">
            抱歉，您的账号没有访问此页面的权限。<br>
            如需开通权限，请联系管理员。
        </p>
        <div class="buttons">
            <a href="/" class="btn btn-primary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                    <polyline points="9 22 9 12 15 12 15 22"></polyline>
                </svg>
                返回首页
            </a>
            <a href="/logout" class="btn btn-secondary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
                退出登录
            </a>
        </div>
    </div>
    <div class="footer">
        Powered by <a href="#">EmbyPulse</a>
    </div>
</body>
</html>''',
            status_code=403
        )
    return None

def get_common_vars(request: Request, active_page: str, extra_vars: dict = None):
    # 优先用 get_main_public_url 解析多线路配置
    emby_url = cfg.get_main_public_url()
    if not emby_url:
        emby_url = cfg.get("emby_host") or ""
    emby_url = emby_url.strip().rstrip('/')
    
    server_id = ""
    try:
        sys_res = requests.get(f"{cfg.get('emby_host')}/emby/System/Info?api_key={cfg.get('emby_api_key')}", timeout=2)
        if sys_res.status_code == 200: 
            raw_id = sys_res.json().get("Id", "")
            if raw_id:
                server_id = str(raw_id).replace('\r', '').replace('\n', '').strip()
    except Exception: pass

    # ================= 🔥 新增：查询 Pro 状态 =================
    is_pro = True
    # =========================================================

    # ================= 🔥 新增：用户权限信息 =================
    user = request.session.get("user", {})
    user_permissions = user.get("permissions", [])
    if isinstance(user_permissions, str):
        try:
            user_permissions = json.loads(user_permissions)
        except:
            user_permissions = []
    
    is_admin = user.get("auth_type") == "emby" or user.get("role") == "admin"
    user_name = user.get("name", "用户")  # 当前登录用户名
    user_avatar = user.get("avatar", "")  # 当前登录用户头像
    # =========================================================

    vars_dict = {
        "request": request,
        "version": APP_VERSION,
        "active_page": active_page,
        "emby_url": emby_url,
        "server_id": server_id,
        "is_pro": is_pro,
        "user_permissions": user_permissions,  # 用户权限列表
        "is_admin": is_admin,  # 是否为管理员
        "user_name": user_name,  # 当前登录用户名
        "user_avatar": user_avatar,  # 当前登录用户头像
    }
    if extra_vars: vars_dict.update(extra_vars)
    return vars_dict

@router.get("/apple-touch-icon.png")
@router.get("/apple-touch-icon-precomposed.png")
async def get_apple_touch_icon():
    icon_path_new = os.path.join("static", "img", "logo-app-2.png")
    icon_path_old = os.path.join("static", "img", "logo-app.png")
    
    if os.path.exists(icon_path_new): 
        return FileResponse(icon_path_new)
    elif os.path.exists(icon_path_old): 
        return FileResponse(icon_path_old)
        
    return RedirectResponse("/static/img/logo-light.png")

@router.get("/favicon.ico")
async def get_favicon():
    icon_path = os.path.join("static", "img", "logo-app.png")
    return FileResponse(icon_path)

@router.get("/manifest.json")
async def get_manifest():
    return JSONResponse({
        "name": "EmbyPulse 映迹",
        "short_name": "EmbyPulse",
        "start_url": "/?v=2",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#4f46e5",
        "icons": [{"src": "/static/img/logo-app.png", "sizes": "180x180", "type": "image/png"}, {"src": "/static/img/logo-app.png", "sizes": "512x512", "type": "image/png"}]
    })

from fastapi.responses import PlainTextResponse

@router.get("/request_manifest.json")
async def get_request_manifest():
    # 重定向到动态 manifest API
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/api/pwa/manifest.json")

@router.get("/sw.js")
async def get_service_worker():
    # PWA 已移除：返回一个自卸载 SW，让任何残留注册的客户端立即清理缓存并注销自己。
    # 必须返回合法 JS 而不是 404，否则浏览器会保留旧 SW 继续拦截请求。
    sw_content = (
        "self.addEventListener('install',e=>self.skipWaiting());"
        "self.addEventListener('activate',e=>{"
        "e.waitUntil("
        "caches.keys().then(ks=>Promise.all(ks.map(k=>caches.delete(k))))"
        ".then(()=>self.registration.unregister())"
        ".then(()=>self.clients.matchAll()).then(cs=>cs.forEach(c=>c.navigate(c.url)))"
        ");"
        "});"
    )
    return PlainTextResponse(content=sw_content, media_type="application/javascript")

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/")
    if perm_check:
        # 如果是首页无权限，尝试跳转到用户有权限的第一个页面
        first_page = get_first_allowed_page(request)
        if first_page and first_page != "/":
            return RedirectResponse(first_page, status_code=303)
        return perm_check
    return templates.TemplateResponse("index.html", get_common_vars(request, "dashboard"))

@router.get("/logout")
async def logout(request: Request):
    """退出登录 - 清除 session 并重定向到登录页"""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if check_login(request): return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request, "version": APP_VERSION})

@router.get("/invite/{code}", response_class=HTMLResponse)
async def invite_page(code: str, request: Request):
    invite = get_invitation_by_code(code)
    valid = False; days = 0
    if invite and invite['used_count'] < invite['max_uses']: valid = True; days = invite['days']
    
    # 🔥 检查是否启用用户社区注册重定向
    redirect_to_community = cfg.get("register_redirect_to_community", "false").lower() == "true"
    user_portal_url = cfg.get("user_portal_url", "")
    
    if redirect_to_community and user_portal_url:
        # 🔥 安全修复：验证重定向URL
        safe_url = validate_redirect_url(user_portal_url)
        if safe_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(f"{safe_url}?code={code}")
    
    # 原来的独立注册页面
    client_url = cfg.get("client_download_url") or "https://emby.media/download.html"
    return templates.TemplateResponse("register.html", {"request": request, "code": code, "valid": valid, "days": days, "client_download_url": client_url, "version": APP_VERSION})


# ==================== 注册 API ====================

class RegisterModel(BaseModel):
    code: str
    username: str
    password: str

def _restore_invitation_code(code):
    """Emby 用户创建失败时回滚邀请码消费计数"""
    try:
        restore_invitation_code_usage(code)
    except Exception:
        pass


@router.post("/api/register")
async def api_register(data: RegisterModel, request: Request):
    """邀请码注册 API"""
    try:
        # 1. 先校验用户名和密码（不消耗邀请码）
        username = data.username.strip()
        if not username or len(username) < 2:
            return {"status": "error", "message": "用户名至少需要 2 个字符"}

        if len(username) > 16:
            return {"status": "error", "message": "用户名最多 16 个字符，当前 " + str(len(username)) + " 个字符"}

        safe_name = re.sub(r'[^a-zA-Z0-9一-龥_\-.@]', '', username)

        if safe_name != username:
            invalid_chars = set(re.findall(r'[^a-zA-Z0-9一-龥_\-.@]', username))
            invalid_str = ', '.join(f"'{c}'" for c in list(invalid_chars)[:5])
            return {"status": "error", "message": f"用户名包含不支持的字符: {invalid_str}。只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 ."}

        if not safe_name:
            return {"status": "error", "message": "用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 ."}

        password = data.password.strip()
        pw_valid, pw_error = validate_password_strength(password)
        if not pw_valid:
            return {"status": "error", "message": pw_error}

        # 2. 检查 Emby 用户名是否已存在
        try:
            users = media_api.get("/Users", timeout=5).json()
            if any(u['Name'].lower() == safe_name.lower() for u in users):
                return {"status": "error", "message": "注册失败，请稍后再试"}
        except Exception as e:
            return {"status": "error", "message": safe_error_message(e, "检查用户名失败")}

        # 3. 所有校验通过后，原子抢占邀请码（防 TOCTOU 竞态）
        invite, claim_error = claim_registration_invitation(data.code, safe_name)
        if claim_error:
            return {"status": "error", "message": claim_error}

        days = invite['days'] if invite['days'] else 30
        template_user_id = invite['template_user_id'] if invite['template_user_id'] else None
        routes = invite['routes'] if invite['routes'] else ''
        route_mode = invite['route_mode'] if invite['route_mode'] else 'block'
        req_free = invite['req_free'] if 'req_free' in invite.keys() else 0
        req_free_count = invite['req_free_count'] if 'req_free_count' in invite.keys() else -1

        # 4. 创建 Emby 用户
        try:
            create_res = media_api.post("/Users/New", json={"Name": safe_name}, timeout=10)
            if create_res.status_code not in [200, 201]:
                logger.warning("Emby 用户创建失败: status=%s body=%s", create_res.status_code, create_res.text)
                _restore_invitation_code(data.code)
                return {"status": "error", "message": "注册失败，请稍后再试"}
            
            new_user = create_res.json()
            uid = new_user.get("Id")
            
            # 设置密码
            media_api.post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)
            
            # 应用模板（如果有）
            if template_user_id:
                try:
                    tpl = media_api.get(f"/Users/{template_user_id}", timeout=5).json()
                    if tpl.get("Policy"):
                        policy = tpl["Policy"]
                        policy["IsAdministrator"] = False
                        policy["IsDisabled"] = False
                        media_api.post(f"/Users/{uid}/Policy", json=policy, timeout=5)
                except:
                    pass
            else:
                # 没有模板时，确保账号启用
                try:
                    # 读取完整 Policy 再合并，避免 Emby 整体替换清空默认权限
                    user_info = media_api.get(f"/Users/{uid}", timeout=5).json()
                    policy = user_info.get("Policy", {})
                    policy["IsDisabled"] = False
                    media_api.post(f"/Users/{uid}/Policy", json=policy, timeout=3)
                except:
                    pass
            
            # 6. 保存用户元数据
            # 处理永久注册码：days = 0 或 days >= 36500（100年）视为永久
            expire_date = None
            if days == 0 or days >= 36500:
                expire_date = None  # 永久有效用 None 表示
            elif days > 0:
                expire_date = (datetime.date.today() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            
            # 设置用户线路权限
            allow_routes = ""
            block_routes = ""
            if routes:
                if route_mode == 'allow':
                    allow_routes = routes
                else:
                    block_routes = routes
            
            save_registered_user_meta(uid, expire_date, allow_routes, block_routes, req_free, req_free_count)
            
            # 清除用户列表缓存
            try:
                from app.routers.users import invalidate_emby_users_cache
                invalidate_emby_users_cache()
            except:
                pass
            
            # 7. 发送通知
            try:
                from app.services.bot_service import bot
                days_display = "永久" if (days == 0 or days >= 36500) else f"{days} 天"
                msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{data.code}\n📱 注册渠道：管理后台"
                bot.send_message("sys_notify", msg, platform="all")
                add_system_notification("user", f"新用户注册: {safe_name}", f"管理后台邀请码注册，有效期 {days_display}", "/users_manage")
            except:
                pass
            
            # 9. 构建返回数据 - 获取用户可访问的线路
            # 获取全局线路配置
            all_routes = cfg.get_all_routes()
            user_routes = []
            
            if allow_routes:
                # 允许模式：只返回用户被允许的线路（按名称匹配）
                allowed_names = set(r.strip() for r in allow_routes.split(',') if r.strip())
                user_routes = [r for r in all_routes if r.get('name', '') in allowed_names]
            elif block_routes:
                # 屏蔽模式：返回所有未被屏蔽的线路
                blocked_names = set(r.strip() for r in block_routes.split(',') if r.strip())
                user_routes = [r for r in all_routes if r.get('name', '') not in blocked_names]
            else:
                # 没有特定线路配置，返回所有全局可见线路
                user_routes = [r for r in all_routes if r.get('show_to_users', True) != False]
            
            # 如果没有任何线路，使用默认服务器地址
            if not user_routes:
                server_url = cfg.get_main_public_url() or cfg.get("emby_host", "")
                if server_url:
                    user_routes = [{"name": "默认推荐节点", "url": server_url, "is_main": True}]
            
            welcome_message = cfg.get("welcome_message", "")
            user_portal_url = cfg.get("user_portal_url", "")
            
            return {
                "status": "success",
                "message": "注册成功",
                "server_url": json.dumps(user_routes) if user_routes else "",
                "welcome_message": welcome_message,
                "user_portal_url": user_portal_url
            }
            
        except Exception as e:
            logger.error(f"[注册] 创建用户失败: {e}")
            _restore_invitation_code(data.code)
            return {"status": "error", "message": safe_error_message(e, "注册失败")}
            
    except Exception as e:
        logger.error(f"[注册] 系统错误: {e}")
        return {"status": "error", "message": safe_error_message(e, "系统错误")}


@router.get("/content", response_class=HTMLResponse)
async def content_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/content")
    if perm_check: return perm_check
    return templates.TemplateResponse("content.html", get_common_vars(request, "content"))

@router.get("/details", response_class=HTMLResponse)
async def details_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/details")
    if perm_check: return perm_check
    return templates.TemplateResponse("details.html", get_common_vars(request, "details"))

@router.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/report")
    if perm_check: return perm_check
    return templates.TemplateResponse("report.html", get_common_vars(request, "report"))

@router.get("/bot", response_class=HTMLResponse)
async def bot_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/bot")
    if perm_check: return perm_check
    return templates.TemplateResponse("bot.html", get_common_vars(request, "bot"))

@router.get("/users_manage", response_class=HTMLResponse)
@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/users_manage")
    if perm_check: return perm_check
    return templates.TemplateResponse("users.html", get_common_vars(request, "users"))

@router.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/messages")
    if perm_check: return perm_check
    return templates.TemplateResponse("messages.html", get_common_vars(request, "messages"))

@router.get("/settings", response_class=HTMLResponse)
@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/settings")
    if perm_check: return perm_check
    return templates.TemplateResponse("settings.html", get_common_vars(request, "settings"))

@router.get("/insight", response_class=HTMLResponse)
async def insight_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/insight")
    if perm_check: return perm_check
    return templates.TemplateResponse("insight.html", get_common_vars(request, "insight"))

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/tasks")
    if perm_check: return perm_check
    return templates.TemplateResponse("tasks.html", get_common_vars(request, "tasks"))

@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login", status_code=303)
    perm_check = check_page_permission(request, "/history")
    if perm_check: return perm_check
    return templates.TemplateResponse("history.html", get_common_vars(request, "history", {"user": user}))

@router.get("/request", response_class=HTMLResponse)
async def request_page(request: Request):
    req_user = request.session.get("req_user")
    response = templates.TemplateResponse("request.html", {"request": request, "req_user": req_user, "version": APP_VERSION})
    # 🔥 强制禁止缓存（防止 CDN/代理缓存导致用户数据混乱）
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Vary'] = 'Cookie, Authorization'
    return response

@router.get("/request_login", response_class=HTMLResponse)
async def request_login_page(request: Request):
    if request.session.get("req_user"): return RedirectResponse("/request")
    return templates.TemplateResponse("request_login.html", {"request": request, "version": APP_VERSION})

@router.get("/requests_admin", response_class=HTMLResponse)
async def requests_admin_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/requests_admin")
    if perm_check: return perm_check
    return templates.TemplateResponse("requests_admin.html", get_common_vars(request, "requests_admin"))

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/clients")
    if perm_check: return perm_check
    return templates.TemplateResponse("clients.html", get_common_vars(request, "clients"))

@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/about")
    if perm_check: return perm_check
    return templates.TemplateResponse("about.html", get_common_vars(request, "about"))

@router.get("/gaps", response_class=HTMLResponse)
async def gaps_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/gaps")
    if perm_check: return perm_check
    return templates.TemplateResponse("gaps.html", get_common_vars(request, "gaps"))

@router.get("/risk", response_class=HTMLResponse)
async def risk_control_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/risk")
    if perm_check: return perm_check
    return templates.TemplateResponse("risk.html", get_common_vars(request, "risk", {"title": "风险管控中心"}))

@router.get("/api/wallpaper")
async def get_wallpaper():
    fallback_wallpapers = [
        {"url": "https://images.unsplash.com/photo-1536440136628-849c177e76a1?q=80&w=1925&auto=format&fit=crop", "title": "电影之夜 - Unsplash"},
        {"url": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=2070&auto=format&fit=crop", "title": "家庭影院 - Unsplash"}
    ]
    tmdb_key = cfg.get("tmdb_api_key")
    from app.utils.proxy_helper import get_safe_proxies as _get_safe_proxies
    proxies = _get_safe_proxies()
    if tmdb_key:
        try:
            res = requests.get(f"https://api.themoviedb.org/3/trending/all/day?api_key={tmdb_key}&language=zh-CN", proxies=proxies, timeout=3)
            if res.status_code == 200:
                valid_items = [item for item in res.json().get("results", []) if item.get("backdrop_path")]
                if valid_items:
                    item = random.choice(valid_items)
                    title = item.get("title") or item.get("name") or "TMDB 热门"
                    url = f"https://image.tmdb.org/t/p/original{item['backdrop_path']}"
                    return {"status": "success", "url": url, "title": f"今日热门: {title}"}
        except Exception: pass
    item = random.choice(fallback_wallpapers)
    return {"status": "success", "url": item["url"], "title": item["title"]}

@router.get("/dedupe", response_class=HTMLResponse)
async def dedupe_page(request: Request):
    if not check_login(request): return RedirectResponse("/login")
    perm_check = check_page_permission(request, "/dedupe")
    if perm_check: return perm_check
    return templates.TemplateResponse("dedupe.html", get_common_vars(request, "dedupe"))
