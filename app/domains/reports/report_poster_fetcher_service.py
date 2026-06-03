import io
import logging

from app.domains.reports.report_assets import HAS_PIL
from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.clients.tmdb_client import tmdb_client

if HAS_PIL:
    from PIL import Image


logger = logging.getLogger("uvicorn")

_media_api_provider = lambda: media_api
_tmdb_client_provider = lambda: tmdb_client
_network_client_provider = lambda: network_client
_has_pil_provider = lambda: HAS_PIL
_logger_provider = lambda: logger


def set_dependency_providers(
    media_api_provider=None,
    tmdb_client_provider=None,
    network_client_provider=None,
    has_pil_provider=None,
    logger_provider=None,
):
    global _media_api_provider
    global _tmdb_client_provider
    global _network_client_provider
    global _has_pil_provider
    global _logger_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if network_client_provider is not None:
        _network_client_provider = network_client_provider
    if has_pil_provider is not None:
        _has_pil_provider = has_pil_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


class ReportPosterFetcher:
    def get_series_id(self, item_id, item_name):
        if not item_id:
            return None
        try:
            res = _media_api_provider().get("/Users", timeout=3)
            if res.status_code != 200:
                return None
            users = res.json()
            if not users:
                return None
            user_id = users[0]['Id']
            detail_res = _media_api_provider().get(f"/Users/{user_id}/Items/{item_id}", timeout=3)
            if detail_res.status_code == 200:
                detail = detail_res.json()
                series_id = detail.get('SeriesId')
                if series_id:
                    return series_id
        except:
            pass
        return None

    def fetch_emby_poster(self, item_id, width=120, height=160):
        if not item_id or not _has_pil_provider():
            return None
        try:
            params = {"maxHeight": height * 2, "maxWidth": width * 2, "quality": 85}
            res = _media_api_provider().get(f"/Items/{item_id}/Images/Primary", params=params, timeout=5)
            if res.status_code == 200:
                poster = Image.open(io.BytesIO(res.content)).convert('RGB')
                poster = poster.resize((width, height), Image.LANCZOS)
                return poster
        except:
            pass
        return None

    def fetch_tmdb_poster(self, item_name, width=120, height=160, is_tv=False):
        if not item_name or not _has_pil_provider():
            return None
        if not _tmdb_client_provider().api_key:
            return None

        clean_name = str(item_name).split(' - ')[0].strip()
        if not clean_name:
            return None

        try:
            proxies = None
            try:
                from app.utils.proxy_helper import get_safe_proxies
                proxies = get_safe_proxies()
            except Exception:
                pass

            media_type = "tv" if is_tv else "movie"
            if media_type == "tv":
                res = _tmdb_client_provider().search_tv(clean_name, proxies=proxies, timeout=5)
            else:
                res = _tmdb_client_provider().search_movie(clean_name, proxies=proxies, timeout=5)
            if res.status_code != 200:
                return None
            results = res.json().get("results", [])
            poster_path = next((r.get("poster_path") for r in results if r.get("poster_path")), None)
            if not poster_path and not is_tv:
                tv_res = _tmdb_client_provider().search_tv(clean_name, proxies=proxies, timeout=5)
                if tv_res.status_code == 200:
                    poster_path = next((r.get("poster_path") for r in tv_res.json().get("results", []) if r.get("poster_path")), None)
            if not poster_path:
                return None

            img_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            img_res = _network_client_provider().get(img_url, proxies=proxies, timeout=8)
            if img_res.status_code == 200:
                poster = Image.open(io.BytesIO(img_res.content)).convert('RGB')
                poster = poster.resize((width, height), Image.LANCZOS)
                _logger_provider().info(f"[海报生成] TMDB 封面兜底成功: {clean_name}")
                return poster
        except Exception as e:
            _logger_provider().debug(f"[海报生成] TMDB 封面兜底失败: {item_name}, {e}")
        return None

    def get_best_poster(self, item_id, item_name, width=120, height=160, is_tv=False):
        poster = None
        if is_tv and item_id:
            series_id = self.get_series_id(item_id, item_name)
            if series_id:
                poster = self.fetch_emby_poster(series_id, width, height)
        if not poster and item_id:
            poster = self.fetch_emby_poster(item_id, width, height)
        if not poster:
            poster = self.fetch_tmdb_poster(item_name, width, height, is_tv=is_tv)
        return poster


report_poster_fetcher = ReportPosterFetcher()
