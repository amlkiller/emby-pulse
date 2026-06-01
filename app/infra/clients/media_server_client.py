import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import cfg

logger = logging.getLogger("uvicorn")


class MediaServerAdapter:
    def __init__(self):
        # 🔥 工业级抗压处理：使用全局 Session 复用连接，并设置指数退避重试
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100))
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100))
        # 健康检查结果缓存：(timestamp, healthy)
        self._health_cache = (0.0, False)
        self._health_cache_ttl = 5.0

    @property
    def host(self):
        return cfg.get("emby_host", "").rstrip('/')

    @property
    def api_key(self):
        return cfg.get("emby_api_key", "")

    @property
    def server_type(self):
        # 获取类型，转为小写，默认为 emby
        return cfg.get("server_type", "emby").lower()

    def _build_url(self, path: str) -> str:
        """智能路由转换器：解决 Jellyfin 和 Emby 路径差异"""
        if not path.startswith('/'):
            path = '/' + path

        if self.server_type == "jellyfin":
            # Jellyfin 的 API 抛弃了 /emby 前缀
            if path.startswith('/emby/'):
                path = path.replace('/emby/', '/', 1)
        else:
            # Emby 保留 /emby 前缀
            if not path.startswith('/emby/'):
                path = '/emby' + path

        return f"{self.host}{path}"

    def _build_url_for(self, host: str, server_type: str, path: str) -> str:
        """Build a media server URL from explicit candidate settings."""
        if not path.startswith('/'):
            path = '/' + path

        if (server_type or "emby").lower() == "jellyfin":
            if path.startswith('/emby/'):
                path = path.replace('/emby/', '/', 1)
        else:
            if not path.startswith('/emby/'):
                path = '/emby' + path

        return f"{(host or '').rstrip('/')}{path}"

    def _get_headers(self, custom_headers=None, skip_content_type=False) -> dict:
        """智能鉴权转换器：解决鉴权方式差异

        Args:
            custom_headers: 自定义 headers
            skip_content_type: 是否跳过 Content-Type（用于 multipart 上传，让 requests 自动设置 boundary）
        """
        headers = {}
        if self.server_type == "jellyfin":
            headers["Authorization"] = f'MediaBrowser Token="{self.api_key}"'
        else:
            headers["X-Emby-Token"] = self.api_key

        if custom_headers:
            if skip_content_type and "Content-Type" in custom_headers:
                # 复制 custom_headers 但移除 Content-Type
                custom_headers = {k: v for k, v in custom_headers.items() if k.lower() != "content-type"}
            headers.update(custom_headers)
        return headers

    def _get_headers_for(self, api_key: str, server_type: str, custom_headers=None) -> dict:
        """Build auth headers from explicit candidate settings."""
        headers = {}
        if (server_type or "emby").lower() == "jellyfin":
            headers["Authorization"] = f'MediaBrowser Token="{api_key}"'
        else:
            headers["X-Emby-Token"] = api_key

        if custom_headers:
            headers.update(custom_headers)
        return headers

    def request(self, method: str, path: str, **kwargs):
        """统一请求拦截入口"""
        if not self.host or not self.api_key:
            raise ValueError("Media Server 尚未配置完整 (Host 或 API Key 缺失)")

        url = self._build_url(path)

        # 检测是否为 multipart 上传（有 files 参数时需要让 requests 自动设置 Content-Type）
        skip_content_type = 'files' in kwargs and kwargs['files'] is not None
        kwargs['headers'] = self._get_headers(kwargs.get('headers'), skip_content_type=skip_content_type)

        # 如果 params 中没有 api_key，则添加它（某些 API 如封面上传需要 URL 中的 api_key）
        if 'params' not in kwargs:
            kwargs['params'] = {}
        if 'api_key' not in kwargs['params']:
            kwargs['params']['api_key'] = self.api_key

        return self.session.request(method, url, **kwargs)

    # 便捷方法包装
    def get(self, path: str, **kwargs): return self.request('GET', path, **kwargs)
    def post(self, path: str, **kwargs): return self.request('POST', path, **kwargs)
    def delete(self, path: str, **kwargs): return self.request('DELETE', path, **kwargs)

    def authenticate_by_name(self, username: str, password: str, *, timeout: float = 10):
        headers = {
            "X-Emby-Authorization": 'MediaBrowser Client="EmbyPulse", Device="EmbyPulse", DeviceId="EmbyPulse", Version="1.0"',
        }
        return self.session.post(
            self._build_url("/Users/AuthenticateByName"),
            data={"Username": username, "Pw": password},
            headers=headers,
            timeout=timeout,
        )

    def probe_settings(self, host: str, api_key: str, server_type: str = "emby", *, timeout: float = 5):
        """Probe System/Info using unsaved candidate settings."""
        url = self._build_url_for(host, server_type, "/System/Info")
        headers = self._get_headers_for(api_key, server_type)
        return self.session.get(url, headers=headers, timeout=timeout)

    def restart_server(self, host: str, api_key: str, server_type: str = "emby", *, timeout: float = 10):
        """Send a restart command using explicit media server settings."""
        url = self._build_url_for(host, server_type, "/System/Restart")
        headers = self._get_headers_for(api_key, server_type)
        return self.session.post(url, headers=headers, params={"api_key": api_key}, timeout=timeout)

    def submit_custom_query(self, host: str, api_key: str, custom_query: str, *, timeout: float = 20):
        """Submit a playback reporting custom query against an explicit media server."""
        url = self._build_url_for(host, "emby", "/user_usage_stats/submit_custom_query")
        headers = {"X-Emby-Token": api_key, "Content-Type": "application/json"}
        payload = {"CustomQueryString": custom_query}
        return self.session.post(url, headers=headers, json=payload, timeout=timeout)

    def health_check(self, timeout: float = 3.0) -> bool:
        """探活 Emby/Jellyfin。结果带 5 秒 TTL 缓存，避免批量场景放大请求。

        独立的 Session（不使用全局重试 Session），避免重试机制把"快速失败"拖到 12 秒+。
        """
        now = time.time()
        ts, healthy = self._health_cache
        if now - ts < self._health_cache_ttl:
            return healthy
        ok = False
        try:
            if not self.host or not self.api_key:
                ok = False
            else:
                url = self._build_url('/System/Info')
                headers = self._get_headers()
                params = {'api_key': self.api_key}
                # 单次请求，不复用全局重试 Session
                resp = requests.get(url, headers=headers, params=params, timeout=timeout)
                ok = (resp.status_code == 200)
        except Exception as e:
            logger.warning(f"[media_adapter] health_check 失败: {e!r}")
            ok = False
        self._health_cache = (now, ok)
        return ok


# 实例化单例，全局复用
media_api = MediaServerAdapter()
