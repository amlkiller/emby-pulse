import requests


class QBittorrentClient:
    Timeout = requests.exceptions.Timeout
    ConnectionError = requests.exceptions.ConnectionError

    @staticmethod
    def create_session():
        return requests.Session()

    @staticmethod
    def base_url(host: str) -> str:
        return (host or "").rstrip("/")

    def login(self, session, host: str, user: str, password: str, *, timeout: float = 10):
        return session.post(
            f"{self.base_url(host)}/api/v2/auth/login",
            data={"username": user, "password": password},
            timeout=timeout,
        )

    def list_torrents(self, session, host: str, *, timeout: float = 10):
        return session.get(
            f"{self.base_url(host)}/api/v2/torrents/info?filter=all&sort=added_on&reverse=true",
            timeout=timeout,
        )

    def list_files(self, session, host: str, torrent_hash: str, *, timeout: float = 10):
        return session.get(
            f"{self.base_url(host)}/api/v2/torrents/files?hash={torrent_hash}",
            timeout=timeout,
        )

    def set_file_priority(
        self,
        session,
        host: str,
        torrent_hash: str,
        file_ids: str,
        priority: int,
        *,
        timeout: float = 10,
    ):
        return session.post(
            f"{self.base_url(host)}/api/v2/torrents/filePrio",
            data={"hash": torrent_hash, "id": file_ids, "priority": priority},
            timeout=timeout,
        )


qbittorrent_client = QBittorrentClient()
