import requests


class WeComClient:
    def get_access_token(self, base_url: str, corpid: str, corpsecret: str, *, proxies=None, timeout: float = 10):
        return requests.get(
            f"{base_url.rstrip('/')}/cgi-bin/gettoken",
            params={"corpid": corpid, "corpsecret": corpsecret},
            proxies=proxies,
            timeout=timeout,
        )

    def send_message(self, base_url: str, access_token: str, payload: dict, *, proxies=None, timeout: float = 10):
        return requests.post(
            f"{base_url.rstrip('/')}/cgi-bin/message/send",
            params={"access_token": access_token},
            json=payload,
            proxies=proxies,
            timeout=timeout,
        )

    def create_menu(self, base_url: str, access_token: str, agentid: str, payload: dict, *, proxies=None, timeout: float = 5):
        return requests.post(
            f"{base_url.rstrip('/')}/cgi-bin/menu/create",
            params={"access_token": access_token, "agentid": agentid},
            json=payload,
            proxies=proxies,
            timeout=timeout,
        )

    def upload_image(self, base_url: str, access_token: str, files: dict, *, proxies=None, timeout: float = 10):
        return requests.post(
            f"{base_url.rstrip('/')}/cgi-bin/media/uploadimg",
            params={"access_token": access_token},
            files=files,
            proxies=proxies,
            timeout=timeout,
        )


wecom_client = WeComClient()
