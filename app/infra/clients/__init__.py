"""External service client infrastructure boundaries."""

from .media_server_client import MediaServerAdapter, media_api
from .moviepilot_client import MoviePilotClient, moviepilot_client
from .telegram_client import TelegramClient, telegram_client
from .tmdb_client import TmdbClient, tmdb_client
from .wecom_client import WeComClient, wecom_client

__all__ = [
    "MediaServerAdapter",
    "media_api",
    "MoviePilotClient",
    "moviepilot_client",
    "TelegramClient",
    "telegram_client",
    "TmdbClient",
    "tmdb_client",
    "WeComClient",
    "wecom_client",
]
