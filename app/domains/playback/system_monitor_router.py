import psutil
from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.users import public_service as user_service


router = APIRouter()

_user_service_provider = lambda: user_service
_psutil_provider = lambda: psutil
_safe_error_message_provider = lambda: safe_error_message


def set_dependency_providers(
    *,
    user_service_provider=None,
    psutil_provider=None,
    safe_error_message_provider=None,
):
    global _user_service_provider
    global _psutil_provider
    global _safe_error_message_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if psutil_provider is not None:
        _psutil_provider = psutil_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


@router.get("/api/system/monitor")
def api_system_monitor(request: Request):
    # 🔒 管理员专用：只检查后台登录
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        psutil_module = _psutil_provider()
        # 🔥 interval=0 立即返回（非阻塞），使用上次采样值
        cpu_usage = psutil_module.cpu_percent(interval=0)

        # 内存使用率
        memory_info = psutil_module.virtual_memory()
        memory_usage = memory_info.percent

        # 根目录磁盘使用率
        disk_info = psutil_module.disk_usage('/')
        disk_usage = disk_info.percent

        return {
            "status": "success",
            "data": {
                "cpu": cpu_usage,
                "memory": memory_usage,
                "disk": disk_usage
            }
        }
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "探针读取失败")}
