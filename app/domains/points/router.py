import datetime
import random
import json
import os
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from app.core.config import templates
from app.infra.db.notification_dao import add_sys_notification
from app.domains.system import invitation_dao
from app.domains.users import public_service as user_service
from app.domains.points import point_dao
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
            add_sys_notification("points", f"商城订单: {item_name}", f"用户 {user['Name']} 兑换了该商品", "/points")
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


# ===================== 🎰 老虎机 API =====================

@router.get("/api/slot/usage")
def get_slot_usage(request: Request):
    """获取今日老虎机使用次数"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        return {"status": "success", "used_today": point_dao.count_today_point_logs(user['Id'], action='老虎机')}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/slot/spin")
def slot_spin(request: Request):
    """老虎机抽奖"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 获取配置
        config = point_dao.get_point_config()

        # 检查是否启用
        if config.get('enable_slot') != '1':
            return {"status": "error", "message": "老虎机功能未启用"}
        
        # 解析配置
        cost = int(config.get('slot_cost', 10))
        daily_free = int(config.get('slot_daily_free', 3))
        max_per_day = int(config.get('slot_max_per_day', 20))
        triple_mult = int(config.get('slot_triple_multiplier', 10))
        double_mult = int(config.get('slot_double_multiplier', 2))
        special_mult = int(config.get('slot_special_multiplier', 50))
        win_rate_modifier = float(config.get('slot_win_rate_modifier', 1.0))  # 中奖概率调节 (0-1)
        
        # 获取今日使用次数（使用 SQLite 本地时间函数）
        used_today = point_dao.count_today_point_logs(user['Id'], action='老虎机')
        
        # 检查每日次数限制
        if used_today >= max_per_day:
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}

        # 获取用户积分
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0

        # 🔥 修复：当 daily_free = 0 时，永远不免费
        # 当 daily_free > 0 时，前 daily_free 次免费
        is_free = False
        if daily_free > 0 and used_today < daily_free:
            is_free = True
        
        # 检查积分（非免费时需要足够积分）
        if not is_free and current_points < cost:
            return {"status": "error", "message": f"积分不足（需要 {cost} 积分）"}
        
        # 解析图案配置
        symbols_text = config.get('slot_symbols', '🍒|20|false\n🍋|20|false\n🍊|15|false\n🍇|15|false\n💎|10|false\n7️⃣|10|true\n⭐|5|true\n🎰|5|true')
        symbols = []
        for line in symbols_text.split('\n'):
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) >= 2:
                symbols.append({
                    'emoji': parts[0].strip(),
                    'weight': int(parts[1]) if parts[1].strip().isdigit() else 10,
                    'special': parts[2].strip().lower() == 'true' if len(parts) > 2 else False
                })
        
        if not symbols:
            symbols = [
                {'emoji': '🍒', 'weight': 20, 'special': False},
                {'emoji': '🍋', 'weight': 20, 'special': False},
                {'emoji': '🍊', 'weight': 15, 'special': False},
                {'emoji': '🍇', 'weight': 15, 'special': False},
                {'emoji': '💎', 'weight': 10, 'special': False},
                {'emoji': '7️⃣', 'weight': 10, 'special': True},
                {'emoji': '⭐', 'weight': 5, 'special': True},
                {'emoji': '🎰', 'weight': 5, 'special': True}
            ]
        
        # 随机选择三个图案（按权重）
        import random
        
        # 🔥 中奖概率调节：通过增加"不匹配"的概率来降低中奖率
        # win_rate_modifier = 1.0 时，正常随机
        # win_rate_modifier < 1.0 时，后两个图案有更高概率选择不同的图案
        def get_random_symbol():
            total_weight = sum(s['weight'] for s in symbols)
            r = random.uniform(0, total_weight)
            for s in symbols:
                r -= s['weight']
                if r <= 0:
                    return s
            return symbols[0]
        
        def get_different_symbol(exclude_emoji):
            """选择一个与 exclude_emoji 不同的图案"""
            different_symbols = [s for s in symbols if s['emoji'] != exclude_emoji]
            if not different_symbols:
                return get_random_symbol()
            total_weight = sum(s['weight'] for s in different_symbols)
            r = random.uniform(0, total_weight)
            for s in different_symbols:
                r -= s['weight']
                if r <= 0:
                    return s
            return different_symbols[0]
        
        # 第一个图案正常随机
        first = get_random_symbol()
        
        # 第二、三个图案根据 win_rate_modifier 决定是否尝试不匹配
        if win_rate_modifier < 1.0 and random.random() > win_rate_modifier:
            # 尝试选择不同的图案
            second = get_different_symbol(first['emoji'])
        else:
            second = get_random_symbol()
        
        if win_rate_modifier < 1.0 and random.random() > win_rate_modifier:
            # 尝试选择与前两个都不同的图案
            exclude_emojis = [first['emoji'], second['emoji']]
            different_symbols = [s for s in symbols if s['emoji'] not in exclude_emojis]
            if different_symbols:
                total_weight = sum(s['weight'] for s in different_symbols)
                r = random.uniform(0, total_weight)
                for s in different_symbols:
                    r -= s['weight']
                    if r <= 0:
                        third = s
                        break
                else:
                    third = different_symbols[0]
            else:
                third = get_random_symbol()
        else:
            third = get_random_symbol()
        
        result = [first, second, third]
        result_emojis = [r['emoji'] for r in result]
        
        # 计算奖励
        reward = 0
        win = False
        message = "再接再厉！"
        
        # 🔥 基准积分用于奖励计算（始终使用配置的 cost 作为基准）
        base_cost = cost
        
        # 检查是否三同
        if result[0]['emoji'] == result[1]['emoji'] == result[2]['emoji']:
            win = True
            multiplier = special_mult if result[0]['special'] else triple_mult
            reward = base_cost * multiplier
            message = f"🎉 三同大奖！{result[0]['emoji']} x3 获得 {reward} 积分！"
        # 检查是否两同
        elif result[0]['emoji'] == result[1]['emoji'] or result[1]['emoji'] == result[2]['emoji'] or result[0]['emoji'] == result[2]['emoji']:
            win = True
            # 找出相同的图案
            if result[0]['emoji'] == result[1]['emoji']:
                matched = result[0]
            elif result[1]['emoji'] == result[2]['emoji']:
                matched = result[1]
            else:
                matched = result[0]
            
            multiplier = special_mult if matched['special'] else double_mult
            reward = base_cost * multiplier
            message = f"✨ 两同小奖！{matched['emoji']} x2 获得 {reward} 积分！"
        else:
            message = f"未中奖，{result_emojis[0]} {result_emojis[1]} {result_emojis[2]}"
        
        # 扣除积分（如果不是免费）
        if not is_free:
            current_points -= cost
        
        # 增加积分（如果中奖）
        if win:
            current_points += reward
        
        # 记录日志
        action_desc = f"老虎机抽奖: {result_emojis[0]} {result_emojis[1]} {result_emojis[2]}"
        if win:
            action_desc += f" 获得 {reward} 积分"
        else:
            action_desc += " 未中奖"
        
        balance_change = reward - (0 if is_free else cost)
        log_amount = reward if win else (-cost if not is_free else 0)
        point_result = point_dao.apply_game_point_change(
            user['Id'],
            user['Name'],
            '老虎机',
            balance_change,
            log_amount=log_amount,
        )
        if point_result.get("status") != "success":
            return {"status": "error", "message": point_result.get("message", "积分更新失败")}
        current_points = point_result["points"]
        
        return {
            "status": "success",
            "result": result_emojis,
            "win": win,
            "reward": reward,
            "message": message,
            "new_points": current_points,
            "used_today": used_today + 1
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ===================== 🎫 刮刮乐 API =====================

# 存储当前用户的刮刮卡状态（简单实现，生产环境应该用 Redis 或数据库）
scratch_cards = {}

@router.post("/api/scratch/buy")
def buy_scratch_card(request: Request):
    """购买刮刮卡"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        config = point_dao.get_point_config()
        
        # 检查是否启用
        if config.get('enable_web_scratch') != '1':
            return {"status": "error", "message": "刮刮乐功能未启用"}
        
        # 解析配置
        cost = int(config.get('web_scratch_cost', 10))
        win_numbers_count = int(config.get('web_scratch_win_numbers', 3))
        grid_count = int(config.get('web_scratch_grid_count', 12))
        min_reward = int(config.get('web_scratch_min_reward', 5))
        max_reward = int(config.get('web_scratch_max_reward', 100))
        match_rate = float(config.get('web_scratch_match_rate', 20))
        max_per_day = int(config.get('web_scratch_max_per_day', 20))  # 🔥 每日次数限制
        
        # 🔥 检查今日使用次数（使用 SQLite 本地时间函数）
        used_today = point_dao.count_today_point_logs(user['Id'], action_like='刮刮乐%')
        
        if used_today >= max_per_day:
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}
        
        # 获取用户积分
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0
        
        # 检查积分
        if current_points < cost:
            return {"status": "error", "message": f"积分不足（需要 {cost} 积分）"}
        
        buy_result = point_dao.buy_scratch_card(user['Id'], user['Name'], cost)
        if buy_result.get("status") != "success":
            return {"status": "error", "message": buy_result.get("message", "积分更新失败")}
        current_points = buy_result["new_points"]
        
        # 生成中奖数字（随机 3 个不重复的数字 1-50）
        import random
        win_numbers = random.sample(range(1, 51), win_numbers_count)
        
        # 生成格子（每个格子有数字和积分，数字可重复）
        grid = []
        for i in range(grid_count):
            # 根据匹配概率决定这个格子是否匹配中奖数字
            if random.uniform(0, 100) < match_rate:
                # 匹配：从中奖数字中随机选一个
                num = random.choice(win_numbers)
                is_match = True
            else:
                # 不匹配：生成一个不在中奖数字中的数字
                available_nums = [n for n in range(1, 51) if n not in win_numbers]
                num = random.choice(available_nums) if available_nums else random.randint(1, 50)
                is_match = False
            
            # 每个格子都有积分值
            cell_reward = random.randint(min_reward, max_reward)
            
            grid.append({
                'number': num,
                'reward': cell_reward,      # 格子显示的积分
                'matched': is_match,         # 是否匹配中奖数字
                'revealed': False
            })
        
        # 存储刮刮卡状态
        scratch_cards[user['Id']] = {
            'win_numbers': win_numbers,
            'grid': grid,
            'created_at': datetime.datetime.now().isoformat()
        }
        
        # 调试：确保每个格子都有 reward
        for i, cell in enumerate(grid):
            if cell.get('reward', 0) == 0:
                grid[i]['reward'] = random.randint(min_reward, max_reward)
        
        return {
            "status": "success",
            "win_numbers": win_numbers,
            "grid": grid,
            "new_points": current_points
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/scratch/reveal")
async def reveal_scratch_cell(request: Request):
    """刮开格子"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        data = await request.json()
        cell_index = data.get('cell_index', 0)
        
        # 获取刮刮卡
        card = scratch_cards.get(user['Id'])
        if not card:
            return {"status": "error", "message": "请先购买刮刮卡"}
        
        if cell_index < 0 or cell_index >= len(card['grid']):
            return {"status": "error", "message": "无效的格子"}

        cell = card['grid'][cell_index]

        # 已刮开的格子不能重复领奖
        if cell.get('revealed'):
            return {"status": "error", "message": "该格子已刮开"}

        # 如果匹配，发放奖励
        if cell['matched'] and cell['reward'] > 0:
            reward_result = point_dao.reveal_scratch_reward(user['Id'], user['Name'], cell['reward'])
            if reward_result.get("status") != "success":
                return {"status": "error", "message": reward_result.get("message", "积分更新失败")}
            current_points = reward_result["new_points"]

            cell['revealed'] = True

            return {
                "status": "success",
                "number": cell['number'],
                "reward": cell['reward'],
                "matched": True,
                "new_points": current_points
            }
        else:
            cell['revealed'] = True

            # 未匹配也返回格子的积分值（只是不能获得）
            return {
                "status": "success",
                "number": cell['number'],
                "reward": cell['reward'],
                "matched": False,
                "new_points": None
            }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 🎡 幸运转盘
wheel_usage = {}  # 用户使用次数缓存

@router.get("/api/wheel/usage")
async def get_wheel_usage(request: Request):
    """获取转盘今日使用次数"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    # 获取配置
    config = point_dao.get_point_config()
    max_per_day = int(config.get('wheel_max_per_day', 20))
    
    count = point_dao.count_today_point_logs(user['Id'], action='幸运转盘')
    
    return {
        "status": "success",
        "used_today": count,
        "max_per_day": max_per_day
    }

@router.post("/api/wheel/spin")
async def spin_wheel(request: Request):
    """转动转盘"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 获取配置
        config = point_dao.get_point_config()
        enabled = config.get('enable_wheel', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "转盘功能未启用"}
        
        cost = int(config.get('wheel_cost', 10))
        daily_free = int(config.get('wheel_daily_free', 3))
        max_per_day = int(config.get('wheel_max_per_day', 20))
        
        # 加载扇区配置
        sectors = []
        for i in range(1, 7):
            reward = int(config.get(f'wheel_reward_{i}', [50, 30, 20, 10, 5, 0][i-1]))
            weight = int(config.get(f'wheel_weight_{i}', [5, 10, 15, 20, 25, 25][i-1]))
            sectors.append({'reward': reward, 'weight': weight})
        
        used_today = point_dao.count_today_point_logs(user['Id'], action='幸运转盘')
        
        # 检查次数限制
        if used_today >= max_per_day:
            return {"status": "error", "message": "今日次数已用完"}
        
        # 获取当前积分
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0
        
        # 🔥 修复：当 daily_free = 0 时，永远不免费
        is_free = False
        if daily_free > 0 and used_today < daily_free:
            is_free = True
        
        # 扣除积分
        if not is_free:
            if current_points < cost:
                return {"status": "error", "message": "积分不足"}
            current_points -= cost


        # 根据权重随机选择扇区
        total_weight = sum(s['weight'] for s in sectors)
        rand_val = random.uniform(0, total_weight)
        cumulative = 0
        selected_sector = sectors[0]
        sector_index = 0
        for i, sector in enumerate(sectors):
            cumulative += sector['weight']
            if rand_val <= cumulative:
                selected_sector = sector
                sector_index = i
                break
        
        # 发放奖励
        reward = selected_sector['reward']
        if reward > 0:
            current_points += reward
        
        # 记录日志
        used_today += 1
        point_result = point_dao.apply_game_point_change(user['Id'], user['Name'], '幸运转盘', reward - (0 if is_free else cost))
        if point_result.get("status") != "success":
            return {"status": "error", "message": point_result.get("message", "积分更新失败")}
        current_points = point_result["points"]
        
        # 返回结果
        message = f"🎉 恭喜获得 {reward} 积分！" if reward > 0 else "😢 谢谢参与，再接再厉！"
        
        # 计算旋转角度：让目标扇区中心对准顶部指针
        # 扇区0在顶部，扇区1在右上，扇区2在右下，扇区3在底部，扇区4在左下，扇区5在左上
        # 要让扇区N对准顶部，需要逆时针旋转 N*60 度
        rotation_angle = sector_index * 60
        
        return {
            "status": "success",
            "reward": reward,
            "sector_index": sector_index,
            "rotation_angle": rotation_angle,  # 直接返回旋转角度
            "sectors": sectors,
            "message": message,
            "new_points": current_points,
            "used_today": used_today,
            "is_free": is_free
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 🎲 猜数字
guess_games = {}  # 用户游戏状态缓存

@router.post("/api/guess/start")
async def start_guess_game(request: Request):
    """开始猜数字游戏"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 获取配置
        config = point_dao.get_point_config()
        enabled = config.get('enable_guess', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "猜数字功能未启用"}
        
        cost = int(config.get('guess_cost', 5))
        range_str = config.get('guess_range', '1-100')
        range_parts = range_str.split('-')
        min_num = int(range_parts[0]) if len(range_parts) > 0 else 1
        max_num = int(range_parts[1]) if len(range_parts) > 1 else 100
        max_per_day = int(config.get('guess_max_per_day', 20))  # 🔥 每日次数限制
        
        used_today = point_dao.count_today_point_logs(user['Id'], action_like='猜数字%')
        
        if used_today >= max_per_day:
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}
        
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0

        # 扣除积分
        if current_points < cost:
            return {"status": "error", "message": "积分不足"}

        start_result = point_dao.apply_game_point_change(user['Id'], user['Name'], '猜数字-开始', -cost, require_min_points=cost)
        if start_result.get("status") != "success":
            return {"status": "error", "message": start_result.get("message", "积分更新失败")}
        current_points = start_result["points"]
        
        # 生成目标数字
        target_number = random.randint(min_num, max_num)
        
        # 存储游戏状态
        guess_games[user['Id']] = {
            'target_number': target_number,
            'tries_left': int(config.get('guess_max_tries', 7)),
            'history': [],
            'created_at': datetime.datetime.now().isoformat()
        }
        
        return {
            "status": "success",
            "new_points": current_points
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/guess/submit")
async def submit_guess(request: Request):
    """提交猜测"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        data = await request.json()
        guess = int(data.get('guess', 0))
        
        # 获取游戏状态
        game = guess_games.get(user['Id'])
        if not game:
            return {"status": "error", "message": "请先开始游戏"}
        
        # 获取配置
        config = point_dao.get_point_config()
        base_reward = int(config.get('guess_base_reward', 50))
        multipliers = [
            float(config.get('guess_multiplier_1', 5)),
            float(config.get('guess_multiplier_2', 3)),
            float(config.get('guess_multiplier_3', 2)),
            1.5, 1.2, 1, 0.8
        ]
        
        # 更新游戏状态
        game['history'].append(guess)
        game['tries_left'] -= 1
        tries_used = len(game['history'])
        
        # 判断结果
        if guess == game['target_number']:
            # 猜对了
            multiplier = multipliers[min(tries_used - 1, len(multipliers) - 1)]
            reward = int(base_reward * multiplier)
            
            # 发放奖励
            reward_result = point_dao.apply_game_point_change(user['Id'], user['Name'], '猜数字-猜中', reward)
            if reward_result.get("status") != "success":
                return {"status": "error", "message": reward_result.get("message", "积分更新失败")}
            current_points = reward_result["points"]
            
            # 清理游戏状态
            del guess_games[user['Id']]
            
            return {
                "status": "success",
                "won": True,
                "reward": reward,
                "new_points": current_points,
                "tries_left": game['tries_left']
            }
        
        elif game['tries_left'] <= 0:
            # 次数用完，游戏结束
            current_pts = point_dao.get_user_points_balance(user['Id'])
            point_dao.insert_point_log(user['Id'], user['Name'], '猜数字-失败', 0, current_pts)
            
            answer = game['target_number']
            del guess_games[user['Id']]
            
            return {
                "status": "success",
                "game_over": True,
                "answer": answer,
                "tries_left": 0
            }
        
        else:
            # 继续游戏，给出提示
            hint = "大了！往小猜" if guess > game['target_number'] else "小了！往大猜"
            return {
                "status": "success",
                "won": False,
                "game_over": False,
                "hint": hint,
                "tries_left": game['tries_left']
            }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 🎟️ 彩票
@router.get("/api/lottery/my_tickets")
async def get_my_lottery_tickets(request: Request):
    """获取我的彩票号"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        return {
            "status": "success",
            "tickets": point_dao.list_lottery_ticket_numbers(user['Id'], today)
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/lottery/buy")
async def buy_lottery(request: Request):
    """购买彩票"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        data = await request.json()
        count = int(data.get('count', 1))
        if count < 1:
            return {"status": "error", "message": "购买数量无效"}
        custom_number = data.get('custom_number')  # 自选号码
        
        # 获取配置
        config = point_dao.get_point_config()
        enabled = config.get('enable_lottery', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "彩票功能未启用"}
        
        cost = int(config.get('lottery_cost', 100))
        max_per_day = int(config.get('lottery_max_per_day', 10))
        
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        # 生成彩票号
        import random
        tickets = []
        ticket_count = count
        
        # 如果有自选号码，第一张用自选号码
        if custom_number and len(custom_number) == 4 and custom_number.isdigit():
            tickets.append(custom_number)
            count -= 1
        
        # 剩余的随机生成
        for _ in range(count):
            ticket_number = str(random.randint(0, 9999)).zfill(4)
            tickets.append(ticket_number)

        result = point_dao.buy_lottery_tickets(user['Id'], user['Name'], ticket_count, cost, max_per_day, today, tickets)
        if result.get("status") != "success":
            return result
        
        return {
            "status": "success",
            "tickets": tickets,
            "today_tickets": result["today_tickets"],
            "new_points": result["new_points"]
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/lottery/pool")
async def api_user_lottery_pool(request: Request):
    """用户社区获取奖池信息"""
    try:
        user = request.session.get("req_user")
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        # 获取配置
        config = point_dao.get_point_config()
        draw_hour = int(config.get('lottery_draw_hour', 20))
        max_per_day = int(config.get('lottery_max_per_day', 10))
        
        # 检查今天是否已开奖
        today_drawn_row = point_dao.get_lottery_winning_numbers(today)
        
        if today_drawn_row and today_drawn_row["winning_numbers"]:
            # 今天已开奖，显示明天的奖池
            target_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            next_draw_time = f"明天 {(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%m-%d')} {draw_hour}:00"
        else:
            target_date = today
            next_draw_time = f"今天 {datetime.datetime.now().strftime('%m-%d')} {draw_hour}:00"

        pool_info = point_dao.get_lottery_pool_info(user['Id'] if user else None, today, target_date)
        
        return {
            "status": "success",
            "data": {
                "today_pool": pool_info["today_pool"],
                "today_tickets": pool_info["today_tickets"],
                "user_today_tickets": pool_info["user_today_tickets"],
                "target_date": target_date,
                "next_draw_time": next_draw_time,
                "today_winning_number": pool_info["today_winning_number"],
                "my_winning_tickets": pool_info["my_winning_tickets"],
                "my_prize_total": pool_info["my_prize_total"],
                "is_drawn": pool_info["today_drawn"],
                "max_per_day": max_per_day
            }
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/lottery/results")
async def get_lottery_results(request: Request):
    """获取开奖结果"""
    try:
        user = request.session.get("req_user")
        user_id = user['Id'] if user else None
        return {
            "status": "success",
            "results": point_dao.list_lottery_results(user_id)
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
