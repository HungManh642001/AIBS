import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ABES_DB_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setenv("ABES_STORAGE_DIR", str(tmp_path / "storage"))
    import sys
    import config
    config.get_settings.cache_clear()

    # Xóa cache của main, database, models và tất cả routers để reload sạch với DB mới
    for mod_name in [m for m in list(sys.modules) if m == "main" or m == "database" or m == "models" or m.startswith("routers")]:
        sys.modules.pop(mod_name, None)

    import database
    import models  # noqa: F401
    from main import create_app
    return TestClient(create_app())
