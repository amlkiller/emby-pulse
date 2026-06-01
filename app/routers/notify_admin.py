# 通知管理路由
from fastapi import APIRouter, Request
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.dao.notify_admin_dao import (
    ensure_notify_rules_table as ensure_notify_rules_table_data,
    get_notify_rule_row,
    list_notify_rule_rows,
    save_notify_rules,
)
from app.infra.config.notification_settings import (
    get_notification_channels_config,
    set_notification_channels_config,
)
import json

router = APIRouter()
templates = Jinja2Templates(directory="templates", autoescape=True)
from app.main import APP_VERSION

def ensure_notify_rules_table():
    """确保 notify_rules 表存在"""
    ensure_notify_rules_table_data()

# 启动时确保表存在
ensure_notify_rules_table()

# ==================== 通知规则读取函数 ====================
def get_notify_rule(notify_type: str) -> dict:
    """获取单个通知类型的规则配置，供其他模块调用"""
    try:
        row = get_notify_rule_row(notify_type)
        
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
        rows = list_notify_rule_rows()
        
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
        save_notify_rules(rules)
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

    return {"status": "success", "data": get_notification_channels_config()}


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

    try:
        set_notification_channels_config(data)
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        return {"status": "error", "message": "保存配置失败"}
