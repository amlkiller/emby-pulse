import requests


class TransmissionClient:
    Timeout = requests.exceptions.Timeout
    ConnectionError = requests.exceptions.ConnectionError

    @staticmethod
    def create_session():
        return requests.Session()

    @staticmethod
    def base_url(host: str) -> str:
        return (host or "").rstrip("/")

    def handshake(self, session, host: str, auth=None, *, timeout: float = 10):
        return session.post(f"{self.base_url(host)}/transmission/rpc", auth=auth, timeout=timeout)

    def torrent_get(self, session, host: str, payload: dict, auth=None, *, timeout: float = 10):
        return session.post(f"{self.base_url(host)}/transmission/rpc", json=payload, auth=auth, timeout=timeout)


transmission_client = TransmissionClient()
