from fastapi import APIRouter, Request, Response
from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
from app.schemas.models import PushRequestModel
from app.domains.reports.report_service import report_gen, HAS_PIL
from app.services.bot_service import bot
import io

router = APIRouter()

@router.get("/api/report/preview")
async def api_preview_report(request: Request, user_id: str = 'all', period: str = 'day'):
    if not request.session.get("user"): return Response(status_code=401)
    if not is_admin_user(request): return Response(status_code=403)
    if not HAS_PIL: return Response(content="Pillow not installed", status_code=500)
    
    img_io = report_gen.generate_report(user_id, period)
    if img_io:
        return Response(content=img_io.read(), media_type="image/jpeg")
    return Response(status_code=500)

@router.post("/api/report/push")
async def api_push_report(data: PushRequestModel, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    # 调用 bot 发送 (支持文字+图片)
    success = bot.push_now(data.user_id, data.period, data.theme)
    if success:
        return {"status": "success"}
    return {"status": "error", "message": "Bot not configured"}
