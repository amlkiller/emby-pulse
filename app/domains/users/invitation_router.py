import datetime
import secrets
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.system import invitation_dao
from app.domains.users.auth import is_admin_user
from app.infra.config.request_portal_settings import get_user_portal_url


router = APIRouter()

_is_admin_user_provider = lambda: is_admin_user
_invitation_dao_provider = lambda: invitation_dao
_portal_url_provider = lambda: get_user_portal_url
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: None


class InviteGenModelLocal(BaseModel):
    days: int
    count: Optional[int] = 1
    template_user_id: Optional[str] = None
    type: Optional[str] = "register"  # register 或 renew
    routes: Optional[str] = ""  # 线路设置,逗号分隔
    route_mode: Optional[str] = "block"  # 允许或屏蔽模式
    req_free: Optional[int] = 0  # 求片权限:0=跟随全局, 1=免费
    req_free_count: Optional[int] = -1  # -1=无限次, >=0=剩余次数


class InviteBatchModelLocal(BaseModel):
    codes: List[str]
    action: str


def set_dependency_providers(
    *,
    is_admin_user_provider=None,
    invitation_dao_provider=None,
    portal_url_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
):
    global _is_admin_user_provider
    global _invitation_dao_provider
    global _portal_url_provider
    global _client_ip_provider
    global _audit_log_provider

    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if invitation_dao_provider is not None:
        _invitation_dao_provider = invitation_dao_provider
    if portal_url_provider is not None:
        _portal_url_provider = portal_url_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider


@router.post("/api/manage/invite/gen")
def api_gen_invite(data: InviteGenModelLocal, request: Request):
    if not request.session.get("user"):
        return {"status": "error"}
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = _client_ip_provider()(request)

        count = data.count if data.count and data.count > 0 else 1
        code_type = data.type if data.type in ("register", "renew") else "register"
        routes = data.routes if data.routes else ""
        route_mode = data.route_mode if data.route_mode in ("allow", "block") else "block"
        req_free = data.req_free if data.req_free else 0
        req_free_count = data.req_free_count if data.req_free_count is not None else -1
        codes = [secrets.token_hex(4) for _ in range(count)]
        created_at = datetime.datetime.now().isoformat()
        _invitation_dao_provider().create_invitation_codes(
            codes,
            data.days,
            created_at,
            data.template_user_id,
            code_type,
            routes,
            route_mode,
            req_free,
            req_free_count,
        )

        # 记录审计日志
        type_str = "注册码" if code_type == "register" else "续费码"
        audit_log = _audit_log_provider()
        if audit_log:
            audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="生成邀请码",
                target_count=count,
                details=f"类型:{type_str}, 天数:{data.days}, 线路:{routes or '无'}",
                ip_address=ip_address,
            )

        # 构建邀请链接
        portal_url = _portal_url_provider()().rstrip("/")
        links = [f"{portal_url}/invite/{code}" for code in codes] if portal_url and code_type == "register" else []
        return {"status": "success", "codes": codes, "type": code_type, "links": links, "portal_url": portal_url}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/manage/invites")
def api_get_invites(request: Request, code_type: str = "all"):
    if not request.session.get("user"):
        return {"status": "error"}
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        dao = _invitation_dao_provider()
        rows = dao.list_admin_invitations(code_type)
        data = [dict(r) for r in rows] if rows else []
        # 添加邀请链接
        portal_url = _portal_url_provider()().rstrip("/")
        for item in data:
            if item.get("type") == "register" and item.get("code"):
                item["invite_link"] = f"{portal_url}/invite/{item['code']}" if portal_url else ""

        # 计算统计数据(按类型分组)
        stats = {
            "all": {"total": 0, "used": 0, "unused": 0},
            "register": {"total": 0, "used": 0, "unused": 0},
            "renew": {"total": 0, "used": 0, "unused": 0},
        }
        all_rows = dao.list_invitation_usage_stats()
        if all_rows:
            for r in all_rows:
                t = r["type"] or "register"
                is_used = (r["used_count"] or 0) > 0 or r["used_by"]
                stats["all"]["total"] += 1
                stats[t]["total"] += 1
                if is_used:
                    stats["all"]["used"] += 1
                    stats[t]["used"] += 1
                else:
                    stats["all"]["unused"] += 1
                    stats[t]["unused"] += 1

        return {"status": "success", "data": data, "stats": stats}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/manage/invites/export")
def api_export_invites(request: Request, code_type: str = "all"):
    """导出邀请码/续费码为CSV"""
    if not request.session.get("user"):
        return {"status": "error"}
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        rows = _invitation_dao_provider().list_invitation_export_rows(code_type)
        if not rows:
            return {"status": "error", "message": "无数据"}
        portal_url = _portal_url_provider()().rstrip("/")
        lines = ["码,类型,天数,已用次数,最大次数,使用者,状态,生成时间,使用时间,求片权限,免费次数,邀请链接"]
        for r in rows:
            d = dict(r)
            status_str = "已用" if d.get("status") == 1 else "可用"
            type_str = "注册码" if d.get("type") == "register" else "续费码"
            link = f"{portal_url}/invite/{d['code']}" if portal_url and d.get("type") == "register" else ""
            req_free = d.get("req_free", 0) or 0
            req_free_count = d.get("req_free_count", -1) if req_free == 1 else ""
            req_free_text = "免费求片" if req_free == 1 else "跟随全局"
            lines.append(
                f"{d['code']},{type_str},{d['days']},{d['used_count']},{d['max_uses']},"
                f"{d.get('used_by','')},{status_str},{d.get('created_at','')},{d.get('used_at','')},"
                f"{req_free_text},{req_free_count},{link}"
            )
        return PlainTextResponse(
            "\n".join(lines),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=codes_{code_type}.csv"},
        )
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/manage/invites/batch")
def api_manage_invites_batch(data: InviteBatchModelLocal, request: Request):
    if not request.session.get("user"):
        return {"status": "error"}
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = _client_ip_provider()(request)

        if data.action == "delete":
            _invitation_dao_provider().delete_invitation_codes(data.codes)
            # 记录审计日志
            audit_log = _audit_log_provider()
            if audit_log:
                audit_log(
                    admin_id=admin_user.get("id", ""),
                    admin_name=admin_name,
                    action="批量删除邀请码",
                    target_count=len(data.codes),
                    details=f"删除码: {', '.join(data.codes[:10])}{'...' if len(data.codes) > 10 else ''}",
                    ip_address=ip_address,
                )
        return {"status": "success", "message": "删除成功"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
