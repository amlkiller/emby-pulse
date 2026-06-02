# -*- coding: utf-8 -*-
"""
数据库管理工具
提供检测、修复、迁移、备份等功能
"""

import sqlite3
import os
import shutil
import datetime
import logging
import re
from typing import Dict, List, Tuple, Optional
from app.core.config import DB_PATH, SYSTEM_DB_PATH
from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.schema_registry import (
    SYSTEM_TABLES, PLAYBACK_TABLES, TABLE_SCHEMAS, TABLE_ALTERS,
    PLAYBACK_SCHEMA, CORE_TABLES
)

logger = logging.getLogger("uvicorn")

# 备份目录
BACKUP_DIR = "/workspace/data/backups"


def ensure_backup_dir():
    """确保备份目录存在"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def get_db_info(db_path: str) -> Dict:
    """获取数据库基本信息"""
    if not os.path.exists(db_path):
        return {"exists": False, "path": db_path}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取文件大小
        size_bytes = os.path.getsize(db_path)
        size_mb = round(size_bytes / (1024 * 1024), 2)
        
        # 获取所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        # 获取各表行数
        table_counts = {}
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]
            except:
                table_counts[table] = 0
        
        conn.close()
        
        return {
            "exists": True,
            "path": db_path,
            "size_mb": size_mb,
            "tables": tables,
            "table_counts": table_counts
        }
    except Exception as e:
        return {"exists": True, "path": db_path, "error": str(e)}


def check_system_tables() -> Dict:
    """
    检查系统数据库表结构完整性
    返回缺失的表和字段
    """
    result = {
        "system_db_exists": os.path.exists(SYSTEM_DB_PATH),
        "system_db_path": SYSTEM_DB_PATH,
        "existing_tables": [],
        "missing_tables": [],
        "table_details": {},
        "missing_alters": {}
    }
    
    if not result["system_db_exists"]:
        return result
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        cursor = conn.cursor()
        
        # 获取现有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        result["existing_tables"] = list(existing_tables)
        
        # 检查缺失的表
        for table in SYSTEM_TABLES:
            if table in existing_tables:
                # 获取表行数
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                except:
                    count = 0
                
                # 获取表字段
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                
                result["table_details"][table] = {
                    "exists": True,
                    "rows": count,
                    "columns": columns
                }
            else:
                result["missing_tables"].append(table)
                result["table_details"][table] = {
                    "exists": False,
                    "rows": 0,
                    "columns": []
                }
        
        # 检查缺失的字段
        for table, alters in TABLE_ALTERS.items():
            if table in existing_tables:
                cursor.execute(f"PRAGMA table_info({table})")
                existing_columns = {row[1] for row in cursor.fetchall()}
                
                missing_alters = []
                for alter_sql in alters:
                    # 提取字段名：ALTER TABLE xxx ADD COLUMN field_name ...
                    parts = alter_sql.split("ADD COLUMN ")
                    if len(parts) > 1:
                        field_name = parts[1].split()[0]
                        if field_name not in existing_columns:
                            missing_alters.append(field_name)
                
                if missing_alters:
                    result["missing_alters"][table] = missing_alters
        
        conn.close()
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_old_db_tables() -> Dict:
    """
    检查旧数据库中可迁移的系统表
    """
    result = {
        "old_db_exists": os.path.exists(DB_PATH),
        "old_db_path": DB_PATH,
        "migratable_tables": {},
        "total_rows": 0
    }
    
    if not result["old_db_exists"]:
        return result
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 获取现有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        # 检查系统表
        for table in SYSTEM_TABLES:
            if table in existing_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        # 获取字段列表
                        cursor.execute(f"PRAGMA table_info({table})")
                        columns = [row[1] for row in cursor.fetchall()]
                        
                        result["migratable_tables"][table] = {
                            "rows": count,
                            "columns": columns
                        }
                        result["total_rows"] += count
                except:
                    pass
        
        conn.close()
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def ensure_tables() -> Dict:
    """
    确保所有系统表存在且结构完整
    自动创建缺失的表和字段，修复损坏的表
    """
    result = {
        "created_tables": [],
        "added_columns": [],
        "repaired_tables": [],
        "errors": []
    }
    
    try:
        # 确保目录存在
        db_dir = os.path.dirname(SYSTEM_DB_PATH)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        cursor = conn.cursor()
        
        # 获取现有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        # 创建缺失的表
        for table_name, create_sql in TABLE_SCHEMAS.items():
            if table_name not in existing_tables:
                try:
                    cursor.execute(create_sql)
                    result["created_tables"].append(table_name)
                    logger.info(f"[数据库修复] 创建表: {table_name}")
                except Exception as e:
                    result["errors"].append(f"创建表 {table_name} 失败: {str(e)}")
            else:
                # 表存在，检查列是否完整
                try:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    existing_columns_info = cursor.fetchall()
                    existing_columns = {row[1] for row in existing_columns_info}
                    # 获取列的顺序
                    existing_cols_ordered = [row[1] for row in existing_columns_info]
                    
                    # 从 CREATE 语句解析期望的列
                    expected_columns = parse_columns_from_create(create_sql)
                    
                    # 检查缺失的列
                    missing_columns = expected_columns - existing_columns
                    
                    if missing_columns:
                        # 表结构不完整，需要重建
                        logger.warning(f"[数据库修复] 表 {table_name} 缺失列: {missing_columns}，尝试重建")
                        
                        # 备份现有数据
                        cursor.execute(f"SELECT * FROM {table_name}")
                        existing_data = cursor.fetchall()
                        
                        # 获取列名映射（旧列索引 -> 新列索引）
                        new_cols_ordered = list(expected_columns)
                        
                        # 删除旧表
                        cursor.execute(f"DROP TABLE {table_name}")
                        
                        # 创建新表
                        cursor.execute(create_sql)
                        
                        # 恢复数据（只插入共有的列）
                        if existing_data and existing_cols_ordered:
                            # 找出共有的列
                            common_old_cols = []
                            common_new_cols = []
                            old_indices = []
                            
                            for i, col in enumerate(existing_cols_ordered):
                                if col in expected_columns:
                                    common_old_cols.append(col)
                                    common_new_cols.append(col)
                                    old_indices.append(i)
                            
                            if common_old_cols:
                                # 重新映射数据
                                remapped_data = []
                                for row in existing_data:
                                    new_row = [row[i] for i in old_indices]
                                    remapped_data.append(tuple(new_row))
                                
                                placeholders = ", ".join(["?" for _ in common_new_cols])
                                try:
                                    cursor.executemany(
                                        f"INSERT INTO {table_name} ({', '.join(common_new_cols)}) VALUES ({placeholders})",
                                        remapped_data
                                    )
                                    logger.info(f"[数据库修复] 表 {table_name} 恢复了 {len(remapped_data)} 条记录")
                                except Exception as restore_err:
                                    logger.warning(f"[数据库修复] 恢复数据部分失败: {restore_err}")
                        
                        result["repaired_tables"].append(table_name)
                        logger.info(f"[数据库修复] 重建表: {table_name}")
                        
                except Exception as e:
                    result["errors"].append(f"检查表 {table_name} 结构失败: {str(e)}")
        
        # 添加缺失的字段（通过 TABLE_ALTERS）
        for table_name, alters in TABLE_ALTERS.items():
            for alter_sql in alters:
                try:
                    cursor.execute(alter_sql)
                    # 提取字段名
                    parts = alter_sql.split("ADD COLUMN ")
                    if len(parts) > 1:
                        field_name = parts[1].split()[0]
                        result["added_columns"].append(f"{table_name}.{field_name}")
                        logger.info(f"[数据库修复] 添加字段: {table_name}.{field_name}")
                except sqlite3.OperationalError:
                    # 字段已存在，跳过
                    pass
                except Exception as e:
                    result["errors"].append(f"添加字段失败: {str(e)}")
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        result["errors"].append(f"数据库操作失败: {str(e)}")
    
    return result


def parse_columns_from_create(create_sql: str) -> set:
    """从 CREATE TABLE 语句解析列名"""
    columns = set()
    try:
        # 提取括号内的内容
        match = re.search(r'\((.*)\)', create_sql, re.DOTALL)
        if match:
            content = match.group(1)
            # 分割每个列定义（注意处理括号嵌套）
            parts = []
            depth = 0
            current = ""
            for char in content:
                if char == '(':
                    depth += 1
                    current += char
                elif char == ')':
                    depth -= 1
                    current += char
                elif char == ',' and depth == 0:
                    parts.append(current.strip())
                    current = ""
                else:
                    current += char
            if current.strip():
                parts.append(current.strip())
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                    
                # 跳过表级约束
                upper_part = part.upper()
                if upper_part.startswith(('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK', 'CONSTRAINT')):
                    continue
                
                # 第一个词是列名
                words = part.split()
                if words:
                    col_name = words[0]
                    # 确保不是约束关键字
                    if col_name.upper() not in ('PRIMARY', 'FOREIGN', 'UNIQUE', 'CHECK', 'CONSTRAINT'):
                        columns.add(col_name)
    except Exception as e:
        logger.warning(f"[数据库修复] 解析列名失败: {e}")
    return columns


def backup_database(db_path: str) -> Dict:
    """
    备份数据库
    返回备份文件路径
    """
    if not os.path.exists(db_path):
        return {"success": False, "error": "数据库文件不存在"}
    
    try:
        ensure_backup_dir()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        db_name = os.path.basename(db_path).replace(".db", "")
        backup_name = f"{db_name}_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        shutil.copy2(db_path, backup_path)
        
        size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)
        
        return {
            "success": True,
            "backup_path": backup_path,
            "backup_name": backup_name,
            "size_mb": size_mb,
            "timestamp": timestamp
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def migrate_tables(
    mode: str = "incremental",
    tables: List[str] = None,
    progress_callback=None
) -> Dict:
    """
    从旧数据库迁移系统表到新数据库
    
    Args:
        mode: "incremental" 增量迁移（跳过已存在），"overwrite" 强制覆盖
        tables: 指定要迁移的表，None 表示全部系统表
        progress_callback: 进度回调函数
    
    Returns:
        迁移结果
    """
    result = {
        "success": False,
        "migrated_tables": {},
        "skipped_tables": {},
        "errors": [],
        "total_rows": 0
    }
    
    # 检查源数据库
    if not os.path.exists(DB_PATH):
        result["errors"].append("源数据库不存在")
        return result
    
    # 确保目标数据库存在
    db_dir = os.path.dirname(SYSTEM_DB_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    # 要迁移的表
    tables_to_migrate = tables if tables else SYSTEM_TABLES

    if tables:
        invalid = [t for t in tables if t not in SYSTEM_TABLES]
        if invalid:
            raise ValueError(f"非法表名: {invalid}")
    
    try:
        old_conn = sqlite3.connect(DB_PATH)
        old_conn.row_factory = sqlite3.Row
        old_cursor = old_conn.cursor()
        
        new_conn = sqlite3.connect(SYSTEM_DB_PATH)
        new_cursor = new_conn.cursor()
        
        # 获取源数据库中的表
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        old_tables = {row[0] for row in old_cursor.fetchall()}
        
        for table in tables_to_migrate:
            if progress_callback:
                progress_callback(table, "processing")
            
            # 源表中不存在
            if table not in old_tables:
                result["skipped_tables"][table] = "源表中不存在"
                continue
            
            try:
                # 获取源表结构
                old_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
                schema_row = old_cursor.fetchone()
                if not schema_row or not schema_row[0]:
                    result["skipped_tables"][table] = "无法获取表结构"
                    continue
                
                # 确保目标表存在
                if table in TABLE_SCHEMAS:
                    ensure_registered_table(new_cursor, table)
                else:
                    # 使用源表结构创建
                    new_cursor.execute(schema_row[0])
                
                # 获取源表数据
                old_cursor.execute(f"SELECT * FROM {table}")
                rows = old_cursor.fetchall()
                
                if not rows:
                    result["skipped_tables"][table] = "无数据"
                    continue
                
                # 获取列名
                columns = [desc[0] for desc in old_cursor.description]
                placeholders = ",".join(["?" for _ in columns])
                
                if mode == "overwrite":
                    # 强制覆盖：先清空目标表
                    new_cursor.execute(f"DELETE FROM {table}")
                    new_conn.commit()
                    
                    # 插入所有数据
                    for row in rows:
                        try:
                            new_cursor.execute(
                                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                                tuple(row)
                            )
                            result["total_rows"] += 1
                        except Exception as e:
                            pass
                    
                    result["migrated_tables"][table] = len(rows)
                    
                else:
                    # 增量迁移：跳过已存在的主键
                    # 获取主键列
                    new_cursor.execute(f"PRAGMA table_info({table})")
                    pk_columns = [row[1] for row in new_cursor.fetchall() if row[5] == 1]  # pk=1
                    
                    # 如果没有主键，使用第一列
                    if not pk_columns:
                        pk_columns = [columns[0]]
                    
                    migrated_count = 0
                    skipped_count = 0
                    
                    for row in rows:
                        row_dict = dict(row)
                        
                        # 检查是否已存在
                        pk_where = " AND ".join([f"{pk} = ?" for pk in pk_columns])
                        pk_values = [row_dict[pk] for pk in pk_columns if pk in row_dict]
                        
                        if pk_values:
                            new_cursor.execute(f"SELECT 1 FROM {table} WHERE {pk_where}", pk_values)
                            exists = new_cursor.fetchone()
                            
                            if exists:
                                skipped_count += 1
                                continue
                        
                        # 插入新数据
                        try:
                            new_cursor.execute(
                                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                                tuple(row)
                            )
                            migrated_count += 1
                            result["total_rows"] += 1
                        except sqlite3.IntegrityError:
                            skipped_count += 1
                        except Exception as e:
                            pass
                    
                    if migrated_count > 0:
                        result["migrated_tables"][table] = {
                            "migrated": migrated_count,
                            "skipped": skipped_count
                        }
                    else:
                        result["skipped_tables"][table] = f"全部跳过 ({skipped_count} 条已存在)"
                
                new_conn.commit()
                
                if progress_callback:
                    progress_callback(table, "done")
                    
            except Exception as e:
                result["errors"].append(f"迁移表 {table} 失败: {str(e)}")
                if progress_callback:
                    progress_callback(table, "error", str(e))
        
        old_conn.close()
        new_conn.close()
        
        result["success"] = len(result["migrated_tables"]) > 0 or len(result["skipped_tables"]) > 0
        
    except Exception as e:
        result["errors"].append(f"迁移失败: {str(e)}")
    
    return result


def get_backup_list() -> List[Dict]:
    """获取备份文件列表"""
    if not os.path.exists(BACKUP_DIR):
        return []
    
    backups = []
    for filename in os.listdir(BACKUP_DIR):
        if filename.endswith(".db"):
            filepath = os.path.join(BACKUP_DIR, filename)
            try:
                stat = os.stat(filepath)
                backups.append({
                    "filename": filename,
                    "path": filepath,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
            except:
                pass
    
    # 按时间倒序排列
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def delete_backup(filename: str) -> Dict:
    """删除备份文件"""
    # 防御路径穿越：拒绝包含 .. 的文件名
    if ".." in filename or "/" in filename or "\\" in filename:
        return {"success": False, "error": "无效的文件名"}

    filepath = os.path.join(BACKUP_DIR, filename)
    real_path = os.path.realpath(filepath)
    real_backup_dir = os.path.realpath(BACKUP_DIR)
    if not real_path.startswith(real_backup_dir + os.sep):
        return {"success": False, "error": "无效的备份文件路径"}

    if not os.path.exists(filepath):
        return {"success": False, "error": "备份文件不存在"}

    try:
        os.remove(filepath)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_backup(backup_path: str) -> Dict:
    """
    从备份恢复数据库
    注意：这会覆盖当前数据库
    """
    if not os.path.exists(backup_path):
        return {"success": False, "error": "备份文件不存在"}
    
    try:
        # 先备份当前数据库
        current_backup = backup_database(SYSTEM_DB_PATH)
        
        # 恢复
        shutil.copy2(backup_path, SYSTEM_DB_PATH)
        
        return {
            "success": True,
            "restored_from": backup_path,
            "previous_backup": current_backup.get("backup_path") if current_backup.get("success") else None
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def full_health_check() -> Dict:
    """
    完整的健康检查
    返回系统数据库和旧数据库的完整状态
    """
    return {
        "system_db": get_db_info(SYSTEM_DB_PATH),
        "old_db": get_db_info(DB_PATH),
        "table_check": check_system_tables(),
        "migration_check": check_old_db_tables(),
        "backup_dir": BACKUP_DIR,
        "backup_dir_exists": os.path.exists(BACKUP_DIR)
    }
