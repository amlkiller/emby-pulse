import requests


class NetworkClient:
    Timeout = requests.exceptions.Timeout
    ProxyError = requests.exceptions.ProxyError
    SSLError = requests.exceptions.SSLError

    @staticmethod
    def ping(url: str, *, proxies=None, timeout: float = 5, allow_redirects: bool = False):
        return requests.get(url, proxies=proxies, timeout=timeout, allow_redirects=allow_redirects)

    @staticmethod
    def test_proxy(url: str, *, proxies=None, timeout: float = 10):
        return requests.get(url, proxies=proxies, timeout=timeout)


network_client = NetworkClient()
