import logging
import threading
import time

from app.domains.users import user_bot_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_binding_cache = {}
_blacklist_cache = {}
_emby_account_cache = {}
_cache_lock = threading.Lock()
_BINDING_CACHE_TTL = 60
_BLACKLIST_CACHE_TTL = 300
_EMBY_ACCOUNT_CACHE_TTL = 60

_user_bot_dao_provider = lambda: user_bot_dao
_media_api_provider = lambda: media_api
_logger_provider = lambda: logger
_time_provider = lambda: time
_binding_cache_provider = lambda: _binding_cache
_blacklist_cache_provider = lambda: _blacklist_cache
_emby_account_cache_provider = lambda: _emby_account_cache
_cache_lock_provider = lambda: _cache_lock
_binding_cache_ttl_provider = lambda: _BINDING_CACHE_TTL
_blacklist_cache_ttl_provider = lambda: _BLACKLIST_CACHE_TTL
_emby_account_cache_ttl_provider = lambda: _EMBY_ACCOUNT_CACHE_TTL
_get_binding_provider = None


def set_dependency_providers(
    *,
    user_bot_dao_provider=None,
    media_api_provider=None,
    logger_provider=None,
    time_provider=None,
    binding_cache_provider=None,
    blacklist_cache_provider=None,
    emby_account_cache_provider=None,
    cache_lock_provider=None,
    binding_cache_ttl_provider=None,
    blacklist_cache_ttl_provider=None,
    emby_account_cache_ttl_provider=None,
    get_binding_provider=None,
):
    global _user_bot_dao_provider
    global _media_api_provider
    global _logger_provider
    global _time_provider
    global _binding_cache_provider
    global _blacklist_cache_provider
    global _emby_account_cache_provider
    global _cache_lock_provider
    global _binding_cache_ttl_provider
    global _blacklist_cache_ttl_provider
    global _emby_account_cache_ttl_provider
    global _get_binding_provider

    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if time_provider is not None:
        _time_provider = time_provider
    if binding_cache_provider is not None:
        _binding_cache_provider = binding_cache_provider
    if blacklist_cache_provider is not None:
        _blacklist_cache_provider = blacklist_cache_provider
    if emby_account_cache_provider is not None:
        _emby_account_cache_provider = emby_account_cache_provider
    if cache_lock_provider is not None:
        _cache_lock_provider = cache_lock_provider
    if binding_cache_ttl_provider is not None:
        _binding_cache_ttl_provider = binding_cache_ttl_provider
    if blacklist_cache_ttl_provider is not None:
        _blacklist_cache_ttl_provider = blacklist_cache_ttl_provider
    if emby_account_cache_ttl_provider is not None:
        _emby_account_cache_ttl_provider = emby_account_cache_ttl_provider
    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider


def unbind_user(tg_user_id):
    try:
        _user_bot_dao_provider().delete_user_binding(tg_user_id)
        with _cache_lock_provider():
            _binding_cache_provider().pop(str(tg_user_id), None)
    except Exception:
        pass


def get_binding_by_emby_id(emby_user_id):
    """通过 emby_user_id 获取绑定关系"""
    try:
        emby_id_str = str(emby_user_id).strip()
        binding = _user_bot_dao_provider().get_binding_by_emby_id(emby_id_str)
        if binding:
            return binding
        _logger_provider().warning(f"[绑定] 未找到 emby_user_id={emby_id_str} 的 TG 绑定")
        return None
    except Exception as e:
        _logger_provider().error(f"[绑定] 查询 emby_user_id={emby_user_id} 失败: {e}")
        return None


def get_binding(tg_user_id):
    """获取绑定关系（带缓存，线程安全）"""
    cache_key = str(tg_user_id)

    with _cache_lock_provider():
        cached = _binding_cache_provider().get(cache_key)
        if cached and (_time_provider().time() - cached["cached_at"] < _binding_cache_ttl_provider()):
            return cached["binding"]

    try:
        result = _user_bot_dao_provider().get_binding(cache_key)
        with _cache_lock_provider():
            _binding_cache_provider()[cache_key] = {"binding": result, "cached_at": _time_provider().time()}
        return result
    except Exception:
        return None


def get_channel_binding(channel_id):
    """获取频道绑定关系（频道ID -> 用户ID -> Emby账号）"""
    try:
        row = _user_bot_dao_provider().get_channel_binding(channel_id)
        if row:
            tg_user_id = row["tg_user_id"]
            channel_title = row["channel_title"]
            get_binding_func = _get_binding_provider() if _get_binding_provider is not None else get_binding
            user_binding = get_binding_func(tg_user_id)
            if user_binding:
                return {**user_binding, "channel_title": channel_title, "bound_tg_user_id": tg_user_id}
        return None
    except Exception:
        return None


def bind_channel(channel_id, tg_user_id, channel_title=""):
    """绑定频道到用户"""
    try:
        _user_bot_dao_provider().bind_channel(channel_id, tg_user_id, channel_title)
        return True
    except Exception as e:
        _logger_provider().error(f"绑定频道失败: {e}")
        return False


def unbind_channel(channel_id):
    """解绑频道"""
    try:
        _user_bot_dao_provider().unbind_channel(channel_id)
        return True
    except Exception:
        return False


def get_all_bindings():
    """获取所有绑定关系"""
    try:
        return _user_bot_dao_provider().list_bindings()
    except Exception:
        return []


def record_bot_user(tg_user_id, tg_name=""):
    """记录/更新机器人用户（所有 /start 过的用户）"""
    try:
        _user_bot_dao_provider().record_bot_user(tg_user_id, tg_name)
    except Exception as e:
        _logger_provider().error(f"记录机器人用户失败: {e}")


def get_all_bot_users():
    """获取所有启动过机器人的用户"""
    try:
        return _user_bot_dao_provider().list_bot_users()
    except Exception:
        return []


def bind_user(tg_user_id, emby_user_id, emby_username, init_password="", tg_username="", tg_display_name=""):
    """
    绑定 TG 用户与 Emby 账号
    - 确保一个 Emby 账号只能被一个 TG 用户绑定
    - 绑定前会清理该 Emby 账号的旧绑定关系
    """
    try:
        _user_bot_dao_provider().bind_user(
            tg_user_id,
            emby_user_id,
            emby_username,
            init_password,
            tg_username,
            tg_display_name,
        )
        with _cache_lock_provider():
            _binding_cache_provider()[str(tg_user_id)] = {
                "binding": {
                    "emby_user_id": emby_user_id,
                    "emby_username": emby_username,
                    "init_password": init_password,
                },
                "cached_at": _time_provider().time(),
            }
    except Exception:
        pass


def is_blacklisted(tg_user_id):
    """检查是否在黑名单（带缓存，线程安全）"""
    cache_key = str(tg_user_id)

    with _cache_lock_provider():
        cached = _blacklist_cache_provider().get(cache_key)
        if cached and (_time_provider().time() - cached["cached_at"] < _blacklist_cache_ttl_provider()):
            return cached["blacklisted"]

    try:
        result = _user_bot_dao_provider().is_blacklisted(cache_key)
        with _cache_lock_provider():
            _blacklist_cache_provider()[cache_key] = {"blacklisted": result, "cached_at": _time_provider().time()}
        return result
    except Exception:
        return False


def add_to_blacklist(tg_user_id, reason=""):
    try:
        _user_bot_dao_provider().add_to_blacklist(tg_user_id, reason)
    except Exception:
        pass


def check_emby_account(binding):
    """检查绑定的 Emby 账号是否还存在（带缓存，线程安全）"""
    if not binding:
        return False

    user_id = binding["emby_user_id"]

    with _cache_lock_provider():
        cached = _emby_account_cache_provider().get(user_id)
        if cached and (_time_provider().time() - cached["cached_at"] < _emby_account_cache_ttl_provider()):
            return cached["exists"]

    try:
        res = _media_api_provider().get(f"/Users/{user_id}", timeout=5)
        exists = res.status_code == 200
        with _cache_lock_provider():
            _emby_account_cache_provider()[user_id] = {"exists": exists, "cached_at": _time_provider().time()}
        return exists
    except Exception:
        return True
