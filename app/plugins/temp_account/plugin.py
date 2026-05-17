"""
临时观影账号管理插件 (Pro 专享)
创建临时观影账号，密码定时自动更新，支持通知推送
"""
import time
import logging
import threading
import datetime
import requests
import sqlite3
import secrets
import string
import json
from fastapi import Request
from app.plugins.base import PluginBase
from app.core.config import cfg
from app.core.database import query_db, DB_PATH, SYSTEM_DB_PATH

logger = logging.getLogger("uvicorn")


class TempAccountPlugin(PluginBase):
    id = "temp_account"
    name = "临时账号管理"
    description = "创建临时观影账号，密码定时自动更新并推送通知（Pro 专享）"
    icon = "fa-user-clock"
    icon_color = "from-violet-500 to-purple-500"
    version = "1.0.0"
    author = "EmbyPulse"
    pro_only = True  # Pro 专享

    def __init__(self):
        super().__init__()
        self._thread = None
        self._running = False
        self._setup_routes()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        try:
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            c = conn.cursor()
            
            # 临时账号表
            c.execute("""
                CREATE TABLE IF NOT EXISTS temp_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    emby_user_id TEXT,
                    current_password TEXT NOT NULL,
                    template_user_id TEXT,
                    allow_routes TEXT DEFAULT '',
                    block_routes TEXT DEFAULT '',
                    req_free INTEGER DEFAULT 0,
                    req_free_count INTEGER DEFAULT -1,
                    auto_update_enabled INTEGER DEFAULT 1,
                    update_interval_hours INTEGER DEFAULT 24,
                    update_interval_minutes INTEGER DEFAULT 0,
                    last_password_update TEXT,
                    next_password_update TEXT,
                    notify_tg INTEGER DEFAULT 1,
                    notify_wecom INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    remark TEXT DEFAULT '临时账号',
                    tags TEXT DEFAULT ''
                )
            """)
            
            # 数据库迁移：添加缺失的列
            try:
                c.execute("ALTER TABLE temp_accounts ADD COLUMN allow_routes TEXT DEFAULT ''")
            except:
                pass
            try:
                c.execute("ALTER TABLE temp_accounts ADD COLUMN block_routes TEXT DEFAULT ''")
            except:
                pass
            try:
                c.execute("ALTER TABLE temp_accounts ADD COLUMN tags TEXT DEFAULT ''")
            except:
                pass
            try:
                c.execute("ALTER TABLE temp_accounts ADD COLUMN req_free INTEGER DEFAULT 0")
            except:
                pass
            try:
                c.execute("ALTER TABLE temp_accounts ADD COLUMN req_free_count INTEGER DEFAULT -1")
            except:
                pass
            
            # 密码更新历史表
            c.execute("""
                CREATE TABLE IF NOT EXISTS temp_account_password_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    old_password TEXT,
                    new_password TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    notify_sent INTEGER DEFAULT 0,
                    FOREIGN KEY (account_id) REFERENCES temp_accounts(id)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("[临时账号] 数据库表初始化完成")
        except Exception as e:
            logger.error(f"[临时账号] 初始化数据库失败: {e}")

    def _setup_routes(self):
        """注册 API 路由"""

        @self.router.get("")
        async def temp_account_page(request: Request):
            """临时账号管理页面"""
            if not request.session.get("user"):
                from fastapi.responses import RedirectResponse
                return RedirectResponse("/login", status_code=303)
            
            from fastapi.templating import Jinja2Templates
            templates = Jinja2Templates(directory="templates")
            
            return templates.TemplateResponse("temp_account.html", {"request": request})

        @self.router.get("/accounts")
        async def api_get_accounts(request: Request):
            """获取临时账号列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM temp_accounts ORDER BY created_at DESC
                """).fetchall()
                conn.close()
                
                accounts = []
                for row in rows:
                    # 根据 allow_routes/block_routes 推导 route_mode
                    allow_routes = row["allow_routes"] or ""
                    block_routes = row["block_routes"] or ""
                    if allow_routes:
                        route_mode = "allow"
                        routes = allow_routes
                    else:
                        route_mode = "block"
                        routes = block_routes
                    
                    accounts.append({
                        "id": row["id"],
                        "username": row["username"],
                        "emby_user_id": row["emby_user_id"],
                        "current_password": row["current_password"],
                        "template_user_id": row["template_user_id"],
                        "route_mode": route_mode,
                        "routes": routes,
                        "allow_routes": allow_routes,
                        "block_routes": block_routes,
                        "req_free": row["req_free"],
                        "req_free_count": row["req_free_count"],
                        "auto_update_enabled": row["auto_update_enabled"],
                        "update_interval_hours": row["update_interval_hours"],
                        "update_interval_minutes": row["update_interval_minutes"],
                        "last_password_update": row["last_password_update"],
                        "next_password_update": row["next_password_update"],
                        "notify_tg": row["notify_tg"],
                        "notify_wecom": row["notify_wecom"],
                        "enabled": row["enabled"],
                        "created_at": row["created_at"],
                        "remark": row["remark"],
                        "tags": row["tags"]
                    })
                
                return {"status": "success", "data": accounts}
            except Exception as e:
                logger.error(f"[临时账号] 获取账号列表失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/accounts")
        async def api_create_account(request: Request):
            """创建临时账号"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                data = await request.json()
                usernames = data.get("usernames", [])
                template_user_id = data.get("template_user_id", "")
                route_mode = data.get("route_mode", "block")
                routes = data.get("routes", "")
                req_free = int(data.get("req_free", 0) or 0)
                req_free_count = int(data.get("req_free_count", -1) or -1)
                update_interval_hours = int(data.get("update_interval_hours") or 0)
                update_interval_minutes = int(data.get("update_interval_minutes") or 0)
                notify_tg = int(data.get("notify_tg", 1) or 1)
                notify_wecom = int(data.get("notify_wecom", 0) or 0)
                remark_prefix = data.get("remark_prefix", "临时账号")
                tags = data.get("tags", "临时账号")  # 标签
                
                if not usernames:
                    return {"status": "error", "message": "请输入用户名"}
                
                # 转换线路权限为 allow_routes/block_routes 格式
                allow_routes = ""
                block_routes = ""
                if routes:
                    if route_mode == 'allow':
                        allow_routes = routes
                    else:
                        block_routes = routes
                
                # 批量创建
                created = []
                failed = []
                
                for i, username in enumerate(usernames):
                    username = username.strip()
                    if not username:
                        continue
                    
                    # 生成备注
                    remark = f"{remark_prefix}{i+1}" if len(usernames) > 1 else remark_prefix
                    
                    # 创建账号
                    result = self._create_single_account(
                        username=username,
                        template_user_id=template_user_id,
                        allow_routes=allow_routes,
                        block_routes=block_routes,
                        req_free=req_free,
                        req_free_count=req_free_count,
                        update_interval_hours=update_interval_hours,
                        update_interval_minutes=update_interval_minutes,
                        notify_tg=notify_tg,
                        notify_wecom=notify_wecom,
                        remark=remark,
                        tags=tags
                    )
                    
                    if result.get("success"):
                        created.append({
                            "username": username,
                            "password": result["password"],
                            "emby_user_id": result["emby_user_id"],
                            "remark": remark
                        })
                    else:
                        failed.append({
                            "username": username,
                            "error": result.get("error", "未知错误")
                        })
                
                return {
                    "status": "success",
                    "data": {
                        "created": created,
                        "failed": failed,
                        "total": len(usernames),
                        "success_count": len(created)
                    }
                }
            except Exception as e:
                logger.error(f"[临时账号] 创建账号失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.delete("/accounts/{account_id}")
        async def api_delete_account(account_id: int, request: Request):
            """删除临时账号"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                # 获取账号信息
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM temp_accounts WHERE id = ?", (account_id,)
                ).fetchone()
                
                if not row:
                    conn.close()
                    return {"status": "error", "message": "账号不存在"}
                
                emby_user_id = row["emby_user_id"]
                username = row["username"]
                
                # 删除 Emby 用户
                if emby_user_id:
                    self._delete_emby_user(emby_user_id)
                
                # 删除数据库记录
                conn.execute("DELETE FROM temp_accounts WHERE id = ?", (account_id,))
                conn.execute("DELETE FROM temp_account_password_history WHERE account_id = ?", (account_id,))
                conn.commit()
                conn.close()
                
                self.log(f"删除临时账号: {username}")
                return {"status": "success", "message": "删除成功"}
            except Exception as e:
                logger.error(f"[临时账号] 删除账号失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/accounts/{account_id}/refresh_password")
        async def api_refresh_password(account_id: int, request: Request):
            """手动刷新密码"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                result = self._refresh_account_password(account_id, manual=True)
                if result.get("success"):
                    return {"status": "success", "data": result}
                return {"status": "error", "message": result.get("error", "刷新失败")}
            except Exception as e:
                logger.error(f"[临时账号] 刷新密码失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/accounts/{account_id}/toggle")
        async def api_toggle_account(account_id: int, request: Request):
            """启用/禁用账号"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                data = await request.json()
                enabled = data.get("enabled", 1)
                
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT emby_user_id, username FROM temp_accounts WHERE id = ?", (account_id,)
                ).fetchone()
                
                if not row:
                    conn.close()
                    return {"status": "error", "message": "账号不存在"}
                
                emby_user_id = row["emby_user_id"]
                username = row["username"]
                
                # 更新 Emby 用户状态
                if emby_user_id:
                    self._set_emby_user_enabled(emby_user_id, enabled)
                
                # 更新数据库
                conn.execute(
                    "UPDATE temp_accounts SET enabled = ? WHERE id = ?",
                    (enabled, account_id)
                )
                conn.commit()
                conn.close()
                
                action = "启用" if enabled else "禁用"
                self.log(f"{action}临时账号: {username}")
                return {"status": "success", "message": f"{action}成功"}
            except Exception as e:
                logger.error(f"[临时账号] 切换状态失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.put("/accounts/{account_id}")
        async def api_update_account(account_id: int, request: Request):
            """更新账号配置"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                data = await request.json()
                
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM temp_accounts WHERE id = ?", (account_id,)
                ).fetchone()
                
                if not row:
                    conn.close()
                    return {"status": "error", "message": "账号不存在"}
                
                emby_user_id = row["emby_user_id"]
                
                # 检查是否更新了间隔时间
                need_recalculate_next = False
                new_interval_hours = data.get("update_interval_hours")
                new_interval_minutes = data.get("update_interval_minutes")
                
                if new_interval_hours is not None or new_interval_minutes is not None:
                    need_recalculate_next = True
                
                # 更新字段
                update_fields = []
                update_values = []
                
                for field in ["remark", "auto_update_enabled", "update_interval_hours", 
                              "update_interval_minutes", "notify_tg", "notify_wecom",
                              "allow_routes", "block_routes", "req_free", "req_free_count", "tags"]:
                    if field in data:
                        update_fields.append(f"{field} = ?")
                        update_values.append(data[field])
                
                # 如果更新了间隔，重新计算下次更新时间
                if need_recalculate_next:
                    hours = new_interval_hours if new_interval_hours is not None else row["update_interval_hours"]
                    minutes = new_interval_minutes if new_interval_minutes is not None else row["update_interval_minutes"]
                    now = datetime.datetime.now()
                    next_update = now + datetime.timedelta(minutes=int(hours) * 60 + int(minutes))
                    update_fields.append("next_password_update = ?")
                    update_values.append(next_update.isoformat())
                
                if update_fields:
                    update_values.append(account_id)
                    conn.execute(
                        f"UPDATE temp_accounts SET {', '.join(update_fields)} WHERE id = ?",
                        update_values
                    )
                    
                    # 同步更新 users_meta
                    if emby_user_id:
                        meta_fields = []
                        meta_values = []
                        for field in ["remark", "allow_routes", "block_routes", "req_free", "req_free_count", "tags"]:
                            if field in data:
                                meta_fields.append(f"{field} = ?")
                                meta_values.append(data[field])
                        if meta_fields:
                            meta_values.append(emby_user_id)
                            conn.execute(
                                f"UPDATE users_meta SET {', '.join(meta_fields)} WHERE user_id = ?",
                                meta_values
                            )
                    
                    conn.commit()
                
                conn.close()
                return {"status": "success", "message": "更新成功"}
            except Exception as e:
                logger.error(f"[临时账号] 更新配置失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/accounts/{account_id}/history")
        async def api_get_password_history(account_id: int, request: Request, limit: int = 20):
            """获取密码更新历史"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM temp_account_password_history 
                    WHERE account_id = ? 
                    ORDER BY updated_at DESC 
                    LIMIT ?
                """, (account_id, limit)).fetchall()
                conn.close()
                
                history = [dict(row) for row in rows]
                return {"status": "success", "data": history}
            except Exception as e:
                logger.error(f"[临时账号] 获取历史失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/template_users")
        async def api_get_template_users(request: Request):
            """获取可用的模板用户列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                emby_host = cfg.get("emby_host", "")
                emby_key = cfg.get("emby_api_key", "")
                if not emby_host or not emby_key:
                    return {"status": "error", "message": "Emby API 未配置"}
                
                res = requests.get(
                    f"{emby_host}/Users",
                    headers={"X-Emby-Token": emby_key},
                    timeout=10
                )
                if res.status_code != 200:
                    return {"status": "error", "message": "获取用户列表失败"}
                
                users = res.json()
                # 过滤掉管理员
                template_users = [
                    {"id": u["Id"], "name": u["Name"]}
                    for u in users
                    if not u.get("Policy", {}).get("IsAdministrator", False)
                ]
                return {"status": "success", "data": template_users}
            except Exception as e:
                logger.error(f"[临时账号] 获取模板用户失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/routes")
        async def api_get_routes(request: Request):
            """获取可用线路列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                # 使用系统配置的线路列表
                all_routes = cfg.get_all_routes()
                routes = [{"id": r.get("name", ""), "name": r.get("name", ""), "url": r.get("url", "")} for r in all_routes if r.get("name")]
                return {"status": "success", "data": routes}
            except Exception as e:
                logger.error(f"[临时账号] 获取线路失败: {e}")
                return {"status": "error", "message": str(e)}

    def on_enable(self):
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        self.log("插件已启用，后台密码更新线程已启动")

    def on_disable(self):
        self._running = False
        self.log("插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "password_length", "label": "密码长度", "type": "number", "placeholder": "12", "hint": "随机密码长度，默认12位"},
            {"key": "password_chars", "label": "密码字符类型", "type": "select", "options": [
                {"value": "alphanumeric", "label": "字母+数字"},
                {"value": "full", "label": "字母+数字+特殊字符"},
            ], "hint": "密码包含的字符类型"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def _get_config(self):
        """获取插件配置"""
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)

    def _generate_password(self) -> str:
        """生成随机密码"""
        config = self._get_config()
        length = int(config.get("password_length", 12) or 12)  # 强制转换为 int
        chars_type = config.get("password_chars", "alphanumeric")
        
        if chars_type == "full":
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
        else:
            chars = string.ascii_letters + string.digits
        
        # 确保至少包含字母和数字
        password = []
        password.append(secrets.choice(string.ascii_lowercase))
        password.append(secrets.choice(string.ascii_uppercase))
        password.append(secrets.choice(string.digits))
        
        # 填充剩余长度
        for _ in range(length - 3):
            password.append(secrets.choice(chars))
        
        # 打乱顺序
        secrets.SystemRandom().shuffle(password)
        return ''.join(password)

    def _create_single_account(self, username: str, template_user_id: str = "",
                               allow_routes: str = "", block_routes: str = "",
                               req_free: int = 0, req_free_count: int = -1,
                               update_interval_hours: int = 24, update_interval_minutes: int = 0,
                               notify_tg: int = 1, notify_wecom: int = 0,
                               remark: str = "临时账号", tags: str = "") -> dict:
        """创建单个临时账号"""
        try:
            emby_host = cfg.get("emby_host", "")
            emby_key = cfg.get("emby_api_key", "")
            if not emby_host or not emby_key:
                return {"success": False, "error": "Emby API 未配置"}
            
            # 检查用户名是否已存在
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            existing = conn.execute(
                "SELECT id FROM temp_accounts WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                conn.close()
                return {"success": False, "error": "用户名已存在"}
            
            # 生成密码
            password = self._generate_password()
            
            # 创建 Emby 用户
            create_res = requests.post(
                f"{emby_host}/Users/New",
                params={"Name": username},
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if create_res.status_code != 200:
                conn.close()
                error_msg = f"创建Emby用户失败: {create_res.status_code}"
                try:
                    err_data = create_res.json()
                    if isinstance(err_data, dict):
                        error_msg = err_data.get("message", error_msg)
                except:
                    pass
                return {"success": False, "error": error_msg}
            
            emby_user = create_res.json()
            emby_user_id = emby_user.get("Id")
            
            # 设置密码
            requests.post(
                f"{emby_host}/Users/{emby_user_id}/Password",
                json={"Id": emby_user_id, "CurrentPw": "", "NewPw": password},
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            
            # 应用权限模板（包含线路权限）
            if template_user_id:
                self._apply_policy_template_with_routes(emby_user_id, template_user_id, allow_routes, block_routes, emby_host, emby_key)
            elif allow_routes or block_routes:
                # 如果没有模板，只应用线路权限
                self._apply_route_policy(emby_user_id, allow_routes, block_routes, emby_host, emby_key)
            
            # 发送创建成功通知
            if notify_tg:
                self._send_tg_notification(username, password, "账号创建成功")
            if notify_wecom:
                self._send_wecom_notification(username, password, "账号创建成功")
            
            # 计算下次更新时间
            now = datetime.datetime.now()
            interval_minutes = update_interval_hours * 60 + update_interval_minutes
            next_update = now + datetime.timedelta(minutes=interval_minutes)
            
            # 写入数据库
            conn.execute("""
                INSERT INTO temp_accounts (
                    username, emby_user_id, current_password, template_user_id,
                    allow_routes, block_routes, req_free, req_free_count,
                    auto_update_enabled, update_interval_hours, update_interval_minutes,
                    last_password_update, next_password_update,
                    notify_tg, notify_wecom, enabled, created_at, remark, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username, emby_user_id, password, template_user_id,
                allow_routes, block_routes, req_free, req_free_count,
                1, update_interval_hours, update_interval_minutes,
                now.isoformat(), next_update.isoformat(),
                notify_tg, notify_wecom, 1, now.isoformat(), remark, tags
            ))
            
            # 同步到 users_meta 表（包括标签）
            conn.execute("""
                INSERT OR REPLACE INTO users_meta (user_id, remark, is_vip, max_concurrent, req_free, req_free_count, allow_routes, block_routes, tags)
                VALUES (?, ?, 0, NULL, ?, ?, ?, ?, ?)
            """, (emby_user_id, remark, req_free, req_free_count, allow_routes, block_routes, tags))
            
            # 同步标签到 user_tags 表（确保标签出现在筛选列表中）
            if tags:
                for tag_name in tags.split(','):
                    tag_name = tag_name.strip()
                    if tag_name:
                        # 检查标签是否存在
                        existing = conn.execute(
                            "SELECT id FROM user_tags WHERE name = ?", (tag_name,)
                        ).fetchone()
                        if not existing:
                            # 创建新标签（默认蓝色）
                            conn.execute(
                                "INSERT INTO user_tags (name, color) VALUES (?, 'blue')",
                                (tag_name,)
                            )
            
            conn.commit()
            conn.close()
            
            self.log(f"创建临时账号: {username}")
            return {"success": True, "password": password, "emby_user_id": emby_user_id}
            
        except Exception as e:
            logger.error(f"[临时账号] 创建账号失败: {e}")
            return {"success": False, "error": str(e)}

    # 权限策略键定义（与 users.py 一致）
    DANGEROUS_POLICY_KEYS = {'IsAdministrator', 'IsDisabled', 'LoginAttemptsBeforeLockout'}
    LIBRARY_POLICY_KEYS = {'EnableAllFolders', 'EnabledFolders', 'ExcludedSubFolders', 'BlockedMediaFolders', 'BlockedChannels', 'EnableAllChannels', 'EnabledChannels'}
    PARENTAL_POLICY_KEYS = {'MaxParentalRating', 'BlockUnratedItems', 'BlockedTags', 'AllowedTags'}

    def _apply_policy_template_with_routes(self, target_user_id: str, template_user_id: str,
                                           allow_routes: str, block_routes: str,
                                           emby_host: str, emby_key: str):
        """应用权限模板并合并线路权限（一次性操作，避免覆盖）"""
        try:
            # 获取模板用户信息
            template_res = requests.get(
                f"{emby_host}/Users/{template_user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if template_res.status_code != 200:
                logger.error(f"[临时账号] 获取模板用户失败: {template_res.status_code}")
                return
            
            template_data = template_res.json()
            template_policy = template_data.get("Policy", {})
            
            # 获取目标用户当前策略
            target_res = requests.get(
                f"{emby_host}/Users/{target_user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if target_res.status_code != 200:
                logger.error(f"[临时账号] 获取目标用户失败: {target_res.status_code}")
                return
            
            target_data = target_res.json()
            target_policy = target_data.get("Policy", {})
            
            # 1. 先复制模板策略（排除危险字段）
            for k, v in template_policy.items():
                if k in self.DANGEROUS_POLICY_KEYS:
                    continue
                target_policy[k] = v
            
            # 2. 如果有线路权限，覆盖媒体库设置
            if allow_routes or block_routes:
                # 获取所有媒体库
                lib_res = requests.get(
                    f"{emby_host}/Library/VirtualFolders",
                    headers={"X-Emby-Token": emby_key},
                    timeout=10
                )
                if lib_res.status_code == 200:
                    libraries = lib_res.json()
                    allow_list = [r.strip() for r in (allow_routes or "").split(",") if r.strip()]
                    block_list = [r.strip() for r in (block_routes or "").split(",") if r.strip()]
                    
                    if allow_list:
                        # 白名单模式
                        target_policy["EnableAllFolders"] = False
                        enabled_folders = []
                        for lib in libraries:
                            lib_id = lib.get("ItemId", "")
                            lib_name = lib.get("Name", "")
                            if lib_id in allow_list or lib_name in allow_list:
                                enabled_folders.append(lib_id)
                        target_policy["EnabledFolders"] = enabled_folders if enabled_folders else target_policy.get("EnabledFolders", [])
                    elif block_list:
                        # 黑名单模式
                        target_policy["EnableAllFolders"] = True
                        excluded_folders = []
                        for lib in libraries:
                            lib_id = lib.get("ItemId", "")
                            lib_name = lib.get("Name", "")
                            if lib_id in block_list or lib_name in block_list:
                                excluded_folders.append(lib_id)
                        target_policy["ExcludedSubFolders"] = excluded_folders
            
            # 更新策略
            update_res = requests.post(
                f"{emby_host}/Users/{target_user_id}/Policy",
                json=target_policy,
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if update_res.status_code == 200:
                logger.info(f"[临时账号] 成功应用权限模板+线路: {template_user_id} -> {target_user_id}")
            else:
                logger.error(f"[临时账号] 更新策略失败: {update_res.status_code} - {update_res.text}")
        except Exception as e:
            logger.error(f"[临时账号] 应用权限模板失败: {e}")

    def _apply_policy_template(self, target_user_id: str, template_user_id: str,
                               emby_host: str, emby_key: str):
        """应用权限模板（与用户管理一致）"""
        try:
            # 获取模板用户信息
            template_res = requests.get(
                f"{emby_host}/Users/{template_user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if template_res.status_code != 200:
                logger.error(f"[临时账号] 获取模板用户失败: {template_res.status_code}")
                return
            
            template_data = template_res.json()
            template_policy = template_data.get("Policy", {})
            
            # 获取目标用户当前策略
            target_res = requests.get(
                f"{emby_host}/Users/{target_user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if target_res.status_code != 200:
                logger.error(f"[临时账号] 获取目标用户失败: {target_res.status_code}")
                return
            
            target_data = target_res.json()
            target_policy = target_data.get("Policy", {})
            
            # 使用与 users.py 一致的克隆逻辑
            for k, v in template_policy.items():
                if k in self.DANGEROUS_POLICY_KEYS:
                    continue
                target_policy[k] = v
            
            # 更新策略
            update_res = requests.post(
                f"{emby_host}/Users/{target_user_id}/Policy",
                json=target_policy,
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if update_res.status_code == 200:
                logger.info(f"[临时账号] 成功应用权限模板: {template_user_id} -> {target_user_id}")
            else:
                logger.error(f"[临时账号] 更新策略失败: {update_res.status_code} - {update_res.text}")
        except Exception as e:
            logger.error(f"[临时账号] 应用权限模板失败: {e}")

    def _delete_emby_user(self, user_id: str):
        """删除 Emby 用户"""
        try:
            emby_host = cfg.get("emby_host", "")
            emby_key = cfg.get("emby_api_key", "")
            if not emby_host or not emby_key:
                return
            
            requests.delete(
                f"{emby_host}/Users/{user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
        except Exception as e:
            logger.error(f"[临时账号] 删除Emby用户失败: {e}")

    def _set_emby_user_enabled(self, user_id: str, enabled: int):
        """设置 Emby 用户启用/禁用状态"""
        try:
            emby_host = cfg.get("emby_host", "")
            emby_key = cfg.get("emby_api_key", "")
            if not emby_host or not emby_key:
                return
            
            # 获取用户当前策略
            user_res = requests.get(
                f"{emby_host}/Users/{user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if user_res.status_code != 200:
                return
            
            user_data = user_res.json()
            policy = user_data.get("Policy", {})
            policy["IsDisabled"] = not enabled
            
            # 更新策略
            requests.post(
                f"{emby_host}/Users/{user_id}/Policy",
                json=policy,
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
        except Exception as e:
            logger.error(f"[临时账号] 设置用户状态失败: {e}")

    def _apply_route_policy(self, user_id: str, allow_routes: str, block_routes: str,
                            emby_host: str, emby_key: str):
        """应用线路权限到 Emby Policy"""
        try:
            # 获取用户当前策略
            user_res = requests.get(
                f"{emby_host}/Users/{user_id}",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if user_res.status_code != 200:
                return
            
            user_data = user_res.json()
            policy = user_data.get("Policy", {})
            
            # 获取所有媒体库
            lib_res = requests.get(
                f"{emby_host}/Library/VirtualFolders",
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            if lib_res.status_code != 200:
                return
            
            libraries = lib_res.json()
            all_folder_ids = [lib.get("ItemId") for lib in libraries if lib.get("ItemId")]
            
            # 解析线路名称对应的媒体库ID
            # 线路名称格式: "线路名" -> 需要找到对应的媒体库
            # 这里简化处理：allow_routes/block_routes 存储的是媒体库ID列表
            allow_list = [r.strip() for r in (allow_routes or "").split(",") if r.strip()]
            block_list = [r.strip() for r in (block_routes or "").split(",") if r.strip()]
            
            if allow_list:
                # 白名单模式：只允许指定媒体库
                policy["EnableAllFolders"] = False
                # 尝试匹配媒体库名称或ID
                enabled_folders = []
                for lib in libraries:
                    lib_id = lib.get("ItemId", "")
                    lib_name = lib.get("Name", "")
                    if lib_id in allow_list or lib_name in allow_list:
                        enabled_folders.append(lib_id)
                policy["EnabledFolders"] = enabled_folders if enabled_folders else all_folder_ids
            elif block_list:
                # 黑名单模式：排除指定媒体库
                policy["EnableAllFolders"] = True
                excluded_folders = []
                for lib in libraries:
                    lib_id = lib.get("ItemId", "")
                    lib_name = lib.get("Name", "")
                    if lib_id in block_list or lib_name in block_list:
                        excluded_folders.append(lib_id)
                policy["ExcludedSubFolders"] = excluded_folders
            
            # 更新策略
            requests.post(
                f"{emby_host}/Users/{user_id}/Policy",
                json=policy,
                headers={"X-Emby-Token": emby_key},
                timeout=10
            )
            logger.info(f"[临时账号] 已应用线路权限: allow={allow_routes}, block={block_routes}")
        except Exception as e:
            logger.error(f"[临时账号] 应用线路权限失败: {e}")

    def _refresh_account_password(self, account_id: int, manual: bool = False) -> dict:
        """刷新账号密码"""
        try:
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM temp_accounts WHERE id = ?", (account_id,)
            ).fetchone()
            
            if not row:
                conn.close()
                return {"success": False, "error": "账号不存在"}
            
            emby_user_id = row["emby_user_id"]
            username = row["username"]
            old_password = row["current_password"]
            notify_tg = row["notify_tg"]
            notify_wecom = row["notify_wecom"]
            update_interval_hours = row["update_interval_hours"]
            update_interval_minutes = row["update_interval_minutes"]
            
            # 生成新密码
            new_password = self._generate_password()
            
            # 更新 Emby 密码
            emby_host = cfg.get("emby_host", "")
            emby_key = cfg.get("emby_api_key", "")
            
            if emby_host and emby_key and emby_user_id:
                # Emby 密码更新 API - 管理员重置不需要 CurrentPw
                # 注意：需要使用 /emby 前缀
                pwd_url = f"{emby_host.rstrip('/')}/emby/Users/{emby_user_id}/Password"
                pwd_res = requests.post(
                    pwd_url,
                    json={"Id": emby_user_id, "NewPw": new_password},
                    headers={"X-Emby-Token": emby_key},
                    params={"api_key": emby_key},
                    timeout=10
                )
                # 204 No Content 也是成功
                if pwd_res.status_code not in [200, 204]:
                    error_detail = pwd_res.text
                    try:
                        err_json = pwd_res.json()
                        error_detail = err_json.get('message', error_detail)
                    except:
                        pass
                    logger.error(f"[临时账号] 更新Emby密码失败: {pwd_res.status_code} - {error_detail}")
                    conn.close()
                    return {"success": False, "error": f"更新Emby密码失败: {error_detail}"}
            
            # 计算下次更新时间
            now = datetime.datetime.now()
            interval_minutes = update_interval_hours * 60 + update_interval_minutes
            next_update = now + datetime.timedelta(minutes=interval_minutes)
            
            # 更新数据库
            conn.execute("""
                UPDATE temp_accounts 
                SET current_password = ?, last_password_update = ?, next_password_update = ?
                WHERE id = ?
            """, (new_password, now.isoformat(), next_update.isoformat(), account_id))
            
            # 记录历史
            conn.execute("""
                INSERT INTO temp_account_password_history (account_id, old_password, new_password, updated_at)
                VALUES (?, ?, ?, ?)
            """, (account_id, old_password, new_password, now.isoformat()))
            
            conn.commit()
            conn.close()
            
            # 发送通知
            notify_sent = False
            if notify_tg:
                notify_sent = self._send_tg_notification(username, new_password) or notify_sent
            if notify_wecom:
                notify_sent = self._send_wecom_notification(username, new_password) or notify_sent
            
            action = "手动刷新" if manual else "自动更新"
            self.log(f"{action}密码: {username} -> {new_password}")
            logger.info(f"[临时账号] 密码刷新成功: {username}, 新密码: {new_password}")
            
            return {
                "success": True,
                "password": new_password,
                "notify_sent": notify_sent
            }
        except Exception as e:
            logger.error(f"[临时账号] 刷新密码失败: {e}")
            return {"success": False, "error": str(e)}

    def _send_tg_notification(self, username: str, password: str, action: str = "密码更新") -> bool:
        """发送 TG 通知（使用系统配置）"""
        try:
            # 使用系统 TG 机器人配置
            bot_token = cfg.get("tg_bot_token", "")
            chat_id = cfg.get("tg_chat_id", "")
            
            if not bot_token or not chat_id:
                logger.warning("[临时账号] TG 机器人未配置")
                return False
            
            if action == "账号创建成功":
                message = f"🎉 临时账号创建成功\n\n用户名: {username}\n密码: {password}\n\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                message = f"🔐 临时账号密码更新\n\n用户名: {username}\n新密码: {password}\n\n更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            proxy = cfg.get("proxy_url")
            proxies = {"http": proxy, "https": proxy} if proxy else None
            
            res = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                proxies=proxies,
                timeout=10
            )
            return res.status_code == 200
        except Exception as e:
            logger.error(f"[临时账号] TG通知失败: {e}")
            return False

    def _send_wecom_notification(self, username: str, password: str, action: str = "密码更新") -> bool:
        """发送企业微信通知（使用系统配置）"""
        try:
            # 使用系统企微配置
            corpid = cfg.get("wecom_corpid", "")
            corpsecret = cfg.get("wecom_corpsecret", "")
            agentid = cfg.get("wecom_agentid", "")
            
            if not corpid or not corpsecret or not agentid:
                logger.warning("[临时账号] 企业微信未配置")
                return False
            
            # 获取 access_token
            proxy_url = cfg.get("wecom_proxy_url", "https://qyapi.weixin.qq.com").rstrip('/')
            token_url = f"{proxy_url}/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}"
            
            proxy = cfg.get("proxy_url")
            proxies = {"http": proxy, "https": proxy} if proxy else None
            
            token_res = requests.get(token_url, proxies=proxies, timeout=10)
            if token_res.status_code != 200:
                return False
            
            access_token = token_res.json().get("access_token")
            if not access_token:
                return False
            
            # 发送消息
            touser = cfg.get("wecom_touser", "@all")
            if action == "账号创建成功":
                message = f"🎉 临时账号创建成功\n\n用户名: {username}\n密码: {password}\n\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                message = f"🔐 临时账号密码更新\n\n用户名: {username}\n新密码: {password}\n\n更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            send_url = f"{proxy_url}/cgi-bin/message/send?access_token={access_token}"
            send_data = {
                "touser": touser,
                "msgtype": "text",
                "agentid": int(agentid),
                "text": {"content": message}
            }
            
            res = requests.post(send_url, json=send_data, proxies=proxies, timeout=10)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"[临时账号] 企微通知失败: {e}")
            return False

    def _check_loop(self):
        """后台检查循环"""
        while self._running:
            try:
                self._check_password_updates()
            except Exception as e:
                logger.error(f"[临时账号] 检查循环错误: {e}")
            
            # 每分钟检查一次
            time.sleep(60)

    def _check_password_updates(self):
        """检查需要更新密码的账号"""
        try:
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            conn.row_factory = sqlite3.Row
            now = datetime.datetime.now()
            
            # 查找需要更新的账号
            rows = conn.execute("""
                SELECT id, username, next_password_update 
                FROM temp_accounts 
                WHERE enabled = 1 AND auto_update_enabled = 1
            """).fetchall()
            
            for row in rows:
                try:
                    next_update = datetime.datetime.fromisoformat(row["next_password_update"])
                    if now >= next_update:
                        self._refresh_account_password(row["id"], manual=False)
                except Exception as e:
                    logger.error(f"[临时账号] 更新账号 {row['username']} 失败: {e}")
            
            conn.close()
        except Exception as e:
            logger.error(f"[临时账号] 检查密码更新失败: {e}")


# 插件实例
plugin = TempAccountPlugin()
