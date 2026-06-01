# EmbyPulse-Pro 安全审计修复计划

> 基于 WooYun 方法论审计发现，按 P0-P3 优先级排列。
> 每个修复项包含：问题定位、修复方案、涉及文件、验证方法。

---

## P0 — 立即修复（阻断级风险）

### 1. CORS 配置：移除 allow_credentials 与通配符组合

**问题**：`app/main.py:280` — `allow_origins=["*"]` + `allow_credentials=True`，跨域请求可携带会话 Cookie。

**修复方案**：移除 `allow_credentials=True`，或改为显式允许的源列表。

```python
# 方案 A：不需要跨域携带 Cookie 时（推荐）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # 关闭
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Telegram-Bot-Api-Secret-Token"],
)

# 方案 B：需要跨域携带 Cookie 时（如外部集成）
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # 显式列出
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Telegram-Bot-Api-Secret-Token"],
)
```

**涉及文件**：`app/main.py`
**验证**：浏览器控制台检查 `Access-Control-Allow-Origin` 不再返回 `*` 带 `credentials`。

---

### 2. 路径穿越：PWA 图标读取

**问题**：`app/routers/pwa.py:66-75` — `get_pwa_icon(filename)` 未过滤 `../`，可读取任意文件。

**修复方案**：校验 filename 不含路径分隔符，并限制在目标目录内。

```python
@router.get("/api/pwa/icon/{filename}")
async def get_pwa_icon(filename: str):
    """获取上传的 PWA 图标"""
    from fastapi.responses import FileResponse
    import os

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
```

**涉及文件**：`app/routers/pwa.py`
**验证**：请求 `/api/pwa/icon/../../etc/passwd` 应返回 400。

---

### 3. 路径穿越：PWA 图标删除

**问题**：`app/routers/pwa.py:272-292` — `os.remove()` 未验证路径。

**修复方案**：同上，校验 icon_id 并用 `os.path.abspath` 限制范围。

```python
@router.delete("/api/pwa/delete_icon/{icon_id}")
async def delete_custom_icon(icon_id: str, request: Request):
    # ... 现有管理员检查 ...

    # 路径穿越防护
    if ".." in icon_id or "/" in icon_id or "\\" in icon_id:
        raise HTTPException(status_code=400, detail="非法图标 ID")

    base_dir = os.path.abspath("data/pwa_icons")
    filepath = os.path.abspath(os.path.join(base_dir, f"{icon_id}.png"))

    if not filepath.startswith(base_dir):
        raise HTTPException(status_code=400, detail="非法路径")

    # ... 现有删除逻辑 ...
```

**涉及文件**：`app/routers/pwa.py`
**验证**：请求 `/api/pwa/delete_icon/../../config` 应返回 400。

---

## P1 — 紧急修复（高危漏洞）

### 4. 启用 CSRF 中间件

**问题**：`app/core/csrf_middleware.py` 已定义但从未在 `main.py` 中注册。当前实现过于宽松（跳过所有 `/api/` 路径），需要重写。

**修复方案**：重写 CSRF 中间件，对状态变更请求验证 CSRF Token。

```python
# app/core/csrf_middleware.py — 重写

import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# 完全豁免的路径（已使用 Token 认证或无需 CSRF）
CSRF_EXEMPT_PATHS = {
    "/api/v1/webhook",      # Token 认证
    "/api/telegram",         # Telegram Bot Token
    "/api/bot",              # Bot Webhook
    "/api/auth/login",       # 登录本身
    "/api/auth/register",    # 注册
}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        # 豁免路径
        for exempt in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt):
                return await call_next(request)

        # 只有使用 Cookie 会话的请求需要 CSRF 保护
        # 有 Authorization 头的请求使用 JWT，不受 CSRF 影响
        if request.headers.get("Authorization"):
            return await call_next(request)

        # 对所有其他状态变更请求，检查 CSRF Token
        csrf_token = request.headers.get("X-CSRF-Token")
        session = request.scope.get("session", {})
        expected = session.get("csrf_token")

        if not csrf_token or not expected or not secrets.compare_digest(csrf_token, expected):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF 验证失败"}
            )

        return await call_next(request)
```

在 `session_middleware.py` 中为每个新会话生成 CSRF Token：

```python
# app/core/session_middleware.py — 在创建新会话时添加
if "csrf_token" not in session:
    session["csrf_token"] = secrets.token_urlsafe(32)
```

在 `main.py` 中注册：

```python
from app.core.csrf_middleware import CSRFMiddleware
# 在 SecurityHeadersMiddleware 之后、DatabaseSessionMiddleware 之后
app.add_middleware(CSRFMiddleware)  # 在 CORSMiddleware 之前
```

**涉及文件**：`app/core/csrf_middleware.py`、`app/core/session_middleware.py`、`app/main.py`
**验证**：不带 `X-CSRF-Token` 的 POST 请求应返回 403。

---

### 5. 图像代理端点添加认证

**问题**：`app/routers/proxy.py:174, 242` — `/api/proxy/image/` 和 `/api/proxy/smart_image` 无需登录即可访问。

**修复方案**：添加可选认证（允许未登录用户查看公开图片，但限制敏感操作）。

考虑到图像代理是静态资源且被前端大量引用，**不建议强制认证**（会破坏前端图片显示），但应添加速率限制和防盗链：

```python
# app/routers/proxy.py — proxy_image 添加 Referer 检查
from starlette.requests import Request

@router.get("/api/proxy/image/{item_id}/{img_type}")
def proxy_image(item_id: str, img_type: str, request: Request, v: str = None, nocache: bool = False):
    # 防盗链：检查 Referer（非严格，可被绕过但增加门槛）
    referer = request.headers.get("referer", "")
    if referer and not any(referer.startswith(origin) for origin in [str(request.base_url)]):
        pass  # 不阻断，但可记录日志

    # ... 现有逻辑 ...
```

> 注：此端点主要风险是信息泄露（枚举媒体库），若需严格控制可改为需要 API Token。

**涉及文件**：`app/routers/proxy.py`
**验证**：确认图像代理仍可被前端正常使用。

---

### 6. 重启端点添加管理员权限检查

**问题**：`app/routers/system_tools.py:423-436` — 仅检查登录状态，未检查管理员身份。

**修复方案**：添加 `is_admin` 检查。

```python
@router.post("/restart")
async def restart_system(req: Request):
    """重启 EmbyPulse 服务"""
    user = req.session.get("user")
    if not user:
        return {"success": False, "msg": "未授权"}

    is_admin = user.get("is_admin") or user.get("Policy", {}).get("IsAdministrator", False)
    if not is_admin:
        return {"success": False, "msg": "需要管理员权限"}

    # ... 现有重启逻辑 ...
```

**涉及文件**：`app/routers/system_tools.py`
**验证**：以子管理员身份请求 `/api/system/restart` 应返回权限不足。

---

### 7. 日志端点添加管理员权限检查

**问题**：`app/routers/system_tools.py:375-389` — 任何已登录用户都可查看日志。

**修复方案**：同上，添加管理员检查。

```python
@router.get("/logs")
async def get_logs(request: Request, lines: int = 150):
    user = request.session.get("user")
    if not user:
        return {"success": False, "msg": "未授权"}

    is_admin = user.get("is_admin") or user.get("Policy", {}).get("IsAdministrator", False)
    if not is_admin:
        return {"success": False, "msg": "需要管理员权限"}

    # ... 现有日志逻辑 ...
```

同样适用于 `toggle_debug` 端点（`system_tools.py:391`）。

**涉及文件**：`app/routers/system_tools.py`
**验证**：以普通用户身份请求 `/api/system/logs` 应返回权限不足。

---

### 8. 删除 .env.example 中的明文凭证

**问题**：`.env.example:108-109` — 包含真实用户名和密码。

**修复方案**：替换为占位符。

```env
# LOCAL_ADMIN_USERNAME=your_username
# LOCAL_ADMIN_PASSWORD=your_secure_password
```

**涉及文件**：`.env.example`
**验证**：文件中不再包含 `xiaoyu` 和 `Cici0512.8023mm`。

---

## P2 — 高优先级修复

### 9. SQL 注入：重写 `_interpolate_sql`

**问题**：`app/core/database.py:819-835` — 手动转义 SQL 参数，仅用 `replace("'", "''")`。

**修复方案**：使用白名单校验 + 更严格的转义。

```python
def _interpolate_sql(query: str, args) -> str:
    """将参数化查询转为拼接查询（仅用于 API 模式下提交给 Emby）"""
    if not args:
        return query
    parts = query.split('?')
    if len(parts) - 1 != len(args):
        return query

    res = parts[0]
    for i, arg in enumerate(args):
        if isinstance(arg, bool):
            val = "1" if arg else "0"
        elif isinstance(arg, (int, float)):
            val = str(arg)
        elif arg is None:
            val = "NULL"
        else:
            s = str(arg)
            # 严格转义：反斜杠、单引号、空字节、换行符
            s = s.replace('\\', '\\\\')
            s = s.replace("'", "''")
            s = s.replace('\x00', '')
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            s = s.replace('\x1a', '\\Z')  # Ctrl+Z
            val = f"'{s}'"
        res += val + parts[i + 1]
    return res
```

> 注：长期方案应改为使用 Emby API 的参数化查询接口（如果存在）。

**涉及文件**：`app/core/database.py`
**验证**：构造包含 `' OR 1=1 --` 的参数，确认被正确转义。

---

### 10. 添加 Content-Security-Policy 头

**问题**：`app/core/security_headers_middleware.py` — 缺少 CSP 头。

**修复方案**：添加基础 CSP。

```python
async def dispatch(self, request: Request, call_next):
    response = await call_next(request)

    # ... 现有头 ...

    # Content-Security-Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "  # ECharts CDN
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "  # 允许 Emby 图片代理
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self';"
    )

    return response
```

> 注：首次部署需根据实际使用情况调整 `script-src` 和 `img-src`。`unsafe-inline` 和 `unsafe-eval` 是因为模板中有内联脚本，长期应改为 nonce 方案。

**涉及文件**：`app/core/security_headers_middleware.py`
**验证**：检查响应头包含 `Content-Security-Policy`。

---

### 11. Webhook Token 默认值移除

**问题**：`app/core/config.py:121` — 默认值 `"embypulse"` 可被猜测。

**修复方案**：默认值改为空字符串，启动时强制生成。

```python
"webhook_token": "",  # 启动时自动生成，不再使用硬编码默认值
```

确保 `security_check.py` 中的自动轮换逻辑在 token 为空时也能触发。

**涉及文件**：`app/core/config.py`、`app/core/security_check.py`
**验证**：新部署时 webhook_token 不为 `"embypulse"`。

---

### 12. 速率限制器：支持可信代理配置

**问题**：`app/core/rate_limiter.py:126-141` — 盲信 `X-Forwarded-For`。

**修复方案**：添加可信代理白名单。

```python
# 从配置中读取可信代理列表
TRUSTED_PROXIES = set(os.getenv("TRUSTED_PROXIES", "127.0.0.1").split(","))

def _get_client_ip(self, request: Request) -> str:
    """获取客户端真实 IP，仅从可信代理获取"""
    client_ip = request.client.host if request.client else "unknown"

    # 只有当直接连接来自可信代理时，才信任代理头
    if client_ip in TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    return client_ip
```

**涉及文件**：`app/core/rate_limiter.py`
**验证**：从非可信代理发送伪造 `X-Forwarded-For`，应使用实际连接 IP。

---

## P3 — 中优先级修复

### 13. 用户门户路径隔离收紧

**问题**：`app/main.py:134-169` — 用户门户允许 `/api` 路径，意味着管理员 API 可从 10308 端口访问。

**修复方案**：细化用户门户的 API 路径白名单。

```python
USER_PORTAL_ALLOWED_PREFIXES = [
    "/request",
    "/request_login",
    "/static",
    "/favicon.ico",
    "/api/auth/login",
    "/api/auth/register",
    "/api/media-requests",  # 用户提交的媒体请求
    "/api/messages",        # 用户消息
    "/invite",
]
```

**涉及文件**：`app/main.py`
**验证**：从 10308 端口请求 `/api/system/restart` 应被拒绝。

---

### 14. Webhook IP 处理缺失导入

**问题**：`app/routers/webhook.py:186` — `ipaddress` 未导入。

**修复方案**：在文件顶部添加导入。

```python
import ipaddress
```

**涉及文件**：`app/routers/webhook.py`
**验证**：Webhook 处理 IP 地址时不报 `NameError`。

---

### 15. 全局异常处理规范化

**问题**：多处 `except: pass` 吞没异常，无法检测攻击和故障。

**修复方案**：将裸 `except: pass` 替换为 `except Exception` 并记录日志。

```python
# 之前
except: pass

# 之后
except Exception as e:
    logger.debug("操作失败: %s", e)
```

> 注：此为渐进式修复，优先修复 `database.py` 和安全相关模块中的实例。

**涉及文件**：`database.py`、各路由文件
**验证**：触发异常时能在日志中看到记录。

---

### 16. JWT 与会话密钥分离

**问题**：`app/core/jwt_token.py` — JWT 与会话共用 `SECRET_KEY`。

**修复方案**：使用独立的 JWT 密钥。

```python
import os

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "") or os.getenv("SECRET_KEY", "")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning("JWT_SECRET_KEY 未设置，使用自动生成的密钥（重启后失效）")
```

**涉及文件**：`app/core/jwt_token.py`
**验证**：JWT 密钥与会话密钥不同。

---

## 修复检查清单

| # | 修复项 | 优先级 | 文件 | 状态 |
|---|--------|--------|------|------|
| 1 | CORS 移除 credentials + 通配符 | P0 | main.py | [ ] |
| 2 | PWA 图标读取路径穿越 | P0 | pwa.py | [ ] |
| 3 | PWA 图标删除路径穿越 | P0 | pwa.py | [ ] |
| 4 | 启用 CSRF 中间件 | P1 | csrf_middleware.py, session_middleware.py, main.py | [ ] |
| 5 | 图像代理防盗链 | P1 | proxy.py | [ ] |
| 6 | 重启端点管理员检查 | P1 | system_tools.py | [ ] |
| 7 | 日志端点管理员检查 | P1 | system_tools.py | [ ] |
| 8 | 删除明文凭证 | P1 | .env.example | [ ] |
| 9 | SQL 转义加固 | P2 | database.py | [ ] |
| 10 | 添加 CSP 头 | P2 | security_headers_middleware.py | [ ] |
| 11 | Webhook Token 默认值 | P2 | config.py, security_check.py | [ ] |
| 12 | 速率限制可信代理 | P2 | rate_limiter.py | [ ] |
| 13 | 用户门户路径隔离 | P3 | main.py | [ ] |
| 14 | Webhook IP 导入修复 | P3 | webhook.py | [ ] |
| 15 | 异常处理规范化 | P3 | 多文件 | [ ] |
| 16 | JWT 密钥分离 | P3 | jwt_token.py | [ ] |
