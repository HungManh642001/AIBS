from pathlib import Path
import storage


def test_save_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    rel = storage.save_upload(7, "hsmt.pdf", b"hello", subdir="hsmt")
    assert rel.startswith("7/hsmt/")
    assert storage.read_bytes(rel) == b"hello"
    assert storage.abs_path(rel) == Path(tmp_path) / rel
