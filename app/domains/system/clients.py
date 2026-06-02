import datetime
import logging
import time
from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.infra.clients.media_server_client import media_api
from app.infra.db.audit_dao import create_user_audit_log
from app.domains.system.client_dao import (
    add_client_blacklist,
    add_client_whitelist,
    delete_client_blacklist,
    delete_client_whitelist,
    list_client_blacklist,
    list_client_blacklist_names,
    list_client_whitelist,
    list_client_whitelist_user_ids,
)
from app.domains.system.client_queries import count_playback_clients_by_app, count_playback_devices

from app.domains.users import public_service as user_service
from app.core.security_utils import safe_error_message
from app.core.rate_limiter import get_client_ip

router = APIRouter()
logger = logging.getLogger(__name__)

# ==========================================
# 操作审计日志
# ==========================================

def add_audit_log(admin_id: str, admin_name: str, action: str, 
                  target_user_id: str = None, target_user_name: str = None,
                  target_count: int = 0, details: str = "", ip_address: str = ""):
    """添加操作审计日志"""
    try:
        create_user_audit_log(
            admin_id=admin_id,
            admin_name=admin_name,
            action=action,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            target_count=target_count,
            details=details,
            ip_address=ip_address,
            created_at=datetime.datetime.now().isoformat(),
        )
    except Exception as e:
        logging.error(f"[审计日志] 添加失败: {e}")

# 表结构由 db_schemas.py 统一管理，这里不再单独创建

class BlacklistModel(BaseModel):
    app_name: str

class WhitelistModel(BaseModel):
    user_id: str
    user_name: str

# 👇 免费功能：任何人都可以查看黑名单列表
@router.get("/api/clients/blacklist")
async def get_blacklist(request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    rows = list_client_blacklist()
    return {"status": "success", "data": [dict(r) for r in rows] if rows else []}

# 👇 🔥 PRO 功能：添加设备到黑名单
@router.post("/api/clients/blacklist")
async def add_blacklist(data: BlacklistModel, request: Request):
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    app_name = data.app_name.strip()
    if not app_name: 
        return {"status": "error", "message": "软件名不能为空"}
    try:
        add_client_blacklist(app_name)
        
        # 记录审计日志
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = get_client_ip(request)
        add_audit_log(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="添加客户端黑名单",
            target_user_name=app_name,
            details=f"客户端: {app_name}",
            ip_address=ip_address
        )
        
        return {"status": "success"}
    except:
        return {"status": "error", "message": f"[{app_name}] 已存在于黑名单中"}

# 👇 🔥 PRO 功能：从黑名单移除设备
@router.delete("/api/clients/blacklist/{app_name}")
async def delete_blacklist(app_name: str, request: Request):
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    delete_client_blacklist(app_name)
    
    # 记录审计日志
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知"))
    ip_address = get_client_ip(request)
    add_audit_log(
        admin_id=admin_user.get("id", ""),
        admin_name=admin_name,
        action="移除客户端黑名单",
        target_user_name=app_name,
        details=f"客户端: {app_name}",
        ip_address=ip_address
    )
    
    return {"status": "success"}

# ==================== 🔥 白名单用户管理 ====================

# 👇 免费功能：查看白名单用户列表
@router.get("/api/clients/whitelist")
async def get_whitelist(request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    rows = list_client_whitelist()
    return {"status": "success", "data": [dict(r) for r in rows] if rows else []}

# 👇 🔥 PRO 功能：添加用户到白名单
@router.post("/api/clients/whitelist")
async def add_whitelist(data: WhitelistModel, request: Request):
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    user_id = data.user_id.strip()
    user_name = data.user_name.strip()
    if not user_id or not user_name:
        return {"status": "error", "message": "用户ID和用户名不能为空"}
    try:
        add_client_whitelist(user_id, user_name)
        
        # 记录审计日志
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = get_client_ip(request)
        add_audit_log(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="添加客户端白名单用户",
            target_user_id=user_id,
            target_user_name=user_name,
            details=f"白名单用户: {user_name}",
            ip_address=ip_address
        )
        
        return {"status": "success"}
    except:
        return {"status": "error", "message": f"用户 [{user_name}] 已存在于白名单中"}

# 👇 🔥 PRO 功能：从白名单移除用户
@router.delete("/api/clients/whitelist/{user_id}")
async def delete_whitelist(user_id: str, request: Request):
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    delete_client_whitelist(user_id)
    
    # 记录审计日志
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知"))
    ip_address = get_client_ip(request)
    add_audit_log(
        admin_id=admin_user.get("id", ""),
        admin_name=admin_name,
        action="移除客户端白名单用户",
        target_user_id=user_id,
        details=f"白名单用户ID: {user_id}",
        ip_address=ip_address
    )
    
    return {"status": "success"}

# 👇 🔥 PRO 功能：批量添加用户到白名单
@router.post("/api/clients/whitelist/batch")
async def batch_add_whitelist(request: Request):
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    users = data.get("users", [])
    if not users:
        return {"status": "error", "message": "用户列表不能为空"}
    
    added_count = 0
    skipped_count = 0
    
    for user in users:
        user_id = user.get("user_id", "").strip()
        user_name = user.get("user_name", "").strip()
        if not user_id or not user_name:
            skipped_count += 1
            continue
        try:
            add_client_whitelist(user_id, user_name)
            added_count += 1
        except:
            skipped_count += 1
    
    # 记录审计日志
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知"))
    ip_address = get_client_ip(request)
    add_audit_log(
        admin_id=admin_user.get("id", ""),
        admin_name=admin_name,
        action="批量添加客户端白名单用户",
        target_count=added_count,
        details=f"成功添加 {added_count} 个用户，跳过 {skipped_count} 个",
        ip_address=ip_address
    )
    
    return {"status": "success", "added": added_count, "skipped": skipped_count}

# 👇 🔥 PRO 功能：批量移除白名单用户
@router.post("/api/clients/whitelist/batch-delete")
async def batch_delete_whitelist(request: Request):
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    user_ids = data.get("user_ids", [])
    if not user_ids:
        return {"status": "error", "message": "用户ID列表不能为空"}
    
    deleted_count = 0
    for user_id in user_ids:
        delete_client_whitelist(user_id)
        deleted_count += 1
    
    # 记录审计日志
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知"))
    ip_address = get_client_ip(request)
    add_audit_log(
        admin_id=admin_user.get("id", ""),
        admin_name=admin_name,
        action="批量移除客户端白名单用户",
        target_count=deleted_count,
        details=f"移除 {deleted_count} 个白名单用户",
        ip_address=ip_address
    )
    
    return {"status": "success", "deleted": deleted_count}

def parse_emby_utc(date_str):
    if not date_str: return ""
    try:
        clean_str = date_str.split('.')[0].replace('Z', '')
        dt = datetime.datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
        local_dt = dt + datetime.timedelta(hours=8)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str.replace("T", " ").split(".")[0]

# ==================== 🔥 客户端数据缓存 ====================
_clients_cache = {"data": None, "expires": 0}
CLIENTS_CACHE_TTL = 30  # 30 秒缓存

def get_clients_data_cached():
    """获取客户端数据（带缓存）"""
    if _clients_cache["data"] and time.time() < _clients_cache["expires"]:
        return _clients_cache["data"]
    return None

def set_clients_data_cached(data):
    """设置客户端数据缓存"""
    _clients_cache["data"] = data
    _clients_cache["expires"] = time.time() + CLIENTS_CACHE_TTL

# 👇 免费功能：任何人都可以看终端数据和大盘
@router.get("/api/clients/data")
async def get_clients_data(request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    # 🔥 每次请求都检查黑名单（防止漏网之鱼）
    check_and_block_blacklist_devices()
    
    # 🔥 尝试使用缓存
    cached = get_clients_data_cached()
    if cached:
        return cached

    try:
        res = media_api.get("/Devices", timeout=5)
        devices = res.json().get("Items", [])
        
        sess_res = media_api.get("/Sessions", timeout=5)
        sessions = sess_res.json()
        active_sigs = [{
            "device_id": s.get("DeviceId", ""), 
            "client": s.get("Client", ""), 
            "user_name": s.get("UserName", "")
        } for s in sessions if s.get("NowPlayingItem")]
        
        # 🔥 获取有效用户ID列表（过滤已删除用户）
        users_res = media_api.get("/Users", timeout=5)
        valid_user_ids = set()
        valid_user_names = set()
        if users_res.status_code == 200:
            for u in users_res.json():
                valid_user_ids.add(u.get("Id"))
                valid_user_names.add(u.get("Name"))
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "连接媒体服务器失败")}

    app_counts = {}
    top_devices = {}
    
    try:
        pie_rows = count_playback_clients_by_app()
        if pie_rows:
            app_counts = {r['c_name']: r['cnt'] for r in pie_rows}
            
        bar_rows = count_playback_devices()
        if bar_rows:
            top_devices = {r['DeviceName']: r['cnt'] for r in bar_rows}
    except Exception as e:
        logger.warning(f"[客户端统计] 查询播放数据失败: {e}")

    if not app_counts:
        for d in devices:
            an = d.get("AppName") or "未知客户端"
            app_counts[an] = app_counts.get(an, 0) + 1
            
    if not top_devices:
        sorted_devs = sorted(devices, key=lambda x: x.get("DateLastActivity", ""), reverse=True)[:10]
        top_devices = { (d.get("Name") or "未知设备"): 1 for d in sorted_devs}

    blacklist_rows = list_client_blacklist_names()
    blacklist = [r['app_name'].lower() for r in blacklist_rows] if blacklist_rows else []
    
    # 🔥 获取白名单用户列表
    whitelist_rows = list_client_whitelist_user_ids()
    whitelist_user_ids = set(r['user_id'] for r in whitelist_rows) if whitelist_rows else set()

    table_data = []
    now_utc = datetime.datetime.utcnow()
    
    # 🔥 如果获取用户列表失败，不过滤任何设备
    filter_deleted_users = len(valid_user_ids) > 0
    filtered_count = 0

    for d in devices:
        app_name = d.get("AppName") or "未知客户端"
        date_str = d.get("DateLastActivity", "")
        last_active = parse_emby_utc(date_str) if date_str else "从未连接"
        last_user = d.get("LastUserName") or ""
        last_user_id = d.get("LastUserId") or ""
        
        # 🔥 判断是否被阻断：黑名单客户端 且 不在白名单用户中
        is_blocked = app_name.lower() in blacklist
        if is_blocked and last_user_id and last_user_id in whitelist_user_ids:
            is_blocked = False  # 白名单用户无视黑名单
        
        if filter_deleted_users:
            # 如果有用户名但不在有效列表中，跳过
            if last_user and last_user not in valid_user_names:
                filtered_count += 1
                continue
            # 如果有用户ID但不在有效列表中，跳过
            if last_user_id and last_user_id not in valid_user_ids:
                filtered_count += 1
                continue
            # 🔥 隐藏没有关联用户的设备
            if not last_user and not last_user_id:
                filtered_count += 1
                continue
        
        # 显示用户名
        display_user = last_user if last_user else "未知用户"
        
        time_diff_sec = 9999999
        if date_str:
            try:
                clean_str = date_str.split('.')[0].replace('Z', '')
                dt = datetime.datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
                time_diff_sec = abs((now_utc - dt).total_seconds())
            except Exception:
                pass

        d_id = d.get("Id", "")
        is_active = False
        
        for sig in active_sigs:
            if d_id and sig["device_id"] and d_id == sig["device_id"]:
                is_active = True
                break
            if app_name and sig["client"] and last_user and sig["user_name"]:
                if app_name.lower() == sig["client"].lower() and last_user.lower() == sig["user_name"].lower():
                    if time_diff_sec <= 900:
                        is_active = True
                        break
        
        table_data.append({
            "id": d_id,
            "name": d.get("Name") or "未知设备",
            "app_name": app_name,
            "last_active": last_active,
            "last_user": display_user,
            "is_active": is_active,
            "is_blocked": is_blocked
        })

    table_data.sort(key=lambda x: x["last_active"], reverse=True)

    result = {
        "status": "success",
        "charts": {
            "pie": {"labels": list(app_counts.keys()), "data": list(app_counts.values())},
            "bar": {"labels": list(top_devices.keys()), "data": list(top_devices.values())}
        },
        "devices": table_data
    }
    
    # 🔥 缓存结果
    set_clients_data_cached(result)
    return result

# 👇 🔥 PRO 功能：全网阻断扫描
@router.post("/api/clients/execute_block")
async def execute_block(request: Request):
    """执行一次阻断扫描"""
    # 🔒 安全检查：写操作必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    result = _do_block_devices()  # 不是异步函数，不需要 await
    
    # 记录审计日志
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知"))
    ip_address = get_client_ip(request)
    add_audit_log(
        admin_id=admin_user.get("id", ""),
        admin_name=admin_name,
        action="执行客户端阻断",
        target_count=result["blocked_count"],
        details=f"阻断设备: {', '.join(result['blocked_names'][:10])}{'...' if len(result['blocked_names']) > 10 else ''}",
        ip_address=ip_address
    )
    
    msg = f"扫描完成！成功强制注销了 {result['blocked_count']} 个违规设备。"
    if result.get('whitelist_skipped', 0) > 0:
        msg += f" 白名单用户跳过 {result['whitelist_skipped']} 个。"
    return {"status": "success", "message": msg}


def _do_block_devices():
    """执行阻断逻辑（可被定时任务调用）"""
    blacklist_rows = list_client_blacklist_names()
    if not blacklist_rows:
        return {"blocked_count": 0, "blocked_names": [], "whitelist_skipped": 0}
    
    blacklist = [r['app_name'].lower() for r in blacklist_rows]
    
    # 🔥 获取白名单用户列表
    whitelist_rows = list_client_whitelist_user_ids()
    whitelist_user_ids = set(r['user_id'] for r in whitelist_rows) if whitelist_rows else set()
    
    blocked_count = 0
    blocked_names = []
    whitelist_skipped = 0  # 白名单用户跳过计数
    
    try:
        res = media_api.get("/Devices", timeout=5)
        devices = res.json().get("Items", [])
        
        for d in devices:
            app_name = (d.get("AppName") or "").lower()
            last_user_id = d.get("LastUserId") or ""
            
            if app_name in blacklist:
                # 🔥 检查是否为白名单用户
                if last_user_id and last_user_id in whitelist_user_ids:
                    whitelist_skipped += 1
                    logger.info(f"[白名单跳过] 用户 {d.get('LastUserName')} 在白名单中，跳过阻断")
                    continue
                
                blocked_names.append(d.get("AppName") or app_name)
                try:
                    media_api.delete("/Devices", params={"Id": d['Id']}, timeout=2)
                    blocked_count += 1
                except Exception as e:
                    logger.warning(f"[阻断设备失败] {d.get('AppName')}: {e}")
        
        return {"blocked_count": blocked_count, "blocked_names": blocked_names, "whitelist_skipped": whitelist_skipped}
    except Exception as e:
        logger.error(f"[执行阻断失败] {e}")
        return {"blocked_count": 0, "blocked_names": [], "whitelist_skipped": 0}


# 🔥 定时检查黑名单设备（每 30 秒）
_block_check_interval = 30  # 秒
_last_block_check = 0

def check_and_block_blacklist_devices():
    """定时检查并阻断黑名单设备（由调用方决定是否执行）"""
    global _last_block_check
    current_time = time.time()
    
    # 检查是否到达检查间隔
    if current_time - _last_block_check < _block_check_interval:
        return None
    
    _last_block_check = current_time
    
    # 执行阻断
    result = _do_block_devices()
    if result["blocked_count"] > 0:
        logger.info(f"🔥 [定时阻断] 踢出 {result['blocked_count']} 个黑名单设备: {', '.join(result['blocked_names'][:5])}")
    
    return result
