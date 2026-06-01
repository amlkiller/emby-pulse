"""Compatibility re-export for the media server client boundary."""

from app.infra.clients.media_server_client import MediaServerAdapter, media_api

__all__ = ["MediaServerAdapter", "media_api"]
