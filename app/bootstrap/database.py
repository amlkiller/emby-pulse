import os

from app.core.config import DB_PATH, SYSTEM_DB_PATH
from app.infra.db.database import auto_migrate_system_db, init_db
from app.infra.db.db_manager import ensure_tables


def initialize_databases() -> None:
    """Initialize and repair application databases without changing behavior."""
    print("[🚀 启动] 正在检查数据库状态...")
    if os.getenv("AUTO_MIGRATE_DB", "") == "1":
        auto_migrate_system_db()
    else:
        print("[🔄 迁移检测] 自动迁移已关闭，跳过（设置 AUTO_MIGRATE_DB=1 启用）")

    init_db(skip_migration=True)

    table_result = ensure_tables()
    if table_result["created_tables"]:
        print(f"[🔧 自动修复] 已创建缺失表: {', '.join(table_result['created_tables'])}")

    print(f"[📊 数据库] 系统库: {SYSTEM_DB_PATH} {'✅' if os.path.exists(SYSTEM_DB_PATH) else '❌'}")
    print(f"[📊 数据库] 播放库: {DB_PATH} {'✅' if os.path.exists(DB_PATH) else '❌ (将使用API模式)'}")
