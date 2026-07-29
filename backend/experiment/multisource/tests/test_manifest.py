"""Bỏ qua bước chuẩn bị khi đầu vào không đổi — và PHẢI chạy lại khi có gì đó đổi.

Cache sai ở đây nguy hiểm hơn chậm: dùng chunk của HSMT cũ cho HSMT mới là sai thầm lặng, không
có gì báo. Nên phần lớn test dưới đây là test "phải chạy lại", không phải "được bỏ qua".
"""
import json
from pathlib import Path

import pytest

from experiment.multisource.manifest import Manifest, hash_file, hash_ma_nguon, khoa


# ---- hash ----
def test_hash_file_theo_noi_dung_khong_theo_ten_hay_mtime(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(b"noi dung giong nhau")
    b.write_bytes(b"noi dung giong nhau")
    assert hash_file(a) == hash_file(b)          # khác tên, cùng nội dung -> cùng khóa

    a.write_bytes(b"noi dung DA SUA")
    assert hash_file(a) != hash_file(b)


def test_hash_ma_nguon_doi_khi_sua_code(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "m.py").write_text("x = 1\n", encoding="utf-8")
    truoc = hash_ma_nguon(d)

    (d / "m.py").write_text("x = 2\n", encoding="utf-8")
    assert hash_ma_nguon(d) != truoc, "sửa logic mà khóa không đổi -> im lặng dùng kết quả cũ"


def test_hash_ma_nguon_bo_qua_tests_va_pycache(tmp_path):
    d = tmp_path / "pkg"
    (d / "tests").mkdir(parents=True)
    (d / "__pycache__").mkdir()
    (d / "m.py").write_text("x = 1\n", encoding="utf-8")
    truoc = hash_ma_nguon(d)

    (d / "tests" / "test_x.py").write_text("assert True\n", encoding="utf-8")
    (d / "__pycache__" / "m.pyc").write_bytes(b"\x00\x01")
    assert hash_ma_nguon(d) == truoc, "thêm test mà bắt chạy lại chunk là phí"


def test_khoa_khong_nhap_nhang_khi_ghep():
    assert khoa("ab", "c") != khoa("a", "bc")


# ---- manifest ----
def test_con_moi_chi_dung_khi_khoa_khop_VA_artefact_con(tmp_path):
    art = tmp_path / "chunks.jsonl"
    art.write_text("{}", encoding="utf-8")
    mf = Manifest(tmp_path)
    mf.ghi("chunk", "K1")

    assert mf.con_moi("chunk", "K1", [art]) is True
    assert mf.con_moi("chunk", "K2", [art]) is False        # khóa đổi
    art.unlink()
    assert mf.con_moi("chunk", "K1", [art]) is False        # mất artefact -> không tin khóa suông


def test_manifest_song_qua_lan_chay_moi(tmp_path):
    art = tmp_path / "a.json"
    art.write_text("{}", encoding="utf-8")
    Manifest(tmp_path).ghi("extract", "K")
    assert Manifest(tmp_path).con_moi("extract", "K", [art]) is True


def test_bo_khoa_khi_buoc_chay_do_dang(tmp_path):
    """Bước raise giữa chừng -> khóa phải bị xoá, lần sau KHÔNG được tin file dở."""
    art = tmp_path / "a.json"
    art.write_text("{}", encoding="utf-8")
    mf = Manifest(tmp_path)
    mf.ghi("chunk", "K")
    mf.bo("chunk")
    assert Manifest(tmp_path).con_moi("chunk", "K", [art]) is False


def test_file_manifest_hong_thi_chay_lai_het(tmp_path):
    (tmp_path / "prepare_manifest.json").write_text("{ hỏng", encoding="utf-8")
    art = tmp_path / "a.json"
    art.write_text("{}", encoding="utf-8")
    assert Manifest(tmp_path).con_moi("chunk", "K", [art]) is False   # không raise, chỉ chạy lại


# ---- luồng thật run_multi ----
@pytest.fixture
def gia_lap(tmp_path, monkeypatch):
    """Tiêm mọi bước nặng bằng hàm giả có ĐẾM, để đo bước nào thực sự chạy."""
    import experiment.multisource.run_rubric as rr

    dem = {"chunk": 0, "extract": 0, "ocr": 0}
    hsmt = tmp_path / "hsmt.pdf"
    hsmt.write_bytes(b"HSMT v1")
    tbmt = tmp_path / "tbmt.pdf"
    tbmt.write_bytes(b"TBMT v1")
    out = tmp_path / "work"

    def fake_chunk(pdf, o):
        dem["chunk"] += 1
        (Path(o)).mkdir(parents=True, exist_ok=True)
        (Path(o) / "chunks.jsonl").write_text(
            json.dumps({"chunk_id": "c1", "text": "điều khoản", "source_doc": "hsmt"}) + "\n",
            encoding="utf-8")

    def fake_extract(pdf, o):
        dem["extract"] += 1
        (Path(o) / "chuong3_groups.json").write_text(
            json.dumps({"doc": "HSMT", "groups": []}, ensure_ascii=False), encoding="utf-8")

    async def fake_ocr(pdf, source_doc, vision_fn=None, **kw):
        dem["ocr"] += 1
        return [{"chunk_id": f"{source_doc}-p1-0", "text": "mốc đóng thầu", "source_doc": source_doc}]

    async def fake_summarize(source_doc, chunks, llm_fn=None):
        return {"tom_tat": source_doc, "cac_truong": []}

    def fake_index(**kw):
        return {"n_points": 1}

    async def fake_decompose(**kw):
        return {"doc": "HSMT", "n_criteria": 0}

    monkeypatch.setattr(rr, "chunk_run", fake_chunk)
    monkeypatch.setattr(rr, "extract_run", fake_extract)
    monkeypatch.setattr(rr, "ocr_scan_to_chunks", fake_ocr)
    monkeypatch.setattr(rr, "summarize_source", fake_summarize)
    monkeypatch.setattr(rr, "index_run", fake_index)
    monkeypatch.setattr(rr, "decompose_run", fake_decompose)
    return rr, dem, str(hsmt), str(tbmt), str(out)


async def test_chay_lai_khong_doi_gi_thi_bo_qua_ca_ba_buoc(gia_lap):
    rr, dem, hsmt, tbmt, out = gia_lap
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)
    assert dem == {"chunk": 1, "extract": 1, "ocr": 1}

    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)
    assert dem == {"chunk": 1, "extract": 1, "ocr": 1}, "chạy lại mà vẫn làm lại -> manifest vô dụng"


async def test_doi_HSMT_thi_chunk_va_extract_chay_lai_con_OCR_thi_khong(gia_lap):
    """Khóa phải TÁCH theo file: đổi HSMT không có lý do gì bắt OCR lại TBMT."""
    rr, dem, hsmt, tbmt, out = gia_lap
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)

    Path(hsmt).write_bytes(b"HSMT v2 DA SUA")
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)

    assert dem == {"chunk": 2, "extract": 2, "ocr": 1}


async def test_doi_TBMT_thi_chi_OCR_chay_lai(gia_lap):
    rr, dem, hsmt, tbmt, out = gia_lap
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)

    Path(tbmt).write_bytes(b"TBMT v2 DA SUA")
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)

    assert dem == {"chunk": 1, "extract": 1, "ocr": 2}


async def test_force_thi_chay_lai_het(gia_lap):
    rr, dem, hsmt, tbmt, out = gia_lap
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out, force=True)
    assert dem == {"chunk": 2, "extract": 2, "ocr": 2}


async def test_xoa_artefact_thi_chay_lai_du_khoa_con(gia_lap):
    rr, dem, hsmt, tbmt, out = gia_lap
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)

    (Path(out) / "chunks.jsonl").unlink()
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)
    assert dem["chunk"] == 2 and dem["extract"] == 1


async def test_bo_qua_OCR_van_giu_du_chunk_va_summary(gia_lap):
    """Bỏ qua không được làm MẤT dữ liệu: chunk TBMT vẫn phải vào chunks_merged."""
    rr, dem, hsmt, tbmt, out = gia_lap
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)
    await rr.run_multi(hsmt, [("tbmt", tbmt)], out)

    merged = [json.loads(l) for l in
              (Path(out) / "chunks_merged.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(c["source_doc"] == "tbmt" for c in merged), "bỏ qua OCR làm rơi mất chunk TBMT"
    sums = json.loads((Path(out) / "source_summaries.json").read_text(encoding="utf-8"))
    assert "tbmt" in sums
