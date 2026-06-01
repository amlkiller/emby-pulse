import requests


class HdhiveClient:
    base_url = "https://hdhive.com/api/open"

    def request(self, method: str, api_key: str, path: str, *, params=None, json=None, proxies=None, timeout: float = 10):
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            raise ValueError("HDHive API key is required")
        return requests.request(
            method,
            f"{self.base_url}{path}",
            headers={"X-API-Key": normalized_key, "Content-Type": "application/json"},
            params=params,
            json=json,
            proxies=proxies,
            timeout=timeout,
        )

    def get(self, api_key: str, path: str, *, params=None, proxies=None, timeout: float = 10):
        return self.request("GET", api_key, path, params=params, proxies=proxies, timeout=timeout)

    def post(self, api_key: str, path: str, *, json=None, proxies=None, timeout: float = 10):
        return self.request("POST", api_key, path, json=json, proxies=proxies, timeout=timeout)

    def ping(self, api_key: str, *, proxies=None, timeout: float = 10):
        return self.get(api_key, "/ping", proxies=proxies, timeout=timeout)

    def get_quota(self, api_key: str, *, proxies=None, timeout: float = 10):
        return self.get(api_key, "/quota", proxies=proxies, timeout=timeout)

    def get_me(self, api_key: str, *, proxies=None, timeout: float = 10):
        return self.get(api_key, "/me", proxies=proxies, timeout=timeout)

    def search_resources(self, api_key: str, res_type: str, tmdb_id: str, *, proxies=None, timeout: float = 15):
        api_res_type = "movie" if res_type == "movie" else "tv"
        return self.get(api_key, f"/resources/{api_res_type}/{tmdb_id}", proxies=proxies, timeout=timeout)

    def unlock_resource(self, api_key: str, slug: str, *, proxies=None, timeout: float = 15):
        return self.post(api_key, "/resources/unlock", json={"slug": slug}, proxies=proxies, timeout=timeout)

    def check_resource(self, api_key: str, url: str, *, proxies=None, timeout: float = 10):
        return self.post(api_key, "/check/resource", json={"url": url}, proxies=proxies, timeout=timeout)

    def checkin(self, api_key: str, *, is_gambler: bool = False, proxies=None, timeout: float = 15):
        return self.post(api_key, "/checkin", json={"is_gambler": is_gambler}, proxies=proxies, timeout=timeout)

    def get_usage(self, api_key: str, *, params=None, proxies=None, timeout: float = 10):
        return self.get(api_key, "/usage", params=params, proxies=proxies, timeout=timeout)

    def get_usage_today(self, api_key: str, *, proxies=None, timeout: float = 10):
        return self.get(api_key, "/usage/today", proxies=proxies, timeout=timeout)

    def get_vip_weekly_quota(self, api_key: str, *, proxies=None, timeout: float = 10):
        return self.get(api_key, "/vip/weekly-free-quota", proxies=proxies, timeout=timeout)


hdhive_client = HdhiveClient()
