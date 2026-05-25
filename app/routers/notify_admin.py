# 通知管理路由
from fastapi import APIRouter, Request
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.database import query_db, SYSTEM_DB_PATH
from app.core.config import cfg
import sqlite3
import json
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates", autoescape=True)
from app.main import APP_VERSION

def ensure_notify_rules_table():
    """确保 notify_rules 表存在"""
    if not os.path.exists(SYSTEM_DB_PATH):
        return
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notify_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notify_type TEXT UNIQUE NOT NULL,
        notify_name TEXT NOT NULL,
        channels TEXT DEFAULT '[]',
        enabled INTEGER DEFAULT 1,
        config TEXT DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

# 启动时确保表存在
ensure_notify_rules_table()

# ==================== 通知规则读取函数 ====================
def get_notify_rule(notify_type: str) -> dict:
    """获取单个通知类型的规则配置，供其他模块调用"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM notify_rules WHERE notify_type = ?", (notify_type,))
        row = c.fetchone()
        conn.close()
        
        if row:
            rule = dict(row)
            rule["channels"] = json.loads(rule.get("channels", "[]"))
            return rule
    except Exception as e:
        pass
    
    # 返回默认值
    for t in NOTIFY_TYPES:
        if t["type"] == notify_type:
            return {
                "notify_type": notify_type,
                "notify_name": t["name"],
                "enabled": 1,
                "channels": t["default_channels"]
            }
    return None

# ==================== 通知类型定义 ====================
NOTIFY_TYPES = [
    {"type": "user_register", "name": "用户注册", "desc": "邀请码注册成功", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "user_login", "name": "用户登录", "desc": "用户登录 Emby", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "user_delete", "name": "用户删除", "desc": "用户账号删除", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "media_delete", "name": "媒体删除", "desc": "媒体物理删除", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "risk_alert", "name": "风险告警", "desc": "并发/违规检测告警", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "request_new", "name": "工单提交", "desc": "求片申请提交", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "request_done", "name": "工单完成", "desc": "求片入库完成", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "request_update", "name": "追新提交", "desc": "追新请求提交", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "request_update_done", "name": "追新完成", "desc": "追新入库完成", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "request_status", "name": "工单状态变更", "desc": "工单审批/入库/拒绝通知用户", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "feedback_new", "name": "用户报错", "desc": "用户提交报错反馈", "default_channels": ["tg_bot", "wecom"]},
    {"type": "point_redeem", "name": "积分兑换", "desc": "商城兑换商品", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "task_exec", "name": "任务执行", "desc": "定时任务完成/失败", "default_channels": ["tg_bot", "wecom", "web"]},
    {"type": "user_expire", "name": "用户过期预警", "desc": "到期前 N 天预警", "default_channels": ["tg_bot", "wecom"]},
    {"type": "library_new", "name": "媒体入库", "desc": "电影/剧集入库", "default_channels": ["tg_channel", "wecom"]},
    {"type": "view_report", "name": "观影报告", "desc": "日报/周报/月报推送", "default_channels": ["tg_channel", "wecom"]},
    {"type": "hdhive_sign", "name": "签到完成", "desc": "影巢签到结果", "default_channels": ["tg_bot", "wecom"]},
    {"type": "msg_center", "name": "消息中心", "desc": "用户发送消息通知", "default_channels": ["tg_bot", "wecom"]},
]

CHANNEL_OPTIONS = [
    {"id": "tg_bot", "name": "TG 管理机器人", "icon": "fa-telegram"},
    {"id": "tg_channel", "name": "TG 频道", "icon": "fa-bullhorn"},
    {"id": "wecom", "name": "企业微信", "icon": "fa-weixin"},
    {"id": "web", "name": "Web 通知中心", "icon": "fa-bell"},
]


# ==================== 页面路由 ====================
@router.get("/notify_admin", response_class=HTMLResponse)
def notify_admin_page(request: Request):
    """通知管理页面"""
    # 检查登录状态
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    
    # 获取用户权限信息
    user_permissions = user.get("permissions", [])
    if isinstance(user_permissions, str):
        try:
            user_permissions = json.loads(user_permissions)
        except:
            user_permissions = []
    
    is_admin = user.get("auth_type") == "emby" or user.get("role") == "admin"
    user_name = user.get("name", "用户")
    user_avatar = user.get("avatar", "")
    
    is_pro = True
    
    return templates.TemplateResponse(
        "notify_admin.html",
        {
            "request": request,
            "version": APP_VERSION,
            "active_page": "notify_admin",
            "user_permissions": user_permissions,
            "is_admin": is_admin,
            "user_name": user_name,
            "user_avatar": user_avatar,
            "is_pro": is_pro
        }
    )


# ==================== API 路由 ====================
@router.get("/api/notify/types")
def api_get_notify_types(request: Request):
    """获取通知类型定义"""
    # 🔥 安全：必须登录才能访问
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "请先登录"}
    return {"status": "success", "data": NOTIFY_TYPES, "channels": CHANNEL_OPTIONS}


@router.get("/api/notify/rules")
def api_get_notify_rules(request: Request):
    """获取通知规则配置"""
    # 🔥 安全：必须登录才能访问
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "请先登录"}
    
    ensure_notify_rules_table()
    
    rules_dict = {}
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM notify_rules")
        rows = c.fetchall()
        conn.close()
        
        for r in rows:
            rule = dict(r)
            rule["channels"] = json.loads(rule.get("channels", "[]"))
            rule["config"] = json.loads(rule.get("config", "{}"))
            rules_dict[rule["notify_type"]] = rule
    except Exception:
        pass
    
    # 补充默认值
    for t in NOTIFY_TYPES:
        if t["type"] not in rules_dict:
            rules_dict[t["type"]] = {
                "notify_type": t["type"],
                "notify_name": t["name"],
                "channels": t["default_channels"],
                "enabled": 1,
                "config": {}
            }
    
    return {"status": "success", "data": rules_dict}


@router.post("/api/notify/rules")
def api_save_notify_rules(request: Request, data: dict):
    """保存通知规则配置"""
    # 检查登录状态
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "请先登录"}
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    rules = data.get("rules", {})
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        for notify_type, rule in rules.items():
            channels_json = json.dumps(rule.get("channels", []))
            config_json = json.dumps(rule.get("config", {}))
            # 🔥 布尔值转换为整数
            enabled = 1 if rule.get("enabled", False) else 0
            notify_name = rule.get("notify_name", notify_type)
            
            c.execute("""
                INSERT OR REPLACE INTO notify_rules 
                (notify_type, notify_name, channels, enabled, config, updated_at) 
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
            """, (notify_type, notify_name, channels_json, enabled, config_json))
        
        conn.commit()
        conn.close()
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        return {"status": "error", "message": "保存规则失败"}


@router.get("/api/notify/channels_config")
def api_get_channels_config(request: Request):
    """获取通知渠道配置（TG机器人、TG频道、企业微信）"""
    # 检查登录状态
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "请先登录"}
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 🔒 安全：脱敏敏感字段
    def mask_token(value):
        if not value or not isinstance(value, str):
            return value
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]
    
    config = {
        "tg_bot": {
            "token": mask_token(cfg.get("tg_bot_token", "")),
            "chat_id": cfg.get("tg_chat_id", ""),
            "enabled": cfg.get("enable_bot", False)
        },
        "tg_channels": json.loads(cfg.get("notify_channels", "[]")),
        "wecom": {
            "webhook": mask_token(cfg.get("wecom_webhook", cfg.get("wechat_webhook", ""))),
            "enabled": cfg.get("enable_wecom", cfg.get("enable_wechat", False))
        }
    }
    return {"status": "success", "data": config}


@router.post("/api/notify/channels_config")
def api_save_channels_config(request: Request, data: dict):
    """保存通知渠道配置"""
    # 检查登录状态
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "请先登录"}
    # 🔒 安全检查：必须管理员（该接口可修改 TG Token / Webhook，必须严格校验）
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 🔒 安全：如果值包含脱敏标记 ****，则不更新（保留原值）
    def should_update(value):
        if not value or not isinstance(value, str):
            return False
        return "****" not in value
    
    try:
        # 更新配置
        if "tg_bot" in data:
            token = data["tg_bot"].get("token", "")
            if should_update(token):
                cfg.config["tg_bot_token"] = token
            cfg.config["tg_chat_id"] = data["tg_bot"].get("chat_id", "")
            cfg.config["enable_bot"] = data["tg_bot"].get("enabled", False)
        
        if "tg_channels" in data:
            cfg.config["notify_channels"] = json.dumps(data["tg_channels"])
        
        if "wecom" in data:
            webhook = data["wecom"].get("webhook", "")
            if should_update(webhook):
                cfg.config["wecom_webhook"] = webhook
            cfg.config["enable_wecom"] = data["wecom"].get("enabled", False)
        
        cfg.save()
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        return {"status": "error", "message": "保存配置失败"}
