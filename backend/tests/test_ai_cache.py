"""Kho cache kết quả chấm trên DB — gắn phạm vi gói/nhà thầu để xóa có chọn lọc."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from services.ai_cache import DbCallCache, xoa_ai_cache


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _pkg(db, ma_so="G-AI"):
    p = models.ProcurementPackage(ma_so=ma_so, ten="g")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_get_none_khi_chua_co(db):
    assert DbCallCache(db, _pkg(db).id, 1).get("k") is None


def test_put_roi_get_tra_dung_du_lieu(db):
    c = DbCallCache(db, _pkg(db).id, 1)
    c.put("k", {"ket_qua": "đạt", "trang": [1]})
    assert c.get("k") == {"ket_qua": "đạt", "trang": [1]}


def test_cung_khoa_ghi_lai_khong_tao_ban_ghi_trung(db):
    pkg = _pkg(db)
    c = DbCallCache(db, pkg.id, 1)
    c.put("k", {"v": 1})
    c.put("k", {"v": 2})
    assert c.get("k") == {"v": 2}
    assert db.query(models.AiCallCache).count() == 1


def test_cache_tach_theo_nha_thau(db):
    """Cùng khóa nhưng khác nhà thầu -> KHÔNG dùng chung (prompt khác nhau, nhưng chặn nhầm lẫn)."""
    pkg = _pkg(db)
    DbCallCache(db, pkg.id, 1).put("k", {"v": "A"})
    assert DbCallCache(db, pkg.id, 2).get("k") is None


def test_xoa_theo_nha_thau(db):
    pkg = _pkg(db)
    DbCallCache(db, pkg.id, 1).put("k", {"v": 1})
    DbCallCache(db, pkg.id, 2).put("k", {"v": 2})

    n = xoa_ai_cache(db, pkg.id, vendor_id=1)
    assert n == 1
    assert DbCallCache(db, pkg.id, 1).get("k") is None
    assert DbCallCache(db, pkg.id, 2).get("k") == {"v": 2}


def test_xoa_goi_thau_thi_cache_di_theo(db):
    """Cache phải sống/chết cùng gói — không để lại rác trỏ tới gói đã xóa."""
    pkg = _pkg(db)
    DbCallCache(db, pkg.id, 1).put("k", {"v": 1})
    db.delete(pkg)
    db.commit()
    assert db.query(models.AiCallCache).count() == 0


def test_xoa_ca_goi_khong_dung_toi_goi_khac(db):
    a, b = _pkg(db), _pkg(db, "G-KHAC")
    DbCallCache(db, a.id, 1).put("k", {"v": 1})
    DbCallCache(db, b.id, 1).put("k", {"v": 2})

    assert xoa_ai_cache(db, a.id) == 1
    assert DbCallCache(db, a.id, 1).get("k") is None
    assert DbCallCache(db, b.id, 1).get("k") == {"v": 2}
