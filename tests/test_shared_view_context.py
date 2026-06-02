import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaResponse:
    status_code = 200

    def json(self):
        return {"Id": " server-1\r\n"}


class FakeMediaApi:
    def __init__(self):
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        return FakeMediaResponse()


def test_common_template_context_preserves_fields_and_normalization(monkeypatch):
    from app.shared import view_context

    fake_media_api = FakeMediaApi()
    request = SimpleNamespace(
        session={
            "user": {
                "name": "User One",
                "avatar": "avatar.png",
                "auth_type": "local",
                "role": "user",
                "permissions": '["points", "plugins"]',
            }
        }
    )

    monkeypatch.setattr(view_context, "media_api", fake_media_api)
    monkeypatch.setattr(view_context, "get_media_server_main_public_or_host", lambda: "https://emby.example/")

    result = view_context.get_common_vars(request, "points", {"title": "Points"})

    assert result == {
        "request": request,
        "version": view_context.APP_VERSION,
        "active_page": "points",
        "emby_url": "https://emby.example",
        "server_id": "server-1",
        "is_pro": True,
        "user_permissions": ["points", "plugins"],
        "is_admin": False,
        "user_name": "User One",
        "user_avatar": "avatar.png",
        "title": "Points",
    }
    assert fake_media_api.calls == [("/System/Info", 2)]
