import logging

from app.utils.sensitive_filter import SensitiveLogFilter


def configure_sensitive_log_filter() -> None:
    """Attach the sensitive-data filter to application loggers."""
    for handler in logging.getLogger().handlers:
        handler.addFilter(SensitiveLogFilter())
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        for handler in logging.getLogger(logger_name).handlers:
            handler.addFilter(SensitiveLogFilter())
    print("[🔒 安全] 已启用日志脱敏过滤器")

