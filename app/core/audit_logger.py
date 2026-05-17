"""
审计日志系统 - 记录敏感操作
"""
import sqlite3
import json
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from app.core.config import SYSTEM_DB_PATH

logger = logging.getLogger("uvicorn")

# 审计日志表结构
AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    datetime TEXT NOT NULL,
    user_id TEXT,
    user_name TEXT,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    details TEXT,
    status TEXT DEFAULT 'success',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
"""

# 需要审计的敏感操作
AUDIT_ACTIONS = {
    # 认证相关
    "login": "用户登录",
    "login_failed": "登录失败",
    "logout": "用户登出",
    "password_change": "修改密码",
    "totp_enable": "启用二次验证",
    "totp_disable": "禁用二次验证",
    
    # 用户管理
    "user_create": "创建用户",
    "user_delete": "删除用户",
    "user_update": "更新用户",
    "user_permission_change": "修改用户权限",
    "user_action": "用户管理操作",
    "tag_create": "创建标签",
    "tag_delete": "删除标签",
    
    # 配置变更
    "config_update": "更新配置",
    "bot_token_update": "更新机器人Token",
    "api_key_update": "更新API Key",
    "webhook_token_update": "更新Webhook Token",
    
    # 数据操作
    "backup_create": "创建备份",
    "backup_restore": "恢复备份",
    "backup_delete": "删除备份",
    "db_migrate": "数据库迁移",
    "db_repair": "数据库修复",
    
    # 邀请码
    "invitation_create": "创建邀请码",
    "invitation_use": "使用邀请码",
    "invitation_delete": "删除邀请码",
    
    # 积分操作
    "points_add": "增加积分",
    "points_deduct": "扣除积分",
    "points_redeem": "积分兑换",
    
    # 媒体操作
    "media_delete": "删除媒体",
    "media_request": "请求媒体",
    
    # 安全事件
    "rate_limit_hit": "触发速率限制",
    "suspicious_activity": "可疑活动",
    "blacklist_add": "添加黑名单",
    "blacklist_remove": "移除黑名单",
}


def init_audit_table():
    """初始化审计日志表"""
    try:
        # 确保数据库目录存在
        import os
        db_dir = os.path.dirname(SYSTEM_DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"[审计日志] 创建数据库目录: {db_dir}")
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.executescript(AUDIT_TABLE_SQL)
        conn.commit()
        conn.close()
        logger.info("🔒 [审计日志] 审计日志表已初始化")
    except Exception as e:
        logger.error(f"[审计日志] 初始化失败: {e}")


def log_audit(
    action: str,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[Any, Any]] = None,
    status: str = "success"
):
    """
    记录审计日志
    
    Args:
        action: 操作类型（如 login, user_create 等）
        user_id: 用户ID
        user_name: 用户名
        resource_type: 资源类型（如 user, config, invitation 等）
        resource_id: 资源ID
        ip_address: IP地址
        user_agent: 用户代理
        details: 详细信息（字典）
        status: 状态（success/failed）
    """
    try:
        now = time.time()
        datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details_json = json.dumps(details, ensure_ascii=False) if details else None
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("""
            INSERT INTO audit_logs 
            (timestamp, datetime, user_id, user_name, action, resource_type, resource_id, ip_address, user_agent, details, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, datetime_str, user_id, user_name, action, resource_type, resource_id, ip_address, user_agent, details_json, status))
        conn.commit()
        conn.close()
        
        # 同时输出到日志（方便实时监控）
        action_desc = AUDIT_ACTIONS.get(action, action)
        log_msg = f"[审计] {action_desc}"
        if user_name:
            log_msg += f" | 用户: {user_name}"
        if ip_address:
            log_msg += f" | IP: {ip_address}"
        if status == "failed":
            log_msg += f" | 状态: 失败"
        
        logger.info(log_msg)
        
    except Exception as e:
        logger.error(f"[审计日志] 记录失败: {e}")


def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
) -> list:
    """
    查询审计日志
    
    Args:
        user_id: 按用户ID过滤
        action: 按操作类型过滤
        start_time: 开始时间戳
        end_time: 结束时间戳
        limit: 返回数量限制
        offset: 偏移量
    
    Returns:
        审计日志列表
    """
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        
        where_clauses = []
        params = []
        
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)
        
        if action:
            where_clauses.append("action = ?")
            params.append(action)
        
        if start_time:
            where_clauses.append("timestamp >= ?")
            params.append(start_time)
        
        if end_time:
            where_clauses.append("timestamp <= ?")
            params.append(end_time)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        sql = f"""
            SELECT * FROM audit_logs 
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        logger.error(f"[审计日志] 查询失败: {e}")
        return []


def get_audit_stats(days: int = 7) -> dict:
    """
    获取审计日志统计
    
    Args:
        days: 统计天数
    
    Returns:
        统计数据
    """
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        
        start_time = time.time() - days * 86400
        
        # 按操作类型统计
        action_stats = conn.execute("""
            SELECT action, COUNT(*) as count
            FROM audit_logs
            WHERE timestamp >= ?
            GROUP BY action
            ORDER BY count DESC
        """, (start_time,)).fetchall()
        
        # 按用户统计
        user_stats = conn.execute("""
            SELECT user_name, COUNT(*) as count
            FROM audit_logs
            WHERE timestamp >= ? AND user_name IS NOT NULL
            GROUP BY user_name
            ORDER BY count DESC
            LIMIT 10
        """, (start_time,)).fetchall()
        
        # 失败操作统计
        failed_stats = conn.execute("""
            SELECT action, COUNT(*) as count
            FROM audit_logs
            WHERE timestamp >= ? AND status = 'failed'
            GROUP BY action
            ORDER BY count DESC
        """, (start_time,)).fetchall()
        
        # 总数
        total = conn.execute("""
            SELECT COUNT(*) as count
            FROM audit_logs
            WHERE timestamp >= ?
        """, (start_time,)).fetchone()[0]
        
        conn.close()
        
        return {
            "total": total,
            "by_action": [{"action": row[0], "count": row[1]} for row in action_stats],
            "by_user": [{"user": row[0], "count": row[1]} for row in user_stats],
            "failed": [{"action": row[0], "count": row[1]} for row in failed_stats],
        }
        
    except Exception as e:
        logger.error(f"[审计日志] 统计失败: {e}")
        return {"total": 0, "by_action": [], "by_user": [], "failed": []}


def cleanup_old_audit_logs(days: int = 90):
    """
    清理旧的审计日志
    
    Args:
        days: 保留天数
    """
    try:
        cutoff_time = time.time() - days * 86400
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        result = conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff_time,))
        deleted = result.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logger.info(f"[审计日志] 已清理 {deleted} 条旧记录（{days}天前）")
        
        return deleted
        
    except Exception as e:
        logger.error(f"[审计日志] 清理失败: {e}")
        return 0


# 启动时初始化
init_audit_table()
