import io
import json
import logging

from app.infra.clients.network_client import network_client
from app.infra.clients.telegram_client import telegram_client
from app.infra.config.bot_settings import get_tg_chat_id
from app.infra.config.notification_settings import (
    get_tg_bot_token,
    get_wecom_corpid,
    get_wecom_touser,
)
from app.utils.proxy_helper import get_safe_proxies


logger = logging.getLogger("uvicorn")

_network_client_provider = lambda: network_client
_telegram_client_provider = lambda: telegram_client
_safe_proxies_provider = lambda: get_safe_proxies
_tg_bot_token_provider = lambda: get_tg_bot_token
_tg_chat_id_provider = lambda: get_tg_chat_id
_wecom_corpid_provider = lambda: get_wecom_corpid
_wecom_touser_provider = lambda: get_wecom_touser
_submit_bot_task_provider = lambda: None
_extract_request_tmdb_id_provider = lambda: None
_record_request_admin_message_provider = lambda: None
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    network_client_provider=None,
    telegram_client_provider=None,
    safe_proxies_provider=None,
    tg_bot_token_provider=None,
    tg_chat_id_provider=None,
    wecom_corpid_provider=None,
    wecom_touser_provider=None,
    submit_bot_task_provider=None,
    extract_request_tmdb_id_provider=None,
    record_request_admin_message_provider=None,
    logger_provider=None,
):
    global _network_client_provider
    global _telegram_client_provider
    global _safe_proxies_provider
    global _tg_bot_token_provider
    global _tg_chat_id_provider
    global _wecom_corpid_provider
    global _wecom_touser_provider
    global _submit_bot_task_provider
    global _extract_request_tmdb_id_provider
    global _record_request_admin_message_provider
    global _logger_provider

    if network_client_provider is not None:
        _network_client_provider = network_client_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if tg_bot_token_provider is not None:
        _tg_bot_token_provider = tg_bot_token_provider
    if tg_chat_id_provider is not None:
        _tg_chat_id_provider = tg_chat_id_provider
    if wecom_corpid_provider is not None:
        _wecom_corpid_provider = wecom_corpid_provider
    if wecom_touser_provider is not None:
        _wecom_touser_provider = wecom_touser_provider
    if submit_bot_task_provider is not None:
        _submit_bot_task_provider = submit_bot_task_provider
    if extract_request_tmdb_id_provider is not None:
        _extract_request_tmdb_id_provider = extract_request_tmdb_id_provider
    if record_request_admin_message_provider is not None:
        _record_request_admin_message_provider = record_request_admin_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _resolve_tg_chat_ids(chat_id):
    raw_cids = str(_tg_chat_id_provider()())
    if chat_id in ["sys_notify", "admin"]:
        return [c.strip() for c in raw_cids.replace("，", ",").split(",") if c.strip()]
    if chat_id.startswith("user_"):
        real_tg_id = chat_id.replace("user_", "")
        return [real_tg_id]
    return [chat_id]


def _download_photo_bytes(photo_io):
    if isinstance(photo_io, str):
        try:
            res = _network_client_provider().get(
                photo_io,
                proxies=_safe_proxies_provider()() if "tmdb" in photo_io.lower() else None,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if res.status_code == 200:
                return res.content
        except Exception:
            pass
        return None
    return photo_io.read()


def send_photo(bot, chat_id, photo_io, caption, parse_mode="HTML", reply_markup=None, platform="all", wecom_photo_io=None):
    _logger_provider().debug(f"[Bot] send_photo called: chat_id={chat_id}, platform={platform}, caption_len={len(caption)}")
    photo_bytes = _download_photo_bytes(photo_io)

    wecom_photo_bytes = photo_bytes
    if wecom_photo_io is not None and wecom_photo_io != photo_io:
        wecom_photo_bytes = _download_photo_bytes(wecom_photo_io)

    if platform in ["all", "wecom"] and _wecom_corpid_provider()():
        wecom_touser = _wecom_touser_provider()()
        _submit_bot_task_provider()(bot._send_wecom_photo, wecom_photo_bytes, caption, reply_markup, wecom_touser)

    if platform in ["all", "tg"] and _tg_bot_token_provider()():
        tg_cids = _resolve_tg_chat_ids(chat_id)
        if chat_id.startswith("user_"):
            _logger_provider().info(f"[Bot] 用户TG照片通知: chat_id={chat_id} -> tg_id={tg_cids[0]}")

        _logger_provider().debug(f"[Bot] send_photo TG: tg_cids={tg_cids}")

        for tg_cid in tg_cids:
            try:
                data = {"chat_id": tg_cid, "caption": caption, "parse_mode": parse_mode}
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)
                if photo_bytes:
                    r = _telegram_client_provider().send_photo(
                        _tg_bot_token_provider()(),
                        data=data,
                        files={"photo": ("image.jpg", io.BytesIO(photo_bytes), "image/jpeg")},
                        proxies=_safe_proxies_provider()(),
                        timeout=20,
                    )
                    _logger_provider().info(f"[Bot] TG photo response: {r.status_code} - {r.text[:300] if r.text else 'empty'}")
                    if r.status_code == 200:
                        try:
                            tmdb_id = _extract_request_tmdb_id_provider()(reply_markup)
                            result = r.json().get("result", {})
                            _record_request_admin_message_provider()(tmdb_id, tg_cid, result.get("message_id"), True, caption)
                        except Exception as e:
                            _logger_provider().error(f"[求片审核同步] 解析发送结果失败: {e}")
                    else:
                        _logger_provider().error("[Bot] TG photo failed, fallback to text")
                        bot.send_message(tg_cid, caption, parse_mode, reply_markup, platform="tg")
                else:
                    bot.send_message(tg_cid, caption, parse_mode, reply_markup, platform="tg")
            except Exception as e:
                _logger_provider().error(f"[Bot] TG photo error: {e}")
                bot.send_message(tg_cid, caption, parse_mode, reply_markup, platform="tg")


def send_message(bot, chat_id, text, parse_mode="HTML", reply_markup=None, platform="all"):
    text_preview = text[:100] + "..." if len(text) > 100 else text
    text_preview = text_preview.replace("\n", " ")
    _logger_provider().info(f"[Bot] 📤 发送消息 -> {chat_id}: {text_preview}")

    if platform in ["all", "wecom"] and _wecom_corpid_provider()():
        wecom_touser = _wecom_touser_provider()()
        _submit_bot_task_provider()(bot._send_wecom_message, text, reply_markup, wecom_touser)

    if platform in ["all", "tg"] and _tg_bot_token_provider()():
        tg_cids = _resolve_tg_chat_ids(chat_id)

        for tg_cid in tg_cids:
            try:
                data = {"chat_id": tg_cid, "text": text, "parse_mode": parse_mode}
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)
                r = _telegram_client_provider().send_message(_tg_bot_token_provider()(), data, proxies=_safe_proxies_provider()(), timeout=10)
                if r.status_code == 200:
                    try:
                        tmdb_id = _extract_request_tmdb_id_provider()(reply_markup)
                        result = r.json().get("result", {})
                        _record_request_admin_message_provider()(tmdb_id, tg_cid, result.get("message_id"), False, text)
                    except Exception as e:
                        _logger_provider().error(f"[求片审核同步] 解析文字发送结果失败: {e}")
                else:
                    _logger_provider().error(f"[Bot] ❌ 发送失败: {r.status_code} - {r.text[:200]}")
            except Exception as e:
                _logger_provider().error(f"[Bot] ❌ 发送异常: {e}")


def edit_message(bot, chat_id, message_id, text, parse_mode="HTML", reply_markup=None, platform="tg"):
    _logger_provider().info(f"[Bot] edit_message called: chat_id={chat_id}, message_id={message_id}")

    if platform != "tg" or not _tg_bot_token_provider()():
        return False

    try:
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        r = _telegram_client_provider().post_api(_tg_bot_token_provider()(), "editMessageText", json=data, proxies=_safe_proxies_provider()(), timeout=10)
        _logger_provider().info(f"[Bot] TG edit response: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        _logger_provider().error(f"[Bot] TG edit error: {e}")
        return False
