import glob
import io
import logging
import os
import re
import time

from app.core.config import REPORT_COVER_URL
from app.infra.clients.media_server_client import media_api
from app.infra.clients.wecom_client import wecom_client
from app.infra.config.media_server_settings import (
    get_media_server_api_key,
    get_media_server_host,
    get_media_server_main_public_or_host,
)
from app.infra.config.notification_settings import (
    get_pulse_url,
    get_wecom_agentid,
    get_wecom_corpid,
    get_wecom_corpsecret,
)
from app.utils.proxy_helper import get_safe_wecom_base


logger = logging.getLogger("uvicorn")

_wecom_corpid_provider = lambda: get_wecom_corpid
_wecom_corpsecret_provider = lambda: get_wecom_corpsecret
_wecom_agentid_provider = lambda: get_wecom_agentid
_safe_wecom_base_provider = lambda: get_safe_wecom_base
_pulse_url_provider = lambda: get_pulse_url
_media_server_main_public_or_host_provider = lambda: get_media_server_main_public_or_host
_media_server_host_provider = lambda: get_media_server_host
_media_server_api_key_provider = lambda: get_media_server_api_key
_wecom_client_provider = lambda: wecom_client
_media_api_provider = lambda: media_api
_report_cover_url_provider = lambda: REPORT_COVER_URL
_logger_provider = lambda: logger
_time_provider = lambda: time


def set_dependency_providers(
    *,
    wecom_corpid_provider=None,
    wecom_corpsecret_provider=None,
    wecom_agentid_provider=None,
    safe_wecom_base_provider=None,
    pulse_url_provider=None,
    media_server_main_public_or_host_provider=None,
    media_server_host_provider=None,
    media_server_api_key_provider=None,
    wecom_client_provider=None,
    media_api_provider=None,
    report_cover_url_provider=None,
    logger_provider=None,
    time_provider=None,
):
    global _wecom_corpid_provider
    global _wecom_corpsecret_provider
    global _wecom_agentid_provider
    global _safe_wecom_base_provider
    global _pulse_url_provider
    global _media_server_main_public_or_host_provider
    global _media_server_host_provider
    global _media_server_api_key_provider
    global _wecom_client_provider
    global _media_api_provider
    global _report_cover_url_provider
    global _logger_provider
    global _time_provider

    if wecom_corpid_provider is not None:
        _wecom_corpid_provider = wecom_corpid_provider
    if wecom_corpsecret_provider is not None:
        _wecom_corpsecret_provider = wecom_corpsecret_provider
    if wecom_agentid_provider is not None:
        _wecom_agentid_provider = wecom_agentid_provider
    if safe_wecom_base_provider is not None:
        _safe_wecom_base_provider = safe_wecom_base_provider
    if pulse_url_provider is not None:
        _pulse_url_provider = pulse_url_provider
    if media_server_main_public_or_host_provider is not None:
        _media_server_main_public_or_host_provider = media_server_main_public_or_host_provider
    if media_server_host_provider is not None:
        _media_server_host_provider = media_server_host_provider
    if media_server_api_key_provider is not None:
        _media_server_api_key_provider = media_server_api_key_provider
    if wecom_client_provider is not None:
        _wecom_client_provider = wecom_client_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if time_provider is not None:
        _time_provider = time_provider


def get_wecom_token(bot):
    corpid = _wecom_corpid_provider()()
    corpsecret = _wecom_corpsecret_provider()()
    proxy_url = _safe_wecom_base_provider()()
    if not corpid or not corpsecret:
        return None
    if bot.wecom_token and _time_provider().time() < bot.wecom_token_expires:
        return bot.wecom_token
    try:
        res = _wecom_client_provider().get_access_token(proxy_url, corpid, corpsecret, timeout=5).json()
        if res.get("errcode") == 0:
            bot.wecom_token = res["access_token"]
            bot.wecom_token_expires = _time_provider().time() + res["expires_in"] - 60
            _logger_provider().info(f"[企业微信] 获取 access_token 成功，有效期 {res['expires_in']} 秒")
            return bot.wecom_token
        else:
            _logger_provider().error(f"[企业微信] 获取 access_token 失败: errcode={res.get('errcode')}, errmsg={res.get('errmsg')}")
    except Exception as e:
        _logger_provider().error(f"[企业微信] 获取 access_token 异常: {e}")
    return None


def html_to_wecom_text(html_text, inline_keyboard=None):
    text = html_text.replace("<b>", "【").replace("</b>", "】").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
    text = re.sub(r"<a\s+href=['\"](.*?)['\"]>(.*?)</a>", r"\2: \1", text)
    if inline_keyboard and "inline_keyboard" in inline_keyboard:
        text += "\n\n"
        for row in inline_keyboard["inline_keyboard"]:
            for btn in row:
                if "text" in btn and "url" in btn:
                    text += f"🔗 {btn['text']}: {btn['url']}\n"
    return text.strip()


def set_wecom_menu(bot):
    token = bot._get_wecom_token()
    agentid = _wecom_agentid_provider()()
    proxy_url = _safe_wecom_base_provider()()
    if not token or not agentid:
        return

    menu_data = {
        "button": [
            {
                "name": "数据大盘",
                "sub_button": [
                    {"type": "click", "name": "📈 今日日报", "key": "/stats"},
                    {"type": "click", "name": "📅 本周周报", "key": "/weekly"},
                    {"type": "click", "name": "🗓️ 本月月报", "key": "/monthly"},
                ],
            },
            {
                "name": "媒体大厅",
                "sub_button": [
                    {"type": "click", "name": "🟢 正在播放", "key": "/now"},
                    {"type": "click", "name": "🆕 最近入库", "key": "/latest"},
                    {"type": "click", "name": "📜 播放记录", "key": "/recent"},
                ],
            },
            {
                "name": "系统运维",
                "sub_button": [
                    {"type": "click", "name": "🔍 资源搜索", "key": "/search"},
                    {"type": "click", "name": "📡 系统探针", "key": "/check"},
                    {"type": "click", "name": "🤖 帮助菜单", "key": "/help"},
                ],
            },
        ]
    }

    try:
        res = _wecom_client_provider().create_menu(proxy_url, token, agentid, menu_data, timeout=5)
        res_data = res.json()
        if res_data.get("errcode") == 0:
            _logger_provider().info("✅ [企微助手] 底部三栏菜单推送成功！")
        else:
            _logger_provider().error(f"❌ [企微助手] 菜单推送失败！错误码: {res_data.get('errcode')}, 详情: {res_data.get('errmsg')}")
    except Exception as e:
        _logger_provider().error(f"❌ [企微助手] 菜单请求发生网络异常: {e}")


def send_wecom_message(bot, text, inline_keyboard=None, touser="@all"):
    token = bot._get_wecom_token()
    agentid = _wecom_agentid_provider()()
    proxy_url = _safe_wecom_base_provider()()

    if not token:
        _logger_provider().warning("[企业微信] 获取 access_token 失败，请检查 wecom_corpid 和 wecom_corpsecret 配置")
        return
    if not agentid:
        _logger_provider().warning("[企业微信] 未配置 wecom_agentid")
        return

    _logger_provider().info(f"[企业微信] 准备发送消息: touser={touser}, agentid={agentid}")

    try:
        content = bot._html_to_wecom_text(text, inline_keyboard)
        if len(content.encode("utf-8")) > 2048:
            suffix = "\n\n[字数超限已被截断...]"
            max_bytes = 2048 - len(suffix.encode("utf-8")) - 5
            content = content.encode("utf-8")[:max_bytes].decode("utf-8", "ignore") + suffix

        res = _wecom_client_provider().send_message(
            proxy_url,
            token,
            {"touser": touser, "msgtype": "text", "agentid": int(agentid), "text": {"content": content}},
            timeout=10,
        )
        res_json = res.json() if res.text else {}
        if res_json.get("errcode") == 0:
            _logger_provider().info(f"[企业微信] 消息发送成功: touser={touser}")
        else:
            errcode = res_json.get("errcode")
            errmsg = res_json.get("errmsg", "")
            _logger_provider().error(f"[企业微信] 消息发送失败: errcode={errcode}, errmsg={errmsg}")
            if errcode == 81013:
                _logger_provider().error(f"[企业微信] 错误81013: touser '{touser}' 无效。请配置 wecom_touser 为具体用户ID，或在企业微信后台给应用添加'发送到所有人'权限")
    except Exception as e:
        _logger_provider().error(f"[企业微信] 消息发送异常: {e}")


def send_wecom_photo(bot, photo_bytes, html_text, inline_keyboard=None, touser="@all"):
    token = bot._get_wecom_token()
    agentid = _wecom_agentid_provider()()
    proxy_url = _safe_wecom_base_provider()()
    if not token or not agentid:
        return

    pic_url = _report_cover_url_provider()
    upload_success = False

    try:
        if photo_bytes and len(photo_bytes) > 0:
            if len(photo_bytes) > 2 * 1024 * 1024:
                _logger_provider().debug(f"[企业微信] 图片过大 ({len(photo_bytes)} bytes)，尝试压缩")
                try:
                    from PIL import Image

                    img = Image.open(io.BytesIO(photo_bytes))
                    output = io.BytesIO()
                    img.save(output, format="JPEG", quality=70, optimize=True)
                    photo_bytes = output.getvalue()
                    _logger_provider().debug(f"[企业微信] 压缩后大小: {len(photo_bytes)} bytes")
                except Exception as e:
                    _logger_provider().debug(f"[企业微信] 图片压缩失败: {e}")

            _logger_provider().info(f"[企业微信] 开始上传图片，大小: {len(photo_bytes)} bytes")
            _logger_provider().info(f"[企业微信] 上传URL: {proxy_url.rstrip('/')}/cgi-bin/media/uploadimg?access_token=***")
            upload_res = _wecom_client_provider().upload_image(proxy_url, token, {"media": ("image.jpg", photo_bytes, "image/jpeg")}, timeout=15)
            if upload_res.status_code == 200 and upload_res.text.strip():
                resp_json = upload_res.json()
                if "url" in resp_json:
                    pic_url = resp_json["url"]
                    upload_success = True
                    _logger_provider().info(f"[企业微信] 图片上传成功: {pic_url[:60]}...")
                else:
                    errcode = resp_json.get("errcode")
                    errmsg = resp_json.get("errmsg", "")
                    _logger_provider().warning(f"[企业微信] 图片上传失败: errcode={errcode}, errmsg={errmsg}")
            else:
                _logger_provider().warning(f"[企业微信] 图片上传请求失败: status={upload_res.status_code}")
    except Exception as e:
        _logger_provider().warning(f"[企业微信] 图片上传异常: {e}")

    if not upload_success:
        if inline_keyboard and "inline_keyboard" in inline_keyboard:
            try:
                play_url = inline_keyboard["inline_keyboard"][0][0].get("url", "")
                match = re.search(r"id=([a-zA-Z0-9]+)", play_url)
                if match:
                    item_id = match.group(1)
                    base_emby = (_media_server_main_public_or_host_provider()() or _media_server_host_provider()() or "").rstrip("/")
                    api_key = _media_server_api_key_provider()() or ""
                    if base_emby and api_key:
                        pic_url = f"{base_emby}/emby/Items/{item_id}/Images/Backdrop?maxWidth=800&api_key={api_key}"
                        _logger_provider().info("[企业微信] 使用 Emby 横版图片作为封面")
            except Exception as e:
                _logger_provider().debug(f"[企业微信] 提取图片URL失败: {e}")

        if pic_url == _report_cover_url_provider() and photo_bytes:
            try:
                public_dir = "/app/public"
                if not os.path.exists(public_dir):
                    public_dir = "/public"
                if not os.path.exists(public_dir):
                    public_dir = os.path.join(os.getcwd(), "public")
                    os.makedirs(public_dir, exist_ok=True)

                try:
                    max_age_seconds = 7 * 24 * 3600
                    current_time = _time_provider().time()
                    for old_file in glob.glob(os.path.join(public_dir, "report_*.jpg")):
                        if current_time - os.path.getmtime(old_file) > max_age_seconds:
                            os.remove(old_file)
                            _logger_provider().debug(f"[企业微信] 清理旧图片: {old_file}")
                except Exception as e:
                    _logger_provider().debug(f"[企业微信] 清理旧图片失败: {e}")

                report_filename = f"report_{int(_time_provider().time())}.jpg"
                report_path = os.path.join(public_dir, report_filename)
                with open(report_path, "wb") as f:
                    f.write(photo_bytes)

                pulse_url = _pulse_url_provider()()
                if pulse_url:
                    pic_url = f"{pulse_url.rstrip('/')}/public/{report_filename}"
                    _logger_provider().info(f"[企业微信] 使用本地图片URL: {pic_url}")
            except Exception as e:
                _logger_provider().warning(f"[企业微信] 保存本地图片失败: {e}")

        _logger_provider().info(f"[企业微信] 使用网络图片作为封面: {pic_url[:60]}...")
        upload_success = True

    try:
        plain_text = re.sub(r"<[^>]+>", "", html_text).strip()
        lines = [line.strip() for line in plain_text.split("\n")]

        title = lines[0] if lines else "EmbyPulse 通知"
        if len(title.encode("utf-8")) > 128:
            title = title.encode("utf-8")[:120].decode("utf-8", "ignore") + "..."

        desc = re.sub(r"\n{3,}", "\n\n", "\n".join(lines[1:]).strip()) if len(lines) > 1 else ""
        if len(desc.encode("utf-8")) > 512:
            suffix = "...\n[字数超限，点击卡片阅读完整详情]"
            max_bytes = 512 - len(suffix.encode("utf-8")) - 5
            desc = desc.encode("utf-8")[:max_bytes].decode("utf-8", "ignore") + suffix

        jump_url = _media_server_main_public_or_host_provider()() or _media_server_host_provider()() or "https://emby.media"
        if inline_keyboard and "inline_keyboard" in inline_keyboard:
            try:
                jump_url = inline_keyboard["inline_keyboard"][0][0]["url"]
            except Exception:
                pass
        else:
            links = re.findall(r"href=['\"](.*?)['\"]", html_text)
            if links:
                jump_url = links[0]

        item_id_match = re.search(r"id=([a-zA-Z0-9]+)", jump_url)
        if item_id_match and pic_url == _report_cover_url_provider():
            item_id = item_id_match.group(1)
            base_emby = (_media_server_main_public_or_host_provider()() or _media_server_host_provider()()).rstrip("/")
            api_key = _media_server_api_key_provider()()

            img_type = "Backdrop"
            try:
                if _media_api_provider().request("HEAD", f"/Items/{item_id}/Images/Backdrop", timeout=2).status_code != 200:
                    img_type = "Primary"
            except Exception:
                pass
            pic_url = f"{base_emby}/emby/Items/{item_id}/Images/{img_type}?maxWidth=800&api_key={api_key}"

        pulse_url = _pulse_url_provider()()
        if pulse_url and any(kw in title for kw in ["求片", "心愿", "报错", "工单", "风控", "系统告警", "安全告警"]):
            base_pulse = pulse_url.rstrip("/")
            if "求片" in title or "心愿" in title:
                jump_url = f"{base_pulse}/requests_admin"
            elif "报错" in title or "工单" in title:
                jump_url = f"{base_pulse}/requests_admin"
            elif "风控" in title:
                jump_url = f"{base_pulse}/risk"
            elif "用户" in title:
                jump_url = f"{base_pulse}/users"
            else:
                jump_url = base_pulse

        news_payload = {
            "touser": touser,
            "msgtype": "news",
            "agentid": int(agentid),
            "news": {
                "articles": [
                    {
                        "title": title,
                        "description": desc,
                        "url": jump_url,
                        "picurl": pic_url,
                    }
                ]
            },
        }
        _logger_provider().debug(f"[企业微信] 发送图文消息: title={title[:30]}..., pic_url={pic_url[:50]}...")
        res = _wecom_client_provider().send_message(proxy_url, token, news_payload, timeout=10)
        res_json = res.json() if res.text else {}
        if res_json.get("errcode") == 0:
            _logger_provider().debug(f"[企业微信] 图文消息发送成功: touser={touser}")
        else:
            _logger_provider().error(f"[企业微信] 图文消息发送失败: errcode={res_json.get('errcode')}, errmsg={res_json.get('errmsg')}")
    except Exception as e:
        _logger_provider().error(f"[企业微信] 发送图文消息异常: {e}")
        bot._send_wecom_message(html_text, inline_keyboard, touser)
