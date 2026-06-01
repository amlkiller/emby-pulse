"""External service client infrastructure boundaries."""

from .cloud115_client import Cloud115Client, cloud115_client
from .media_server_client import MediaServerAdapter, media_api
from .hdhive_client import HdhiveClient, hdhive_client
from .hdhive_site_client import HdhiveSiteClient, hdhive_site_client
from .moviepilot_client import MoviePilotClient, moviepilot_client
from .qbittorrent_client import QBittorrentClient, qbittorrent_client
from .ip_location_client import IpLocationClient, ip_location_client
from .telegram_client import TelegramClient, telegram_client
from .transmission_client import TransmissionClient, transmission_client
from .tmdb_client import TmdbClient, tmdb_client
from .webdav_client import WebDavClient, webdav_client
from .weather_client import WeatherClient, weather_client
from .network_client import NetworkClient, network_client
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
    "QBittorrentClient",
    "qbittorrent_client",
    "IpLocationClient",
    "ip_location_client",
    "TelegramClient",
    "telegram_client",
    "TransmissionClient",
    "transmission_client",
    "TmdbClient",
    "tmdb_client",
    "WebDavClient",
    "webdav_client",
    "WeatherClient",
    "weather_client",
    "NetworkClient",
    "network_client",
    "WeComClient",
    "wecom_client",
]
