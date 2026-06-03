import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True
        if self.target:
            self.target()


class FakeMoviePilotClient:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text
        self.calls = []

    def add_download(self, url, token, payload, timeout=None):
        self.calls.append((url, token, payload, timeout))
        return SimpleNamespace(status_code=self.status_code, text=self.text)


def _patch_download_dependencies(monkeypatch, *, config=None, moviepilot_status=200):
    from app.domains.media_requests import gaps

    save_calls = []
    moviepilot = FakeMoviePilotClient(status_code=moviepilot_status)
    scan_state = {
        "results": [
            {
                "series_id": "series-1",
                "gaps": [
                    {"season": 2, "episode": 3, "status": 0},
                    {"season": 2, "episode": 4, "status": 0},
                ],
            }
        ]
    }

    monkeypatch.setattr(gaps, "scan_state", scan_state)
    monkeypatch.setattr(gaps, "moviepilot_client", moviepilot)
    monkeypatch.setattr(gaps, "get_moviepilot_url", lambda: "http://mp.local")
    monkeypatch.setattr(gaps, "get_moviepilot_token", lambda: "mp-token")
    monkeypatch.setattr(gaps, "get_gap_config_map", lambda: config or {})
    monkeypatch.setattr(gaps, "save_gap_record_status", lambda *args: save_calls.append(args))
    monkeypatch.setattr(gaps.threading, "Thread", ImmediateThread)
    return gaps, moviepilot, save_calls, scan_state


def test_gap_episode_extraction_wrappers_preserve_patterns():
    from app.domains.media_requests import gap_download_service, gaps

    expected = {5, 6, 7}
    assert gaps.extract_episodes_from_filename("Show.S01E05-E07.1080p.mkv") == expected
    assert gap_download_service.extract_episodes_from_filename("Show.S01E05-E07.1080p.mkv") == expected
    assert gaps.extract_episodes_from_filename("剧集 第5-7集.mkv") == expected
    assert gaps.extract_episodes_from_filename("1080p.05.mkv") == {5}


def test_gap_download_denies_non_admin_before_thread_and_dependencies(monkeypatch):
    from app.domains.media_requests import gaps

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    monkeypatch.setattr(gaps.user_service, "is_admin_user", lambda seen_request: calls.append(seen_request) or False)
    monkeypatch.setattr(gaps.threading, "Thread", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("thread should not start")))

    response = gaps.download_gap_item(request, {"series_id": "series-1"})

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_gap_download_immediate_response_and_success_side_effects(monkeypatch):
    gaps, moviepilot, save_calls, scan_state = _patch_download_dependencies(monkeypatch)

    response = gaps.download_gap_item(
        request=None,
        payload={
            "series_id": "series-1",
            "series_name": "Show",
            "season": 2,
            "episodes": [3],
            "torrent_info": {"size": "123.0", "title": "Show S02E03"},
        },
    )

    assert response == {"status": "success", "message": "种子已提交到后台队列，正在处理..."}
    assert moviepilot.calls == [
        ("http://mp.local", "mp-token", {"torrent_in": {"size": 123, "title": "Show S02E03"}}, 60)
    ]
    assert save_calls == [("series-1", "Show", 2, 3, 2)]
    assert scan_state["results"][0]["gaps"] == [
        {"season": 2, "episode": 3, "status": 2},
        {"season": 2, "episode": 4, "status": 0},
    ]


def test_gap_download_dispatches_qbittorrent_hook_through_legacy_wrapper(monkeypatch):
    config = {
        "client_type": "qbittorrent",
        "client_url": "http://qb.local",
        "client_user": "qb-user",
        "client_pass": "qb-pass",
    }
    gaps, _moviepilot, _save_calls, _scan_state = _patch_download_dependencies(monkeypatch, config=config)
    hook_calls = []

    monkeypatch.setattr(
        gaps,
        "hook_qbittorrent",
        lambda host, user, password, expected_size, target_episodes, torrent_name=None: hook_calls.append(
            (host, user, password, expected_size, target_episodes, torrent_name)
        )
        or (True, "done"),
    )

    response = gaps.download_gap_item(
        request=None,
        payload={
            "series_id": "series-1",
            "series_name": "Show",
            "season": 2,
            "episodes": [3],
            "torrent_info": {"org_payload": {"size": "456", "name": "Show S02E03"}},
        },
    )

    assert response["status"] == "success"
    assert hook_calls == [("http://qb.local", "qb-user", "qb-pass", 456, [3], "Show S02E03")]
