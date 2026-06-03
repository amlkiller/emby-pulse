import logging


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger


def set_dependency_providers(*, logger_provider=None):
    global _logger_provider

    if logger_provider is not None:
        _logger_provider = logger_provider


def handle_plugin_callback(data, cid, cq_id, cq):
    if data.startswith("p115_"):
        try:
            from app.plugins.cloud115.plugin import handle_115_callback, handle_115_offline_callback

            if data.startswith("p115_tf_"):
                if handle_115_callback(data, cid, cq_id, "tg"):
                    return True
            elif data.startswith("p115_ol_"):
                if handle_115_offline_callback(data, cid, cq_id, "tg"):
                    return True
        except Exception:
            pass

    if data.startswith("hdhive_sr_"):
        try:
            from app.plugins.hdhive.plugin import handle_hdhive_search_callback

            if handle_hdhive_search_callback(data, cid, cq_id, "tg"):
                return True
        except Exception:
            pass

    if data.startswith("hdhive_tmdb_"):
        try:
            from app.plugins.hdhive.plugin import handle_hdhive_tmdb_callback

            if handle_hdhive_tmdb_callback(data, cid, cq_id, "tg"):
                return True
        except Exception:
            pass

    logger_obj = _logger_provider()
    logger_obj.info(f"[Bot] 检查TMDB分页回调: data={data[:50]}...")
    if data.startswith("hdhive_tmdbprev_") or data.startswith("hdhive_tmdbnext_") or data.startswith("hdhive_tmdbpage_"):
        logger_obj.info(f"[Bot] 匹配到TMDB分页回调: {data}")
        try:
            from app.plugins.hdhive.plugin import handle_hdhive_tmdbpage_callback

            message_id = cq.get("message", {}).get("message_id")
            result = handle_hdhive_tmdbpage_callback(data, cid, cq_id, "tg", message_id)
            logger_obj.info(f"[Bot] TMDB分页回调结果: {result}")
            if result:
                return True
        except Exception as e:
            logger_obj.error(f"[Bot] TMDB分页回调异常: {e}")

    if data.startswith("hdhive_page_"):
        try:
            from app.plugins.hdhive.plugin import handle_hdhive_page_callback

            message_id = cq.get("message", {}).get("message_id")
            if handle_hdhive_page_callback(data, cid, cq_id, "tg", message_id):
                return True
        except Exception:
            pass

    return False


def handle_request_hdhive_callback(data, cid, cq_id):
    if not data.startswith("req_hdhive_"):
        return False
    try:
        from app.plugins.hdhive.plugin import handle_request_hdhive_callback as _handle_request_hdhive_callback

        if _handle_request_hdhive_callback(data, cid, cq_id, "tg"):
            return True
    except Exception as e:
        _logger_provider().error(f"[Bot] 求片影巢搜索回调异常: {e}")
    return False
