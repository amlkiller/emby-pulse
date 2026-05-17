"""
EmbyPulse 插件加载器
启动时扫描 app/plugins/ 下所有子目录，自动发现并注册插件
"""
import os
import importlib
import sqlite3
import json
import logging
import threading
from typing import Dict, List, Optional
from app.plugins.base import PluginBase, _config_cache, _config_cache_lock
from app.core.database import SYSTEM_DB_PATH

logger = logging.getLogger("uvicorn")

# 全局插件注册表
_registry: Dict[str, PluginBase] = {}


def _ensure_plugin_table():
    try:
        # 确保 data 目录存在
        db_dir = os.path.dirname(SYSTEM_DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"[🧩 插件] 创建数据库目录: {db_dir}")
        
        conn = sqlite3.connect(SYSTEM_DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")  # 使用 WAL 模式减少锁等待
        conn.execute("""CREATE TABLE IF NOT EXISTS plugin_state (
            plugin_id TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            config TEXT DEFAULT '{}'
        )""")
        conn.commit()
        conn.close()
        print(f"[🧩 插件] 数据库表初始化成功: {SYSTEM_DB_PATH}")
    except Exception as e:
        print(f"[🧩 插件] 初始化数据库表失败: {e}")
        import traceback
        traceback.print_exc()


def discover_plugins():
    """扫描 app/plugins/ 下所有含 plugin.py 的子目录"""
    _ensure_plugin_table()
    plugins_dir = os.path.dirname(__file__)

    for name in os.listdir(plugins_dir):
        pkg_dir = os.path.join(plugins_dir, name)
        if not os.path.isdir(pkg_dir):
            continue
        # 兼容源码(.py)和编译后(.pyc)两种模式
        has_plugin = os.path.exists(os.path.join(pkg_dir, "plugin.py")) or os.path.exists(os.path.join(pkg_dir, "plugin.pyc"))
        if not has_plugin:
            continue

        try:
            module = importlib.import_module(f"app.plugins.{name}.plugin")
            
            # 优先查找模块级别的 plugin 实例（推荐模式：模块底部创建实例并注册路由）
            if hasattr(module, 'plugin') and isinstance(module.plugin, PluginBase):
                instance = module.plugin
                if instance.id:
                    _registry[instance.id] = instance
                    logger.info(f"🧩 发现插件: {instance.name} (v{instance.version}), routes={len(instance.router.routes)}")
                continue
            
            # 回退：查找类并创建实例
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                    instance = attr()
                    if instance.id:
                        _registry[instance.id] = instance
                        logger.info(f"🧩 发现插件: {instance.name} (v{instance.version})")
        except Exception as e:
            logger.error(f"加载插件 {name} 失败: {e}")
            import traceback
            traceback.print_exc()

    # 从数据库恢复启用状态
    _restore_states()


def _restore_states():
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute("SELECT plugin_id, enabled, config FROM plugin_state").fetchall()
        conn.close()
        print(f"[🧩 插件] 从数据库恢复状态，发现 {len(rows)} 条记录")
        for pid, enabled, config_json in rows:
            print(f"[🧩 插件] 检查插件 {pid}: enabled={enabled}, in_registry={pid in _registry}")
            
            # 🔥 加载配置到缓存
            try:
                config = json.loads(config_json) if config_json else {}
                with _config_cache_lock:
                    _config_cache[pid] = config
            except:
                pass
            
            if pid in _registry and enabled:
                print(f"[🧩 插件] 启用插件: {pid}")
                _registry[pid].enable()
    except Exception as e:
        print(f"[🧩 插件] 恢复状态异常: {e}")
        import traceback
        traceback.print_exc()


def get_all_plugins() -> List[dict]:
    return [p.get_meta() for p in _registry.values()]


def get_plugin(plugin_id: str) -> Optional[PluginBase]:
    return _registry.get(plugin_id)


def get_enabled_plugins() -> List[PluginBase]:
    return [p for p in _registry.values() if p.enabled]


def set_plugin_enabled(plugin_id: str, enabled: bool) -> bool:
    plugin = _registry.get(plugin_id)
    if not plugin:
        return False
    if enabled:
        plugin.enable()
    else:
        plugin.disable()
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        # 🔥 修复：保留原有配置，只更新 enabled 字段
        conn.execute("""
            INSERT OR REPLACE INTO plugin_state (plugin_id, enabled, config) 
            VALUES (?, ?, COALESCE((SELECT config FROM plugin_state WHERE plugin_id = ?), '{}'))
        """, (plugin_id, 1 if enabled else 0, plugin_id))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return True


def get_plugin_config(plugin_id: str) -> dict:
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")  # 使用 WAL 模式减少锁等待
        row = conn.execute("SELECT config FROM plugin_state WHERE plugin_id = ?", (plugin_id,)).fetchone()
        conn.close()
        return json.loads(row[0]) if row and row[0] else {}
    except Exception:
        return {}


def save_plugin_config(plugin_id: str, config: dict):
    """保存插件配置并刷新缓存"""
    global _config_cache
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT OR REPLACE INTO plugin_state (plugin_id, enabled, config) VALUES (?, COALESCE((SELECT enabled FROM plugin_state WHERE plugin_id = ?), 0), ?)",
                     (plugin_id, plugin_id, json.dumps(config, ensure_ascii=False)))
        conn.commit()
        conn.close()
        # 刷新缓存
        with _config_cache_lock:
            _config_cache[plugin_id] = config
    except Exception:
        pass


def update_plugin_config(plugin_id: str, updates: dict, merge: bool = True):
    """更新插件配置
    
    Args:
        plugin_id: 插件ID
        updates: 配置更新
        merge: 是否合并现有配置（默认True）。如果为False，直接保存updates
    """
    if merge:
        current = get_plugin_config(plugin_id)
        current.update(updates)
        save_plugin_config(plugin_id, current)
        return current
    else:
        save_plugin_config(plugin_id, updates)
        return updates


def get_plugin_logs(plugin_id: str, limit: int = 50):
    """获取插件日志"""
    plugin = _registry.get(plugin_id)
    if plugin:
        return plugin.get_logs(limit)
    return []


def clear_plugin_logs(plugin_id: str):
    """清空插件日志"""
    plugin = _registry.get(plugin_id)
    if plugin:
        return plugin.clear_logs()
    return False
