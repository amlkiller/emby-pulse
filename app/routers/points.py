import sqlite3
import datetime
import random
import json
import os
import requests
from fastapi import APIRouter, Request, Depends, HTTPException
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from app.core.config import cfg, templates
from app.core.database import SYSTEM_DB_PATH, add_sys_notification
from app.dao import invitation_dao
from app.dao import point_dao
from app.core.media_adapter import media_api
from app.services.bot_service import bot

from app.routers.auth import check_permission

from app.routers.views import get_common_vars

router = APIRouter()
from app.main import APP_VERSION
from app.core.security_utils import safe_error_message

get_point_config = point_dao.get_point_config

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
    if not check_permission(request, "points"):
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
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    point_dao.save_point_config_values(data.get('configs', {}))
    return {"status": "success", "message": "全局配置已保存"}

@router.get("/api/points/users")
def get_users_points(request: Request, page: int = 1, page_size: int = 20):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
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
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
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
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
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
        conn = sqlite3.connect(SYSTEM_DB_PATH); c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        try: store_items = json.loads(config.get('store_items', '[]'))
        except: store_items = []

        target_item = next((x for x in store_items if x.get("id") == data.item_id), None)
        if not target_item: conn.rollback(); conn.close(); return {"status": "error", "message": "商品不存在或已下架"}

        # 检查购买数量限制
        max_buys = int(target_item.get('max_buys', 0))  # 0 表示无限制
        if max_buys > 0:
            buy_count_row = c.execute(
                "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action LIKE ?",
                (user['Id'], f'商城兑换: {target_item.get("name")}%')
            ).fetchone()
            buy_count = buy_count_row[0] if buy_count_row else 0
            if buy_count >= max_buys:
                conn.rollback(); conn.close()
                return {"status": "error", "message": f"该商品限购 {max_buys} 次，您已购买 {buy_count} 次"}

        cost = int(target_item.get('cost', 0))
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_points = row[0] if row else 0

        if current_points < cost: conn.rollback(); conn.close(); return {"status": "error", "message": f"余额不足！需要 {cost} 积分。"}

        exp_row = c.execute("SELECT expire_date FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_exp = exp_row[0] if exp_row else None
        
        # 检查永久用户不能购买续期类商品
        is_permanent = not current_exp or current_exp == "" or "2099" in current_exp or "3000" in current_exp or "永久" in current_exp
        if target_item.get("type") in ["renew", "random_renew"] and is_permanent:
            conn.rollback(); conn.close(); return {"status": "error", "message": "您的账号当前为【永久有效】，无需兑换续期！"}

        new_points = current_points - cost
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user['Id']))

        new_exp_str = ""
        if target_item.get("type") == "renew":
            days = int(target_item.get("val", 30))
            today = datetime.date.today()
            try:
                exp_date = datetime.datetime.strptime(current_exp, "%Y-%m-%d").date()
                if exp_date < today: exp_date = today
            except: exp_date = today

            new_exp_date = exp_date + datetime.timedelta(days=days)
            new_exp_str = new_exp_date.strftime("%Y-%m-%d")
            c.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp_str, user['Id']))
            action_desc = f"商城兑换: {target_item.get('name')} (至 {new_exp_str})"
            
            # 检查是否需要自动解除禁用（仅当 admin_disabled != 1 时才解除）
            admin_disabled_row = c.execute("SELECT admin_disabled FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
            admin_disabled = admin_disabled_row[0] if admin_disabled_row else 0
            if admin_disabled != 1:
                try:
                    # 获取当前 Policy，只修改 IsDisabled 字段
                    u_res = requests.get(f"{cfg.get('emby_host')}/emby/Users/{user['Id']}?api_key={cfg.get('emby_api_key')}", timeout=5)
                    if u_res.status_code == 200:
                        user_data = u_res.json()
                        policy = user_data.get('Policy', {})
                        policy['IsDisabled'] = False
                        requests.post(f"{cfg.get('emby_host')}/emby/Users/{user['Id']}/Policy?api_key={cfg.get('emby_api_key')}", json=policy, timeout=3)
                except Exception: pass
        
        elif target_item.get("type") == "random_renew":
            # 🎲 随机定价延期模式
            base_days = int(target_item.get("base_days", 30))
            random_min = int(target_item.get("random_min", -10))
            random_max = int(target_item.get("random_max", 60))
            
            # 计算随机天数（简化的概率调节）
            luck_mode = target_item.get("luck_mode", "normal")
            luck_value = int(target_item.get("luck_value", 50))  # 0-100
            
            if luck_mode == "lucky":
                # 幸运模式：值越高越容易抽中高天数（多次随机取最大）
                import random as rand_module
                times = max(1, int(luck_value / 25))  # 0-100 映射到 1-4 次
                random_bonus = max(rand_module.randint(random_min, random_max) for _ in range(times))
            elif luck_mode == "unlucky":
                # 挑战模式：值越高越容易抽中低天数（多次随机取最小）
                import random as rand_module
                times = max(1, int(luck_value / 25))  # 0-100 映射到 1-4 次
                random_bonus = min(rand_module.randint(random_min, random_max) for _ in range(times))
            else:
                # 均匀随机
                random_bonus = random.randint(random_min, random_max)
            
            actual_days = base_days + random_bonus
            actual_days = max(1, actual_days)  # 确保至少1天
            
            today = datetime.date.today()
            try:
                exp_date = datetime.datetime.strptime(current_exp, "%Y-%m-%d").date()
                if exp_date < today: exp_date = today
            except: exp_date = today

            new_exp_date = exp_date + datetime.timedelta(days=actual_days)
            new_exp_str = new_exp_date.strftime("%Y-%m-%d")
            c.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp_str, user['Id']))
            
            # 构建描述（包含随机结果）
            bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
            action_desc = f"🎲商城兑换: {target_item.get('name')} (基础{base_days}天{bonus_text}={actual_days}天，至{new_exp_str})"
            
            # 检查是否需要自动解除禁用
            admin_disabled_row = c.execute("SELECT admin_disabled FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
            admin_disabled = admin_disabled_row[0] if admin_disabled_row else 0
            if admin_disabled != 1:
                try:
                    # 获取当前 Policy，只修改 IsDisabled 字段
                    u_res = requests.get(f"{cfg.get('emby_host')}/emby/Users/{user['Id']}?api_key={cfg.get('emby_api_key')}", timeout=5)
                    if u_res.status_code == 200:
                        user_data = u_res.json()
                        policy = user_data.get('Policy', {})
                        policy['IsDisabled'] = False
                        requests.post(f"{cfg.get('emby_host')}/emby/Users/{user['Id']}/Policy?api_key={cfg.get('emby_api_key')}", json=policy, timeout=3)
                except Exception: pass
        else: 
            action_desc = f"商城兑换: {target_item.get('name')}"

        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)", (user['Id'], user['Name'], action_desc, -cost, new_points))
        conn.commit(); conn.close()

        try:
            msg = f"🎁 <b>积分商城兑换提醒</b>\n\n👤 <b>用户</b>: {user['Name']}\n🛒 <b>商品</b>: {target_item.get('name')}\n💰 <b>花费</b>: {cost} 积分\n"
            if target_item.get("type") == "renew":
                msg += f"⏳ <b>结果</b>: 账号已自动续期至 {new_exp_str}"
            elif target_item.get("type") == "random_renew":
                base_days = int(target_item.get("base_days", 30))
                random_min = int(target_item.get("random_min", -10))
                random_max = int(target_item.get("random_max", 60))
                random_bonus = actual_days - base_days
                bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
                msg += f"🎲 <b>随机结果</b>: 基础{base_days}天 {bonus_text} = {actual_days}天\n⏳ <b>新到期</b>: {new_exp_str}"
            else:
                msg += f"⚠️ <b>结果</b>: 此商品需人工发货，请尽快联系用户！"
            
            bot.send_message("sys_notify", msg, platform="all")
            add_sys_notification("points", f"商城订单: {target_item.get('name')}", f"用户 {user['Name']} 兑换了该商品", "/points")
        except Exception: pass

        if target_item.get("type") == "manual":
            return {"status": "success", "message": f"兑换成功！已提醒管理员，请凭账号名主动联系服主领取奖励！"}
        
        # 随机延期返回详细结果（带盲盒类型）
        if target_item.get("type") == "random_renew":
            base_days = int(target_item.get("base_days", 30))
            random_bonus = actual_days - base_days
            bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
            result_emoji = "🎉" if random_bonus > 0 else ("😅" if random_bonus == 0 else "😢")
            
            # 🔥 判断盲盒结果类型（基于 random_bonus 相对于范围）
            random_min = int(target_item.get("random_min", -10))
            random_max = int(target_item.get("random_max", 60))
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
                "message": f"{target_item.get('name')}\n\n🎲 随机结果：基础{base_days}天 {bonus_text} = {actual_days}天\n📅 新到期日：{new_exp_str}", 
                "actual_days": actual_days, 
                "random_bonus": random_bonus, 
                "new_expire": new_exp_str
            }
        
        return {"status": "success", "message": f"兑换成功！{target_item.get('name')}已生效。"}

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


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
                u_res = requests.get(f"{cfg.get('emby_host')}/emby/Users/{uid}?api_key={cfg.get('emby_api_key')}", timeout=5)
                if u_res.status_code == 200:
                    user_data = u_res.json()
                    if user_data.get('Policy', {}).get('IsDisabled', False):
                        # 自动解除禁用
                        policy = user_data.get('Policy', {})
                        policy['IsDisabled'] = False
                        policy['LoginAttemptsBeforeLockout'] = -1
                        requests.post(f"{cfg.get('emby_host')}/emby/Users/{uid}/Policy?api_key={cfg.get('emby_api_key')}", json=policy, timeout=3)
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
        conn = sqlite3.connect(SYSTEM_DB_PATH); c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}

        # 检查是否启用转赠
        if int(config.get('enable_transfer', 0)) == 0:
            conn.rollback(); conn.close(); return {"status": "error", "message": "积分转赠功能未开启"}

        # 检查转赠金额范围
        min_amount = int(config.get('transfer_min', 10))
        max_amount = int(config.get('transfer_max', 1000))
        if data.amount < min_amount or data.amount > max_amount:
            conn.rollback(); conn.close(); return {"status": "error", "message": f"转赠金额需在 {min_amount}-{max_amount} 之间"}

        # 不能转给自己
        if data.to_user_id == user['Id']:
            conn.rollback(); conn.close(); return {"status": "error", "message": "不能转赠给自己"}
        
        # 获取目标用户信息
        to_user_row = c.execute("SELECT user_id FROM users_meta WHERE user_id = ?", (data.to_user_id,)).fetchone()
        if not to_user_row:
            # 检查 Emby 用户是否存在
            try:
                emby_users = media_api.get("/Users", timeout=5).json()
                if not any(u['Id'] == data.to_user_id for u in emby_users):
                    conn.rollback(); conn.close(); return {"status": "error", "message": "目标用户不存在"}
            except:
                conn.rollback(); conn.close(); return {"status": "error", "message": "无法验证目标用户"}
        
        # 获取发送者积分
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        from_points = row[0] if row else 0
        
        if from_points < data.amount:
            conn.rollback(); conn.close(); return {"status": "error", "message": f"积分不足！当前积分: {from_points}"}
        
        # 计算手续费
        fee_rate = int(config.get('transfer_fee_rate', 10))
        fee = int(data.amount * fee_rate / 100)
        actual_amount = data.amount - fee
        
        # 获取目标用户积分
        to_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (data.to_user_id,)).fetchone()
        to_points = (to_row[0] or 0) + actual_amount if to_row else actual_amount
        
        # 更新积分
        new_from_points = from_points - data.amount
        if to_row:
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (to_points, data.to_user_id))
        else:
            c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (data.to_user_id, to_points))
        
        if row:
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, user['Id']))
        else:
            c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user['Id'], new_from_points))
        
        # 获取目标用户名
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            to_user_name = next((u['Name'] for u in emby_users if u['Id'] == data.to_user_id), "未知用户")
        except:
            to_user_name = "未知用户"
        
        # 记录日志
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (user['Id'], user['Name'], f"转赠给 {to_user_name} (手续费{fee})", -data.amount, new_from_points))
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (data.to_user_id, to_user_name, f"收到 {user['Name']} 转赠", actual_amount, to_points))
        c.execute("INSERT INTO point_transfer_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, fee) VALUES (?, ?, ?, ?, ?, ?)",
                 (user['Id'], user['Name'], data.to_user_id, to_user_name, data.amount, fee))
        
        conn.commit(); conn.close()
        
        return {
            "status": "success",
            "message": f"转赠成功！已转赠 {actual_amount} 积分给 {to_user_name}（手续费 {fee}）",
            "actual_amount": actual_amount,
            "fee": fee,
            "balance": new_from_points
        }
    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


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
                    bot.send_message(chat_id, msg, platform="telegram")
                else:
                    bot.send_message("sys_notify", msg, platform="all")
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
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
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
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
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
        conn = sqlite3.connect(SYSTEM_DB_PATH); c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}

        # 检查是否启用打劫
        if int(config.get('enable_rob', 0)) == 0:
            conn.rollback(); conn.close(); return {"status": "error", "message": "打劫功能未开启"}

        # 不能打劫自己
        if data.to_user_id == user['Id']:
            conn.rollback(); conn.close(); return {"status": "error", "message": "不能打劫自己"}
        
        # 获取配置
        success_rate = int(config.get('rob_success_rate', 50))
        rob_min = int(config.get('rob_min', 1))
        rob_max = int(config.get('rob_max', 10))
        counter_rate = int(config.get('rob_counter_rate', 30))
        counter_min = int(config.get('rob_counter_min', 1))
        counter_max = int(config.get('rob_counter_max', 5))
        protect_threshold = int(config.get('rob_protect_threshold', 50))
        max_per_day = int(config.get('rob_max_per_day', 5))
        max_be_robbed = int(config.get('rob_max_be_robbed', 3))
        cooldown_hours = int(config.get('rob_cooldown_hours', 2))
        
        # 获取攻击者积分
        from_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        from_points = from_row[0] if from_row else 0
        
        # 获取目标用户积分
        to_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (data.to_user_id,)).fetchone()
        to_points = to_row[0] if to_row else 0
        
        # 🔥 检查攻击者积分是否低于保护阈值
        if from_points < protect_threshold:
            conn.rollback(); conn.close(); return {"status": "error", "message": f"你的积分低于 {protect_threshold}，无法打劫他人"}

        # 检查目标用户是否存在
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            to_user_name = next((u['Name'] for u in emby_users if u['Id'] == data.to_user_id), None)
            if not to_user_name:
                conn.rollback(); conn.close(); return {"status": "error", "message": "目标用户不存在"}
        except:
            conn.rollback(); conn.close(); return {"status": "error", "message": "无法验证目标用户"}

        # 检查目标用户积分是否低于保护阈值
        if to_points < protect_threshold:
            conn.rollback(); conn.close(); return {"status": "error", "message": f"对方积分低于 {protect_threshold}，处于保护状态"}
        
        # 检查攻击者今日打劫次数
        today_rob_count = c.execute(
            "SELECT COUNT(*) FROM point_rob_logs WHERE from_user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()[0]
        if today_rob_count >= max_per_day:
            conn.rollback(); conn.close(); return {"status": "error", "message": f"今日打劫次数已达上限（{max_per_day}次）"}

        # 检查目标用户今日被被打劫次数
        today_be_robbed_count = c.execute(
            "SELECT COUNT(*) FROM point_rob_logs WHERE to_user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (data.to_user_id,)
        ).fetchone()[0]
        if today_be_robbed_count >= max_be_robbed:
            conn.rollback(); conn.close(); return {"status": "error", "message": f"对方今日已被打劫 {max_be_robbed} 次，休息一下吧"}

        # 检查冷却时间
        last_rob = c.execute(
            "SELECT created_at FROM point_rob_logs WHERE from_user_id = ? AND to_user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user['Id'], data.to_user_id)
        ).fetchone()
        if last_rob:
            from datetime import datetime, timedelta
            try:
                last_time = datetime.fromisoformat(last_rob[0].replace('Z', '+00:00'))
                cooldown_end = last_time + timedelta(hours=cooldown_hours)
                if datetime.now(last_time.tzinfo) < cooldown_end:
                    remaining = int((cooldown_end - datetime.now(last_time.tzinfo)).total_seconds() / 60)
                    conn.rollback(); conn.close(); return {"status": "error", "message": f"冷却中，还需等待 {remaining} 分钟"}
            except:
                pass
        
        # 随机打劫金额
        rob_amount = random.randint(rob_min, rob_max)
        
        # 判断是否成功
        is_success = random.randint(1, 100) <= success_rate
        
        if is_success:
            # 打劫成功
            actual_amount = min(rob_amount, to_points)  # 不能超过对方持有积分
            
            # 更新积分
            new_from_points = from_points + actual_amount
            new_to_points = to_points - actual_amount
            
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, user['Id']))
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_to_points, data.to_user_id))
            
            # 记录日志
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (user['Id'], user['Name'], f"打劫 {to_user_name}", actual_amount, new_from_points))
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (data.to_user_id, to_user_name, f"被 {user['Name']} 打劫", -actual_amount, new_to_points))
            c.execute("INSERT INTO point_rob_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, success, counter_amount) VALUES (?, ?, ?, ?, ?, 1, 0)",
                     (user['Id'], user['Name'], data.to_user_id, to_user_name, actual_amount))
            
            conn.commit(); conn.close()
            
            return {
                "status": "success",
                "message": f"🎉 打劫成功！从 {to_user_name} 身上抢到 {actual_amount} 积分",
                "success": True,
                "amount": actual_amount,
                "balance": new_from_points
            }
        else:
            # 打劫失败，触发反杀
            counter_amount = random.randint(counter_min, counter_max)
            actual_counter = min(counter_amount, from_points)  # 不能超过自己持有积分
            
            # 更新积分（攻击者损失，受害者获得）
            new_from_points = from_points - actual_counter
            new_to_points = to_points + actual_counter
            
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, user['Id']))
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_to_points, data.to_user_id))
            
            # 记录日志
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (user['Id'], user['Name'], f"打劫 {to_user_name} 失败", -actual_counter, new_from_points))
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (data.to_user_id, to_user_name, f"反杀 {user['Name']}", actual_counter, new_to_points))
            c.execute("INSERT INTO point_rob_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, success, counter_amount) VALUES (?, ?, ?, ?, ?, 0, ?)",
                     (user['Id'], user['Name'], data.to_user_id, to_user_name, 0, actual_counter))
            
            conn.commit(); conn.close()
            
            return {
                "status": "success",
                "message": f"😢 打劫失败！被 {to_user_name} 反杀，损失 {actual_counter} 积分",
                "success": False,
                "counter_amount": actual_counter,
                "balance": new_from_points
            }

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


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
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用用户PK
        if int(config.get('enable_user_pk', 0)) == 0:
            conn.close()
            return {"status": "error", "message": "用户PK功能未开启"}
        
        # 不能PK自己
        if data.target_id == user['Id']:
            conn.close()
            return {"status": "error", "message": "不能PK自己"}
        
        # 获取配置
        min_points = int(config.get('user_pk_min_points', 10))
        max_points = int(config.get('user_pk_max_points', 500))
        max_per_day = int(config.get('user_pk_max_per_day', 5))
        timeout_minutes = int(config.get('user_pk_timeout', 5))
        
        # 检查下注积分范围
        if data.points < min_points or data.points > max_points:
            conn.close()
            return {"status": "error", "message": f"下注积分必须在 {min_points}-{max_points} 之间"}
        
        # 获取发起者积分
        from_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        from_points = from_row[0] if from_row else 0
        
        if from_points < data.points:
            conn.close()
            return {"status": "error", "message": f"积分不足，当前积分: {from_points}"}
        
        # 获取目标用户积分
        to_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (data.target_id,)).fetchone()
        to_points = to_row[0] if to_row else 0
        
        if to_points < data.points:
            conn.close()
            return {"status": "error", "message": f"对方积分不足（{to_points}），无法接受此PK"}
        
        # 获取目标用户名称
        try:
            emby_users = media_api.get("/Users", timeout=5).json()
            to_user_name = next((u['Name'] for u in emby_users if u['Id'] == data.target_id), None)
            if not to_user_name:
                conn.close()
                return {"status": "error", "message": "目标用户不存在"}
        except:
            conn.close()
            return {"status": "error", "message": "无法验证目标用户"}
        
        # 检查今日PK次数
        today_pk_count = c.execute(
            "SELECT COUNT(*) FROM pk_logs WHERE challenger_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()[0]
        if today_pk_count >= max_per_day:
            conn.close()
            return {"status": "error", "message": f"今日PK次数已达上限（{max_per_day}次）"}
        
        # 清理过期邀请
        c.execute("DELETE FROM pk_invitations WHERE expires_at < datetime('now', 'localtime')")
        
        # 检查是否有待处理的邀请
        pending = c.execute(
            "SELECT id FROM pk_invitations WHERE challenger_id = ? AND target_id = ? AND status = 'pending' AND expires_at > datetime('now', 'localtime')",
            (user['Id'], data.target_id)
        ).fetchone()
        if pending:
            conn.close()
            return {"status": "error", "message": "已有待处理的PK邀请，请等待对方回应"}
        
        # 创建邀请
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(minutes=timeout_minutes)
        
        c.execute(
            "INSERT INTO pk_invitations (challenger_id, challenger_name, target_id, target_name, points, chat_id, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, 'pending')",
            (user['Id'], user['Name'], data.target_id, to_user_name, data.points, data.chat_id, expires_at.isoformat())
        )
        invite_id = c.lastrowid
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": f"已向 {to_user_name} 发起PK邀请，下注 {data.points} 积分",
            "invite_id": invite_id,
            "expires_at": expires_at.isoformat(),
            "timeout_minutes": timeout_minutes
        }

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


@router.post("/api/user/points/pk/accept")
def pk_accept(data: PKAcceptModel, request: Request):
    """接受PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}

        # 获取邀请
        invite = c.execute(
            "SELECT * FROM pk_invitations WHERE id = ? AND status = 'pending'",
            (data.invite_id,)
        ).fetchone()

        if not invite:
            conn.rollback(); conn.close()
            return {"status": "error", "message": "邀请不存在或已过期"}
        
        # 检查是否是目标用户
        if invite[3] != user['Id']:  # target_id
            conn.rollback(); conn.close()
            return {"status": "error", "message": "这不是发给你的PK邀请"}

        # 检查是否过期
        from datetime import datetime
        expires_at = datetime.fromisoformat(invite[9])  # expires_at
        if datetime.now() > expires_at:
            c.execute("UPDATE pk_invitations SET status = 'expired' WHERE id = ?", (data.invite_id,))
            conn.commit()
            conn.close()
            return {"status": "error", "message": "PK邀请已过期"}
        
        # 🔥 重新检查积分范围（防止配置被修改后绕过）
        points = invite[5]  # 下注积分
        min_points = int(config.get('user_pk_min_points', 10))
        max_points = int(config.get('user_pk_max_points', 500))
        if points < min_points or points > max_points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (data.invite_id,))
            conn.commit(); conn.close()
            return {"status": "error", "message": f"积分范围已变更，PK取消（需在 {min_points}-{max_points} 之间）"}
        
        # 获取配置
        tax_rate = int(config.get('user_pk_tax', 5))
        
        # 获取双方积分
        challenger_points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (invite[1],)).fetchone()
        challenger_points = challenger_points_row[0] if challenger_points_row else 0
        
        target_points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (invite[3],)).fetchone()
        target_points = target_points_row[0] if target_points_row else 0
        
        points = invite[5]  # 下注积分
        
        # 再次检查双方积分
        if challenger_points < points or target_points < points:
            conn.rollback(); conn.close()
            return {"status": "error", "message": "双方积分不足，PK取消"}
        
        # 掷骰子
        challenger_roll = random.randint(1, 100)
        target_roll = random.randint(1, 100)
        
        # 判断胜负
        if challenger_roll > target_roll:
            winner_id = invite[1]  # challenger_id
            winner_name = invite[2]  # challenger_name
            loser_id = invite[3]  # target_id
            loser_name = invite[4]  # target_name
        elif target_roll > challenger_roll:
            winner_id = invite[3]  # target_id
            winner_name = invite[4]  # target_name
            loser_id = invite[1]  # challenger_id
            loser_name = invite[2]  # challenger_name
        else:
            # 平局，不扣积分
            c.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (data.invite_id,))
            conn.commit()
            conn.close()
            return {
                "status": "success",
                "message": f"平局！{invite[2]}({challenger_roll}点) vs {invite[4]}({target_roll}点)，积分退还",
                "challenger_roll": challenger_roll,
                "target_roll": target_roll,
                "tie": True
            }
        
        # 计算积分转移（扣除手续费）
        win_amount = points
        tax = int(win_amount * tax_rate / 100)
        actual_win = win_amount - tax
        
        # 🔥 再次检查积分是否足够（防止并发问题）
        challenger_points_now = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (invite[1],)).fetchone()
        target_points_now = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (invite[3],)).fetchone()
        challenger_balance = challenger_points_now[0] if challenger_points_now else 0
        target_balance = target_points_now[0] if target_points_now else 0
        
        # 🔥 检查输家是否有足够积分
        loser_balance = challenger_balance if loser_id == invite[1] else target_balance
        if loser_balance < points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (data.invite_id,))
            conn.commit()
            conn.close()
            return {"status": "error", "message": f"积分不足，PK取消（输家积分：{loser_balance}，需要：{points}）"}
        
        # 更新积分
        c.execute("UPDATE users_meta SET points = points + ? WHERE user_id = ?", (actual_win, winner_id))
        c.execute("UPDATE users_meta SET points = points - ? WHERE user_id = ?", (points, loser_id))
        
        # 记录日志
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
            (winner_id, winner_name, f"PK战胜 {loser_name}", actual_win, winner_id)
        )
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
            (loser_id, loser_name, f"PK败给 {winner_name}", -points, loser_id)
        )
        
        # 记录PK日志
        c.execute(
            "INSERT INTO pk_logs (challenger_id, challenger_name, target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (invite[1], invite[2], invite[3], invite[4], points, challenger_roll, target_roll, winner_id, winner_name, tax)
        )
        
        # 更新邀请状态
        c.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (data.invite_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": f"🎉 {winner_name}({max(challenger_roll, target_roll)}点) 战胜 {loser_name}({min(challenger_roll, target_roll)}点)，获得 {actual_win} 积分（扣{tax_rate}%手续费）",
            "challenger_roll": challenger_roll,
            "target_roll": target_roll,
            "winner_name": winner_name,
            "win_amount": actual_win,
            "tax": tax
        }

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


@router.post("/api/user/points/pk/reject")
def pk_reject(data: PKRejectModel, request: Request):
    """拒绝PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取邀请
        invite = c.execute(
            "SELECT * FROM pk_invitations WHERE id = ? AND status = 'pending'",
            (data.invite_id,)
        ).fetchone()
        
        if not invite:
            conn.close()
            return {"status": "error", "message": "邀请不存在或已处理"}
        
        # 检查是否是目标用户
        if invite[3] != user['Id']:  # target_id
            conn.close()
            return {"status": "error", "message": "这不是发给你的PK邀请"}
        
        # 更新状态
        c.execute("UPDATE pk_invitations SET status = 'rejected' WHERE id = ?", (data.invite_id,))
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": f"已拒绝 {invite[2]} 的PK邀请"
        }

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


@router.get("/api/user/points/pk/pending")
def pk_pending(request: Request):
    """获取待处理的PK邀请"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 清理过期邀请
        c.execute("UPDATE pk_invitations SET status = 'expired' WHERE expires_at < datetime('now', 'localtime') AND status = 'pending'")
        conn.commit()
        
        # 获取发给当前用户的待处理邀请
        invites = c.execute(
            "SELECT id, challenger_id, challenger_name, points, created_at, expires_at FROM pk_invitations WHERE target_id = ? AND status = 'pending' ORDER BY created_at DESC",
            (user['Id'],)
        ).fetchall()
        conn.close()
        
        result = []
        for inv in invites:
            result.append({
                "id": inv[0],
                "challenger_id": inv[1],
                "challenger_name": inv[2],
                "points": inv[3],
                "created_at": inv[4],
                "expires_at": inv[5]
            })
        
        return {"status": "success", "data": result}

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


@router.post("/api/points/pk/clear")
def clear_pk_invitations(request: Request):
    """清除所有PK邀请"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 清除所有PK邀请
        c.execute("DELETE FROM pk_invitations")
        count = c.rowcount
        
        conn.commit()
        conn.close()
        
        return {"status": "success", "count": count, "message": f"已清除 {count} 条PK邀请"}

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


# ===================== 🎰 老虎机 API =====================

@router.get("/api/slot/usage")
def get_slot_usage(request: Request):
    """获取今日老虎机使用次数"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 使用 SQLite 本地时间函数，与 CURRENT_TIMESTAMP (UTC) 对齐
        row = c.execute(
            "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action = '老虎机' AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()
        
        conn.close()
        return {"status": "success", "used_today": row[0] if row else 0}

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


@router.post("/api/slot/spin")
def slot_spin(request: Request):
    """老虎机抽奖"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")

        # 获取配置
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}

        # 检查是否启用
        if config.get('enable_slot') != '1':
            conn.rollback(); conn.close()
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
        used_row = c.execute(
            "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action = '老虎机' AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()
        used_today = used_row[0] if used_row else 0
        
        # 检查每日次数限制
        if used_today >= max_per_day:
            conn.rollback(); conn.close()
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}

        # 获取用户积分
        points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_points = points_row[0] if points_row else 0

        # 🔥 修复：当 daily_free = 0 时，永远不免费
        # 当 daily_free > 0 时，前 daily_free 次免费
        is_free = False
        if daily_free > 0 and used_today < daily_free:
            is_free = True
        
        # 检查积分（非免费时需要足够积分）
        if not is_free and current_points < cost:
            conn.close()
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
        
        # 更新积分
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))
        
        # 记录日志
        action_desc = f"老虎机抽奖: {result_emojis[0]} {result_emojis[1]} {result_emojis[2]}"
        if win:
            action_desc += f" 获得 {reward} 积分"
        else:
            action_desc += " 未中奖"
        
        amount_change = reward if win else (-cost if not is_free else 0)
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (user['Id'], user['Name'], '老虎机', amount_change, current_points)
        )
        
        conn.commit()
        conn.close()
        
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
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


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
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取配置
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用
        if config.get('enable_web_scratch') != '1':
            conn.close()
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
        used_today = c.execute(
            "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action LIKE '刮刮乐%' AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()[0]
        
        if used_today >= max_per_day:
            conn.close()
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}
        
        # 获取用户积分
        points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_points = points_row[0] if points_row else 0
        
        # 检查积分
        if current_points < cost:
            conn.close()
            return {"status": "error", "message": f"积分不足（需要 {cost} 积分）"}
        
        # 扣除积分
        conn.execute("BEGIN IMMEDIATE")
        current_points -= cost
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))

        # 记录日志
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (user['Id'], user['Name'], '刮刮乐-购买', -cost, current_points)
        )
        
        conn.commit()
        conn.close()
        
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
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass


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
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            c = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")

            # 获取当前积分
            points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
            current_points = points_row[0] if points_row else 0

            # 增加积分
            current_points += cell['reward']
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))

            # 记录日志
            c.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user['Id'], user['Name'], '刮刮乐-中奖', cell['reward'], current_points)
            )

            conn.commit()
            conn.close()

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
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass

# 🎡 幸运转盘
wheel_usage = {}  # 用户使用次数缓存

@router.get("/api/wheel/usage")
async def get_wheel_usage(request: Request):
    """获取转盘今日使用次数"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    # 获取配置
    config = get_point_config()
    max_per_day = int(config.get('wheel_max_per_day', 20))
    
    # 查询今日使用次数（使用 SQLite 本地时间函数）
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    count = c.execute(
        "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action = '幸运转盘' AND date(created_at, 'localtime') = date('now', 'localtime')",
        (user['Id'],)
    ).fetchone()[0]
    conn.close()
    
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
        config = get_point_config()
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
        
        # 查询今日使用次数（使用 SQLite 本地时间函数）
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        used_today = c.execute(
            "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action = '幸运转盘' AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()[0]
        
        # 检查次数限制
        if used_today >= max_per_day:
            conn.close()
            return {"status": "error", "message": "今日次数已用完"}
        
        # 获取当前积分
        points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_points = points_row[0] if points_row else 0
        
        # 🔥 修复：当 daily_free = 0 时，永远不免费
        is_free = False
        if daily_free > 0 and used_today < daily_free:
            is_free = True
        
        # 扣除积分
        if not is_free:
            if current_points < cost:
                conn.rollback(); conn.close()
                return {"status": "error", "message": "积分不足"}
            current_points -= cost
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))


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
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))
        
        
        # 记录日志
        used_today += 1
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (user['Id'], user['Name'], '幸运转盘', reward - (0 if is_free else cost), current_points)
        )
        
        conn.commit()
        conn.close()
        
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
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass

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
        config = get_point_config()
        enabled = config.get('enable_guess', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "猜数字功能未启用"}
        
        cost = int(config.get('guess_cost', 5))
        range_str = config.get('guess_range', '1-100')
        range_parts = range_str.split('-')
        min_num = int(range_parts[0]) if len(range_parts) > 0 else 1
        max_num = int(range_parts[1]) if len(range_parts) > 1 else 100
        max_per_day = int(config.get('guess_max_per_day', 20))  # 🔥 每日次数限制
        
        # 获取当前积分
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 🔥 检查今日使用次数（使用 SQLite 本地时间函数）
        used_today = c.execute(
            "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action LIKE '猜数字%' AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user['Id'],)
        ).fetchone()[0]
        
        if used_today >= max_per_day:
            conn.close()
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}
        
        points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_points = points_row[0] if points_row else 0

        # 扣除积分
        if current_points < cost:
            conn.close()
            return {"status": "error", "message": "积分不足"}

        conn.execute("BEGIN IMMEDIATE")
        current_points -= cost
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))

        # 记录扣分日志
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (user['Id'], user['Name'], '猜数字-开始', -cost, current_points)
        )

        conn.commit()
        conn.close()
        
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
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass

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
        config = get_point_config()
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
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            c = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")
            points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
            current_points = points_row[0] if points_row else 0
            current_points += reward
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))
            c.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user['Id'], user['Name'], '猜数字-猜中', reward, current_points)
            )
            conn.commit()
            conn.close()
            
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
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            c = conn.cursor()
            # 获取当前积分用于记录
            points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
            current_pts = points_row[0] if points_row else 0
            c.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user['Id'], user['Name'], '猜数字-失败', 0, current_pts)
            )
            conn.commit()
            conn.close()
            
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
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass

# 🎟️ 彩票
@router.get("/api/lottery/my_tickets")
async def get_my_lottery_tickets(request: Request):
    """获取我的彩票号"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        # 查询我的彩票号（使用 numbers 字段）
        tickets = c.execute(
            "SELECT numbers FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
            (user['Id'], today)
        ).fetchall()
        conn.close()
        
        return {
            "status": "success",
            "tickets": [t[0] for t in tickets]
        }
    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass

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
        config = get_point_config()
        enabled = config.get('enable_lottery', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "彩票功能未启用"}
        
        cost = int(config.get('lottery_cost', 100))
        max_per_day = int(config.get('lottery_max_per_day', 10))
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        today = datetime.datetime.now().strftime('%Y-%m-%d')

        # 检查今日已购买数量
        today_count = c.execute(
            "SELECT COUNT(*) FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
            (user['Id'], today)
        ).fetchone()[0]
        
        if today_count + count > max_per_day:
            conn.rollback(); conn.close()
            return {"status": "error", "message": f"今日最多购买 {max_per_day} 张"}
        
        # 获取当前积分
        points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user['Id'],)).fetchone()
        current_points = points_row[0] if points_row else 0
        
        total_cost = cost * count
        if current_points < total_cost:
            conn.rollback(); conn.close()
            return {"status": "error", "message": "积分不足"}
        
        # 扣除积分
        current_points -= total_cost
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user['Id']))
        
        # 生成彩票号
        import random
        tickets = []
        
        # 如果有自选号码，第一张用自选号码
        if custom_number and len(custom_number) == 4 and custom_number.isdigit():
            tickets.append(custom_number)
            c.execute(
                "INSERT INTO lottery_tickets (user_id, username, numbers, cost, draw_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user['Id'], user.get('Name', ''), custom_number, cost, today, datetime.datetime.now().isoformat())
            )
            count -= 1
        
        # 剩余的随机生成
        for _ in range(count):
            ticket_number = str(random.randint(0, 9999)).zfill(4)
            tickets.append(ticket_number)
            c.execute(
                "INSERT INTO lottery_tickets (user_id, username, numbers, cost, draw_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user['Id'], user.get('Name', ''), ticket_number, cost, today, datetime.datetime.now().isoformat())
            )
        
        # 记录日志
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (user['Id'], user['Name'], '购买彩票', -total_cost, current_points)
        )
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "tickets": tickets,
            "today_tickets": today_count + len(tickets),
            "new_points": current_points
        }

    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass

@router.get("/api/lottery/pool")
async def api_user_lottery_pool(request: Request):
    """用户社区获取奖池信息"""
    try:
        user = request.session.get("req_user")
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取配置
        config = get_point_config()
        draw_hour = int(config.get('lottery_draw_hour', 20))
        max_per_day = int(config.get('lottery_max_per_day', 10))
        
        # 检查今天是否已开奖
        today_drawn = c.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''", (today,)).fetchone()
        
        if today_drawn:
            # 今天已开奖，显示明天的奖池
            target_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            next_draw_time = f"明天 {(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%m-%d')} {draw_hour}:00"
        else:
            target_date = today
            next_draw_time = f"今天 {datetime.datetime.now().strftime('%m-%d')} {draw_hour}:00"
        
        # 确保目标日期有记录
        c.execute("INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)", (target_date,))
        conn.commit()
        
        # 获取目标日期奖池
        target_pool = c.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (target_date,)).fetchone()
        target_pool = target_pool[0] if target_pool else 0
        
        # 获取目标日期购票数（全局）
        target_tickets = c.execute("SELECT COUNT(*) FROM lottery_tickets WHERE draw_date = ?", (target_date,)).fetchone()[0]
        
        # 🔥 获取当前用户今日购票数
        user_today_tickets = 0
        if user:
            user_today_tickets = c.execute(
                "SELECT COUNT(*) FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                (user['Id'], target_date)
            ).fetchone()[0]
        
        # 获取今日开奖号码
        today_winning = c.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''", (today,)).fetchone()
        today_winning_number = today_winning[0] if today_winning else None
        
        # 检查用户是否中奖
        my_winning = []
        my_prize_total = 0
        if user and today_winning_number:
            my_tickets = c.execute(
                "SELECT numbers FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                (user['Id'], today)
            ).fetchall()
            for t in my_tickets:
                if t[0] == today_winning_number:
                    my_winning.append(t[0])
            # 计算中奖总额
            if my_winning:
                # 获取今日奖池和中奖人数
                today_pool = c.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
                today_pool = today_pool[0] if today_pool else 0
                winner_count = c.execute("SELECT COUNT(*) FROM lottery_winners WHERE draw_date = ?", (today,)).fetchone()[0]
                winner_count = max(winner_count, 1)
                my_prize_total = len(my_winning) * (today_pool // winner_count)
        
        conn.close()
        
        return {
            "status": "success",
            "data": {
                "today_pool": target_pool,
                "today_tickets": target_tickets,
                "user_today_tickets": user_today_tickets,
                "target_date": target_date,
                "next_draw_time": next_draw_time,
                "today_winning_number": today_winning_number,
                "my_winning_tickets": my_winning,
                "my_prize_total": my_prize_total,
                "is_drawn": today_drawn is not None,
                "max_per_day": max_per_day
            }
        }
    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass
@router.get("/api/lottery/results")
async def get_lottery_results(request: Request):
    """获取开奖结果"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        user = request.session.get("req_user")
        user_id = user['Id'] if user else None
        
        # 获取最近7天的开奖结果（字段名：winning_numbers）
        results = c.execute('''
            SELECT draw_date, winning_numbers, total_pool 
            FROM lottery_results 
            WHERE winning_numbers != ''
            ORDER BY draw_date DESC 
            LIMIT 7
        ''').fetchall()
        
        # 统计每天的中奖人数和用户中奖情况
        formatted_results = []
        for r in results:
            draw_date = r[0]
            winning_number = r[1]
            pool = r[2]
            
            winner_count = c.execute(
                "SELECT COUNT(*) FROM lottery_winners WHERE draw_date = ?",
                (draw_date,)
            ).fetchone()[0]
            
            # 获取中奖名单
            winners_list = []
            my_username = None
            if winner_count > 0:
                winners_data = c.execute('''
                    SELECT w.user_id, w.username, w.prize_level, w.prize_amount
                    FROM lottery_winners w
                    WHERE w.draw_date = ?
                    ORDER BY w.prize_amount DESC
                ''', (draw_date,)).fetchall()
                for w in winners_data:
                    winner_user_id = w[0]
                    username = w[1] or ''
                    # 如果是当前用户，不脱敏，并记录用户名
                    if user_id and winner_user_id == user_id:
                        masked_username = username
                        my_username = username
                    else:
                        # 其他用户脱敏：保留前3个字符，后面用***代替
                        if len(username) > 3:
                            masked_username = username[:3] + '***'
                        else:
                            masked_username = username[:1] + '***' if username else '***'
                    winners_list.append({
                        "username": masked_username,
                        "prize_level": w[2],
                        "prize_amount": w[3]
                    })
            
            # 检查用户在该期是否中奖
            my_won = False
            my_prize = 0
            my_winning_tickets = []
            if user_id:
                my_tickets = c.execute(
                    "SELECT numbers FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                    (user_id, draw_date)
                ).fetchall()
                for t in my_tickets:
                    ticket_number = t[0]
                    if ticket_number == winning_number:
                        my_won = True
                        my_winning_tickets.append(ticket_number)
                # 计算中奖金额
                if my_won and winner_count > 0:
                    my_prize = len(my_winning_tickets) * (pool // winner_count)
            
            formatted_results.append({
                "date": draw_date,
                "winning_number": winning_number,
                "pool": pool,
                "winners": winner_count,
                "winners_list": winners_list,
                "my_won": my_won,
                "my_prize": my_prize,
                "my_winning_tickets": my_winning_tickets
            })
        
        conn.close()
        
        return {
            "status": "success",
            "results": formatted_results
        }
    except Exception as e:
        try: conn.rollback()
        except: pass
        return {"status": "error", "message": safe_error_message(e)}
    finally:
        try: conn.close()
        except: pass
