import requests


class TelegramClient:
    base_url = "https://api.telegram.org"

    def request(self, method: str, token: str, api_method: str, *, params=None, data=None, json=None, files=None, proxies=None, timeout: float = 10):
        normalized_token = (token or "").strip()
        if not normalized_token:
            raise ValueError("Telegram bot token is required")
        return requests.request(
            method,
            f"{self.base_url}/bot{normalized_token}/{api_method}",
            params=params,
            data=data,
            json=json,
            files=files,
            proxies=proxies,
            timeout=timeout,
        )

    def get_api(self, token: str, api_method: str, *, params=None, proxies=None, timeout: float = 10):
        return self.request("GET", token, api_method, params=params, proxies=proxies, timeout=timeout)

    def post_api(self, token: str, api_method: str, *, data=None, json=None, files=None, proxies=None, timeout: float = 10):
        return self.request("POST", token, api_method, data=data, json=json, files=files, proxies=proxies, timeout=timeout)

    def send_message(self, token: str, payload: dict, *, proxies=None, timeout: float = 10):
        return self.post_api(token, "sendMessage", json=payload, proxies=proxies, timeout=timeout)

    def send_photo(self, token: str, *, data: dict, files=None, proxies=None, timeout: float = 20):
        return self.post_api(token, "sendPhoto", data=data, files=files, proxies=proxies, timeout=timeout)

    def get_updates(self, token: str, *, params=None, proxies=None, timeout: float = 35):
        return self.get_api(token, "getUpdates", params=params, proxies=proxies, timeout=timeout)


telegram_client = TelegramClient()
