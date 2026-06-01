# -*- coding: utf-8 -*-
"""
数据库管理 API 路由
提供检测、修复、迁移、备份等接口
"""

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List
from app.infra.db.migration_service import (
    backup_existing_databases,
    backup_old_database,
    backup_system_database,
    check_old_db_tables,
    check_system_tables,
    deep_check_system_database,
    delete_backup,
    ensure_tables,
    full_health_check,
    get_backup_directory,
    get_backup_list,
    get_system_table_names,
    migrate_tables,
    old_database_exists,
    old_database_path,
    restore_backup,
)
from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
import os
from app.core.rate_limiter import get_client_ip

router = APIRouter(prefix="/api/db", tags=["数据库管理"])


@router.get("/health")
async def api_db_health(request: Request):
    """
    数据库健康检查
    返回系统数据库和旧数据库的完整状态
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    return full_health_check()


@router.get("/check")
async def api_db_check(request: Request):
    """
    检查系统表完整性
    返回缺失的表和字段
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    result = check_system_tables()
    
    # 简化返回结果
    return {
        "system_db_exists": result["system_db_exists"],
        "system_db_path": result["system_db_path"],
        "total_tables": len(result["existing_tables"]),
        "missing_tables": result["missing_tables"],
        "missing_alters": result["missing_alters"],
        "is_healthy": len(result["missing_tables"]) == 0 and len(result["missing_alters"]) == 0,
        "table_details": result["table_details"]
    }


@router.get("/deep_check")
async def api_db_deep_check(request: Request):
    """
    深度检测 - 返回详细的检测结果，包括所有表的扫描状态
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})

    return deep_check_system_database()


@router.get("/migration/check")
async def api_migration_check(request: Request):
    """
    检查可迁移的旧数据库表
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    return check_old_db_tables()


@router.post("/repair")
async def api_db_repair(request: Request):
    """
    修复数据库 - 创建缺失的表和字段
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    # 🔒 审计日志
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    log_audit(
        action="db_repair",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=get_client_ip(request),
        resource_type="database",
        details={"message": "数据库修复"}
    )
    
    # 先备份
    backup_result = backup_system_database()
    
    # 执行修复
    repair_result = ensure_tables()
    
    return {
        "success": len(repair_result["errors"]) == 0,
        "backup": backup_result,
        "created_tables": repair_result["created_tables"],
        "added_columns": repair_result["added_columns"],
        "errors": repair_result["errors"],
        "message": f"已创建 {len(repair_result['created_tables'])} 张表，添加 {len(repair_result['added_columns'])} 个字段" if repair_result["created_tables"] or repair_result["added_columns"] else "数据库结构完整，无需修复"
    }


@router.post("/backup")
async def api_db_backup(request: Request):
    """
    备份数据库
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    # 🔒 审计日志
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    log_audit(
        action="backup_create",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=get_client_ip(request),
        resource_type="database",
        details={"message": "创建数据库备份"}
    )
    
    results = backup_existing_databases()
    
    success = any(r.get("success") for r in results.values() if r)
    
    return {
        "success": success,
        "backups": results,
        "backup_dir": get_backup_directory()
    }


@router.get("/backups")
async def api_list_backups(request: Request):
    """
    获取备份文件列表
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    return {
        "success": True,
        "backup_dir": get_backup_directory(),
        "backups": get_backup_list()
    }


@router.delete("/backup/{filename}")
async def api_delete_backup(request: Request, filename: str):
    """
    删除备份文件
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    # 🔒 审计日志
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    log_audit(
        action="backup_delete",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=get_client_ip(request),
        resource_type="backup",
        details={"filename": filename}
    )
    
    result = delete_backup(filename)
    return result


@router.post("/migrate")
async def api_db_migrate(
    request: Request,
    mode: str = "incremental",  # incremental 或 overwrite
    tables: Optional[str] = None  # 逗号分隔的表名
):
    """
    从旧数据库迁移系统表
    
    Args:
        mode: incremental=增量迁移（跳过已存在），overwrite=强制覆盖
        tables: 指定要迁移的表（逗号分隔），不指定则迁移全部系统表
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    # 🔒 审计日志
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    log_audit(
        action="db_migrate",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=get_client_ip(request),
        resource_type="database",
        details={"mode": mode, "tables": tables}
    )
    
    # 检查旧数据库是否存在
    if not old_database_exists():
        return {
            "success": False,
            "error": "源数据库不存在，无法迁移",
            "old_db_path": old_database_path()
        }
    
    # 解析要迁移的表
    system_tables = get_system_table_names()
    tables_list = None
    if tables:
        tables_list = [t.strip() for t in tables.split(",") if t.strip() and t.strip() in system_tables]
        if not tables_list:
            return {"success": False, "error": "指定的表名均不在系统表列表中"}
    
    # 先备份目标数据库
    backup_result = backup_system_database()
    
    # 执行迁移
    migrate_result = migrate_tables(mode=mode, tables=tables_list)
    
    return {
        "success": migrate_result["success"],
        "backup": backup_result,
        "mode": mode,
        "migrated_tables": migrate_result["migrated_tables"],
        "skipped_tables": migrate_result["skipped_tables"],
        "total_rows": migrate_result["total_rows"],
        "errors": migrate_result["errors"]
    }


@router.post("/restore")
async def api_db_restore(request: Request):
    """
    从备份恢复数据库
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    body = await request.json()
    backup_path = body.get("backup_path")
    
    if not backup_path:
        return {"success": False, "error": "请指定备份文件路径"}
    
    # 🔒 审计日志
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    log_audit(
        action="backup_restore",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=get_client_ip(request),
        resource_type="database",
        details={"backup_path": backup_path}
    )
    
    # 安全检查：确保备份文件在备份目录中（防御路径穿越）
    if ".." in backup_path.split("/") or ".." in backup_path.split("\\"):
        return {"success": False, "error": "无效的备份文件路径"}
    real_backup = os.path.realpath(backup_path)
    real_backup_dir = os.path.realpath(get_backup_directory())
    if not real_backup.startswith(real_backup_dir + os.sep) and real_backup != real_backup_dir:
        return {"success": False, "error": "无效的备份文件路径"}
    
    result = restore_backup(backup_path)
    return result


@router.post("/full_check")
async def api_full_check(request: Request):
    """
    完整检测并修复（一键操作）
    自动备份 + 修复缺失表 + 迁移数据（如果有）
    """
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    results = {
        "backup": None,
        "repair": None,
        "migration": None,
        "actions": []
    }
    
    # 1. 备份
    results["backup"] = backup_system_database()
    if results["backup"]:
        if results["backup"].get("success"):
            results["actions"].append(f"已备份: {results['backup']['backup_name']}")
    
    # 2. 检查并修复表结构
    table_check = check_system_tables()
    if table_check["missing_tables"] or table_check["missing_alters"]:
        results["repair"] = ensure_tables()
        if results["repair"]["created_tables"]:
            results["actions"].append(f"已创建表: {', '.join(results['repair']['created_tables'])}")
        if results["repair"]["added_columns"]:
            results["actions"].append(f"已添加字段: {len(results['repair']['added_columns'])} 个")
    
    # 3. 检查是否需要迁移
    if old_database_exists():
        migration_check = check_old_db_tables()
        if migration_check["migratable_tables"]:
            # 自动增量迁移
            results["migration"] = migrate_tables(mode="incremental")
            if results["migration"]["migrated_tables"]:
                results["actions"].append(f"已迁移: {results['migration']['total_rows']} 条记录")
    
    results["success"] = True
    results["message"] = " | ".join(results["actions"]) if results["actions"] else "数据库状态良好，无需操作"
    
    return results
