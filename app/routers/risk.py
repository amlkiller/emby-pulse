from fastapi import APIRouter, HTTPException, Request
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from pydantic import BaseModel
import sqlite3
import requests
import json
from app.core.config import cfg, DB_PATH, save_config
from app.core.database import SYSTEM_DB_PATH
from app.services.risk_service import ban_user, unban_user, log_risk_action, get_user_concurrent_limit

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
    
    host = cfg.get("emby_host", "").rstrip('/')
    api_key = cfg.get("emby_api_key", "")
    if not host or not api_key: return {"error": "未配置 Emby 服务器信息"}

    try:
        res = requests.get(f"{host}/emby/Sessions", headers={"X-Emby-Token": api_key}, timeout=10)
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
        max_devices = cfg.get("max_devices", 10)
        
        return {"data": result_list, "max_devices": max_devices}
    except Exception as e:
        return {"error": str(e)}

@router.post("/kick")
def api_kick_session(req: ActionRequest, request: Request):
    """🔥 真·物理拔网线：直接注销第三方播放器的设备 Token"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未授权")
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    host = cfg.get("emby_host", "").rstrip('/')
    api_key = cfg.get("emby_api_key", "")

    # 1. 发送常规 Stop 指令 (给官方客户端面子)
    if req.session_id:
        requests.post(f"{host}/emby/Sessions/{req.session_id}/Playing/Stop", headers={"X-Emby-Token": api_key}, timeout=5)

    # 2. 降维打击：直接删除设备登录凭证 (专门对付 Infuse 等第三方流氓客户端)
    if req.device_id:
        delete_url = f"{host}/emby/Devices?Id={req.device_id}"
        requests.delete(delete_url, headers={"X-Emby-Token": api_key}, timeout=5)

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
        host = cfg.get("emby_host", "").rstrip('/')
        api_key = cfg.get("emby_api_key", "")
        if not host or not api_key:
            return {"error": "未配置 Emby 服务器信息"}

        res = requests.get(f"{host}/emby/Users/{user_id}", headers={"X-Emby-Token": api_key}, timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            is_disabled = user_data.get("Policy", {}).get("IsDisabled", False)
            return {"user_id": user_id, "is_banned": is_disabled, "username": user_data.get("Name", "未知")}
        return {"error": "无法获取用户信息"}
    except Exception as e:
        return {"error": str(e)}

@router.get("/logs")
def get_risk_logs(request: Request):
    """获取历史审计日志"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM risk_logs ORDER BY created_at DESC LIMIT 200")
        rows = cur.fetchall()
        conn.close()
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
        "enable_risk_control": cfg.get("enable_risk_control", False),
        "default_max_concurrent": cfg.get("default_max_concurrent", 2),
        "violation_action": cfg.get("violation_action", "warn_only"),
        "enable_sys_notification": cfg.get("enable_risk_sys_notification", True)
    }

@router.post("/config")
def update_risk_config(req: ConfigRequest, request: Request):
    """保存风控设置"""
    # 🔒 安全检查：必须管理员
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未授权")
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    cfg["enable_risk_control"] = req.enable_risk_control
    cfg["default_max_concurrent"] = req.default_max_concurrent
    cfg["violation_action"] = req.violation_action
    cfg["enable_risk_sys_notification"] = req.enable_sys_notification
    save_config()
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
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. 统计近 24 小时的拦截数据
        cur.execute("SELECT action, COUNT(*) as cnt FROM risk_logs WHERE datetime(created_at) >= datetime('now', '-1 day') GROUP BY action")
        today_stats = {"warn": 0, "kick": 0, "ban": 0}
        for row in cur.fetchall():
            today_stats[row['action']] = row['cnt']

        # 2. 统计历史高危账号排行榜 (违规次数最多的前 5 名)
        cur.execute("SELECT username, COUNT(*) as total_violations FROM risk_logs GROUP BY username ORDER BY total_violations DESC LIMIT 5")
        top_offenders = [dict(r) for r in cur.fetchall()]

        # 3. 统计有多少人拥有"专属并发特权"
        cur.execute("SELECT COUNT(*) as vip_count FROM users_meta WHERE is_vip = 1")
        vip_row = cur.fetchone()
        vip_count = vip_row['vip_count'] if vip_row else 0

        conn.close()
        return {
            "status": "success",
            "today_stats": today_stats,
            "top_offenders": top_offenders,
            "vip_count": vip_count,
            "global_limit": cfg.get("default_max_concurrent", 2)
        }
    except Exception as e:
        return {"error": str(e)}