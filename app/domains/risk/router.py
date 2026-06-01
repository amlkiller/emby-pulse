from fastapi import APIRouter, HTTPException, Request
from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
from pydantic import BaseModel
import json
from app.dao.risk_dao import (
    count_recent_risk_actions,
    count_vip_users,
    list_risk_logs,
    list_top_risk_offenders,
)
from app.infra.clients.media_server_client import media_api
from app.infra.config.risk_settings import (
    get_default_max_concurrent,
    get_max_devices,
    get_violation_action,
    is_risk_control_enabled,
    is_risk_sys_notification_enabled,
    set_default_max_concurrent,
    set_risk_control_enabled,
    set_risk_sys_notification_enabled,
    set_violation_action,
)
from app.services.risk_service import ban_user, unban_user, log_risk_action, get_user_concurrent_limit
from app.core.security_utils import safe_error_message

router = APIRouter(prefix="/api/risk", tags=["RiskControl"])

class ActionRequest(BaseModel):
    user_id: str
    username: str
    session_id: str = None
    device_id: str = None  # 🔥 新增设备ID参数，用于物理拔网线
    reason: str = "风控系统强制执行"

class ConfigRequest(BaseModel):
    enable_risk_control: bool
    default_max_concurrent: int
    violation_action: str = "warn_only"  # warn_only | warn_user | auto_ban
    enable_sys_notification: bool = True  # 是否推送到全局通知中心

@router.get("/online")
def get_online_status(request: Request):
    """获取所有在线用户的风控大盘数据"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    if not media_api.host or not media_api.api_key: return {"error": "未配置 Emby 服务器信息"}

    try:
        res = media_api.get("/Sessions", timeout=10)
        if res.status_code != 200: return {"error": "无法连接到 Emby"}

        sessions = res.json()
        active_users = {}
        
        # 当前时间（用于判断最近活跃）
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        active_threshold = timedelta(minutes=5)  # 5分钟内活跃算在线

        for s in sessions:
            uid = s.get("UserId")
            if not uid: continue
            
            # 判断是否在线：正在播放 或 最近5分钟有活动
            is_playing = s.get("NowPlayingItem") and s["NowPlayingItem"].get("MediaType") == "Video"
            
            # 检查最后活动时间
            last_activity = s.get("LastActivityDate")
            is_recently_active = False
            if last_activity:
                try:
                    # Emby 返回的是 ISO 格式时间
                    last_dt = datetime.fromisoformat(last_activity.replace('Z', '+00:00').replace('+00:00', ''))
                    is_recently_active = (now - last_dt) < active_threshold
                except:
                    pass
            
            # SupportsRemoteControl 为 True 也算在线
            is_remote_control = s.get("SupportsRemoteControl", False)
            
            # 只统计真正在线的设备
            if not (is_playing or is_recently_active or is_remote_control):
                continue
            
            if uid not in active_users:
                limit, is_vip = get_user_concurrent_limit(uid)
                active_users[uid] = {
                    "user_id": uid, "username": s.get("UserName", "未知"),
                    "limit": limit, "current_count": 0, "is_warning": False,
                    "is_vip": is_vip, "devices": []
                }

            # 如果正在播放视频，计入 current_count
            if is_playing:
                active_users[uid]["current_count"] += 1
            
            active_users[uid]["devices"].append({
                "session_id": s.get("Id"),
                "device_id": s.get("DeviceId"),
                "device_name": s.get("DeviceName", "未知设备"),
                "client": s.get("Client", "未知客户端"),
                "ip": s.get("RemoteEndPoint", "未知IP"),
                "item_name": s["NowPlayingItem"].get("Name", "未知影片") if s.get("NowPlayingItem") else "空闲"
            })

        result_list = []
        for uid, data in active_users.items():
            # VIP用户永远不显示警告（limit为-1表示无限制）
            if not data.get("is_vip") and data["current_count"] > data["limit"]:
                data["is_warning"] = True
            result_list.append(data)

        result_list.sort(key=lambda x: x["is_warning"], reverse=True)
        
        # 获取全局最大设备数配置
        max_devices = get_max_devices()
        
        return {"data": result_list, "max_devices": max_devices}
    except Exception as e:
        return {"error": safe_error_message(e)}

@router.post("/kick")
def api_kick_session(req: ActionRequest, request: Request):
    """🔥 真·物理拔网线：直接注销第三方播放器的设备 Token"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未授权")
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    # 1. 发送常规 Stop 指令 (给官方客户端面子)
    if req.session_id:
        media_api.post(f"/Sessions/{req.session_id}/Playing/Stop", timeout=5)

    # 2. 降维打击：直接删除设备登录凭证 (专门对付 Infuse 等第三方流氓客户端)
    if req.device_id:
        media_api.delete("/Devices", params={"Id": req.device_id}, timeout=5)

    log_risk_action(req.user_id, req.username, "kick", "强制注销设备Token并断开")
    return {"message": "已成功拔掉该设备的网线！"}

@router.post("/ban")
def api_ban_user(req: ActionRequest, request: Request):
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未授权")
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    if ban_user(req.user_id):
        log_risk_action(req.user_id, req.username, "ban", req.reason)
        return {"message": f"用户 {req.username} 已被关入小黑屋并冻结"}
    raise HTTPException(status_code=500, detail="封禁失败，请检查 API 权限")

@router.post("/unban")
def api_unban_user(req: ActionRequest, request: Request):
    """解封用户"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未授权")
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    if unban_user(req.user_id):
        log_risk_action(req.user_id, req.username, "unban", "管理员解封")
        return {"message": f"用户 {req.username} 已解除封禁"}
    raise HTTPException(status_code=500, detail="解封失败，请检查 API 权限")

@router.get("/user_status/{user_id}")
def get_user_status(user_id: str, request: Request):
    """获取用户封禁状态"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    try:
        if not media_api.host or not media_api.api_key:
            return {"error": "未配置 Emby 服务器信息"}

        res = media_api.get(f"/Users/{user_id}", timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            is_disabled = user_data.get("Policy", {}).get("IsDisabled", False)
            return {"user_id": user_id, "is_banned": is_disabled, "username": user_data.get("Name", "未知")}
        return {"error": "无法获取用户信息"}
    except Exception as e:
        return {"error": safe_error_message(e)}

@router.get("/logs")
def get_risk_logs(request: Request):
    """获取历史审计日志"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    try:
        rows = list_risk_logs()
        return {"data": [dict(r) for r in rows]}
    except: return {"data": []}

@router.get("/config")
def get_risk_config(request: Request):
    """获取风控设置"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    return {
        "enable_risk_control": is_risk_control_enabled(),
        "default_max_concurrent": get_default_max_concurrent(),
        "violation_action": get_violation_action(),
        "enable_sys_notification": is_risk_sys_notification_enabled()
    }

@router.post("/config")
def update_risk_config(req: ConfigRequest, request: Request):
    """保存风控设置"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未授权")
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    set_risk_control_enabled(req.enable_risk_control)
    set_default_max_concurrent(req.default_max_concurrent)
    set_violation_action(req.violation_action)
    set_risk_sys_notification_enabled(req.enable_sys_notification)
    return {"message": "配置已生效"}

@router.get("/summary")
def get_risk_summary(request: Request):
    """空闲状态下的风控战报简报"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    try:
        # 1. 统计近 24 小时的拦截数据
        today_stats = {"warn": 0, "kick": 0, "ban": 0}
        for row in count_recent_risk_actions():
            today_stats[row['action']] = row['cnt']

        # 2. 统计历史高危账号排行榜 (违规次数最多的前 5 名)
        top_offenders = [dict(r) for r in list_top_risk_offenders()]

        # 3. 统计有多少人拥有"专属并发特权"
        vip_count = count_vip_users()

        return {
            "status": "success",
            "today_stats": today_stats,
            "top_offenders": top_offenders,
            "vip_count": vip_count,
            "global_limit": get_default_max_concurrent()
        }
    except Exception as e:
        return {"error": safe_error_message(e)}
