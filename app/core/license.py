import os
import uuid
import sqlite3
import datetime
from app.core.database import SYSTEM_DB_PATH

def get_machine_id():
    """获取或生成当前设备的唯一指纹 (防 Docker 重启丢失)"""
    db_dir = os.path.dirname(SYSTEM_DB_PATH)
    id_file = os.path.join(db_dir, ".machine_id")
    
    # 如果已有指纹，直接读取
    if os.path.exists(id_file):
        with open(id_file, "r") as f:
            return f.read().strip()
    
    # 如果没有，生成一个新的唯一指纹并持久化保存
    new_id = "EP-" + uuid.uuid4().hex[:16].upper()
    try:
        with open(id_file, "w") as f:
            f.write(new_id)
    except Exception as e:
        print(f"[授权模块] 写入设备指纹失败: {e}")
    
    return new_id

def get_local_license_status():
    """读取本地授权状态"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        row = c.execute("SELECT * FROM sys_license LIMIT 1").fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return {"status": "free", "license_key": None}
    except:
        return {"status": "free", "license_key": None}