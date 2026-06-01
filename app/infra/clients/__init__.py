"""External service client infrastructure boundaries."""

from .cloud115_client import Cloud115Client, cloud115_client
from .media_server_client import MediaServerAdapter, media_api
from .hdhive_client import HdhiveClient, hdhive_client
from .hdhive_site_client import HdhiveSiteClient, hdhive_site_client
from .moviepilot_client import MoviePilotClient, moviepilot_client
from .telegram_client import TelegramClient, telegram_client
from .tmdb_client import TmdbClient, tmdb_client
from .wecom_client import WeComClient, wecom_client

__all__ = [
    "MediaServerAdapter",
    "media_api",
    "Cloud115Client",
    "cloud115_client",
    "HdhiveClient",
    "hdhive_client",
    "HdhiveSiteClient",
    "hdhive_site_client",
    "MoviePilotClient",
    "moviepilot_client",
    "TelegramClient",
    "telegram_client",
    "TmdbClient",
    "tmdb_client",
    "WeComClient",
    "wecom_client",
]
