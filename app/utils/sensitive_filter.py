"""
敏感信息过滤器 - 防止日志泄露 Token、API Key 等
"""
import re

# 敏感字段正则模式
SENSITIVE_PATTERNS = [
    # Telegram Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
    (r'\b(\d{8,10}:[A-Za-z0-9_-]{30,40})\b', lambda m: f'{m.group(1)[:4]}****{m.group(1)[-4:]}'),
    # API Key (通用): 32-64 位字母数字
    (r'\b([a-zA-Z0-9]{8})[a-zA-Z0-9]{16,48}([a-zA-Z0-9]{8})\b', r'\1****\2'),
    # Emby API Key: 32 位 hex
    (r'\b([a-f0-9]{8})[a-f0-9]{16}([a-f0-9]{8})\b', r'\1****\2'),
    # TMDB API Key: 32 位字母数字
    (r'\b([a-zA-Z0-9]{4})[a-zA-Z0-9]{24}([a-zA-Z0-9]{4})\b', r'\1****\2'),
]

# 敏感字段名（用于过滤 JSON 日志）
SENSITIVE_KEYS = [
    'tg_bot_token', 'tg_user_bot_token', 'emby_api_key', 'tmdb_api_key',
    'wecom_corpsecret', 'wecom_token', 'wecom_aeskey', 'webhook_token',
    'moviepilot_token', 'weather_qweather_key', 'weather_amap_key',
    'password', 'secret', 'token', 'api_key', 'apikey'
]


def mask_sensitive_value(value: str, show_len: int = 4) -> str:
    """脱敏单个值"""
    if not value or not isinstance(value, str):
        return value
    if len(value) <= show_len * 2:
        return "****"
    return f"{value[:show_len]}****{value[-show_len:]}"


def filter_sensitive_text(text: str) -> str:
    """过滤文本中的敏感信息"""
    if not isinstance(text, str):
        return text
    
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        try:
            result = re.sub(pattern, replacement, result)
        except:
            pass
    
    return result


def filter_sensitive_dict(data: dict) -> dict:
    """过滤字典中的敏感信息"""
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        
        # 检查是否为敏感字段
        is_sensitive = any(s in key_lower for s in SENSITIVE_KEYS)
        
        if is_sensitive and isinstance(value, str) and value:
            result[key] = mask_sensitive_value(value)
        elif isinstance(value, dict):
            result[key] = filter_sensitive_dict(value)
        elif isinstance(value, list):
            result[key] = [filter_sensitive_dict(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    
    return result


class SensitiveLogFilter:
    """日志过滤器 - 自动脱敏敏感信息"""
    
    def filter(self, record):
        """过滤日志记录"""
        # 脱敏消息
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = filter_sensitive_text(record.msg)
        
        # 脱敏参数
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = filter_sensitive_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    filter_sensitive_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        
        return True
