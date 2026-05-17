import os
import json
from fastapi.templating import Jinja2Templates

# ================= 🔥 加载 .env 文件(本地开发) =================
# Docker 环境不需要,直接使用环境变量
try:
    from dotenv import load_dotenv
    # 查找 .env 文件(项目根目录)
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _env_file = os.path.join(_project_root, ".env")
    if os.path.exists(_env_file):
        load_dotenv(_env_file)
        print(f"[配置] 已加载 .env 文件: {_env_file}")
except ImportError:
    pass  # python-dotenv 未安装,跳过(Docker 环境正常)

# ================= 🔥 核心修复:路径动态识别 =================
# 1. Docker 环境:优先使用 /workspace/config
# 2. Windows 本地开发:使用项目目录下的 data/config
# 3. 其他 Linux:回退到 /app/config
import sys

# 检测是否在 Docker 容器中运行
_IN_DOCKER = os.path.exists("/.dockerenv") or os.path.exists("/workspace/config") or os.path.exists("/workspace")

if _IN_DOCKER:
    CONFIG_DIR = "/workspace/config"
elif os.name == 'nt':  # Windows 本地开发
    # 使用项目根目录下的 data 文件夹
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    CONFIG_DIR = os.path.join(_project_root, "data", "config")
else:
    CONFIG_DIR = "/app/config"

if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR, exist_ok=True)

# 统一使用 config.json,确保代码读写的是同一个文件
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
FONT_DIR = os.path.join(CONFIG_DIR, "fonts")
if not os.path.exists(FONT_DIR):
    os.makedirs(FONT_DIR, exist_ok=True)

# ================= 资源常量 =================
# 注意:DB_PATH 从环境变量读取,挂载 Emby 插件的 playback_reporting.db
# Windows 下默认路径为当前目录下的数据库文件
DB_ENV = os.getenv("DB_PATH", "")
if DB_ENV:
    DB_PATH = DB_ENV
elif os.name == 'nt':  # Windows
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "playback.db")
else:  # Linux/Docker
    # 🔥 修复:使用 /workspace/data/playback.db 与 webhook 保存路径一致
    DB_PATH = "/workspace/data/playback.db"

# 🔥 系统数据库:固定路径,存储系统表(用户、邀请码、许可证、公告等)
# 与播放数据分离,实现无感升级和数据持久化
if _IN_DOCKER:
    SYSTEM_DB_PATH = "/workspace/data/emby_pulse.db"
elif os.name == 'nt':  # Windows
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Windows 下使用 data/emby_pulse.db(与 Docker 一致)
    SYSTEM_DB_PATH = os.path.join(_project_root, "data", "emby_pulse.db")
else:
    SYSTEM_DB_PATH = "/app/data/emby_pulse.db"

# 确保系统数据库目录存在
_system_db_dir = os.path.dirname(SYSTEM_DB_PATH)
if _system_db_dir and not os.path.exists(_system_db_dir):
    os.makedirs(_system_db_dir, exist_ok=True)
# 字体下载 URL(使用多个镜像源)
FONT_URLS = [
    "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Simplified/NotoSansCJKsc-Bold.otf",
    "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/Simplified/NotoSansCJKsc-Bold.otf",
]
FONT_PATH = os.path.join(FONT_DIR, "NotoSansCJKsc-Bold.otf")

# 🔥 内置字体路径(插件自带,无需下载)
# 使用硬编码路径避免循环导入
BUILTIN_FONT_DIR = "/workspace/app/plugins/view_report/fonts"
BUILTIN_FONT_PATH = os.path.join(BUILTIN_FONT_DIR, "NotoSansCJKsc-Bold.otf")
REPORT_COVER_URL = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=1200&auto=format&fit=crop"
FALLBACK_IMAGE_URL = "https://img.hotimg.com/a444d32a033994d5b.png"

TMDB_FALLBACK_POOL = [
    "https://image.tmdb.org/t/p/original/zfbjgQE1uSd9wiPTX4VzsLi0rGG.jpg",
    "https://image.tmdb.org/t/p/original/rLb2cs785pePbIKYQz1CADtovh7.jpg",
    "https://image.tmdb.org/t/p/original/tmU7GeKVybMWFButWEGl2M4GeiP.jpg",
    "https://image.tmdb.org/t/p/original/kXfqcdQKsToO0OUXHcrrNCHDBzO.jpg",
    "https://image.tmdb.org/t/p/original/zb6fM1CX41D9rF9hdgclu0peUmy.jpg"
]

THEMES = {
    "black_gold": {"bg": (26, 26, 26), "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (234, 179, 8)},
    "cyber":      {"bg": (46, 16, 101), "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (0, 255, 255)},
    "ocean":      {"bg": (15, 23, 42),  "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (56, 189, 248)},
    "aurora":     {"bg": (6, 78, 59),   "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (52, 211, 153)},
    "magma":      {"bg": (127, 29, 29), "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (251, 146, 60)},
    "sunset":     {"bg": (124, 45, 18), "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (253, 186, 116)},
    "concrete":   {"bg": (82, 82, 82),  "text": (255, 255, 255), "card": (255, 255, 255, 20), "highlight": (212, 212, 216)},
    "white":      {"bg": (255, 255, 255), "text": (51, 51, 51), "card": (0, 0, 0, 10), "highlight": (234, 179, 8)}
}

# 使用你原本定义的 lowercase 字段名
# 🔥 注意:环境变量不在这里读取,而是在 load() 中处理
DEFAULT_CONFIG = {
    "emby_host": "",  # 空字符串,load 时再从环境变量或配置文件读取
    "emby_api_key": "",
    "emby_public_host": "",
    "tmdb_api_key": "",
    "proxy_url": "",
    "hidden_users": [],
    "tg_bot_token": "",
    "tg_chat_id": "",
    "enable_bot": False,
    "enable_notify": False,
    "enable_library_notify": False,
    "notify_user_login": False,
    "notify_item_deleted": False,
    "webhook_token": "",
    "calendar_cache_ttl": 86400,
    "scheduled_tasks": [],
    "emby_public_url": "",
    "welcome_message": "",
    "client_download_url": "",
    "moviepilot_url": "",
    "moviepilot_token": "",
    "pulse_url": "",
    "server_type": "emby",
    "default_user_template_id": "",
    "user_portal_url": "",  # 用户社区公网地址,用于生成邀请链接
    "disable_emby_auth": False  # 禁用 Emby 管理员登录(需先开启本地认证)
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        # 🔒 敏感字段列表(只能通过环境变量设置)
        self.SENSITIVE_ENV_FIELDS = {
            "tg_bot_token": "TG_BOT_TOKEN",
            "tg_user_bot_token": "TG_USER_BOT_TOKEN",
            "emby_api_key": "EMBY_API_KEY",
            "tmdb_api_key": "TMDB_API_KEY",
            "moviepilot_token": "MOVIEPILOT_TOKEN",
            "wecom_corpsecret": "WECOM_CORPSECRET",
            "wecom_token": "WECOM_TOKEN",
            "wecom_aeskey": "WECOM_AESKEY",
            "webhook_token": "WEBHOOK_TOKEN",
        }

        # 🔧 普通环境变量字段(用于首次初始化)
        self.ENV_DEFAULTS = {
            "emby_host": "EMBY_HOST",
            "tg_chat_id": "TG_CHAT_ID",
        }
        self.load()

    def load(self):
        # 🔥 配置文件优先:保存后的配置会持久化
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception as e:
                print(f"⚠️ Config Load Error: {e}")

        # 🔒 环境变量强制覆盖敏感字段(优先级最高)
        env_fields_set = []
        for config_key, env_key in self.SENSITIVE_ENV_FIELDS.items():
            env_val = os.getenv(env_key, "")
            if env_val:
                self.config[config_key] = env_val.strip()
                env_fields_set.append(config_key)
                print(f"[Config] 🔒 环境变量 {env_key} -> {config_key} (长度: {len(env_val)})")

        # 🔒 安全:如果环境变量设置了敏感字段,清除配置文件中的对应值
        if env_fields_set and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)

                need_save = False
                for field in env_fields_set:
                    if field in saved and saved[field]:
                        saved[field] = ""
                        need_save = True

                if need_save:
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(saved, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ 清除配置文件敏感字段失败: {e}")

        # 🔥 普通环境变量(仅用于首次初始化,配置文件中无值时)
        env_defaults = {
            "emby_host": os.getenv("EMBY_HOST", "").rstrip('/'),
            "tg_chat_id": os.getenv("TG_CHAT_ID", ""),
        }
        for key, env_val in env_defaults.items():
            if env_val and not self.config.get(key):
                self.config[key] = env_val

        # 🔥 如果 emby_host 仍为空,设置默认值
        if not self.config.get("emby_host"):
            self.config["emby_host"] = "http://127.0.0.1:8096"

        # 🔥 本地认证环境变量
        local_auth_enabled = os.getenv("LOCAL_AUTH_ENABLED", "").lower() in ("true", "1", "yes")
        if local_auth_enabled:
            self.config["enable_local_auth"] = True

        # 🔍 调试:打印关键配置
        print(f"[Config] ✅ 加载完成 - emby_api_key: {'已设置' if self.config.get('emby_api_key') else '未设置'}, emby_host: {self.config.get('emby_host', '未设置')}")

    def get_env_source(self, key):
        """检查字段是否来自环境变量"""
        env_key = self.SENSITIVE_ENV_FIELDS.get(key)
        if env_key:
            env_val = os.getenv(env_key, "")
            if env_val:
                return "env"
        return "config"

    def save(self):
        """保存配置到文件(自动排除环境变量控制的敏感字段)"""
        try:
            config_to_save = self.config.copy()

            for config_key, env_key in self.SENSITIVE_ENV_FIELDS.items():
                if os.getenv(env_key, ""):
                    config_to_save[config_key] = ""

            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Config Save Error: {e}")

    def set(self, key, value):
        """设置配置值(禁止修改环境变量控制的敏感字段)"""
        env_key = self.SENSITIVE_ENV_FIELDS.get(key)
        if env_key:
            env_val = os.getenv(env_key, "")
            if env_val:
                # 🔒 环境变量已设置,禁止修改
                print(f"[Config] 🚫 拒绝修改环境变量字段 {key}(来自 {env_key})")
                return

        self.config[key] = value
        self.save()

    def get(self, key, default=None):
        return self.config.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def get_main_public_url(self):
        raw_url_str = self.get("emby_public_url", "")
        if not raw_url_str:
            # fallback到emby_public_host
            return self.get("emby_public_host", "").rstrip('/')
        try:
            routes = json.loads(raw_url_str)
            if isinstance(routes, list) and len(routes) > 0:
                # 优先取 is_main 的线路
                for r in routes:
                    if r.get("is_main"):
                        return r.get("url", "").rstrip('/')
                return routes[0].get("url", "").rstrip('/')
        except Exception:
            pass
        return raw_url_str.strip().rstrip('/')

    def get_all_routes(self):
        """获取所有线路(管理员用)"""
        raw = self.get("emby_public_url", "")
        if not raw:
            return []
        try:
            routes = json.loads(raw)
            if isinstance(routes, list):
                return routes
        except:
            pass
        return [{"name": "默认线路", "url": raw.strip().rstrip('/'), "is_main": True}] if raw else []

    def get_user_routes(self, user_id=None):
        """获取用户可见的线路
        优先级:用户专属允许 > 用户专属屏蔽 > 全局允许设置
        """
        all_routes = self.get_all_routes()
        if not all_routes:
            return []

        # 获取用户的专属线路配置
        user_allowed_routes = []
        user_blocked_routes = []
        if user_id:
            try:
                from app.core.database import query_db
                row = query_db("SELECT allow_routes, block_routes FROM users_meta WHERE user_id = ?", (user_id,), one=True)
                # 转换为字典,处理 sqlite3.Row
                if row:
                    row_dict = dict(row) if hasattr(row, 'keys') else {k: row[i] for i, k in enumerate(row.keys())}
                    allow_val = row_dict.get('allow_routes', '') or ''
                    block_val = row_dict.get('block_routes', '') or ''
                    if allow_val:
                        user_allowed_routes = [r.strip() for r in allow_val.split(',') if r.strip()]
                    if block_val:
                        user_blocked_routes = [r.strip() for r in block_val.split(',') if r.strip()]
            except Exception as e:
                print(f"[DEBUG] get_user_routes Error: {e}")

        # 1. 如果用户有专属允许线路,只返回这些线路
        if user_allowed_routes:
            return [r for r in all_routes if r.get('name', '') in user_allowed_routes]

        # 2. 否则,检查全局允许设置 + 用户专属屏蔽
        visible = []
        for r in all_routes:
            route_name = r.get('name', '')

            # 全局设置:show_to_users !== false 表示允许访问
            is_globally_allowed = r.get("show_to_users") != False

            # 如果全局不允许,但用户在精选用户列表中,仍可见
            if not is_globally_allowed:
                vip_users = r.get("vip_only_users", [])
                # 确保 vip_users 是列表
                if not isinstance(vip_users, list):
                    vip_users = []
                # 转换为字符串比较,避免类型不匹配(如 "123" vs 123)
                vip_users_str = [str(u) for u in vip_users] if vip_users else []
                # user_id 也需要转换为字符串比较
                user_id_str = str(user_id) if user_id is not None else None
                if vip_users_str and user_id_str and user_id_str in vip_users_str:
                    pass  # 允许访问
                else:
                    continue  # 全局不允许,跳过

            # 检查用户专属屏蔽列表
            if route_name in user_blocked_routes:
                continue

            visible.append(r)
        return visible

    def __getitem__(self, key):
        return self.config.get(key, DEFAULT_CONFIG.get(key))

    def __setitem__(self, key, value):
        env_key = self.SENSITIVE_ENV_FIELDS.get(key)
        if env_key and os.getenv(env_key, ""):
            print(f"[Config] 🚫 拒绝修改环境变量字段 {key}(来自 {env_key})")
            return
        self.config[key] = value
        self.save()

    def get_all(self):
        return self.config.copy()  # 🔒 安全：返回副本，防止外部修改

    def is_env_override(self, key):
        """检查字段是否被环境变量覆盖"""
        return self.get_env_source(key) == "env"

cfg = ConfigManager()
templates = Jinja2Templates(directory="templates")

# 🔒 安全：SECRET_KEY 每次启动随机生成（存储在内存中）
import secrets
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)

if not os.getenv("SECRET_KEY"):
    print("🔒 [安全] SECRET_KEY 已自动生成（每次重启会重新生成，Session 会失效）")
    print("💡 [提示] 如需固定 SECRET_KEY，请在 .env 中设置 SECRET_KEY=<随机字符串>")
    
    # 清理旧的 SECRET_KEY 文件（如果存在）
    old_secret_file = os.path.join(CONFIG_DIR, "secret_key.txt")
    if os.path.exists(old_secret_file):
        try:
            os.remove(old_secret_file)
            print(f"🧹 [清理] 已删除旧的 SECRET_KEY 文件: {old_secret_file}")
        except Exception as e:
            print(f"⚠️ [清理] 删除旧文件失败: {e}")

PORT = int(os.getenv("PORT", "10307"))

def save_config():
    cfg.save()