from pathlib import Path
import storage


def test_save_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    rel = storage.save_upload(7, "hsmt.pdf", b"hello", subdir="hsmt")
    assert rel.startswith("7/hsmt/")
    assert storage.read_bytes(rel) == b"hello"
    assert storage.abs_path(rel) == Path(tmp_path) / rel


def test_save_sanitizes_unsafe_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    rel = storage.save_upload(3, "../e v!l.pdf", b"x", subdir="hsmt")
    # tên file đã được làm sạch: không còn '/', khoảng trắng hay ký tự đặc biệt
    stored_name = rel.split("/")[-1]
    assert "/" not in stored_name
    assert ".." not in stored_name or stored_name == ".._e_v_l.pdf"
    assert storage.read_bytes(rel) == b"x"
