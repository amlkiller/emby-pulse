from fastapi import APIRouter, Request, Response
from app.schemas.models import BotSettingsModel
from app.infra.clients.media_server_client import media_api
from app.infra.clients.telegram_client import telegram_client
from app.infra.clients.wecom_client import wecom_client
from app.infra.config.bot_settings import (
    get_all_bot_settings,
    get_bot_setting_source,
    get_bot_settings_audit_values,
    get_tg_bot_token,
    get_tg_chat_id,
    get_user_bot_token,
    get_wecom_aeskey,
    get_wecom_token,
    get_webhook_base_url,
    get_webhook_token,
    set_bot_setting,
    should_update_sensitive_bot_setting,
)
from app.infra.config.notification_settings import get_wecom_runtime_config
from app.infra.config.user_bot_settings import (
    get_user_bot_allowed_groups,
    get_user_bot_reg_quota,
    get_user_bot_reg_quota_mode,
    is_user_bot_open_reg_enabled,
    is_user_bot_open_reg_notify_group_enabled,
    is_user_bot_open_reg_notify_user_enabled,
    set_user_bot_registration_batch_used,
)
from app.bot.bot_admin_dao import (
    adjust_lottery_pool,
    clear_active_scratch_card,
    clear_registration_logs,
    count_registration_logs,
    fix_lottery_pool,
    get_lottery_draw_result,
    get_lottery_pool_info,
    get_registration_stats,
    list_registration_logs,
    list_tg_bindings,
    list_tg_bindings_for_sync,
    list_user_blacklist,
    remove_user_blacklist,
    reset_lottery_draw,
    update_tg_binding_names,
)
from app.bot.notification_bot.bot_service import bot
from app.domains.points import point_dao
from app.domains.users import public_service as user_service
import threading
import base64
import struct
import hashlib
import xml.etree.ElementTree as ET
import logging
import datetime
from app.core.security_utils import safe_error_message
from app.core.rate_limiter import get_client_ip

logger = logging.getLogger("uvicorn")

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None

router = APIRouter()

@router.get("/api/bot/settings")
def api_get_bot_settings(request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    all_config = get_all_bot_settings()
    
    # 🔒 安全：脱敏敏感字段
    def mask_sensitive(value):
        """脱敏敏感字段"""
        if not value or not isinstance(value, str):
            return ""
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]
    
    # 🔒 完整敏感字段列表（包括环境变量控制的和其他敏感字段）
    SENSITIVE_ENV_FIELDS = [
        "tg_bot_token", "tg_user_bot_token",
        "wecom_corpsecret", "wecom_token", "wecom_aeskey",
        "webhook_token"
    ]
    
    # 🔒 其他敏感字段（需要脱敏但可以显示）
    OTHER_SENSITIVE_FIELDS = [
        "emby_api_key", "tmdb_api_key", "moviepilot_token",
        "weather_qweather_key", "weather_amap_key"
    ]
    
    # 脱敏并标记环境变量控制的字段
    for field in SENSITIVE_ENV_FIELDS:
        if field in all_config:
            value = all_config[field]
            source = get_bot_setting_source(field)
            
            if source == "env":
                # 来自环境变量：返回标记，不返回实际值
                all_config[field] = "****（由环境变量设置）"
                all_config[f"{field}_source"] = "env"
                all_config[f"{field}_readonly"] = True
            else:
                # 来自配置文件：返回脱敏值
                all_config[field] = mask_sensitive(value)
                all_config[f"{field}_source"] = "config"
                all_config[f"{field}_readonly"] = False
    
    # 🔒 脱敏其他敏感字段（不标记来源）
    for field in OTHER_SENSITIVE_FIELDS:
        if field in all_config:
            all_config[field] = mask_sensitive(all_config[field])
    
    # 🔥 Webhook Token 特殊处理
    webhook_token = get_webhook_token()
    webhook_source = get_bot_setting_source("webhook_token")
    webhook_base_url = get_webhook_base_url()
    
    if webhook_source == "env":
        all_config["webhook_token"] = "****（由环境变量设置）"
        all_config["webhook_token_source"] = "env"
        all_config["webhook_token_readonly"] = True
        all_config["webhook_token_masked"] = "****"
        # 🔒 安全：webhook_url 中不包含真实 token
        all_config["webhook_url"] = f"{webhook_base_url}/api/v1/webhook?token=****"
    else:
        all_config["webhook_token"] = webhook_token
        all_config["webhook_token_source"] = "config"
        all_config["webhook_token_readonly"] = False
        all_config["webhook_token_masked"] = mask_sensitive(webhook_token)
        # 🔒 安全：webhook_url 中使用脱敏 token
        all_config["webhook_url"] = f"{webhook_base_url}/api/v1/webhook?token={mask_sensitive(webhook_token)}"
    
    return {"status": "success", "data": all_config}

@router.post("/api/bot/settings")
def api_save_bot_settings(data: BotSettingsModel, request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    # 🔒 安全：检查是否应该更新敏感字段
    # 🔥 记录变更前的值（用于审计日志）
    old_values = get_bot_settings_audit_values()
    
    # 🔒 安全：敏感字段仅在非环境变量且非脱敏时更新
    if should_update_sensitive_bot_setting("tg_bot_token", data.tg_bot_token):
        set_bot_setting("tg_bot_token", (data.tg_bot_token or "").strip())
    if should_update_sensitive_bot_setting("tg_user_bot_token", data.tg_user_bot_token):
        set_bot_setting("tg_user_bot_token", (data.tg_user_bot_token or "").strip())
    if should_update_sensitive_bot_setting("wecom_corpsecret", data.wecom_corpsecret):
        set_bot_setting("wecom_corpsecret", (data.wecom_corpsecret or "").strip())
    if should_update_sensitive_bot_setting("wecom_token", data.wecom_token):
        set_bot_setting("wecom_token", (data.wecom_token or "").strip())
    if should_update_sensitive_bot_setting("wecom_aeskey", data.wecom_aeskey):
        set_bot_setting("wecom_aeskey", (data.wecom_aeskey or "").strip())
    
    # 非敏感字段直接保存
    set_bot_setting("tg_chat_id", data.tg_chat_id)
    set_bot_setting("enable_bot", data.enable_bot)
    set_bot_setting("enable_notify", data.enable_notify)
    set_bot_setting("enable_library_notify", data.enable_library_notify) 
    
    set_bot_setting("wecom_corpid", (data.wecom_corpid or "").strip())
    set_bot_setting("wecom_agentid", (data.wecom_agentid or "").strip())
    set_bot_setting("wecom_touser", data.wecom_touser or "@all")
    # 🔒 SSRF 防护：校验企微代理基址
    _wecom_base = (data.wecom_proxy_url or "https://qyapi.weixin.qq.com").strip()
    from app.utils.url_validator import validate_wecom_proxy_base
    _wecom_check = validate_wecom_proxy_base(_wecom_base)
    if not _wecom_check.get("valid"):
        return {"status": "error", "message": f"企微代理地址不合法: {_wecom_check.get('error', '')}"}
    set_bot_setting("wecom_proxy_url", _wecom_base)
    try:
        from app.utils.proxy_helper import invalidate_cache as _proxy_cache_invalidate
        _proxy_cache_invalidate()
    except Exception:
        pass

    # 🤖 Pro: 用户机器人配置
    set_bot_setting("user_bot_open_reg", data.user_bot_open_reg)
    set_bot_setting("user_bot_open_reg_notify_user", data.user_bot_open_reg_notify_user)
    set_bot_setting("user_bot_open_reg_notify_group", data.user_bot_open_reg_notify_group)
    set_bot_setting("user_bot_max_reg", data.user_bot_max_reg)
    set_bot_setting("user_bot_reg_days", data.user_bot_reg_days)
    set_bot_setting("user_bot_template_user", data.user_bot_template_user)
    set_bot_setting("user_bot_portal_url", data.user_bot_portal_url)
    # 开放注册线路设置
    set_bot_setting("user_bot_route_mode", data.user_bot_route_mode or "block")
    set_bot_setting("user_bot_allow_routes", data.user_bot_allow_routes or "")
    set_bot_setting("user_bot_block_routes", data.user_bot_block_routes or "")
    # 🎯 开放注册名额模式
    set_bot_setting("user_bot_reg_quota_mode", data.user_bot_reg_quota_mode or "total")
    set_bot_setting("user_bot_reg_quota", data.user_bot_reg_quota or 0)
    set_bot_setting("user_bot_reg_batch_used", data.user_bot_reg_batch_used or 0)
    
    # 🎯 群聊设置
    set_bot_setting("user_bot_group_enabled", data.user_bot_group_enabled or False)
    set_bot_setting("user_bot_allowed_groups", data.user_bot_allowed_groups or "")
    set_bot_setting("user_bot_group_commands", data.user_bot_group_commands or "checkin,help")
    set_bot_setting("user_bot_welcome_msg", data.user_bot_welcome_msg or "")
    
    # 🔥 使用限制设置
    set_bot_setting("user_bot_restriction_enabled", data.user_bot_restriction_enabled or False)
    set_bot_setting("user_bot_required_channels", data.user_bot_required_channels or "")
    set_bot_setting("user_bot_required_groups", data.user_bot_required_groups or "")
    set_bot_setting("user_bot_restriction_cache_ttl", data.user_bot_restriction_cache_ttl or 120)
    
    # 🎯 频道入库通知
    set_bot_setting("notify_channels", data.notify_channels or "")
    
    # 🎯 入库通知渠道选择
    set_bot_setting("library_notify_channels", data.library_notify_channels or "")

    bot.stop()
    if data.enable_bot: threading.Timer(1.0, bot.start).start()

    from app.bot.user_bot.user_bot_service import user_bot
    user_bot.stop()
    # 只有真正更新了 token 才重启用户机器人
    real_token = get_user_bot_token()
    if real_token:
        threading.Timer(1.5, user_bot.start).start()
    
    # 🔒 审计日志：记录实际变更的字段
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    
    changed_fields = []
    # 检查哪些字段实际发生了变化
    if old_values["tg_bot_token"] != data.tg_bot_token:
        changed_fields.append("tg_bot_token")
    if old_values["tg_user_bot_token"] != data.tg_user_bot_token:
        changed_fields.append("tg_user_bot_token")
    if old_values["wecom_corpsecret"] != data.wecom_corpsecret:
        changed_fields.append("wecom_corpsecret")
    if old_values["wecom_token"] != data.wecom_token:
        changed_fields.append("wecom_token")
    if old_values["wecom_aeskey"] != data.wecom_aeskey:
        changed_fields.append("wecom_aeskey")
    if old_values["enable_bot"] != data.enable_bot:
        changed_fields.append("enable_bot")
    if old_values["user_bot_open_reg"] != data.user_bot_open_reg:
        changed_fields.append("user_bot_open_reg")
    
    log_audit(
        action="config_update",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=get_client_ip(request),
        resource_type="bot_settings",
        details={
            "page": "机器人助手",
            "changed_fields": changed_fields
        }
    )
    
    return {"status": "success", "message": "配置已保存"}

@router.post("/api/bot/open_reg_notify")
def api_send_open_reg_notify(request: Request, data: dict):
    """发送开放注册状态变更通知"""
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    is_open = data.get("is_open", False)
    notify_user = is_user_bot_open_reg_notify_user_enabled()
    notify_group = is_user_bot_open_reg_notify_group_enabled()
    
    if not notify_user and not notify_group:
        return {"status": "success", "message": "未开启通知"}
    
    # 准备消息内容
    if is_open:
        msg = """🎉 <b>开放注册已开启</b>

✨ 本服务器现已开放注册！
🎟️ 快来注册你的专属账号吧~
📱 私聊机器人发送 /register 即可开始

⏰ 开启时间：{}""".format(
            __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")
        )
    else:
        msg = """📢 <b>开放注册已结束</b>

🙏 感谢大家的支持！
📊 本次开放注册已圆满结束
💌 如有疑问请联系管理员

⏰ 结束时间：{}""".format(
            __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")
        )
    
    sent_count = 0
    
    # 发送到用户机器人私聊（所有启动过机器人的用户）
    if notify_user:
        try:
            from app.bot.user_bot import user_bot_binding_service, user_bot_telegram_service
            users = user_bot_binding_service.get_all_bot_users()
            if users:
                for u in users:
                    tg_id = u.get('tg_user_id')
                    try:
                        user_bot_telegram_service.send(int(tg_id), msg)
                        sent_count += 1
                    except Exception as e:
                        logger.error(f"[开放注册通知] 发送给用户 {tg_id} 失败: {e}")
        except Exception as e:
            logger.error(f"[开放注册通知] 用户私聊通知失败: {e}")
    
    # 发送到群聊（使用用户机器人）
    if notify_group:
        try:
            from app.bot.user_bot import user_bot_telegram_service
            allowed_groups = get_user_bot_allowed_groups()
            if allowed_groups:
                group_ids = [g.strip() for g in allowed_groups.replace('，', ',').split('\n') if g.strip()]
                for gid in group_ids:
                    try:
                        user_bot_telegram_service.send(int(gid), msg)
                        sent_count += 1
                    except Exception as e:
                        logger.error(f"[开放注册通知] 发送到群 {gid} 失败: {e}")
            else:
                logger.warning("[开放注册通知] 未配置群 ID，跳过群聊通知")
        except Exception as e:
            logger.error(f"[开放注册通知] 群聊通知失败: {e}")
    
    return {"status": "success", "message": f"通知已发送至 {sent_count} 个目标"}

@router.post("/api/bot/test")
def api_test_bot(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    token = get_tg_bot_token(); chat_id = get_tg_chat_id()
    from app.utils.proxy_helper import get_safe_proxies
    
    if not token: return {"status": "error", "message": "请先保存配置"}
    
    # 🔒 检查 token 是否被脱敏（配置文件被污染）
    if "****" in token:
        return {"status": "error", "message": "Token 无效（包含脱敏标记），请重新输入完整的 Token"}
    
    try:
        proxies = get_safe_proxies()
        res = telegram_client.send_message(token, {"chat_id": chat_id, "text": "🎉 测试消息"}, proxies=proxies, timeout=10)
        return {"status": "success"} if res.status_code == 200 else {"status": "error", "message": f"API Error: {res.text}"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/test_wecom")
def api_test_wecom(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    wecom_config = get_wecom_runtime_config()
    corpid = wecom_config["corpid"]; corpsecret = wecom_config["corpsecret"]; agentid = wecom_config["agentid"]
    from app.utils.proxy_helper import get_safe_wecom_base
    proxy_url = get_safe_wecom_base()
    touser = wecom_config["touser"]
    
    if not corpid or not corpsecret or not agentid:
        return {"status": "error", "message": "请填写完整的企业微信基础配置"}
    try:
        token_res = wecom_client.get_access_token(proxy_url, corpid, corpsecret, timeout=5).json()
        if token_res.get("errcode") != 0: return {"status": "error", "message": f"Token 获取失败: {token_res.get('errmsg')}"}
        access_token = token_res["access_token"]
        msg_res = wecom_client.send_message(
            proxy_url,
            access_token,
            {
                "touser": touser, "msgtype": "markdown", "agentid": int(agentid),
                "markdown": {"content": "🎉 <font color=\"info\">企业微信通道测试成功！</font>\n\n> EmbyPulse 已成功接入代理推送与双向交互通道。"}
            },
            timeout=10,
        ).json()
        if msg_res.get("errcode") == 0: return {"status": "success"}
        else: return {"status": "error", "message": f"发送失败: {msg_res.get('errmsg')}"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/test_channel")
async def api_test_channel(request: Request):
    """测试频道通知"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    token = get_tg_bot_token()
    if not token: return {"status": "error", "message": "请先配置管理机器人 Token"}
    
    try:
        data = await request.json()
        chat_id = data.get("chat_id", "")
        name = data.get("name", "")
    except:
        return {"status": "error", "message": "参数错误"}
    
    if not chat_id: return {"status": "error", "message": "请输入频道 ID"}

    from app.utils.proxy_helper import get_safe_proxies
    proxies = get_safe_proxies()
    
    try:
        res = telegram_client.send_message(
            token,
            {
                "chat_id": chat_id,
                "text": f"📢 <b>频道通知测试成功</b>\n\n频道: {name or chat_id}\n时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n✅ EmbyPulse 已成功连接到此频道，入库通知将推送到这里。",
                "parse_mode": "HTML"
            },
            proxies=proxies,
            timeout=10
        )
        if res.status_code == 200:
            return {"status": "success", "message": "测试消息已发送"}
        else:
            err = res.json().get("description", res.text)
            return {"status": "error", "message": f"发送失败: {err}"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

def get_playback_url(item_id):
    base_url = get_webhook_base_url()
    if base_url.endswith('/'): base_url = base_url[:-1]
    return f"{base_url}/web/index.html#!/item?id={item_id}"

@router.post("/api/bot/webhook")
async def telegram_webhook(request: Request):
    import secrets as _secrets
    # 🔒 安全：Token 从 Header 或 POST body 获取，避免 URL 泄露
    header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    body_data = await request.json()
    body_token = body_data.get("secret_token") if isinstance(body_data, dict) else None
    expected_token = get_tg_bot_token()

    # 🔒 安全：expected_token 未配置时拒绝所有请求
    if not expected_token:
        logger.warning("[TG Webhook] tg_bot_token 未配置，拒绝请求")
        return {"status": "error", "message": "Unauthorized"}

    # 🔒 安全：常量时间比对，防止时序攻击
    token_valid = (
        (header_token is not None and _secrets.compare_digest(str(header_token), str(expected_token))) or
        (body_token is not None and _secrets.compare_digest(str(body_token), str(expected_token)))
    )
    if not token_valid:
        logger.warning("[TG Webhook] Token 验证失败")
        return {"status": "error", "message": "Unauthorized"}
    
    # 移除 secret_token 避免后续处理泄露
    if isinstance(body_data, dict) and "secret_token" in body_data:
        body_data.pop("secret_token")
    data = body_data
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]
        if text.startswith("/search"):
            keyword = text.replace("/search", "").strip()
            if not keyword:
                send_tg_msg(chat_id, "🔍 请输入关键词，例如: /search 你的名字")
            else:
                items = search_emby(keyword)
                if not items: send_tg_msg(chat_id, "TxT 未找到相关资源")
                else:
                    msg = f"🔍 搜索结果: {keyword}\n\n"
                    for item in items[:5]:
                        link = get_playback_url(item['Id'])
                        msg += f"🎬 <b>{item['Name']}</b> ({item.get('ProductionYear', 'N/A')})\n🔗 <a href='{link}'>点击播放</a>\n\n"
                    send_tg_msg(chat_id, msg)
        elif text == "/start":
            send_tg_msg(chat_id, "👋 欢迎使用 EmbyPulse 机器人！\n支持指令:\n/search <关键词> - 搜索资源")
    return {"status": "success"}

def search_emby(keyword):
    try:
        res = media_api.get("/Items", params={
            "Recursive": "true",
            "SearchTerm": keyword,
            "IncludeItemTypes": "Movie,Series",
            "Limit": 5,
        }, timeout=5)
        if res.status_code == 200:
            return res.json().get("Items", [])
    except Exception: pass
    return []

def send_tg_msg(chat_id, text):
    token = get_tg_bot_token()
    from app.utils.proxy_helper import get_safe_proxies
    proxies = get_safe_proxies()
    try: telegram_client.send_message(token, {"chat_id": chat_id,"text": text,"parse_mode": "HTML"}, proxies=proxies, timeout=10)
    except Exception: pass

# ================= 🔥 企微 API 回调交互 (增强查错与防护版) =================
def decrypt_wecom_data(encrypt_msg):
    if not AES: 
        raise Exception("环境缺少 pycryptodome 依赖，请在 requirements.txt 中添加并重新 build 镜像")
    aeskey = get_wecom_aeskey()
    if not aeskey: 
        raise Exception("系统未配置 wecom_aeskey")
    
    aes_key_bytes = base64.b64decode(aeskey + "=")
    cipher = AES.new(aes_key_bytes, AES.MODE_CBC, aes_key_bytes[:16])
    decrypted = cipher.decrypt(base64.b64decode(encrypt_msg))
    pad = decrypted[-1]
    decrypted = decrypted[:-pad]
    msg_len = struct.unpack("!I", decrypted[16:20])[0]
    return decrypted[20:20+msg_len].decode('utf-8')

def check_wecom_signature(msg_signature, timestamp, nonce, encrypt_msg):
    token = get_wecom_token()
    sort_list = [token, timestamp, nonce, encrypt_msg]
    sort_list.sort()
    sha = hashlib.sha1()
    sha.update("".join(sort_list).encode('utf-8'))
    return sha.hexdigest() == msg_signature

@router.get("/api/bot/wecom_webhook")
async def wecom_webhook_get(msg_signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""):
    try:
        # 1. 验证签名
        if not check_wecom_signature(msg_signature, timestamp, nonce, echostr):
            logger.error("WeCom Webhook: 签名校验不通过 (可能是 Token 不匹配)")
            return "Signature Error"
        
        # 2. 解密字符串
        msg = decrypt_wecom_data(echostr)
        logger.info(f"WeCom Webhook: 验证成功，准备向企微放行")
        return Response(content=msg, media_type="text/plain")
        
    except Exception as e:
        logger.error(f"WeCom Webhook 解析崩溃: {str(e)}")
        return "Internal Error"

@router.post("/api/bot/wecom_webhook")
async def wecom_webhook_post(request: Request, msg_signature: str = "", timestamp: str = "", nonce: str = ""):
    try:
        body = await request.body()
        xml_tree = ET.fromstring(body)
        encrypt_msg = xml_tree.find("Encrypt")
        if encrypt_msg is None:
            logger.error("[企微回调] 未找到 Encrypt 节点")
            return "No Encrypt Node"
        
        encrypt_msg = encrypt_msg.text
        
        if not check_wecom_signature(msg_signature, timestamp, nonce, encrypt_msg):
            logger.error("[企微回调] 签名校验失败，请检查 Token 配置")
            return "Signature Error"
        
        xml_content = decrypt_wecom_data(encrypt_msg)
        msg_tree = ET.fromstring(xml_content)
        
        from_user = msg_tree.find("FromUserName")
        from_user = from_user.text if from_user is not None else "unknown"
        
        msg_type_elem = msg_tree.find("MsgType")
        msg_type = msg_type_elem.text if msg_type_elem is not None else "unknown"
        
        command_text = ""
        if msg_type == "text":
            content_elem = msg_tree.find("Content")
            command_text = content_elem.text if content_elem is not None else ""
        elif msg_type == "event":
            event_elem = msg_tree.find("Event")
            event_type = event_elem.text if event_elem is not None else ""
            
            if event_type == "click":
                event_key_elem = msg_tree.find("EventKey")
                command_text = event_key_elem.text if event_key_elem is not None else ""
        
        if command_text:
            logger.info(f"[企微回调] 处理命令: {command_text} (来自: {from_user})")
            threading.Thread(target=bot.notifier._handle_message, args=(command_text, from_user, "wecom")).start()
            
        return Response(content="success", media_type="text/plain")
    except Exception as e:
        logger.error(f"[企微回调] 处理异常: {str(e)}")
        return "Error"


# ==========================================
# 🤖 用户机器人黑名单管理
# ==========================================
@router.get("/api/bot/user_blacklist")
def api_get_user_blacklist(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        rows = list_user_blacklist()
        return {"status": "success", "data": [dict(r) for r in rows]}
    except:
        return {"status": "success", "data": []}


@router.post("/api/bot/user_blacklist/add")
async def api_add_user_blacklist(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    tg_id = data.get("tg_user_id", "").strip()
    reason = data.get("reason", "管理员手动添加")
    if not tg_id: return {"status": "error", "message": "请输入 TG 用户 ID"}
    from app.bot.user_bot import user_bot_binding_service
    user_bot_binding_service.add_to_blacklist(tg_id, reason)
    return {"status": "success"}


@router.post("/api/bot/user_blacklist/remove")
async def api_remove_user_blacklist(request: Request):
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    tg_id = data.get("tg_user_id", "").strip()
    if not tg_id: return {"status": "error"}
    try:
        remove_user_blacklist(tg_id)
    except Exception: pass
    return {"status": "success"}


# ==========================================
# 🎯 开放注册日志管理
# ==========================================
@router.get("/api/bot/reg_logs")
def api_get_reg_logs(request: Request, days: int = 7):
    """获取开放注册日志"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        rows = list_registration_logs(days)
        return {"status": "success", "data": [dict(r) for r in rows]}
    except Exception as e:
        return {"status": "success", "data": []}


@router.get("/api/bot/reg_stats")
def api_get_reg_stats(request: Request):
    """获取注册统计信息"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        return {"status": "success", "data": get_registration_stats()}
    except Exception as e:
        return {"status": "success", "data": {"today": 0, "week": 0, "total": 0, "batch_used": 0, "daily": []}}


@router.post("/api/bot/reg_logs/clear")
async def api_clear_reg_logs(request: Request):
    """清空注册日志"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        clear_registration_logs()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/bot/reg_batch_reset")
async def api_reset_reg_batch(request: Request):
    """重置批次计数"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    set_user_bot_registration_batch_used(0)
    # 同步重置内存中的 batch_used，避免后台线程把旧值写回
    try:
        from app.bot.user_bot import user_bot_registration_quota_service
        with user_bot_registration_quota_service._batch_used_lock:
            user_bot_registration_quota_service._batch_used_mem = 0
            user_bot_registration_quota_service._batch_used_dirty = 0
    except Exception:
        pass
    return {"status": "success"}


@router.get("/api/bot/reg_quota_status")
async def api_get_reg_quota_status(request: Request):
    """获取名额状态（用于前端显示）"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    from app.bot.user_bot import user_bot_registration_queue_service, user_bot_registration_quota_service

    quota_mode = get_user_bot_reg_quota_mode()
    quota = get_user_bot_reg_quota()
    # 直接读内存权威值，避免 cfg.json 落盘滞后
    batch_used = user_bot_registration_quota_service.get_batch_used_snapshot()

    # 用缓存的 Emby 用户数，避免每次轮询都打 /Users
    try:
        total_users = user_bot_registration_quota_service.get_cached_user_count_for_api()
    except Exception:
        total_users = 0

    # 获取开放注册总数
    open_reg_total = 0
    try:
        open_reg_total = count_registration_logs()
    except:
        pass

    return {
        "status": "success",
        "data": {
            "quota_mode": quota_mode,
            "quota": quota,
            "batch_used": batch_used,
            "total_users": total_users,
            "open_reg_total": open_reg_total,
            "open_reg_enabled": is_user_bot_open_reg_enabled(),
            "reg_queue": {
                "active": user_bot_registration_queue_service._reg_active,
                "waiting": user_bot_registration_queue_service._reg_waiters,
                "max": user_bot_registration_queue_service.MAX_CONCURRENT_REG,
            },
        }
    }

@router.post("/api/bot/sync_tg_usernames")
def api_sync_tg_usernames(request: Request):
    """同步已绑定用户的 TG 用户名和显示名称"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        # 获取所有已绑定用户
        rows = list_tg_bindings_for_sync()

        if not rows:
            return {"status": "success", "data": {"updated": 0, "skipped": 0}, "message": "没有已绑定用户"}

        # 获取用户机器人 token
        bot_token = get_user_bot_token()
        if not bot_token:
            return {"status": "error", "message": "用户机器人未配置"}

        updated = 0
        skipped = 0

        for row in rows:
            tg_user_id = row['tg_user_id']
            existing_username = row['tg_username']
            existing_display_name = row['tg_display_name']
            
            # 调用 Telegram API 获取用户信息
            try:
                # 使用代理
                from app.utils.proxy_helper import get_safe_proxies
                proxies = get_safe_proxies()
                
                res = telegram_client.get_api(bot_token, "getChat", params={"chat_id": tg_user_id}, timeout=15, proxies=proxies)
                
                # 检查响应状态
                if res.status_code != 200:
                    logger.error(f"TG API 返回非200: {res.status_code} - {res.text[:200]}")
                    skipped += 1
                    continue
                
                data = res.json()
                
                if data.get("ok"):
                    result = data.get("result", {})
                    username = result.get("username", "")
                    first_name = result.get("first_name", "")
                    last_name = result.get("last_name", "")
                    display_name = f"{first_name} {last_name}".strip() if last_name else first_name
                    
                    # 更新数据库（用户名或显示名称有变化时更新）
                    need_update = False
                    if username and not existing_username:
                        need_update = True
                    if display_name and not existing_display_name:
                        need_update = True

                    if need_update:
                        update_tg_binding_names(tg_user_id, username, display_name)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"获取 TG 用户信息失败: {e}")
                skipped += 1

        return {"status": "success", "data": {"updated": updated, "skipped": skipped}}

    except Exception as e:
        logger.error(f"同步 TG 用户名失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/bot/tg_bindings")
def api_get_tg_bindings(request: Request):
    """获取已绑定用户列表"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        rows = list_tg_bindings()
        bindings = []
        for row in rows:
            bindings.append({
                "tg_user_id": row['tg_user_id'],
                "emby_user_id": row['emby_user_id'],
                "emby_username": row['emby_username'],
                "tg_username": row['tg_username'] or "",
                "tg_display_name": row['tg_display_name'] or "",
                "bound_at": row['bound_at']
            })

        return {"status": "success", "data": bindings}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/lottery_draw")
def api_lottery_draw(request: Request):
    """手动开奖彩票"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    try:
        from app.bot.user_bot import user_bot_lottery_draw_service
        user_bot_lottery_draw_service.do_lottery_draw()

        # 获取开奖结果
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        result = get_lottery_draw_result(today)

        if result and result[0]:
            return {
                "status": "success",
                "data": {
                    "winning_numbers": result[0],
                    "total_pool": result[1]
                }
            }
        else:
            return {"status": "error", "message": "开奖失败或没有彩票"}
            
    except Exception as e:
        logger.error(f"手动开奖失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/lottery_reset")
def api_lottery_reset(request: Request):
    """清除今日开奖记录"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        reset_result = reset_lottery_draw(today, tomorrow)
        if not reset_result["ok"]:
            return {"status": "error", "message": reset_result["message"]}

        remaining_pool = reset_result["remaining_pool"]
        if remaining_pool > 0:
            logger.info(f"[彩票] 从明天奖池中回退 {remaining_pool} 积分")

        logger.info(f"[彩票] 管理员清除今日开奖记录: {today}, 回退剩余奖池: {remaining_pool}")
        return {"status": "success", "message": f"今日开奖记录已清除，回退剩余奖池 {remaining_pool} 积分"}

    except Exception as e:
        logger.error(f"清除开奖记录失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/lottery_fix_pool")
def api_lottery_fix_pool(request: Request):
    """修复奖池：重新计算正确的奖池值"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        result = fix_lottery_pool(today, tomorrow)

        if result["drawn"]:
            logger.info(f"[彩票] 修复明日奖池: {result['new_pool']} (剩余{result['remaining']} + 购票{result['ticket_pool']})")
            return {
                "status": "success",
                "data": {
                    "new_pool": result["new_pool"],
                    "remaining": result["remaining"],
                    "ticket_pool": result["ticket_pool"],
                },
            }

        logger.info(f"[彩票] 修复今日奖池: {result['new_pool']}")
        return {"status": "success", "data": {"new_pool": result["new_pool"]}}

    except Exception as e:
        logger.error(f"修复奖池失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/scratch_clear")
def api_scratch_clear(request: Request):
    """清除当前刮刮卡"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        result = clear_active_scratch_card()
        if not result["ok"]:
            return {"status": "error", "message": result["message"]}

        logger.info(f"[刮刮乐] 管理员清除刮刮卡 #{result['card_id']}")
        return {"status": "success", "message": f"已清除刮刮卡 #{result['card_id']}，退还 {result['refund_count']} 人积分"}

    except Exception as e:
        logger.error(f"清除刮刮卡失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/bot/lottery_pool")
def api_lottery_pool(request: Request):
    """获取当前奖池信息"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        # 获取配置
        config = point_dao.get_point_config()
        draw_hour = int(config.get('lottery_draw_hour', 20))
        max_per_day = int(config.get('lottery_max_per_day', 10))

        pool_info = get_lottery_pool_info(today, tomorrow)
        if pool_info["is_drawn"]:
            # 今天已开奖，显示明天的奖池
            next_draw_time = f"明天 {(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%m-%d')} {draw_hour}:00"
        else:
            next_draw_time = f"今天 {datetime.datetime.now().strftime('%m-%d')} {draw_hour}:00"

        return {
            "status": "success",
            "data": {
                "today_pool": pool_info["target_pool"],
                "today_tickets": pool_info["target_tickets"],
                "total_accumulated": pool_info["total_accumulated"],
                "target_date": pool_info["target_date"],
                "next_draw_time": next_draw_time,
                "draw_hour": draw_hour,
                "max_per_day": max_per_day,
                "is_drawn": pool_info["is_drawn"]
            }
        }

    except Exception as e:
        logger.error(f"获取奖池信息失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/bot/lottery_init_pool")
def api_lottery_init_pool(request: Request, data: dict):
    """设置初始奖池"""
    if not user_service.is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        init_pool = int(data.get("init_pool", 0))
        if init_pool == 0:
            return {"status": "error", "message": "请输入调整数值"}

        today = datetime.datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        result = adjust_lottery_pool(today, tomorrow, init_pool)

        return {"status": "success", "data": result}

    except Exception as e:
        logger.error(f"设置初始奖池失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}
