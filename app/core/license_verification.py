"""
Pro 授权在线验证模块
提供远程验证、定时心跳、离线缓存等功能
"""

import sqlite3
import requests
import time
import logging
import os
from app.core.database import SYSTEM_DB_PATH
from app.core.config import cfg
from app.core.license import get_machine_id

logger = logging.getLogger("uvicorn")

# 授权服务器列表
AUTH_SERVERS = [
    {"url": "https://pro.esa.cchmm.cn/api/v1", "name": "主服务器"},
    {"url": "https://embypulse.ces.cchmm.cn/api/v1", "name": "备用服务器"},
]

# 配置
LICENSE_CONFIG = {
    "verify_on_startup": True,      # 启动时验证
    "heartbeat_interval": 3600,     # 心跳间隔（秒）= 1小时
    "offline_cache_ttl": 86400,     # 离线缓存有效期（秒）= 24小时
    "verify_timeout": 10,           # 验证超时（秒）
    "fallback_on_error": True,      # 网络错误时使用缓存
}

def get_license_key():
    """获取本地授权 Key"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        row = c.execute("SELECT license_key FROM sys_license LIMIT 1").fetchone()
        conn.close()
        return row[0] if row else None
    except:
        return None

def get_license_status():
    """获取本地授权状态"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        row = c.execute("SELECT status, expire_date, last_checked FROM sys_license LIMIT 1").fetchone()
        conn.close()
        
        if row:
            return {
                "status": row[0],
                "expire_date": row[1],
                "last_checked": row[2]
            }
        return {"status": "free"}
    except:
        return {"status": "free"}

def update_license_status(status, expire_date=None, last_checked=None):
    """更新本地授权状态"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 使用当前时间戳（数字格式，便于计算）
        current_time = last_checked if last_checked else time.time()
        
        if expire_date:
            c.execute("UPDATE sys_license SET status = ?, expire_date = ?, last_checked = ?", 
                     (status, expire_date, current_time))
        else:
            c.execute("UPDATE sys_license SET status = ?, last_checked = ?", 
                     (status, current_time))
        
        conn.commit()
        conn.close()
        logger.info(f"[授权] 更新状态: {status}")
    except Exception as e:
        logger.error(f"[授权] 更新状态失败: {e}")

def is_license_cached_valid():
    """检查离线缓存是否有效"""
    status = get_license_status()
    
    # 如果是免费版，不需要缓存
    if status.get("status") != "pro":
        return False
    
    # 检查上次验证时间
    last_checked = status.get("last_checked")
    if not last_checked:
        return False
    
    # 解析时间（支持字符串格式和数字格式）
    try:
        if isinstance(last_checked, (int, float)):
            last_checked_timestamp = float(last_checked)
        elif isinstance(last_checked, str):
            # 尝试解析日期时间字符串
            import datetime
            try:
                # 尝试 ISO 格式
                dt = datetime.datetime.fromisoformat(last_checked.replace(' ', 'T'))
                last_checked_timestamp = dt.timestamp()
            except:
                # 尝试其他格式
                try:
                    dt = datetime.datetime.strptime(last_checked, '%Y-%m-%d %H:%M:%S')
                    last_checked_timestamp = dt.timestamp()
                except:
                    logger.warning(f"[授权] 无法解析时间：{last_checked}")
                    return False
        else:
            logger.warning(f"[授权] 无效的时间格式：{type(last_checked)}")
            return False
    except Exception as e:
        logger.warning(f"[授权] 解析时间失败：{e}")
        return False
    
    # 检查缓存是否过期
    cache_age = time.time() - last_checked_timestamp
    if cache_age > LICENSE_CONFIG["offline_cache_ttl"]:
        logger.warning(f"[授权] 离线缓存已过期（{cache_age}秒 > {LICENSE_CONFIG['offline_cache_ttl']}秒）")
        return False
    
    logger.info(f"[授权] 使用离线缓存（有效期：{cache_age:.0f}秒）")
    return True

def verify_license_online():
    """向授权服务器验证授权"""
    license_key = get_license_key()
    machine_id = get_machine_id()
    
    if not license_key:
        logger.warning("[授权] 无授权 Key")
        return False
    
    # 尝试所有服务器
    for server in AUTH_SERVERS:
        try:
            # 使用 /heartbeat 端点（而不是 /verify）
            url = f"{server['url']}/heartbeat"
            payload = {
                "license_key": license_key,
                "machine_id": machine_id,
                "timestamp": time.time()
            }
            
            logger.info(f"[授权] 验证请求: {server['name']}")
            response = requests.post(
                url,
                json=payload,
                timeout=LICENSE_CONFIG["verify_timeout"]
            )
            
            logger.info(f"[授权] {server['name']} 响应状态: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"[授权] {server['name']} 响应数据: {data}")
                
                # 检查响应状态（兼容多种格式）
                # 格式1: {"status": "valid", ...}
                # 格式2: {"status": "success", ...}
                # 格式3: {"valid": true, ...}
                is_valid = (
                    data.get("status") == "valid" or
                    data.get("status") == "success" or
                    data.get("valid") == True
                )
                
                if is_valid:
                    # 验证成功
                    expire_date = data.get("expire_date") or data.get("data", {}).get("expire_date")
                    update_license_status("pro", expire_date, time.time())
                    logger.info(f"[授权] ✅ 验证成功（有效期至：{expire_date}）")
                    return True
                else:
                    # 验证失败
                    reason = data.get("reason") or data.get("message") or "未知原因"
                    logger.warning(f"[授权] ❌ 验证失败：{reason}")
                    downgrade_to_free(reason)
                    return False
            else:
                logger.warning(f"[授权] {server['name']} 返回错误状态码: {response.status_code}")
                logger.warning(f"[授权] {server['name']} 响应内容: {response.text[:200]}")
            
        except requests.exceptions.Timeout:
            logger.warning(f"[授权] ⏱️ {server['name']} 连接超时")
            continue
        except requests.exceptions.ConnectionError:
            logger.warning(f"[授权] 🔌 {server['name']} 连接失败")
            continue
        except Exception as e:
            logger.error(f"[授权] ⚠️ {server['name']} 异常：{e}")
            continue
    
    # 所有服务器都失败
    logger.error("[授权] ❌ 所有服务器均不可用")
    
    # 使用离线缓存
    if LICENSE_CONFIG["fallback_on_error"] and is_license_cached_valid():
        logger.info("[授权] 使用离线缓存继续运行")
        return True
    
    return False

def downgrade_to_free(reason="验证失败"):
    """降级为免费版"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE sys_license SET status = 'free'")
        conn.commit()
        conn.close()
        
        logger.warning(f"[授权] ⚠️ 已降级为免费版（原因：{reason}）")
        
        # 发送通知
        from app.core.database import add_sys_notification
        add_sys_notification(
            notify_type="system",
            title="⚠️ Pro 授权已失效",
            message=f"授权验证失败，已降级为免费版。\n原因：{reason}\n请检查授权状态或联系管理员。"
        )
    except Exception as e:
        logger.error(f"[授权] 降级失败：{e}")

def verify_on_startup():
    """启动时验证授权"""
    if not LICENSE_CONFIG["verify_on_startup"]:
        return
    
    logger.info("[授权] 🔍 启动验证...")
    
    # 检查本地状态
    status = get_license_status()
    if status.get("status") != "pro":
        logger.info("[授权] 当前为免费版，跳过验证")
        return
    
    # 在线验证
    if verify_license_online():
        logger.info("[授权] ✅ Pro 授权验证成功")
    else:
        logger.warning("[授权] ❌ Pro 授权验证失败")

def start_heartbeat():
    """启动定时心跳"""
    import threading
    
    def heartbeat_loop():
        while True:
            time.sleep(LICENSE_CONFIG["heartbeat_interval"])
            
            # 检查本地状态
            status = get_license_status()
            if status.get("status") == "pro":
                logger.info("[授权] 💓 定时心跳验证...")
                verify_license_online()
    
    # 启动后台线程
    thread = threading.Thread(target=heartbeat_loop, daemon=True)
    thread.start()
    logger.info(f"[授权] 💓 定时心跳已启动（间隔：{LICENSE_CONFIG['heartbeat_interval']}秒）")

# 初始化
def init_license_verification():
    """初始化授权验证"""
    verify_on_startup()
    start_heartbeat()