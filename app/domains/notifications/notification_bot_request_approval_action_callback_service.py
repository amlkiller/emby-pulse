from app.domains.media_requests import media_request_dao
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.telegram_client import telegram_client
from app.infra.config.moviepilot_settings import get_moviepilot_token, get_moviepilot_url


_media_request_dao_provider = lambda: media_request_dao
_moviepilot_client_provider = lambda: moviepilot_client
_moviepilot_url_provider = lambda: get_moviepilot_url
_moviepilot_token_provider = lambda: get_moviepilot_token
_telegram_client_provider = lambda: telegram_client
_record_request_admin_message_provider = lambda: None
_sync_request_admin_messages_provider = lambda: None


def set_dependency_providers(
    *,
    media_request_dao_provider=None,
    moviepilot_client_provider=None,
    moviepilot_url_provider=None,
    moviepilot_token_provider=None,
    telegram_client_provider=None,
    record_request_admin_message_provider=None,
    sync_request_admin_messages_provider=None,
):
    global _media_request_dao_provider
    global _moviepilot_client_provider
    global _moviepilot_url_provider
    global _moviepilot_token_provider
    global _telegram_client_provider
    global _record_request_admin_message_provider
    global _sync_request_admin_messages_provider

    if media_request_dao_provider is not None:
        _media_request_dao_provider = media_request_dao_provider
    if moviepilot_client_provider is not None:
        _moviepilot_client_provider = moviepilot_client_provider
    if moviepilot_url_provider is not None:
        _moviepilot_url_provider = moviepilot_url_provider
    if moviepilot_token_provider is not None:
        _moviepilot_token_provider = moviepilot_token_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if record_request_admin_message_provider is not None:
        _record_request_admin_message_provider = record_request_admin_message_provider
    if sync_request_admin_messages_provider is not None:
        _sync_request_admin_messages_provider = sync_request_admin_messages_provider


def _parse_action(data):
    if data.startswith("req_approve_"):
        return data.replace("req_approve_", ""), "approve", None
    if data.startswith("req_manual_"):
        return data.replace("req_manual_", ""), "manual", None
    if data.startswith("req_reject_do_"):
        parts = data.split("_")
        tid = parts[3]
        reason_index = int(parts[4])
        reasons = ["影片未上映", "剧集未开播", "未找到可用资源", "质量太差等待洗版"]
        return tid, "reject", reasons[reason_index]
    return None, None, None


def _clear_reply_markup(cid, mid, token, proxies):
    try:
        _telegram_client_provider().post_api(
            token,
            "editMessageReplyMarkup",
            json={"chat_id": cid, "message_id": mid, "reply_markup": {"inline_keyboard": []}},
            proxies=proxies,
            timeout=5,
        )
    except Exception:
        pass


def _subscribe_moviepilot(tid, row):
    mp_url = _moviepilot_url_provider()()
    mp_token = _moviepilot_token_provider()()
    if not mp_url or not mp_token:
        return

    payload = {
        "name": row["title"],
        "tmdbid": int(tid),
        "year": str(row["year"]),
        "type": "电影" if row["media_type"] == "movie" else "电视剧",
    }
    if row["media_type"] == "tv":
        payload["season"] = row["season"]

    try:
        _moviepilot_client_provider().subscribe(mp_url, mp_token, payload, timeout=10)
    except Exception:
        pass


def _apply_action(tid, action_db, reject_reason, rows):
    dao = _media_request_dao_provider()
    if action_db == "approve":
        for row in rows:
            _subscribe_moviepilot(tid, row)
            dao.update_media_request_status(tid, row["season"], 1)
        return "✅ 已审批：推送 MP 自动下载"

    if action_db == "manual":
        for row in rows:
            dao.update_media_request_status(tid, row["season"], 4)
        return "✅ 已审批：管理员手动接单"

    if action_db == "reject":
        for row in rows:
            dao.update_media_request_status(tid, row["season"], 3, reject_reason)
        return f"❌ 已拒绝 ({reject_reason})"

    return None


def _sync_admin_message(tid, action_text, cq, cid, mid, token, proxies):
    msg_obj = cq["message"]
    operator = cq.get("from", {}).get("first_name", "Admin")
    if "caption" in msg_obj:
        orig_caption = msg_obj.get("caption", "求片请求")
        _record_request_admin_message_provider()(tid, cid, mid, True, orig_caption)
        _sync_request_admin_messages_provider()(tid, action_text, operator, token, proxies, orig_caption, True)
    else:
        orig_text = msg_obj.get("text", "求片请求")
        _record_request_admin_message_provider()(tid, cid, mid, False, orig_text)
        _sync_request_admin_messages_provider()(tid, action_text, operator, token, proxies, orig_text, False)


def handle_request_approval_action_callback(data, cq, cid, mid, token, proxies):
    tid, action_db, reject_reason = _parse_action(data)
    if not tid:
        return False

    rows = _media_request_dao_provider().list_pending_requests_by_tmdb(tid)
    if not rows:
        _clear_reply_markup(cid, mid, token, proxies)
        return True

    action_text = _apply_action(tid, action_db, reject_reason, rows)
    _sync_admin_message(tid, action_text, cq, cid, mid, token, proxies)
    return True
