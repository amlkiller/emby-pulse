"""
开放注册软预占 + FIFO 排队 并发测试

验证 _reserve_quota_slot / _release_quota_slot / _inc_batch_used / _enter_reg_queue
在高并发（100 线程同时争 quota=10）下行为正确：
- total 模式：恰好 10 次预占成功，其余被拒绝（total_full）
- batch 模式：_batch_used_mem 最终为 10，第 10 次自动关闭 open_reg

运行：pytest tests/test_reg_concurrency.py -v
"""
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# 不需要真实 telegram/emby，只测试纯 Python 并发原语
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _patch_module_for_test(monkeypatch_like_setattr):
    """把模块里的 cfg / media_api / _send_open_reg_closed_notify 替换成可控 mock"""
    from app.services import user_bot_service as ub

    # 模拟 cfg：内存字典
    class FakeCfg:
        def __init__(self, initial=None):
            self._d = dict(initial or {})
            self._lock = threading.Lock()
            self.set_calls = 0

        def get(self, k, default=None):
            with self._lock:
                return self._d.get(k, default)

        def set(self, k, v):
            with self._lock:
                self._d[k] = v
                self.set_calls += 1

    fake_cfg = FakeCfg({
        "user_bot_open_reg": True,
        "user_bot_reg_quota_mode": "total",
        "user_bot_reg_quota": 10,
        "user_bot_reg_batch_used": 0,
        "hidden_users": [],
    })

    # 模拟 media_api.get("/Users") 返回当前已"注册"的用户
    class FakeUsers:
        def __init__(self):
            self.users = []  # list of {"Name": str, "Policy": {"IsAdministrator": False}}
            self.lock = threading.Lock()

        def add(self, name):
            with self.lock:
                self.users.append({"Name": name, "Policy": {"IsAdministrator": False}})

        def snapshot(self):
            with self.lock:
                return list(self.users)

    fake_users = FakeUsers()

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    class FakeMediaApi:
        def get(self, path, timeout=5):
            if path == "/Users":
                return FakeResp(fake_users.snapshot())
            raise NotImplementedError(path)

    monkeypatch_like_setattr(ub, "cfg", fake_cfg)
    monkeypatch_like_setattr(ub, "media_api", FakeMediaApi())
    monkeypatch_like_setattr(ub, "_send_open_reg_closed_notify", lambda *a, **kw: None)

    # 重置模块状态
    with ub._quota_lock:
        ub._quota_reserved = 0
        ub._user_count_cache["count"] = None
        ub._user_count_cache["users"] = None
        ub._user_count_cache["ts"] = 0.0
    with ub._batch_used_lock:
        ub._batch_used_mem = None
        ub._batch_used_dirty = 0
    with ub._reg_waiters_lock:
        ub._reg_waiters = 0
        ub._reg_active = 0
    # 重置信号量（drain 再补满）
    while True:
        if not ub._reg_sema.acquire(blocking=False):
            break
    for _ in range(ub.MAX_CONCURRENT_REG):
        ub._reg_sema.release()

    return ub, fake_cfg, fake_users


def test_total_mode_exactly_quota(monkeypatch):
    """100 线程同时预占，total quota=10，恰好 10 次成功"""
    ub, fake_cfg, fake_users = _patch_module_for_test(monkeypatch.setattr)

    successes = []
    failures = []
    s_lock = threading.Lock()

    def worker(i):
        ok, reason = ub._reserve_quota_slot("total", 10)
        if ok:
            # 模拟注册成功：把用户加入 fake_users，然后释放预占（committed=True）
            fake_users.add(f"user{i}")
            ub._release_quota_slot(committed=True, quota_mode="total", quota=10)
            with s_lock:
                successes.append(i)
        else:
            with s_lock:
                failures.append((i, reason))

    with ThreadPoolExecutor(max_workers=100) as ex:
        list(ex.map(worker, range(100)))

    assert len(successes) == 10, f"成功数应为 10，实际 {len(successes)}；失败={len(failures)}"
    assert len(failures) == 90
    # 全部失败原因应该是 total_full（emby 不可达不会出现，因为我们的 mock 永远成功）
    bad_reasons = [r for _, r in failures if r != "total_full"]
    assert not bad_reasons, f"出现了非 total_full 失败：{bad_reasons[:5]}"


def test_batch_mode_exactly_quota(monkeypatch):
    """100 线程同时预占，batch quota=10，最终 _batch_used_mem == 10"""
    ub, fake_cfg, fake_users = _patch_module_for_test(monkeypatch.setattr)
    fake_cfg.set("user_bot_reg_quota_mode", "batch")
    fake_cfg.set_calls = 0  # 重置计数，便于断言

    successes = []
    failures = []
    s_lock = threading.Lock()

    def worker(i):
        ok, reason = ub._reserve_quota_slot("batch", 10)
        if ok:
            ub._release_quota_slot(committed=True, quota_mode="batch", quota=10)
            with s_lock:
                successes.append(i)
        else:
            with s_lock:
                failures.append((i, reason))

    with ThreadPoolExecutor(max_workers=100) as ex:
        list(ex.map(worker, range(100)))

    assert len(successes) == 10
    assert len(failures) == 90
    assert all(r == "batch_full" for _, r in failures)

    # _batch_used_mem 应该恰好等于 quota
    with ub._batch_used_lock:
        assert ub._batch_used_mem == 10

    # 第 10 次应该已经把 open_reg 关掉
    assert fake_cfg.get("user_bot_open_reg") is False

    # cfg.set 次数应该远少于成功数（因为 BATCH_FLUSH_THRESHOLD + 满额触发，最多写几次）
    # 严格上限：ceil(10 / BATCH_FLUSH_THRESHOLD) + 1（满额触发） + 1（关闭 open_reg）
    assert fake_cfg.set_calls <= 10, f"cfg.set 调用过多：{fake_cfg.set_calls}"


def test_fifo_queue_under_load(monkeypatch):
    """100 线程争 MAX_CONCURRENT_REG 个信号量，所有线程最终都被处理（不被秒拒）"""
    ub, fake_cfg, fake_users = _patch_module_for_test(monkeypatch.setattr)

    # 替换 _send 以避免 TG 调用
    monkeypatch.setattr(ub, "_send", lambda *a, **kw: None)

    entered = []
    e_lock = threading.Lock()

    def worker(i):
        ok = ub._enter_reg_queue(chat_id=i)
        if ok:
            with e_lock:
                entered.append(i)
            ub._leave_reg_queue()

    with ThreadPoolExecutor(max_workers=100) as ex:
        list(ex.map(worker, range(100)))

    # 关键断言：每一个请求都得到处理（没有"超出即拒"丢弃）
    assert len(entered) == 100, f"应有 100 个全部进入临界区，实际 {len(entered)}"

    # 队列应该清空
    with ub._reg_waiters_lock:
        assert ub._reg_active == 0
        assert ub._reg_waiters == 0
