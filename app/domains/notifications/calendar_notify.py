"""
日历通知系统
支持自定义时间推送每日更新日历到 TG 机器人/企业微信
"""
import logging
import json
import datetime
import threading
import time
from fastapi import APIRouter, Request
from app.domains.users import public_service as user_service
from pydantic import BaseModel
from typing import Optional, List
from app.core.security_utils import safe_error_message
from app.infra.clients.telegram_client import telegram_client
from app.infra.clients.wecom_client import wecom_client
from app.infra.config.notification_settings import (
    get_notification_channels_runtime_config,
    get_wecom_runtime_config,
)
from app.domains.notifications.calendar_notify_dao import (
    ensure_calendar_notify_config_table,
    get_calendar_notify_config,
    mark_calendar_notify_sent,
    save_calendar_notify_config,
)

logger = logging.getLogger("uvicorn")
router = APIRouter(prefix="/api/calendar/notify", tags=["日历通知"])

# ============ 数据库初始化 ============
def _ensure_table():
    """确保日历通知配置表存在"""
    try:
        ensure_calendar_notify_config_table()
    except Exception as e:
        logger.error(f"[日历通知] 建表失败: {e}")

# ============ 配置模型 ============
class CalendarNotifyConfig(BaseModel):
    enabled: bool = False
    notify_time: str = "09:00"
    channels: List[str] = ["tg_bot"]
    tg_chat_id: Optional[str] = None
    wecom_touser: str = "@all"

# ============ API 接口 ============
@router.get("/config")
def get_notify_config(request: Request):
    """获取日历通知配置"""
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "未授权"}
    
    try:
        row = get_calendar_notify_config()
        
        if row:
            return {
                "status": "success",
                "data": {
                    "enabled": bool(row['enabled']),
                    "notify_time": row['notify_time'] or "09:00",
                    "channels": json.loads(row['channels'] or '["tg_bot"]'),
                    "tg_chat_id": row['tg_chat_id'] or "",
                    "wecom_touser": row['wecom_touser'] or "@all",
                    "last_sent": row['last_sent']
                }
            }
        return {"status": "success", "data": {"enabled": False, "notify_time": "09:00", "channels": ["tg_bot"], "tg_chat_id": "", "wecom_touser": "@all"}}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/config")
def save_notify_config(request: Request, config: CalendarNotifyConfig):
    """保存日历通知配置"""
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "未授权"}
    
    try:
        save_calendar_notify_config(
            enabled=config.enabled,
            notify_time=config.notify_time,
            channels=json.dumps(config.channels),
            tg_chat_id=config.tg_chat_id or "",
            wecom_touser=config.wecom_touser,
        )
        
        # 重启定时任务 - 使用当前模块的服务实例
        init_calendar_notify_service()
        
        return {"status": "success", "message": "配置已保存"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/test")
def test_notify(request: Request):
    """测试发送日历通知"""
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "未授权"}
    
    try:
        result = send_calendar_notify(test=True)
        if result.get("success"):
            return {"status": "success", "message": f"测试通知已发送: {result.get('message', '')}"}
        else:
            return {"status": "error", "message": result.get("message", "发送失败")}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/send")
def manual_send(request: Request):
    """手动触发发送日历通知"""
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "未授权"}
    
    try:
        result = send_calendar_notify()
        if result.get("success"):
            return {"status": "success", "message": f"通知已发送: {result.get('message', '')}"}
        else:
            return {"status": "error", "message": result.get("message", "发送失败")}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# ============ 通知发送逻辑 ============
def get_today_updates():
    """获取今日更新的剧集列表"""
    try:
        from app.domains.playback.calendar_service import calendar_service
        
        # 获取本周日历数据
        data = calendar_service.get_weekly_calendar(force_refresh=False, week_offset=0)
        
        if not data:
            logger.error("[日历通知] 获取日历数据失败: data is None")
            return []
        
        if data.get("error"):
            logger.error(f"[日历通知] 获取日历数据失败: {data.get('error')}")
            return []
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updates = []
        
        # 遍历每一天 - 数据结构是 {"days": [{"date": ..., "items": [...]}, ...]}
        days = data.get("days", [])
        
        for day_data in days:
            if day_data.get("date") == today:
                items = day_data.get("items", [])
                # 获取该天的所有剧集（日历中都是电视剧，无需检查type）
                for item in items:
                    updates.append({
                        "name": item.get("series_name") or item.get("name", ""),
                        "season": item.get("season", 1),
                        "episode": item.get("episode", 1),
                        "status": item.get("status", "pending"),
                        "year": item.get("year", "")
                    })
                break
        
        logger.info(f"[日历通知] 今日 {today} 共有 {len(updates)} 部剧集更新")
        return updates
    except Exception as e:
        logger.error(f"[日历通知] 获取今日更新失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def format_notify_message(updates: list, test: bool = False):
    """格式化通知消息"""
    if test:
        return """📺 <b>今日剧集更新</b>

🔴 方圆八百米 (2026) S01E10
🟢 绝命律师 (2015) S06E01

<b>共 2 部剧集今日更新</b>
<i>（这是一条测试消息）</i>"""
    
    if not updates:
        return """📺 <b>今日剧集更新</b>

暂无剧集今日更新 🎬"""
    
    # 按状态分组
    ready_items = [u for u in updates if u.get("status") == "ready"]
    pending_items = [u for u in updates if u.get("status") != "ready"]
    
    lines = ["📺 <b>今日剧集更新</b>\n"]
    
    # 已入库（绿灯）
    for item in ready_items:
        year_str = f" ({item['year']})" if item.get('year') else ""
        season = int(str(item.get('season', 1)).split('-')[0]) if item.get('season') else 1
        episode_str = str(item.get('episode', 1))
        lines.append(f"🟢 {item['name']}{year_str} S{season:02d}E{episode_str}")
    
    # 待更新（红灯）
    for item in pending_items:
        year_str = f" ({item['year']})" if item.get('year') else ""
        season = int(str(item.get('season', 1)).split('-')[0]) if item.get('season') else 1
        episode_str = str(item.get('episode', 1))
        lines.append(f"🔴 {item['name']}{year_str} S{season:02d}E{episode_str}")
    
    lines.append(f"\n<b>共 {len(updates)} 部剧集今日更新</b>")
    lines.append("\n<i>🟢 已入库 · 🔴 未入库</i>")
    
    return "\n".join(lines)

def send_calendar_notify(test: bool = False):
    """发送日历通知"""
    try:
        # 获取配置
        row = get_calendar_notify_config()
        
        if not row:
            return {"success": False, "message": "未找到配置"}
        
        channels = json.loads(row['channels'] or '["tg_bot"]')
        
        # 获取今日更新
        updates = get_today_updates() if not test else []
        message = format_notify_message(updates, test)
        
        results = []
        
        # 发送到 TG 管理员机器人
        if "tg_bot" in channels:
            tg_config = get_notification_channels_runtime_config()["tg_bot"]
            tg_chat_id = row['tg_chat_id'] or tg_config["chat_id"]
            tg_token = tg_config["token"]
            
            if tg_chat_id and tg_token:
                try:
                    from app.utils.proxy_helper import get_safe_proxies
                    proxies = get_safe_proxies()
                    
                    res = telegram_client.post_api(tg_token, "sendMessage", data={"chat_id": tg_chat_id, "text": message, "parse_mode": "HTML"}, proxies=proxies, timeout=10)
                    if res.status_code == 200:
                        results.append("TG机器人")
                        logger.info(f"[日历通知] TG机器人发送成功")
                    else:
                        logger.error(f"[日历通知] TG机器人发送失败: {res.text}")
                except Exception as e:
                    logger.error(f"[日历通知] TG机器人发送异常: {e}")
        
        # 发送到企业微信
        if "wecom" in channels:
            wecom_config = get_wecom_runtime_config()
            corpid = wecom_config["corpid"]
            corpsecret = wecom_config["corpsecret"]
            agentid = wecom_config["agentid"]
            touser = row['wecom_touser'] or wecom_config["touser"]
            
            if corpid and corpsecret and agentid:
                try:
                    # 获取 access_token
                    from app.utils.proxy_helper import get_safe_wecom_base
                    proxy_url = get_safe_wecom_base()
                    token_res = wecom_client.get_access_token(proxy_url, corpid, corpsecret, timeout=10)
                    token = token_res.json().get("access_token")
                    
                    if token:
                        # 发送消息
                        send_res = wecom_client.send_message(
                            proxy_url,
                            token,
                            {
                                "touser": touser,
                                "msgtype": "text",
                                "agentid": int(agentid),
                                "text": {"content": message.replace("<b>", "").replace("</b>", "").replace("\n\n", "\n")}
                            },
                            timeout=10,
                        )
                        if send_res.json().get("errcode") == 0:
                            results.append("企业微信")
                            logger.info(f"[日历通知] 企业微信发送成功")
                except Exception as e:
                    logger.error(f"[日历通知] 企业微信发送异常: {e}")
        
        # 更新最后发送时间
        if not test and results:
            mark_calendar_notify_sent()
        
        if results:
            return {"success": True, "message": f"已发送至: {', '.join(results)}"}
        return {"success": False, "message": "未发送到任何渠道"}
        
    except Exception as e:
        logger.error(f"[日历通知] 发送失败: {e}")
        return {"success": False, "message": safe_error_message(e)}

# ============ 定时任务服务 ============
class CalendarNotifyService:
    """日历通知定时服务"""
    
    def __init__(self):
        self.running = False
        self.thread = None
        self._stop_event = threading.Event()
    
    def start(self):
        """启动定时服务"""
        if self.running:
            return
        self._stop_event.clear()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("[日历通知] 定时服务已启动")
    
    def stop(self):
        """停止定时服务"""
        self.running = False
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        logger.info("[日历通知] 定时服务已停止")
    
    def restart(self):
        """重启定时服务"""
        self.stop()
        time.sleep(1)
        self.start()
    
    def _loop(self):
        """定时检查循环"""
        while self.running:
            try:
                # 检查是否启用
                row = get_calendar_notify_config()
                
                if row and row['enabled']:
                    notify_time = row['notify_time'] or "09:00"
                    last_sent = row['last_sent']
                    
                    # 解析通知时间
                    hour, minute = map(int, notify_time.split(":"))
                    now = datetime.datetime.now()
                    
                    # 检查是否到达通知时间
                    if now.hour == hour and now.minute == minute:
                        # 检查今天是否已发送
                        today = now.strftime("%Y-%m-%d")
                        if not last_sent or not last_sent.startswith(today):
                            logger.info(f"[日历通知] 到达通知时间 {notify_time}，开始发送...")
                            send_calendar_notify()
                    
            except Exception as e:
                logger.error(f"[日历通知] 定时检查异常: {e}")
            
            # 每分钟检查一次
            self._stop_event.wait(60)

# 全局实例
calendar_notify_service = CalendarNotifyService()

# ============ 启动服务 ============
def init_calendar_notify_service():
    """初始化并启动日历通知服务"""
    try:
        calendar_notify_service.start()
        return calendar_notify_service
    except Exception as e:
        logger.error(f"[日历通知] 服务启动失败: {e}")
        return None


def start_calendar_notify_services():
    _ensure_table()
    init_calendar_notify_service()
