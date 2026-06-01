import requests

from app.utils.url_validator import validate_url


class MoviePilotClient:
    @staticmethod
    def normalize_url(url: str) -> str:
        return (url or "").strip().rstrip("/")

    @staticmethod
    def normalize_token(token: str) -> str:
        return (token or "").strip().strip("'\"")

    @staticmethod
    def validate_url(url: str) -> dict:
        return validate_url(url, allow_internal=False)

    def test_site(self, url: str, token: str, *, timeout: float = 8):
        normalized_url = self.normalize_url(url)
        normalized_token = self.normalize_token(token)
        return requests.get(
            f"{normalized_url}/api/v1/site/",
            headers={"X-API-KEY": normalized_token, "User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )

    def subscribe(self, url: str, token: str, payload: dict, *, timeout: float = 10):
        normalized_url = self.normalize_url(url)
        normalized_token = self.normalize_token(token)
        return requests.post(
            f"{normalized_url}/api/v1/subscribe/",
            json=payload,
            headers={"X-API-KEY": normalized_token},
            timeout=timeout,
        )

    def search_title(self, url: str, token: str, keyword: str, *, timeout: float = 20):
        normalized_url = self.normalize_url(url)
        normalized_token = self.normalize_token(token)
        return requests.get(
            f"{normalized_url}/api/v1/search/title",
            params={"keyword": keyword},
            headers={"X-API-KEY": normalized_token, "User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=timeout,
        )

    def add_download(self, url: str, token: str, payload: dict, *, timeout: float = 60):
        normalized_url = self.normalize_url(url)
        normalized_token = self.normalize_token(token)
        return requests.post(
            f"{normalized_url}/api/v1/download/add",
            headers={"X-API-KEY": normalized_token, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )


moviepilot_client = MoviePilotClient()
