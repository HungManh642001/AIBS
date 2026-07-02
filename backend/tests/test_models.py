import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_package_with_vendor_and_criteria(db):
    pkg = models.ProcurementPackage(ma_so="G-001", ten="Mua sắm máy tính")
    pkg.vendors.append(models.Vendor(ten="Công ty A"))
    pkg.criteria.append(models.EvaluationCriteria(nhom="hop_le", ten="Đơn dự thầu"))
    db.add(pkg)
    db.commit()
    loaded = db.query(models.ProcurementPackage).filter_by(ma_so="G-001").one()
    assert loaded.trang_thai == "khoi_tao"
    assert loaded.vendors[0].ten == "Công ty A"
    assert loaded.criteria[0].nhom == "hop_le"


def test_rubric_criterion_with_noi_dung_cascade(db):
    pkg = models.ProcurementPackage(ma_so="G-002", ten="g")
    db.add(pkg)
    db.commit()
    crit = models.RubricCriterion(
        package_id=pkg.id, nhom="hop_le", ten="Bảo đảm dự thầu",
        yeu_cau_goc="theo E-HSMT", hsdt_can_kiem_tra=["bao_dam_du_thau"], tien_quyet=True)
    crit.noi_dung.append(models.RubricNoiDung(
        noi_dung_kiem_tra="Giá trị bảo lãnh", hsdt_kiem_tra="bao_dam_du_thau",
        can_tra_cuu=True, thong_tin_bo_sung="6.100.000 VNĐ", nguon="E-BDL 18.2"))
    db.add(crit)
    db.commit()

    loaded = db.query(models.RubricCriterion).filter_by(package_id=pkg.id).one()
    assert loaded.tien_quyet is True and loaded.hsdt_can_kiem_tra == ["bao_dam_du_thau"]
    assert loaded.noi_dung[0].thong_tin_bo_sung == "6.100.000 VNĐ"

    db.delete(loaded)  # cascade -> xoá noi_dung
    db.commit()
    assert db.query(models.RubricNoiDung).count() == 0
