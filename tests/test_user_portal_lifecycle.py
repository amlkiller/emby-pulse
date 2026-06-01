import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


class FakeThread:
    instances = []

    def __init__(self, target=None, args=(), daemon=False, name=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
        self.started = False
        self.alive = False
        self.join_timeout = None
        FakeThread.instances.append(self)

    def start(self):
        self.started = True
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeout = timeout
        self.alive = False


class FakeServer:
    def __init__(self):
        self.should_exit = False


def test_user_portal_thread_start_is_idempotent(monkeypatch):
    from app.bootstrap import user_portal

    user_portal.stop_user_portal_thread()
    FakeThread.instances = []
    monkeypatch.setattr(user_portal.threading, "Thread", FakeThread)

    user_portal.start_user_portal_thread(object(), 10308)
    user_portal.start_user_portal_thread(object(), 10309)

    assert len(FakeThread.instances) == 1
    assert FakeThread.instances[0].args[1] == 10308
    assert user_portal._user_portal_thread is FakeThread.instances[0]

    user_portal._user_portal_thread = None
    user_portal._user_portal_server = None


def test_user_portal_stop_requests_server_exit_and_clears_handles():
    from app.bootstrap import user_portal

    thread = FakeThread()
    thread.start()
    server = FakeServer()
    user_portal._user_portal_thread = thread
    user_portal._user_portal_server = server

    user_portal.stop_user_portal_thread()

    assert server.should_exit is True
    assert thread.join_timeout == 1
    assert user_portal._user_portal_thread is None
    assert user_portal._user_portal_server is None


def test_user_portal_stop_clears_dead_thread_without_server():
    from app.bootstrap import user_portal

    thread = FakeThread()
    user_portal._user_portal_thread = thread
    user_portal._user_portal_server = None

    user_portal.stop_user_portal_thread()

    assert thread.join_timeout is None
    assert user_portal._user_portal_thread is None
    assert user_portal._user_portal_server is None
