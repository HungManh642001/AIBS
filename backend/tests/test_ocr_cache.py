"""Adapter cache OCR trên DB — text đã bóc gắn vào tender_document, khóa theo nội dung file."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from services.ocr_cache import DocumentOcrCache, xoa_cache


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _doc(db, pkg_id: int, vendor_id: int | None = None, path: str = "1/hsdt/1/a.pdf"):
    d = models.TenderDocument(package_id=pkg_id, loai="HSDT", vendor_id=vendor_id,
                              file_path=path, file_kind="pdf_scan", artifact_type="don_du_thau")
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _pkg(db, ma_so: str = "G-OCR"):
    p = models.ProcurementPackage(ma_so=ma_so, ten="g")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


_PAGES = [{"trang": 1, "text": "đơn dự thầu", "co_chu_ky": True, "co_dau": False}]


def test_get_tra_none_khi_chua_cache(db):
    pkg = _pkg(db)
    doc = _doc(db, pkg.id)
    cache = DocumentOcrCache(db, {"k1": doc.id})
    assert cache.get("k1") is None


def test_put_roi_get_tra_dung_trang(db):
    pkg = _pkg(db)
    doc = _doc(db, pkg.id)
    cache = DocumentOcrCache(db, {"k1": doc.id})
    cache.put("k1", _PAGES)
    assert cache.get("k1") == _PAGES
    db.refresh(doc)
    assert doc.ocr_key == "k1" and doc.ocr_pages == _PAGES


def test_get_tra_none_khi_khoa_khac_tai_lieu_da_doi(db):
    """File được tải lại bản khác -> khóa mới không khớp ocr_key cũ -> phải OCR lại."""
    pkg = _pkg(db)
    doc = _doc(db, pkg.id)
    DocumentOcrCache(db, {"k_cu": doc.id}).put("k_cu", _PAGES)
    cache_moi = DocumentOcrCache(db, {"k_moi": doc.id})
    assert cache_moi.get("k_moi") is None


def test_khoa_khong_thuoc_ban_do_thi_bo_qua(db):
    """Khóa lạ (không map tới tài liệu nào) -> get None, put im lặng bỏ qua, KHÔNG nổ."""
    cache = DocumentOcrCache(db, {})
    assert cache.get("la") is None
    cache.put("la", _PAGES)          # không raise


def test_xoa_cache_theo_tai_lieu(db):
    pkg = _pkg(db)
    d1, d2 = _doc(db, pkg.id, path="a.pdf"), _doc(db, pkg.id, path="b.pdf")
    for d in (d1, d2):
        DocumentOcrCache(db, {"k": d.id}).put("k", _PAGES)

    n = xoa_cache(db, pkg.id, doc_id=d1.id)
    db.refresh(d1); db.refresh(d2)
    assert n == 1
    assert d1.ocr_key == "" and d1.ocr_pages == []
    assert d2.ocr_key == "k"                       # tài liệu khác KHÔNG bị đụng


def test_xoa_cache_theo_nha_thau(db):
    pkg = _pkg(db)
    va = models.Vendor(package_id=pkg.id, ten="A")
    vb = models.Vendor(package_id=pkg.id, ten="B")
    db.add_all([va, vb]); db.commit()
    da = _doc(db, pkg.id, vendor_id=va.id, path="a.pdf")
    dbv = _doc(db, pkg.id, vendor_id=vb.id, path="b.pdf")
    for d in (da, dbv):
        DocumentOcrCache(db, {"k": d.id}).put("k", _PAGES)

    n = xoa_cache(db, pkg.id, vendor_id=va.id)
    db.refresh(da); db.refresh(dbv)
    assert n == 1 and da.ocr_key == "" and dbv.ocr_key == "k"


def test_xoa_cache_ca_goi(db):
    pkg = _pkg(db)
    khac = _pkg(db, ma_so="G-KHAC")
    d1 = _doc(db, pkg.id, path="a.pdf")
    d2 = _doc(db, khac.id, path="b.pdf")
    for d in (d1, d2):
        DocumentOcrCache(db, {"k": d.id}).put("k", _PAGES)

    n = xoa_cache(db, pkg.id)
    db.refresh(d1); db.refresh(d2)
    assert n == 1 and d1.ocr_key == ""
    assert d2.ocr_key == "k"                       # gói khác KHÔNG bị đụng


def test_xoa_cache_bo_qua_tai_lieu_chua_cache(db):
    pkg = _pkg(db)
    _doc(db, pkg.id)
    assert xoa_cache(db, pkg.id) == 0      # không có gì để xóa -> 0
