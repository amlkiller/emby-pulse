import time
import logging
from typing import Optional, Dict, Any

from app.infra.db.audit_logger_dao import (
    cleanup_audit_logs_before,
    ensure_audit_table,
    get_audit_stats_since,
    insert_audit_log,
    list_audit_logs,
)

logger = logging.getLogger("uvicorn")

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
        ensure_audit_table()
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
        insert_audit_log(action, user_id, user_name, resource_type, resource_id, ip_address, user_agent, details, status)
        
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
        return list_audit_logs(user_id, action, start_time, end_time, limit, offset)
        
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
        start_time = time.time() - days * 86400
        return get_audit_stats_since(start_time)
        
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
        deleted = cleanup_audit_logs_before(cutoff_time)
        
        if deleted > 0:
            logger.info(f"[审计日志] 已清理 {deleted} 条旧记录（{days}天前）")
        
        return deleted
        
    except Exception as e:
        logger.error(f"[审计日志] 清理失败: {e}")
        return 0

