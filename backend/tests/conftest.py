import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ABES_DB_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setenv("ABES_STORAGE_DIR", str(tmp_path / "storage"))
    import importlib
    import sys
    import config
    config.get_settings.cache_clear()

    # Xóa cache của các module phụ thuộc để reload sạch
    for mod_name in ["database", "models"]:
        sys.modules.pop(mod_name, None)

    import database
    import models  # noqa: F401
    from main import create_app
    return TestClient(create_app())
