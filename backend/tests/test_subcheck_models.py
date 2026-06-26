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


def test_document_artifact_fields(db):
    pkg = models.ProcurementPackage(ma_so="G1", ten="g")
    db.add(pkg); db.commit(); db.refresh(pkg)
    doc = models.TenderDocument(package_id=pkg.id, loai="HSDT", file_path="x",
                                artifact_type="bao_dam_du_thau",
                                artifact_validation={"match": True, "confidence": 0.5})
    db.add(doc); db.commit(); db.refresh(doc)
    assert doc.artifact_type == "bao_dam_du_thau"
    assert doc.artifact_validation["match"] is True


def test_criteria_with_sub_checks_and_results(db):
    pkg = models.ProcurementPackage(ma_so="G2", ten="g"); db.add(pkg); db.commit(); db.refresh(pkg)
    c = models.EvaluationCriteria(package_id=pkg.id, nhom="hop_le", ten="Bảo đảm dự thầu",
                                  required_artifacts=["bao_dam_du_thau"])
    db.add(c); db.commit(); db.refresh(c)
    sc = models.EvaluationSubCheck(criteria_id=c.id, ten="Giá trị ≥ ngưỡng",
                                   check_type="value_threshold",
                                   thong_so={"gia_tri_so": 150000000}, required_artifact="bao_dam_du_thau",
                                   thu_tu=1, blocking=True)
    db.add(sc); db.commit(); db.refresh(sc)
    r = models.SubCheckResult(sub_check_id=sc.id, vendor_id=1, ket_qua="PASS",
                              evidence="Giá trị 200tr", page_ref=[2], nguon_file="bao_dam_du_thau")
    db.add(r); db.commit(); db.refresh(r)
    assert c.required_artifacts == ["bao_dam_du_thau"]
    assert sc.thong_so["gia_tri_so"] == 150000000 and sc.blocking is True
    assert r.ket_qua == "PASS" and r.page_ref == [2]
