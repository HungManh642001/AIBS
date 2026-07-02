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
