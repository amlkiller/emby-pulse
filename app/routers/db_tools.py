# -*- coding: utf-8 -*-
"""
数据库管理 API 路由
提供检测、修复、迁移、备份等接口
"""

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List
from app.core.db_manager import (
    full_health_check, ensure_tables, backup_database, 
    migrate_tables, get_backup_list, delete_backup, restore_backup,
    check_system_tables, check_old_db_tables, BACKUP_DIR
)
from app.core.config import DB_PATH, SYSTEM_DB_PATH
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
import os

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
    
    from app.core.db_schemas import SYSTEM_TABLES, TABLE_SCHEMAS, TABLE_ALTERS
    import sqlite3
    
    results = {
        "system_db": {
            "exists": os.path.exists(SYSTEM_DB_PATH),
            "path": SYSTEM_DB_PATH,
            "size_mb": 0,
            "tables": {},
            "scan_log": []
        }
    }
    
    # 步骤1: 检查数据库文件
    results["system_db"]["scan_log"].append({
        "step": "check_file",
        "status": "running",
        "message": "正在检查数据库文件..."
    })
    
    if not os.path.exists(SYSTEM_DB_PATH):
        results["system_db"]["scan_log"][0]["status"] = "error"
        results["system_db"]["scan_log"][0]["message"] = "数据库文件不存在"
        results["missing_tables"] = list(SYSTEM_TABLES)
        results["is_healthy"] = False
        return results
    
    results["system_db"]["scan_log"][0]["status"] = "success"
    results["system_db"]["scan_log"][0]["message"] = f"数据库文件存在: {SYSTEM_DB_PATH}"
    results["system_db"]["size_mb"] = round(os.path.getsize(SYSTEM_DB_PATH) / (1024 * 1024), 2)
    
    # 步骤2: 连接数据库
    results["system_db"]["scan_log"].append({
        "step": "connect",
        "status": "running",
        "message": "正在连接数据库..."
    })
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        cursor = conn.cursor()
        
        # 获取现有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        results["system_db"]["scan_log"][1]["status"] = "success"
        results["system_db"]["scan_log"][1]["message"] = f"已连接，发现 {len(existing_tables)} 张表"
    except Exception as e:
        results["system_db"]["scan_log"][1]["status"] = "error"
        results["system_db"]["scan_log"][1]["message"] = f"连接失败: {str(e)}"
        results["is_healthy"] = False
        return results
    
    # 步骤3: 逐表检测
    results["system_db"]["scan_log"].append({
        "step": "scan_tables",
        "status": "running",
        "message": f"正在扫描 {len(SYSTEM_TABLES)} 张系统表..."
    })
    
    missing_tables = []
    missing_alters = {}
    table_details = {}
    
    for i, table_name in enumerate(SYSTEM_TABLES):
        if table_name in existing_tables:
            # 获取表信息
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [row[1] for row in cursor.fetchall()]
                
                table_details[table_name] = {
                    "exists": True,
                    "rows": count,
                    "columns": columns,
                    "status": "ok"
                }
            except Exception as e:
                table_details[table_name] = {
                    "exists": True,
                    "rows": 0,
                    "columns": [],
                    "status": "error",
                    "error": str(e)
                }
        else:
            missing_tables.append(table_name)
            table_details[table_name] = {
                "exists": False,
                "rows": 0,
                "columns": [],
                "status": "missing"
            }
    
    results["system_db"]["tables"] = table_details
    results["system_db"]["scan_log"][2]["status"] = "success"
    results["system_db"]["scan_log"][2]["message"] = f"扫描完成: {len(SYSTEM_TABLES) - len(missing_tables)} 正常, {len(missing_tables)} 缺失"
    
    # 步骤4: 检测字段增量
    results["system_db"]["scan_log"].append({
        "step": "check_alters",
        "status": "running",
        "message": "正在检测表字段..."
    })
    
    for table_name, alters in TABLE_ALTERS.items():
        if table_name in existing_tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            for alter_sql in alters:
                parts = alter_sql.split("ADD COLUMN ")
                if len(parts) > 1:
                    field_name = parts[1].split()[0]
                    if field_name not in existing_columns:
                        if table_name not in missing_alters:
                            missing_alters[table_name] = []
                        missing_alters[table_name].append(field_name)
    
    results["system_db"]["scan_log"][3]["status"] = "success"
    results["system_db"]["scan_log"][3]["message"] = f"字段检测完成: {sum(len(v) for v in missing_alters.values())} 个缺失字段"
    
    conn.close()
    
    # 总结
    results["missing_tables"] = missing_tables
    results["missing_alters"] = missing_alters
    results["is_healthy"] = len(missing_tables) == 0 and len(missing_alters) == 0
    results["summary"] = {
        "total_tables": len(SYSTEM_TABLES),
        "existing_tables": len(SYSTEM_TABLES) - len(missing_tables),
        "missing_tables": len(missing_tables),
        "missing_columns": sum(len(v) for v in missing_alters.values())
    }
    
    return results


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
        ip_address=request.client.host if request.client else "",
        resource_type="database",
        details={"message": "数据库修复"}
    )
    
    # 先备份
    backup_result = None
    if os.path.exists(SYSTEM_DB_PATH):
        backup_result = backup_database(SYSTEM_DB_PATH)
    
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
        ip_address=request.client.host if request.client else "",
        resource_type="database",
        details={"message": "创建数据库备份"}
    )
    
    results = {}
    
    # 备份系统数据库
    if os.path.exists(SYSTEM_DB_PATH):
        results["system_db"] = backup_database(SYSTEM_DB_PATH)
    
    # 备份旧数据库（如果存在）
    if os.path.exists(DB_PATH):
        results["old_db"] = backup_database(DB_PATH)
    
    success = any(r.get("success") for r in results.values() if r)
    
    return {
        "success": success,
        "backups": results,
        "backup_dir": BACKUP_DIR
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
        "backup_dir": BACKUP_DIR,
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
        ip_address=request.client.host if request.client else "",
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
        ip_address=request.client.host if request.client else "",
        resource_type="database",
        details={"mode": mode, "tables": tables}
    )
    
    # 检查旧数据库是否存在
    if not os.path.exists(DB_PATH):
        return {
            "success": False,
            "error": "源数据库不存在，无法迁移",
            "old_db_path": DB_PATH
        }
    
    # 解析要迁移的表
    from app.core.db_schemas import SYSTEM_TABLES
    tables_list = None
    if tables:
        tables_list = [t.strip() for t in tables.split(",") if t.strip() and t.strip() in SYSTEM_TABLES]
        if not tables_list:
            return {"success": False, "error": "指定的表名均不在系统表列表中"}
    
    # 先备份目标数据库
    backup_result = None
    if os.path.exists(SYSTEM_DB_PATH):
        backup_result = backup_database(SYSTEM_DB_PATH)
    
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
        ip_address=request.client.host if request.client else "",
        resource_type="database",
        details={"backup_path": backup_path}
    )
    
    # 安全检查：确保备份文件在备份目录中
    if not backup_path.startswith(BACKUP_DIR):
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
    if os.path.exists(SYSTEM_DB_PATH):
        results["backup"] = backup_database(SYSTEM_DB_PATH)
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
    if os.path.exists(DB_PATH):
        migration_check = check_old_db_tables()
        if migration_check["migratable_tables"]:
            # 自动增量迁移
            results["migration"] = migrate_tables(mode="incremental")
            if results["migration"]["migrated_tables"]:
                results["actions"].append(f"已迁移: {results['migration']['total_rows']} 条记录")
    
    results["success"] = True
    results["message"] = " | ".join(results["actions"]) if results["actions"] else "数据库状态良好，无需操作"
    
    return results
