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


def test_hsdt_criterion_eval_with_verdicts_cascade(db):
    pkg = models.ProcurementPackage(ma_so="G-003", ten="g")
    pkg.vendors.append(models.Vendor(ten="Công ty A"))
    db.add(pkg)
    db.commit()
    ev = models.HsdtCriterionEval(
        package_id=pkg.id, vendor_id=pkg.vendors[0].id, thu_tu=0,
        nhom="hop_le", ten="Bảo đảm dự thầu", tien_quyet=True, ket_qua="đạt", loai=False)
    ev.verdicts.append(models.HsdtVerdict(
        thu_tu=0, noi_dung_kiem_tra="Giá trị bảo lãnh", hsdt_kiem_tra="bao_dam_du_thau",
        ket_qua="đạt", bang_chung="200tr", trang=[1], do_tin=0.9))
    ev.verdicts.append(models.HsdtVerdict(
        thu_tu=1, noi_dung_kiem_tra="Hiệu lực", hsdt_kiem_tra="bao_dam_du_thau",
        ket_qua="đạt", bang_chung="150 ngày", trang=[1, 2], do_tin=0.8))
    db.add(ev)
    db.commit()

    loaded = db.query(models.HsdtCriterionEval).filter_by(package_id=pkg.id).one()
    assert len(loaded.verdicts) == 2 and loaded.verdicts[0].trang == [1]

    db.delete(loaded)  # cascade -> xoá verdicts
    db.commit()
    assert db.query(models.HsdtVerdict).count() == 0
