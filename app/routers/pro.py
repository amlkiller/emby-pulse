import sqlite3
import requests
import asyncio
import os
import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from app.core.config import cfg, DB_PATH
from app.core.database import add_sys_notification, SYSTEM_DB_PATH
from app.core.license import get_machine_id
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查  

# 设置日志格式
logger = logging.getLogger("uvicorn")
router = APIRouter()

def ensure_pro_schema():
    """初始化授权数据库表（使用系统数据库）"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        # 🔥 与 db_schemas.py 保持一致
        c.execute('''CREATE TABLE IF NOT EXISTS sys_license (
                        license_key TEXT,
                        machine_id TEXT,
                        pro_token TEXT,
                        status TEXT DEFAULT 'free',
                        expire_date DATETIME,
                        last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
                    )''')
        # 增量更新：添加缺失字段
        try: c.execute("ALTER TABLE sys_license ADD COLUMN pro_token TEXT")
        except: pass
        try: c.execute("ALTER TABLE sys_license ADD COLUMN expire_date DATETIME")
        except: pass
        try: c.execute("ALTER TABLE sys_license ADD COLUMN last_checked DATETIME DEFAULT CURRENT_TIMESTAMP")
        except: pass
        try: c.execute("ALTER TABLE sys_license ADD COLUMN max_devices INTEGER")
        except: pass
        try: c.execute("ALTER TABLE sys_license ADD COLUMN current_devices INTEGER")
        except: pass
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ 授权表初始化失败: {e}")

ensure_pro_schema()

# ==============================================================================
# 🔥 主备服务器自动切换
# ==============================================================================
AUTH_SERVERS = [
    {"url": "https://pro.esa.cchmm.cn/api/v1", "name": "主服务器"},
    {"url": "https://embypulse.ces.cchmm.cn/api/v1", "name": "备用服务器"},
]

def get_available_server(timeout: int = 5) -> dict:
    """
    获取可用的授权服务器（主备自动切换）
    返回: {"url": "服务器地址", "name": "服务器名称", "is_fallback": bool}
    """
    for i, server in enumerate(AUTH_SERVERS):
        try:
            # 尝试健康检查（如果服务器有 /health 接口）
            # 这里直接用激活接口做连通性测试，超时时间短一点
            test_url = f"{server['url']}/activate"
            res = requests.post(test_url, json={}, timeout=timeout)
            # 只要能连上就算通（401/400 也说明服务器在线）
            if res.status_code in [200, 400, 401, 422]:
                logger.info(f"✅ [授权] 连接成功: {server['name']}")
                return {**server, "is_fallback": i > 0}
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ [授权] 连接超时: {server['name']}")
            continue
        except requests.exceptions.ConnectionError:
            logger.warning(f"🔌 [授权] 连接失败: {server['name']}")
            continue
        except Exception as e:
            logger.warning(f"⚠️ [授权] 异常: {server['name']} - {str(e)}")
            continue
    
    # 全挂了还是返回主服务器（让用户看到具体错误）
    logger.error(f"❌ [授权] 所有服务器均不可用，使用主服务器")
    return {**AUTH_SERVERS[0], "is_fallback": False}


def call_auth_server(endpoint: str, payload: dict, timeout: int = 15) -> dict:
    """
    调用授权服务器（主备自动切换）
    
    Args:
        endpoint: 接口路径，如 "activate" 或 "heartbeat"
        payload: 请求体
        timeout: 超时时间（秒）
    
    Returns:
        {"success": bool, "data": dict|None, "error": str|None, "server": dict}
    """
    # 先获取可用服务器
    server = get_available_server(timeout=min(5, timeout))
    
    # 尝试调用
    url = f"{server['url']}/{endpoint}"
    try:
        res = requests.post(url, json=payload, timeout=timeout)
        if res.status_code == 200:
            return {
                "success": True,
                "data": res.json(),
                "error": None,
                "server": server
            }
        else:
            return {
                "success": False,
                "data": None,
                "error": f"服务器返回 {res.status_code}",
                "server": server
            }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "data": None,
            "error": "连接超时",
            "server": server
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "data": None,
            "error": "连接失败",
            "server": server
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e),
            "server": server
        }


# 兼容旧代码的全局变量（废弃，保留向后兼容）
AUTH_SERVER_URL = AUTH_SERVERS[0]["url"] + "/activate"
HEARTBEAT_URL = AUTH_SERVERS[0]["url"] + "/heartbeat"


class ActivateModel(BaseModel):
    license_key: str


@router.post("/api/pro/activate")
async def activate_pro(data: ActivateModel, request: Request):
    """手动激活接口（支持主备自动切换）"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    key = data.license_key.strip()
    mid = get_machine_id()
    
    logger.info(f"🚀 发起激活请求: {key} (设备ID: {mid})")
    
    # 调用授权服务器（自动切换）
    result = call_auth_server("activate", {
        "license_key": key, 
        "machine_id": mid
    }, timeout=15)
    
    # 处理结果
    if not result["success"]:
        server_info = result["server"]["name"]
        error_msg = result["error"]
        logger.error(f"❌ 授权服务器连接失败: {server_info} - {error_msg}")
        return {"status": "error", "message": f"授权服务器连接失败: {error_msg}"}
    
    resp = result["data"]
    server_info = result["server"]
    
    # 如果使用了备用服务器，记录日志
    if server_info.get("is_fallback"):
        logger.warning(f"⚠️ [授权] 已切换到备用服务器: {server_info['name']}")
    
    if resp.get("status") == "success":
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM sys_license") 
        
        # 获取到期时间和设备限制信息
        expire_date = resp.get("expire_date") or resp.get("data", {}).get("expire_date")
        max_devices = resp.get("max_devices") or resp.get("data", {}).get("max_devices")
        current_devices = resp.get("current_devices") or resp.get("data", {}).get("current_devices")
        
        c.execute("INSERT INTO sys_license (license_key, machine_id, status, expire_date, max_devices, current_devices) VALUES (?, ?, ?, ?, ?, ?)", 
                  (key, mid, 'pro', expire_date, max_devices, current_devices))
        conn.commit(); conn.close()
        
        add_sys_notification("system", "👑 Pro 激活成功", "感谢支持，全站高级功能已解锁！")
        
        # 返回消息中提示使用了备用服务器
        message = resp.get("message", "激活成功")
        if server_info.get("is_fallback"):
            message += f" (通过{server_info['name']})"
        
        return {"status": "success", "message": message}
    else:
        return {"status": "error", "message": resp.get("message", "激活失败")}


@router.get("/api/pro/status")
async def get_pro_status(request: Request):
    """获取 Pro 状态（包括当前使用的服务器）"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "权限不足"}
    
    # 获取本地授权状态
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT * FROM sys_license LIMIT 1").fetchone()
        conn.close()
        
        license_info = None
        device_info = None
        if row:
            license_info = {
                "license_key": row[0][:8] + "****" if row[0] else None,  # 脱敏
                "machine_id": row[1],
                "status": row[3] if len(row) > 3 else "free",
                "expire_date": row[5] if len(row) > 5 else None,
            }
            # 设备限制信息
            max_devices = row[6] if len(row) > 6 else None
            current_devices = row[7] if len(row) > 7 else None
            device_info = {
                "max_devices": max_devices or 10,  # 默认 10 设备
                "current_devices": current_devices or 0
            }
        else:
            # 未激活时提供默认值
            device_info = {
                "max_devices": 10,
                "current_devices": 0
            }
    except:
        license_info = None
        device_info = {
            "max_devices": 10,
            "current_devices": 0
        }
    
    # 测试服务器连通性
    server = get_available_server(timeout=3)
    
    return {
        "status": "success",
        "data": {
            "license": license_info,
            "server": {
                "name": server["name"],
                "is_fallback": server.get("is_fallback", False)
            },
            "device": device_info
        }
    }


@router.get("/api/pro/server_test")
async def test_auth_server(request: Request, type: str = "primary"):
    """测试授权服务器连接状态（后端代理，解决跨域问题）"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "权限不足"}
    
    servers = {
        "primary": AUTH_SERVERS[0],
        "backup": AUTH_SERVERS[1]
    }
    
    target = servers.get(type, AUTH_SERVERS[0])
    url = target["url"]
    
    try:
        import time
        start = time.time()
        res = requests.get(f"{url}/health", timeout=5)
        ping = int((time.time() - start) * 1000)
        
        if res.status_code == 200:
            return {
                "status": "success",
                "data": {
                    "online": True,
                    "ping": ping,
                    "name": target["name"]
                }
            }
        else:
            return {
                "status": "success",
                "data": {
                    "online": False,
                    "ping": None,
                    "name": target["name"]
                }
            }
    except Exception as e:
        return {
            "status": "success",
            "data": {
                "online": False,
                "ping": None,
                "name": target["name"],
                "error": str(e)
            }
        }


async def heartbeat_check():
    """后台心跳检查：防止盗版、顶号或过期（支持主备自动切换）"""
    # 先等几秒让系统启动稳当了再查
    await asyncio.sleep(10)
    
    while True:
        try:
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            row = conn.execute("SELECT license_key, machine_id FROM sys_license WHERE status = 'pro'").fetchone()
            conn.close()
            
            if row:
                key, mid = row
                
                # 调用心跳接口（自动切换服务器）
                result = call_auth_server("heartbeat", {
                    "license_key": key, 
                    "machine_id": mid
                }, timeout=10)
                
                if not result["success"]:
                    # 网络错误，跳过本次检查（不降级）
                    logger.warning(f"⚠️ [心跳] 服务器连接失败，跳过本次检查: {result['error']}")
                else:
                    data = result["data"]
                    
                    # 如果使用了备用服务器，记录日志
                    if result["server"].get("is_fallback"):
                        logger.info(f"ℹ️ [心跳] 使用备用服务器: {result['server']['name']}")
                    
                    # 如果状态被置为 kicked 或返回错误，则强制降级
                    if data.get("status") == "kicked" or data.get("status") == "error":
                        conn = sqlite3.connect(SYSTEM_DB_PATH)
                        conn.execute("UPDATE sys_license SET status = 'free'")
                        conn.commit(); conn.close()
                        add_sys_notification("system", "⚠️ 授权已失效", "授权码状态异常或已在别处激活，Pro 权限已撤销。")
                        logger.warning(f"🚨 [安全] 用户 {key} 校验失败，执行强制降级。")
                    else:
                        # 更新设备限制信息
                        max_devices = data.get("max_devices")
                        current_devices = data.get("current_devices")
                        if max_devices is not None:
                            conn = sqlite3.connect(SYSTEM_DB_PATH)
                            conn.execute("UPDATE sys_license SET max_devices = ?, current_devices = ?", (max_devices, current_devices))
                            conn.commit(); conn.close()
        
        except Exception as e:
            # 这里的异常通常是网络抖动，不需要处理，等下一个循环即可
            logger.debug(f"[心跳] 检查异常: {str(e)}")
        
        # 建议测试期 3600 秒（1小时），稳定后可改为 21600 (6小时)
        await asyncio.sleep(3600)


@router.on_event("startup")
async def start_heartbeat():
    asyncio.create_task(heartbeat_check())
