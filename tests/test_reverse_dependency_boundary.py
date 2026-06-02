import importlib
import os
import sys
from datetime import datetime, timedelta

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_foundation_imports_do_not_load_audited_domain_modules():
    audited_domain_modules = [
        "app.domains.playback.queries",
    ]
    foundation_modules = [
        "app.infra.db.database",
        "app.core.jwt_token",
    ]

    for module_name in audited_domain_modules + foundation_modules:
        sys.modules.pop(module_name, None)

    for module_name in foundation_modules:
        importlib.import_module(module_name)

    for module_name in audited_domain_modules:
        assert module_name not in sys.modules


def test_playback_base_filter_callers_use_real_filter_module(monkeypatch):
    from app.infra.db import database, playback_filters

    monkeypatch.setattr("app.infra.db.playback_filters.get_hidden_users", lambda: ["hidden-a", "hidden-b"])

    assert not hasattr(database, "get_base_filter")
    assert playback_filters.get_base_filter("user-a") == ("WHERE 1=1 AND UserId = ?", ["user-a"])
    assert playback_filters.get_base_filter("all") == (
        "WHERE 1=1 AND UserId NOT IN (?,?)",
        ["hidden-a", "hidden-b"],
    )
    assert playback_filters.get_base_filter(None) == (
        "WHERE 1=1 AND UserId NOT IN (?,?)",
        ["hidden-a", "hidden-b"],
    )


def test_system_api_tokens_router_imports_real_token_store():
    path = os.path.join(_repo_root, "app", "domains", "system", "api_tokens.py")
    source = open(path, encoding="utf-8").read()

    assert "from app.infra.db.api_token_store import" in source
    assert "app.domains.system.api_token_dao" not in source


def test_verify_api_token_uses_infra_token_lookup(monkeypatch):
    from app.core import jwt_token

    token = jwt_token.create_api_token("user-a", "User A", is_admin=True)
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    seen = {}

    def fake_get_api_token_by_hash(token_hash):
        seen["token_hash"] = token_hash
        return [expires_at]

    monkeypatch.setattr(jwt_token, "get_api_token_by_hash", fake_get_api_token_by_hash)

    payload = jwt_token.verify_api_token(token)

    assert payload["user_id"] == "user-a"
    assert payload["username"] == "User A"
    assert payload["is_admin"] is True
    assert seen["token_hash"]
