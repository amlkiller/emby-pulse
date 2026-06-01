import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ImageProxyClient:
    RequestException = requests.exceptions.RequestException

    def __init__(self):
        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        self.session.mount("http://", HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100))
        self.session.mount("https://", HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100))

    def get(self, url: str, *, proxies=None, timeout: float = 10, stream: bool = True):
        return self.session.get(url, proxies=proxies, timeout=timeout, stream=stream)


image_proxy_client = ImageProxyClient()
