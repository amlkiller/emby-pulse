import requests
from typing import Optional

from app.infra.config.tmdb_settings import get_tmdb_api_key


class TmdbClient:
    def __init__(self):
        self.base_url = "https://api.themoviedb.org/3"

    @property
    def api_key(self):
        return get_tmdb_api_key()

    def _get(self, path: str, *, params=None, proxies=None, timeout: float = 10):
        request_params = dict(params or {})
        if self.api_key and "api_key" not in request_params:
            request_params["api_key"] = self.api_key
        return requests.get(
            f"{self.base_url}{path}",
            params=request_params,
            proxies=proxies,
            timeout=timeout,
        )

    def get_configuration(self, *, api_key: Optional[str] = None, proxies=None, timeout: float = 10):
        params = {}
        if api_key:
            params["api_key"] = api_key
        return self._get("/configuration", params=params, proxies=proxies, timeout=timeout)

    def get_trending(
        self,
        *,
        media_type: str = "all",
        time_window: str = "day",
        proxies=None,
        timeout: float = 3,
        page: int = 1,
    ):
        return self._get(
            f"/trending/{media_type}/{time_window}",
            params={"language": "zh-CN", "page": page},
            proxies=proxies,
            timeout=timeout,
        )

    def get_top_rated(self, media_type: str, *, proxies=None, timeout: float = 10, page: int = 1):
        return self._get(
            f"/{media_type}/top_rated",
            params={"language": "zh-CN", "page": page},
            proxies=proxies,
            timeout=timeout,
        )

    def discover_tv(
        self,
        *,
        proxies=None,
        timeout: float = 10,
        page: int = 1,
        with_genres: str = None,
        sort_by: str = None,
        vote_count_gte: int = None,
    ):
        params = {"language": "zh-CN", "page": page}
        if with_genres:
            params["with_genres"] = with_genres
        if sort_by:
            params["sort_by"] = sort_by
        if vote_count_gte is not None:
            params["vote_count.gte"] = vote_count_gte
        return self._get("/discover/tv", params=params, proxies=proxies, timeout=timeout)

    def search_multi(self, query: str, *, proxies=None, timeout: float = 10, page: int = 1):
        return self._get(
            "/search/multi",
            params={"language": "zh-CN", "query": query, "page": page},
            proxies=proxies,
            timeout=timeout,
        )

    def search_movie(self, query: str, *, proxies=None, timeout: float = 10, page: int = 1):
        return self._get(
            "/search/movie",
            params={"language": "zh-CN", "query": query, "page": page},
            proxies=proxies,
            timeout=timeout,
        )

    def search_tv(self, query: str, *, proxies=None, timeout: float = 10, page: int = 1):
        return self._get(
            "/search/tv",
            params={"language": "zh-CN", "query": query, "page": page},
            proxies=proxies,
            timeout=timeout,
        )

    def get_tv_details(self, tmdb_id: int, *, proxies=None, timeout: float = 10):
        return self._get(
            f"/tv/{tmdb_id}",
            params={"language": "zh-CN"},
            proxies=proxies,
            timeout=timeout,
        )

    def get_tv_season(self, tmdb_id: int, season: int, *, proxies=None, timeout: float = 10):
        return self._get(
            f"/tv/{tmdb_id}/season/{season}",
            params={"language": "zh-CN"},
            proxies=proxies,
            timeout=timeout,
        )

    def get_movie_details(self, tmdb_id: int, *, proxies=None, timeout: float = 10):
        return self._get(
            f"/movie/{tmdb_id}",
            params={"language": "zh-CN"},
            proxies=proxies,
            timeout=timeout,
        )

    def get_images(self, media_type: str, tmdb_id: int, *, proxies=None, timeout: float = 10, api_key: Optional[str] = None):
        params = {}
        if api_key:
            params["api_key"] = api_key
        return self._get(f"/{media_type}/{tmdb_id}/images", params=params, proxies=proxies, timeout=timeout)


tmdb_client = TmdbClient()
