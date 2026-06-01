import importlib
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_domain_version_imports_do_not_import_app_main():
    sys.modules.pop("app.main", None)

    modules = [
        "app.domains.system.views",
        "app.domains.notifications.notify_admin",
        "app.domains.system.audit",
    ]

    for module_name in modules:
        sys.modules.pop(module_name, None)
        importlib.import_module(module_name)

    assert "app.main" not in sys.modules


def test_app_main_version_matches_shared_version():
    from app.shared.version import APP_VERSION as shared_version
    from app.main import APP_VERSION as main_version

    assert main_version == shared_version
