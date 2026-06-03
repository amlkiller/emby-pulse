import logging

from app.domains.media_requests import media_request_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")


_media_request_dao_provider = lambda: media_request_dao
_media_api_provider = lambda: media_api
_admin_id_provider = lambda: (lambda: None)
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    media_request_dao_provider=None,
    media_api_provider=None,
    admin_id_provider=None,
    logger_provider=None,
):
    global _media_request_dao_provider
    global _media_api_provider
    global _admin_id_provider
    global _logger_provider

    if media_request_dao_provider is not None:
        _media_request_dao_provider = media_request_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if admin_id_provider is not None:
        _admin_id_provider = admin_id_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def sync_pending_requests(daemon):
    try:
        media_request_dao_obj = _media_request_dao_provider()
        rows = media_request_dao_obj.list_pending_sync_requests()
        if not rows:
            return

        admin_id = _admin_id_provider()()
        if not admin_id:
            return

        media_api_obj = _media_api_provider()
        logger_obj = _logger_provider()

        for r in rows:
            tid = r["tmdb_id"]
            mtype = r["media_type"]
            sn = r["season"]
            request_type = r.get("request_type", "new")
            episodes_str = r.get("episodes", "")

            type_filter = "Movie" if mtype == "movie" else "Series"
            params = {"AnyProviderIdEquals": f"tmdb.{tid}", "IncludeItemTypes": type_filter, "Recursive": "true"}
            res = media_api_obj.get(f"/Users/{admin_id}/Items", params=params, timeout=5).json()
            if res.get("Items"):
                if mtype == "movie":
                    media_request_dao_obj.mark_sync_request_finished(tid)
                    logger_obj.info(f"[入库同步] 电影已入库: tmdb_id={tid}")
                else:
                    sid = res["Items"][0]["Id"]

                    if request_type == "update" and episodes_str:
                        requested_eps = [int(e) for e in episodes_str.split(",") if e.strip().isdigit()]
                        ep_params = {
                            "ParentId": sid,
                            "IncludeItemTypes": "Episode",
                            "Recursive": "true",
                            "Fields": "ParentIndexNumber,IndexNumber",
                        }
                        ep_res = media_api_obj.get(f"/Users/{admin_id}/Items", params=ep_params, timeout=5).json()
                        local_eps = []
                        for ep in ep_res.get("Items", []):
                            ep_season = ep.get("ParentIndexNumber")
                            ep_num = ep.get("IndexNumber")
                            if ep_season == sn and ep_num:
                                local_eps.append(ep_num)

                        if requested_eps and all(e in local_eps for e in requested_eps):
                            media_request_dao_obj.mark_sync_request_finished(tid, sn)
                            logger_obj.info(f"[入库同步] 追新已入库: tmdb_id={tid}, season={sn}, episodes={episodes_str}")
                    else:
                        s_res = media_api_obj.get(f"/Shows/{sid}/Seasons", params={"UserId": admin_id}, timeout=5).json()
                        local_seasons = [s.get("IndexNumber") for s in s_res.get("Items", [])]
                        if sn in local_seasons:
                            media_request_dao_obj.mark_sync_request_finished(tid, sn)
                            logger_obj.info(f"[入库同步] 求片已入库: tmdb_id={tid}, season={sn}")
            if daemon._stop_event.wait(0.5):
                return
    except Exception as e:
        _logger_provider().error(f"[入库同步] 定时同步异常: {e}")
