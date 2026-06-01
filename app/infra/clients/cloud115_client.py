import requests


class Cloud115Client:
    @staticmethod
    def _headers(cookie: str) -> dict:
        return {
            "Cookie": (cookie or "").strip(),
            "User-Agent": "Mozilla/5.0",
        }

    def get_nav(self, cookie: str, *, timeout: float = 15):
        return requests.get(
            "https://my.115.com/?ct=ajax&ac=nav",
            headers=self._headers(cookie),
            timeout=timeout,
        )

    def get_offline_space(self, cookie: str, *, timeout: float = 15):
        return requests.get(
            "https://115.com/?ct=offline&ac=space",
            headers=self._headers(cookie),
            timeout=timeout,
        )

    def add_offline_task(self, cookie: str, payload: dict, *, timeout: float = 15):
        headers = self._headers(cookie)
        headers["Referer"] = "https://115.com/"
        return requests.post(
            "https://115.com/web/lixian/?ct=lixian&ac=add_task_url",
            data=payload,
            headers=headers,
            timeout=timeout,
        )

    def get_share_snap(self, cookie: str, share_code: str, receive_code: str, *, timeout: float = 15):
        return requests.get(
            f"https://webapi.115.com/share/snap?share_code={share_code}&offset=0&limit=20&receive_code={receive_code}",
            headers=self._headers(cookie),
            timeout=timeout,
        )

    def receive_share(self, cookie: str, payload: dict, *, timeout: float = 15):
        return requests.post(
            "https://webapi.115.com/share/receive",
            data=payload,
            headers=self._headers(cookie),
            timeout=timeout,
        )


cloud115_client = Cloud115Client()
