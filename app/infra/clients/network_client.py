import requests


class NetworkClient:
    Timeout = requests.exceptions.Timeout
    ProxyError = requests.exceptions.ProxyError
    SSLError = requests.exceptions.SSLError
    ConnectionError = requests.exceptions.ConnectionError
    RequestException = requests.exceptions.RequestException

    @staticmethod
    def request(
        method: str,
        url: str,
        *,
        headers=None,
        params=None,
        data=None,
        json=None,
        files=None,
        auth=None,
        proxies=None,
        timeout: float = 10,
        allow_redirects: bool = True,
        stream: bool = False,
    ):
        return requests.request(
            method,
            url,
            headers=headers,
            params=params,
            data=data,
            json=json,
            files=files,
            auth=auth,
            proxies=proxies,
            timeout=timeout,
            allow_redirects=allow_redirects,
            stream=stream,
        )

    @staticmethod
    def get(
        url: str,
        *,
        headers=None,
        params=None,
        proxies=None,
        timeout: float = 10,
        allow_redirects: bool = True,
        stream: bool = False,
    ):
        return NetworkClient.request(
            "GET",
            url,
            headers=headers,
            params=params,
            proxies=proxies,
            timeout=timeout,
            allow_redirects=allow_redirects,
            stream=stream,
        )

    @staticmethod
    def ping(url: str, *, proxies=None, timeout: float = 5, allow_redirects: bool = False):
        return NetworkClient.get(url, proxies=proxies, timeout=timeout, allow_redirects=allow_redirects)

    @staticmethod
    def test_proxy(url: str, *, proxies=None, timeout: float = 10):
        return NetworkClient.get(url, proxies=proxies, timeout=timeout)


network_client = NetworkClient()
