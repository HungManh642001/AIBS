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
