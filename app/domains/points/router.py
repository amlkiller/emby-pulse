from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from app.core.config import templates
from app.infra.db.notification_dao import add_system_notification
from app.domains.system import invitation_dao
from app.domains.users import public_service as user_service
from app.domains.points import point_dao
from app.domains.points.game_router import router as game_router
from app.infra.clients.media_server_client import media_api
from app.domains.notifications import public_service as notification_service
from app.shared.view_context import get_common_vars

router = APIRouter()
from app.core.security_utils import safe_error_message

try:
    point_dao.ensure_lottery_table()
except Exception:
    pass

try:
    point_dao.ensure_points_schema()
except Exception as e:
    print(f"初始化积分系统数据库失败: {e}")

class PointConfigModel(BaseModel): configs: dict
class BatchPointsModel(BaseModel): user_ids: List[str]; amount: int; reason: str

@router.get("/points")
async def points_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    
    # 权限检查
    if not user_service.check_permission(request, "points"):
        return RedirectResponse("/?no_permission=1", status_code=303)

    return templates.TemplateResponse("points.html", get_common_vars(request, "points", {
        "user": request.session.get("user"),
        "is_pro": True
    }))

@router.get("/api/points/config")
def get_points_config(request: Request):
    # 🔥 支持管理后台和用户社区两种 session
    user = request.session.get("user") or request.session.get("req_user")
    if not user: return {"status": "error"}
    config = point_dao.get_point_config()
    
    config['is_pro'] = True
        
    return {"status": "success", "data": config}

# 👇 注意：这里移除了 Depends，让普通用户也能访问，用来保存“签到”设置
@router.post("/api/points/config")
async def save_points_config(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    point_dao.save_point_config_values(data.get('configs', {}))
    return {"status": "success", "message": "全局配置已保存"}

@router.get("/api/points/users")
def get_users_points(request: Request, page: int = 1, page_size: int = 20):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    try:
        emby_users = media_api.get("/Users", timeout=5).json()
        meta_rows = point_dao.list_user_points()
        points_map = {r['user_id']: (r['points'] or 0) for r in meta_rows} if meta_rows else {}
        results = []
        for u in emby_users:
            last_active = u.get("LastActivityDate", "从未活跃")
            # 🔥 将 Emby 返回的 UTC 时间转换为本地时间 (格式: 2024-04-10T09:30:00.0000000Z)
            if last_active and last_active != "从未活跃":
                try:
                    from datetime import datetime, timezone
                    # 解析 Emby 返回的 ISO 8601 格式时间（带 Z 表示 UTC）
                    dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    # 转换为本地时间
                    local_dt = dt.astimezone()
                    last_active = local_dt.strftime('%Y-%m-%dT%H:%M:%S')
                except:
                    pass  # 解析失败则保留原值
            results.append({"id": u['Id'], "name": u['Name'], "points": points_map.get(u['Id'], 0), "last_active": last_active})
        results.sort(key=lambda x: x['points'], reverse=True)
        
        # 分页
        total = len(results)
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        start = (page - 1) * page_size
        end = start + page_size
        paged_results = results[start:end]
        
        return {"status": "success", "data": paged_results, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 👇 批量发钱功能依然严格锁死！
@router.post("/api/points/batch_update")
def batch_update_points(data: BatchPointsModel, request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝批量改积分（用户名映射依赖 Emby）
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    try:
        users = media_api.get("/Users", timeout=5).json()
        name_map = {u['Id']: u['Name'] for u in users}
        count = point_dao.batch_update_user_points(data.user_ids, data.amount, data.reason, name_map)
        return {"status": "success", "message": f"成功修改了 {count} 名用户的资产"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/points/logs")
def get_point_logs(request: Request, user_id: str = None, page: int = 1, page_size: int = 50, action_type: str = None):
    """获取积分流水（支持分页和筛选）"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        result = point_dao.list_point_logs(user_id=user_id, page=page, page_size=page_size, action_type=action_type)
        
        return {
            "status": "success", 
            "data": result["logs"],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
            "total_pages": (result["total"] + page_size - 1) // page_size
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# ==========================================
# C端 API
# ==========================================
@router.get("/api/user/points/info")
def get_user_points_info(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    try:
        return {"status": "success", "data": point_dao.get_user_points_info(user['Id'])}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/user/points/logs")
def get_my_point_logs(request: Request, page: int = 1, page_size: int = 20):
    """获取用户积分明细（支持分页）"""
    user = request.session.get("req_user")
    if not user: return {"status": "error"}
    try:
        result = point_dao.list_user_point_logs(user['Id'], page=page, page_size=page_size)
        
        return {
            "status": "success",
            "data": result["logs"],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
            "total_pages": (result["total"] + page_size - 1) // page_size
        }
    except Exception as e:
        return {"status": "error"}

@router.post("/api/user/points/checkin")
def user_checkin(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    try:
        return point_dao.perform_user_checkin(user['Id'], user['Name'])
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

class RedeemModel(BaseModel): item_id: str

@router.post("/api/user/points/redeem")
def user_redeem(data: RedeemModel, request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error"}
    try:
        result = point_dao.redeem_store_item(user['Id'], user['Name'], data.item_id)
        if result.get("status") != "success":
            return result

        item_type = result.get("item_type")
        item_name = result.get("item_name")
        cost = result.get("cost", 0)
        new_exp_str = result.get("new_exp_str", "")
        actual_days = result.get("actual_days", 0)
        base_days = result.get("base_days", 0)
        random_bonus = result.get("random_bonus", 0)
        random_min = result.get("random_min", 0)
        random_max = result.get("random_max", 0)

        if item_type in ["renew", "random_renew"] and result.get("admin_disabled") != 1:
            try:
                u_res = media_api.get(f"/Users/{user['Id']}", timeout=5)
                if u_res.status_code == 200:
                    user_data = u_res.json()
                    policy = user_data.get('Policy', {})
                    policy['IsDisabled'] = False
                    media_api.post(f"/Users/{user['Id']}/Policy", json=policy, timeout=3)
            except Exception: pass

        try:
            msg = f"🎁 <b>积分商城兑换提醒</b>\n\n👤 <b>用户</b>: {user['Name']}\n🛒 <b>商品</b>: {item_name}\n💰 <b>花费</b>: {cost} 积分\n"
            if item_type == "renew":
                msg += f"⏳ <b>结果</b>: 账号已自动续期至 {new_exp_str}"
            elif item_type == "random_renew":
                bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
                msg += f"🎲 <b>随机结果</b>: 基础{base_days}天 {bonus_text} = {actual_days}天\n⏳ <b>新到期</b>: {new_exp_str}"
            else:
                msg += f"⚠️ <b>结果</b>: 此商品需人工发货，请尽快联系用户！"
            
            notification_service.send_message("sys_notify", msg, platform="all")
            add_system_notification("points", f"商城订单: {item_name}", f"用户 {user['Name']} 兑换了该商品", "/points")
        except Exception: pass

        if item_type == "manual":
            return {"status": "success", "message": f"兑换成功！已提醒管理员，请凭账号名主动联系服主领取奖励！"}
        
        # 随机延期返回详细结果（带盲盒类型）
        if item_type == "random_renew":
            bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
            
            # 🔥 判断盲盒结果类型（基于 random_bonus 相对于范围）
            range_span = random_max - random_min
            
            # 判断运气等级
            if random_bonus >= random_max - range_span * 0.1:  # 顶级（前10%）
                result_type = "jackpot"
                result_title = "天选之人！欧皇降临！"
            elif random_bonus >= random_max - range_span * 0.3:  # 幸运（前30%）
                result_type = "lucky"
                result_title = "运气不错！"
            elif random_bonus >= random_min + range_span * 0.3:  # 小赚（中间偏上）
                result_type = "good"
                result_title = "还算可以"
            elif random_bonus >= random_min:  # 保本（不低于最小）
                result_type = "normal"
                result_title = "中规中矩"
            elif random_bonus >= random_min - range_span * 0.2:  # 小亏
                result_type = "unlucky"
                result_title = "稍微有点亏"
            else:  # 大亏
                result_type = "bad"
                result_title = "运气不佳..."
            
            return {
                "status": "success", 
                "type": result_type,
                "title": result_title,
                "message": f"{item_name}\n\n🎲 随机结果：基础{base_days}天 {bonus_text} = {actual_days}天\n📅 新到期日：{new_exp_str}",
                "actual_days": actual_days, 
                "random_bonus": random_bonus, 
                "new_expire": new_exp_str
            }
        
        return {"status": "success", "message": f"兑换成功！{item_name}已生效。"}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 用户中心：续费码使用
# ==========================================
class RenewCodeModel(BaseModel): code: str

@router.post("/api/user/renew")
def user_use_renew_code(data: RenewCodeModel, request: Request):
    """用户中心使用续费码续期"""
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    uid = user['Id']
    uname = user['Name']
    code = data.code.strip()
    if not code: return {"status": "error", "message": "请输入续费码"}
    try:
        renew_result, renew_error = invitation_dao.renew_user_with_invitation_code(code, uname, uid)
        if renew_error == "invalid":
            return {"status": "error", "message": "续费码无效、已被使用、不是续费码或已达使用上限"}
        if renew_error == "permanent":
            return {"status": "error", "message": "您的账号为永久有效，无需续费！"}

        days = renew_result["days"]
        new_exp = renew_result["new_exp"]
        admin_disabled = renew_result.get("admin_disabled", 0)
        if days == -1 or days == 0 or days >= 36500:
            days_display = "永久"
        else:
            days_display = f"{days} 天"

        # 如果用户被禁用，且不是管理员手动禁用（admin_disabled != 1），则自动解除
        if admin_disabled != 1:
            try:
                # 检查用户当前是否被禁用
                u_res = media_api.get(f"/Users/{uid}", timeout=5)
                if u_res.status_code == 200:
                    user_data = u_res.json()
                    if user_data.get('Policy', {}).get('IsDisabled', False):
                        # 自动解除禁用
                        policy = user_data.get('Policy', {})
                        policy['IsDisabled'] = False
                        policy['LoginAttemptsBeforeLockout'] = -1
                        media_api.post(f"/Users/{uid}/Policy", json=policy, timeout=3)
                        return {"status": "success", "message": f"续期成功！账号有效期已延长 {days_display}，至 {new_exp}。账号已自动解除禁用。"}
            except Exception as e:
                print(f"[续费码] 解除禁用失败: {e}")

        return {"status": "success", "message": f"续期成功！账号有效期已延长 {days_display}，至 {new_exp}"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 🔥 积分转赠
# ==========================================
class TransferModel(BaseModel):
    to_user_id: str
    amount: int

@router.post("/api/user/points/transfer")
def user_transfer_points(data: TransferModel, request: Request):
    """积分转赠"""
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    try:
        target_exists = None
        to_user_name = "未知用户"
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            emby_user_names = {u['Id']: u['Name'] for u in emby_users}
            target_exists = any(u['Id'] == data.to_user_id for u in emby_users)
            to_user_name = emby_user_names.get(data.to_user_id, "未知用户")
        except Exception:
            pass

        return point_dao.transfer_points(
            user['Id'],
            user['Name'],
            data.to_user_id,
            to_user_name,
            data.amount,
            target_exists,
        )
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 🔥 积分红包
# ==========================================
class RedPacketModel(BaseModel):
    total_amount: int
    total_count: int
    chat_id: Optional[str] = None

@router.post("/api/points/red_packet/create")
def create_red_packet(data: RedPacketModel, request: Request):
    """创建积分红包"""
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    
    try:
        # 检查是否仅管理员可发
        config = point_dao.get_point_config()
        if int(config.get('red_packet_admin_only', 1)) == 1:
            # 检查是否是管理员 - 从 Emby API 获取用户信息
            try:
                user_info = media_api.get(f"/Users/{user['Id']}", timeout=5).json()
                is_admin = user_info.get('Policy', {}).get('IsAdministrator', False)
            except:
                is_admin = False
            if not is_admin:
                return {"status": "error", "message": "仅管理员可发红包"}

        return point_dao.create_red_packet(data.total_amount, data.total_count, data.chat_id, user['Id'], user['Name'])
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


class GrabRedPacketModel(BaseModel):
    packet_id: int

@router.post("/api/points/red_packet/grab")
def grab_red_packet(data: GrabRedPacketModel, request: Request):
    """抢红包"""
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    
    try:
        result = point_dao.grab_red_packet(data.packet_id, user['Id'], user['Name'])
        if result.get("status") != "success":
            return result

        if result.get("is_last_one"):
            # 构建抢完通知消息
            msg = f"🧧 <b>红包已抢完</b>\n\n"
            msg += f"👤 <b>发红包</b>: {result.get('creator_name')}\n"
            msg += f"💰 <b>总金额</b>: {result.get('total_amount')} 积分\n"
            msg += f"📦 <b>总个数</b>: {result.get('total_count')} 个\n\n"
            msg += f"📋 <b>领取明细</b>:\n"
            for i, log in enumerate(result.get("grab_logs", []), 1):
                msg += f"{i}. {log.get('user_name')}: {log.get('amount')} 积分\n"
            
            # 发送通知
            try:
                chat_id = result.get("chat_id")
                if chat_id:
                    notification_service.send_message(chat_id, msg, platform="telegram")
                else:
                    notification_service.send_message("sys_notify", msg, platform="all")
            except Exception as e:
                print(f"[红包] 发送抢完通知失败: {e}")

        return {
            "status": "success",
            "message": result["message"],
            "amount": result["amount"],
            "balance": result["balance"],
            "creator_name": result["creator_name"]
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/points/red_packet/logs")
def get_red_packet_logs(request: Request, packet_id: int):
    """获取红包领取记录"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    try:
        logs = point_dao.list_red_packet_logs(packet_id)
        return {"status": "success", "data": logs}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 🔥 积分排行榜
# ==========================================
@router.get("/api/points/rank")
def get_points_rank(request: Request, limit: int = 10):
    """获取积分排行榜"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    try:
        rows = point_dao.list_point_rank(limit)
        
        # 获取用户名
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            name_map = {u['Id']: u['Name'] for u in emby_users}
        except:
            name_map = {}
        
        rank_list = []
        for i, row in enumerate(rows, 1):
            rank_list.append({
                "rank": i,
                "user_id": row["user_id"],
                "user_name": name_map.get(row["user_id"], "未知用户"),
                "points": row["points"]
            })
        
        return {"status": "success", "data": rank_list}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 🔥 打劫功能
# ==========================================
class RobModel(BaseModel):
    to_user_id: str

@router.post("/api/user/points/rob")
def user_rob(data: RobModel, request: Request):
    """打劫功能"""
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "未登录"}
    try:
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            to_user_name = next((u['Name'] for u in emby_users if u['Id'] == data.to_user_id), None)
            if not to_user_name:
                return {"status": "error", "message": "目标用户不存在"}
        except Exception:
            return {"status": "error", "message": "无法验证目标用户"}

        return point_dao.rob_points(user['Id'], user['Name'], data.to_user_id, to_user_name)

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 🔥 用户PK功能
# ==========================================
class PKInviteModel(BaseModel):
    target_id: str
    points: int
    chat_id: Optional[str] = None

class PKAcceptModel(BaseModel):
    invite_id: int

class PKRejectModel(BaseModel):
    invite_id: int

@router.post("/api/user/points/pk/invite")
def pk_invite(data: PKInviteModel, request: Request):
    """发起PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 不能PK自己
        if data.target_id == user['Id']:
            return {"status": "error", "message": "不能PK自己"}

        # 获取目标用户名称
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            to_user_name = next((u['Name'] for u in emby_users if u['Id'] == data.target_id), None)
            if not to_user_name:
                return {"status": "error", "message": "目标用户不存在"}
        except:
            return {"status": "error", "message": "无法验证目标用户"}

        invite_result = point_dao.create_pk_invitation(
            user['Id'],
            user['Name'],
            user['Name'],
            data.target_id,
            to_user_name,
            "",
            data.points,
            data.chat_id,
            expired_cleanup="delete",
        )
        if invite_result.get("status") != "success":
            message = invite_result.get("message", "PK邀请失败")
            if invite_result.get("code") == "range":
                message = f"下注积分必须在 {invite_result.get('min_points')}-{invite_result.get('max_points')} 之间"
            elif invite_result.get("code") == "challenger_balance":
                message = f"积分不足，当前积分: {invite_result.get('current_points')}"
            return {"status": "error", "message": message}

        return {
            "status": "success",
            "message": f"已向 {to_user_name} 发起PK邀请，下注 {data.points} 积分",
            "invite_id": invite_result["invite_id"],
            "expires_at": invite_result["expires_at"],
            "timeout_minutes": invite_result["timeout_minutes"]
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/user/points/pk/accept")
def pk_accept(data: PKAcceptModel, request: Request):
    """接受PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        result = point_dao.accept_pk_invitation(data.invite_id, user["Id"])
        return result

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/user/points/pk/reject")
def pk_reject(data: PKRejectModel, request: Request):
    """拒绝PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        result = point_dao.reject_pending_pk_invitation(data.invite_id, user['Id'])
        if result.get("status") != "success":
            return result
        return {"status": "success", "message": f"已拒绝 {result['challenger_name']} 的PK邀请"}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/user/points/pk/pending")
def pk_pending(request: Request):
    """获取待处理的PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        return {"status": "success", "data": point_dao.list_pending_pk_invitations_for_target(user['Id'])}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/points/pk/clear")
def clear_pk_invitations(request: Request):
    """清除所有PK邀请"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        count = point_dao.clear_pk_invitations()
        return {"status": "success", "count": count, "message": f"已清除 {count} 条PK邀请"}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

router.include_router(game_router)
