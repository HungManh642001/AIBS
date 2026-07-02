"""Tests report router — sinh Word/Excel từ verdict HSDT (offline, seed DB trực tiếp).

Không gọi /rubric hay /evaluate thật (cần proxy); seed HsdtCriterionEval + HsdtVerdict qua DB.
"""
import io

import pytest
from docx import Document


@pytest.fixture
def db_session(client):  # noqa: ARG001 — phụ thuộc client để DB được khởi tạo trước
    """Session DB dùng chung engine với app."""
    import database as _db
    sess = _db.SessionLocal()
    try:
        yield sess
    finally:
        sess.close()


def _seed_verdict(db, package_id: int, vendor_id: int, ket_qua: str = "đạt") -> int:
    """Tạo 1 HsdtCriterionEval + 1 verdict; trả verdict_id."""
    import models
    ev = models.HsdtCriterionEval(
        package_id=package_id, vendor_id=vendor_id, thu_tu=0, nhom="hop_le",
        ten="Đơn dự thầu hợp lệ", tien_quyet=True, ket_qua=ket_qua,
        loai=(ket_qua == "không đạt"))
    ev.verdicts.append(models.HsdtVerdict(
        thu_tu=0, noi_dung_kiem_tra="Chữ ký & con dấu", hsdt_kiem_tra="don_du_thau",
        yeu_cau="có chữ ký", ket_qua=ket_qua, bang_chung="Có chữ ký, đóng dấu",
        trang=[1], do_tin=0.9))
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev.verdicts[0].id


def _package(client) -> tuple[int, int]:
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-R", "ten": "Gói R", "vendors": ["NhaThauA"]}).json()["data"]
    return p["id"], p["vendors"][0]["id"]


def test_generate_and_download_word(client, db_session):
    pid, vid = _package(client)
    _seed_verdict(db_session, pid, vid)
    gen = client.post(f"/api/v1/packages/{pid}/reports?loai=word").json()["data"]
    assert gen["report_id"]
    dl = client.get(f"/api/v1/reports/{gen['report_id']}/download")
    assert dl.status_code == 200 and len(dl.content) > 0

    doc = Document(io.BytesIO(dl.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "NhaThauA" in text and "Đơn dự thầu hợp lệ" in text


def test_generate_and_download_excel(client, db_session):
    pid, vid = _package(client)
    _seed_verdict(db_session, pid, vid)
    gen = client.post(f"/api/v1/packages/{pid}/reports?loai=excel").json()["data"]
    assert gen["report_id"] and gen["loai"] == "excel"
    dl = client.get(f"/api/v1/reports/{gen['report_id']}/download")
    assert dl.status_code == 200 and len(dl.content) > 0


def test_generate_report_missing_package(client):
    r = client.post("/api/v1/packages/99999/reports?loai=word")
    assert r.status_code == 404


def test_download_missing_report(client):
    r = client.get("/api/v1/reports/99999/download")
    assert r.status_code == 404


def test_export_blocked_when_unresolved_error(client, db_session):
    """Xuất báo cáo phải trả 409 khi còn verdict ket_qua='lỗi' chưa override."""
    pid, vid = _package(client)
    _seed_verdict(db_session, pid, vid, ket_qua="lỗi")
    r = client.post(f"/api/v1/packages/{pid}/reports?loai=excel")
    assert r.status_code == 409
    assert "ai lỗi" in r.json()["error"].lower()
