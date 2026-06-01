import requests


class WebDavClient:
    Timeout = requests.exceptions.Timeout

    @staticmethod
    def request(method: str, url: str, *, auth=None, headers=None, data=None, timeout: float = 30):
        return requests.request(
            method,
            url,
            auth=auth,
            headers=headers,
            data=data,
            timeout=timeout,
        )

    def options(self, url: str, *, auth=None, timeout: float = 10):
        return requests.options(url, auth=auth, timeout=timeout)

    def get(self, url: str, *, auth=None, timeout: float = 60):
        return requests.get(url, auth=auth, timeout=timeout)

    def put(self, url: str, *, data=None, auth=None, timeout: float = 30):
        return requests.put(url, data=data, auth=auth, timeout=timeout)


webdav_client = WebDavClient()
