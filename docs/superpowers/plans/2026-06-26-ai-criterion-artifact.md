# AI Criterion→Artifact→Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng cấp lớp AI của ABES để mỗi tiêu chí HSMT được đánh giá đúng trên loại hồ sơ HSDT tương ứng (qua khóa `artifact_type`), bóc tách thành sub-check có cấu trúc, giải tham chiếu chéo cho HSMT lớn, và để chuyên gia review "đề cương chấm" — kiểm chứng trên nhóm Hợp lệ.

**Architecture:** Pipeline 4 tầng. (1) Định vị mục HSMT (TCĐG+BDS) rồi `extract_de_cuong` sinh tiêu chí → `required_artifacts` + `sub_checks` + ngưỡng (giải tham chiếu chéo). (2) Chuyên gia review/sửa đề cương → chốt. (3) Upload HSDT từng file theo loại, người dùng chọn `artifact_type` + AI `validate_artifact`. (4) Đánh giá định tuyến: mỗi tiêu chí lấy đúng file khớp artifact, chạy sub-check (tất định bằng Python cho value/date, AI cho ngữ nghĩa), thiếu file → FAIL "thiếu hồ sơ", tổng hợp sub-check → verdict.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest (asyncio_mode=auto); React 18 + Vite + TS + Ant Design + axios. AI qua `services/ai_client.ai_json` (LiteLLM + mock fallback).

## Global Constraints

- Python 3.11, **type hints bắt buộc**, PEP 8, snake_case.
- API response envelope **luôn** `{"success": bool, "data": ..., "error": ...}` (error null khi success, data null khi fail).
- Route handlers I/O dùng `async`/`await`.
- Tiền dùng `Decimal`; số/ngày trong sub-check tất định tính bằng Python, không float cho tiền.
- AI: gọi `ai_json(system, prompt, *, mock_key)`; nếu `ai_mock` hoặc lỗi → mock JSON. Mỗi sub-result AI **bắt buộc** `evidence` + `page_ref`.
- Comment/UI tiếng Việt, code tiếng Anh.
- Mỗi module business-logic có pytest test. DB demo: SQLite; `init_db()` tạo bảng mới (reset được, không cần migration).
- Mỗi task TDD: viết test fail → code → pass → commit (prefix `feat:`/`test:`/`fix:`).
- Build lên branch `feat/abes-demo` (codebase demo đã hoàn chỉnh, full suite 31 passed). Frontend KHÔNG chạy được `tsc`/`npm` trong WSL (thiếu node) → verify tĩnh, người dùng chạy ở môi trường có node.

---

## File Structure

```
backend/
  services/
    artifact_catalog.py         # MỚI: danh mục loại hồ sơ + tra cứu + match theo alias
    hsmt_locator.py             # MỚI: định vị mục TCĐG + BDS trong HSMT lớn
    artifact_classify.py        # MỚI: validate_artifact (AI kiểm khớp loại lúc upload)
    extraction.py               # SỬA: thêm extract_de_cuong (giữ extract_criteria cũ)
    evaluation/
      checks.py                 # MỚI: helper tất định presence/value_threshold/date_validity
      base.py                   # SỬA: thêm evaluate_criterion + aggregate_subresults (giữ eval_one)
      legality.py               # SỬA: thêm evaluate_legality_routed + compute_completeness
  models.py                     # SỬA: TenderDocument +artifact_*, EvaluationCriteria +required_artifacts,
                                #      MỚI bảng EvaluationSubCheck + SubCheckResult
  routers/
    documents.py                # SỬA: nhận artifact_type + chạy validate_artifact
    de_cuong.py                 # MỚI: GET/PUT/confirm đề cương (extract → sửa → chốt)
    evaluation.py               # SỬA: evaluate định tuyến theo artifact + lưu sub_check_result + roll-up
  tests/
    test_artifact_catalog.py, test_hsmt_locator.py, test_artifact_classify.py,
    test_extract_de_cuong.py, test_checks.py, test_evaluate_criterion.py,
    test_legality_routed.py, test_subcheck_models.py,
    test_documents_artifact_api.py, test_de_cuong_api.py, test_evaluation_routed_api.py
frontend/src/
  api/types.ts                  # SỬA: thêm SubCheck, SubResult, DeCuong types
  pages/PackageDetail.tsx       # SỬA: select artifact_type khi upload HSDT + cảnh báo nhầm
  pages/DeCuong.tsx             # MỚI: màn review/sửa đề cương
  pages/Evaluation.tsx          # SỬA: breakdown theo sub-check + override mức sub-check
  components/SubCheckTable.tsx  # MỚI: bảng sub-check (evidence + override)
```

---

### Task 1: Artifact Catalog

**Files:**
- Create: `backend/services/artifact_catalog.py`
- Test: `backend/tests/test_artifact_catalog.py`

**Interfaces:**
- Produces:
  - `CATALOG: dict[str, dict]` — key = code, value = `{"label": str, "nhom": str, "mo_ta": str, "aliases": list[str]}`.
  - `get_artifact(code: str) -> dict | None`
  - `all_codes() -> list[str]`
  - `match_artifact(text: str) -> tuple[str | None, float]` — trả `(code, confidence)`: code có nhiều alias xuất hiện nhất trong `text` (lowercase), confidence = số alias khớp / tổng alias của code đó; `(None, 0.0)` nếu không alias nào khớp.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_artifact_catalog.py`

```python
from services import artifact_catalog as cat


def test_catalog_has_legality_codes():
    for code in ["don_du_thau", "bao_dam_du_thau", "thoa_thuan_lien_danh", "tu_cach_phap_ly"]:
        a = cat.get_artifact(code)
        assert a is not None and a["nhom"] == "hop_le" and a["label"]


def test_all_codes_includes_other_groups():
    codes = set(cat.all_codes())
    assert {"bao_cao_tai_chinh", "hop_dong_tuong_tu", "bang_gia"} <= codes


def test_match_artifact_by_alias():
    code, conf = cat.match_artifact("Đây là THƯ BẢO LÃNH dự thầu của ngân hàng")
    assert code == "bao_dam_du_thau" and conf > 0


def test_match_artifact_none_when_no_alias():
    code, conf = cat.match_artifact("nội dung không liên quan abcxyz")
    assert code is None and conf == 0.0
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_artifact_catalog.py -v`
Expected: ImportError / module missing.

- [ ] **Step 3: Viết `backend/services/artifact_catalog.py`**

```python
"""Danh mục loại hồ sơ (artifact) chuẩn theo Luật 22/2023 & NĐ 24/2024."""
from __future__ import annotations

CATALOG: dict[str, dict] = {
    "don_du_thau": {
        "label": "Đơn dự thầu", "nhom": "hop_le",
        "mo_ta": "Đơn dự thầu theo mẫu, có chữ ký và đóng dấu hợp lệ.",
        "aliases": ["đơn dự thầu", "don du thau", "mẫu số 01", "đơn xin dự thầu"],
    },
    "bao_dam_du_thau": {
        "label": "Bảo đảm dự thầu", "nhom": "hop_le",
        "mo_ta": "Thư bảo lãnh ngân hàng hoặc đặt cọc bảo đảm dự thầu.",
        "aliases": ["bảo đảm dự thầu", "bao dam du thau", "thư bảo lãnh", "thu bao lanh", "bảo lãnh dự thầu"],
    },
    "thoa_thuan_lien_danh": {
        "label": "Thỏa thuận liên danh", "nhom": "hop_le",
        "mo_ta": "Thỏa thuận liên danh nếu nhà thầu dự thầu theo hình thức liên danh.",
        "aliases": ["thỏa thuận liên danh", "thoa thuan lien danh", "liên danh"],
    },
    "tu_cach_phap_ly": {
        "label": "Tài liệu tư cách hợp lệ", "nhom": "hop_le",
        "mo_ta": "Giấy chứng nhận đăng ký doanh nghiệp, tư cách pháp lý.",
        "aliases": ["đăng ký doanh nghiệp", "dkkd", "tư cách hợp lệ", "tư cách pháp lý", "giấy chứng nhận đăng ký"],
    },
    "bao_cao_tai_chinh": {
        "label": "Báo cáo tài chính", "nhom": "nang_luc",
        "mo_ta": "Báo cáo tài chính các năm gần nhất.", "aliases": ["báo cáo tài chính", "bctc", "bao cao tai chinh"],
    },
    "hop_dong_tuong_tu": {
        "label": "Hợp đồng tương tự", "nhom": "nang_luc",
        "mo_ta": "Danh sách và chứng minh hợp đồng tương tự.", "aliases": ["hợp đồng tương tự", "hop dong tuong tu"],
    },
    "ke_khai_nhan_su": {
        "label": "Kê khai nhân sự", "nhom": "nang_luc",
        "mo_ta": "Nhân sự chủ chốt, CV, chứng chỉ.", "aliases": ["nhân sự chủ chốt", "ke khai nhan su", "cv nhân sự"],
    },
    "ke_khai_thiet_bi": {
        "label": "Kê khai thiết bị", "nhom": "nang_luc",
        "mo_ta": "Thiết bị, máy móc huy động.", "aliases": ["kê khai thiết bị", "thiết bị máy móc", "ke khai thiet bi"],
    },
    "de_xuat_ky_thuat": {
        "label": "Đề xuất kỹ thuật", "nhom": "ky_thuat",
        "mo_ta": "Thuyết minh giải pháp kỹ thuật.", "aliases": ["đề xuất kỹ thuật", "de xuat ky thuat", "giải pháp kỹ thuật"],
    },
    "catalogue_thong_so": {
        "label": "Catalogue / Bảng thông số", "nhom": "ky_thuat",
        "mo_ta": "Catalogue, bảng thông số kỹ thuật hàng hóa.", "aliases": ["catalogue", "thông số kỹ thuật", "bảng thông số"],
    },
    "bang_gia": {
        "label": "Bảng giá dự thầu", "nhom": "tai_chinh",
        "mo_ta": "Bảng chào giá chi tiết.", "aliases": ["bảng giá", "bang gia", "biểu giá", "chào giá"],
    },
}


def get_artifact(code: str) -> dict | None:
    return CATALOG.get(code)


def all_codes() -> list[str]:
    return list(CATALOG.keys())


def match_artifact(text: str) -> tuple[str | None, float]:
    """Trả (code, confidence) — code có nhiều alias khớp nhất trong text."""
    low = text.lower()
    best_code: str | None = None
    best_conf = 0.0
    for code, info in CATALOG.items():
        aliases = info["aliases"]
        hits = sum(1 for a in aliases if a.lower() in low)
        if hits == 0:
            continue
        conf = hits / len(aliases)
        if conf > best_conf:
            best_conf, best_code = conf, code
    return best_code, best_conf
```

- [ ] **Step 4: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_artifact_catalog.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/artifact_catalog.py backend/tests/test_artifact_catalog.py
git commit -m "feat: artifact catalog with alias matching"
```

---

### Task 2: Data model — artifact fields + sub-check tables

**Files:**
- Modify: `backend/models.py`
- Test: `backend/tests/test_subcheck_models.py`

**Interfaces:**
- Consumes: `Base`, existing entities.
- Produces:
  - `TenderDocument` +`artifact_type: Mapped[str | None]`, +`artifact_validation: Mapped[dict]` (JSON, default dict).
  - `EvaluationCriteria` +`required_artifacts: Mapped[list[str]]` (JSON, default list).
  - `EvaluationSubCheck(id, criteria_id, ten, check_type, thong_so: dict, required_artifact: str, thu_tu: int, blocking: bool)`.
  - `SubCheckResult(id, sub_check_id, vendor_id, ket_qua, evidence, page_ref: list, nguon_file, ai_model, overridden, ghi_chu)`.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_subcheck_models.py`

```python
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
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_subcheck_models.py -v`
Expected: FAIL (`TypeError: 'artifact_type' is an invalid keyword` hoặc model thiếu).

- [ ] **Step 3: Sửa `backend/models.py`**

Trong class `TenderDocument`, thêm sau dòng `extracted_text`:
```python
    artifact_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_validation: Mapped[dict] = mapped_column(JSON, default=dict)
```
Trong class `EvaluationCriteria`, thêm sau dòng `kieu`:
```python
    required_artifacts: Mapped[list[str]] = mapped_column(JSON, default=list)
```
Thêm 2 class mới (cuối file, sau `AuditLog`):
```python
class EvaluationSubCheck(Base):
    __tablename__ = "evaluation_sub_check"
    id: Mapped[int] = mapped_column(primary_key=True)
    criteria_id: Mapped[int] = mapped_column(ForeignKey("evaluation_criteria.id"))
    ten: Mapped[str] = mapped_column(String(512))
    check_type: Mapped[str] = mapped_column(String(32))
    thong_so: Mapped[dict] = mapped_column(JSON, default=dict)
    required_artifact: Mapped[str] = mapped_column(String(64), default="")
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    blocking: Mapped[bool] = mapped_column(default=True)


class SubCheckResult(Base):
    __tablename__ = "sub_check_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    sub_check_id: Mapped[int] = mapped_column(ForeignKey("evaluation_sub_check.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendor.id"))
    ket_qua: Mapped[str] = mapped_column(String(16), default="PARTIAL")
    evidence: Mapped[str] = mapped_column(Text, default="")
    page_ref: Mapped[list[int]] = mapped_column(JSON, default=list)
    nguon_file: Mapped[str] = mapped_column(String(64), default="")
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    overridden: Mapped[bool] = mapped_column(default=False)
    ghi_chu: Mapped[str] = mapped_column(Text, default="")
```
**Lưu ý:** thêm `Integer` vào dòng import `from sqlalchemy import ...` nếu chưa có (Task 2 cũ đã bỏ `Integer`; thêm lại vì `EvaluationSubCheck.thu_tu` dùng `Integer`).

- [ ] **Step 4: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_subcheck_models.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/tests/test_subcheck_models.py
git commit -m "feat: artifact fields and sub-check tables in data model"
```

---

### Task 3: HSMT section locator

**Files:**
- Create: `backend/services/hsmt_locator.py`
- Test: `backend/tests/test_hsmt_locator.py`

**Interfaces:**
- Consumes: PageText shape `{"page": int, "text": str}`.
- Produces: `locate_hsmt_sections(hsmt_pages: list[dict]) -> dict` → `{"tcdg": list[dict], "bds": list[dict]}` (mỗi value là danh sách page dicts). Heuristic: trang chứa từ khóa TCĐG ("tiêu chuẩn đánh giá") → nhóm `tcdg`; trang chứa "bảng dữ liệu đấu thầu"/"bảng dữ liệu" → `bds`. Một trang có thể vào cả hai. **Fallback**: nếu không tìm được trang nào cho một nhóm → nhóm đó = toàn bộ `hsmt_pages` (để extraction vẫn chạy).

- [ ] **Step 1: Viết test fail** — `backend/tests/test_hsmt_locator.py`

```python
from services.hsmt_locator import locate_hsmt_sections

PAGES = [
    {"page": 1, "text": "Chương I. Bảng dữ liệu đấu thầu. Giá trị bảo đảm dự thầu: 150 triệu"},
    {"page": 2, "text": "Nội dung khác không liên quan"},
    {"page": 3, "text": "Chương III. Tiêu chuẩn đánh giá về tính hợp lệ"},
]


def test_locates_tcdg_and_bds():
    out = locate_hsmt_sections(PAGES)
    assert [p["page"] for p in out["tcdg"]] == [3]
    assert [p["page"] for p in out["bds"]] == [1]


def test_fallback_when_section_missing():
    pages = [{"page": 1, "text": "không có heading chuẩn nào cả"}]
    out = locate_hsmt_sections(pages)
    # fallback: cả hai nhóm = toàn bộ trang
    assert out["tcdg"] == pages and out["bds"] == pages
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_hsmt_locator.py -v`
Expected: ImportError.

- [ ] **Step 3: Viết `backend/services/hsmt_locator.py`**

```python
"""Định vị mục Tiêu chuẩn đánh giá (TCĐG) + Bảng dữ liệu đấu thầu (BDS) trong HSMT lớn."""
from __future__ import annotations

_TCDG_KW = ["tiêu chuẩn đánh giá", "tieu chuan danh gia"]
_BDS_KW = ["bảng dữ liệu đấu thầu", "bang du lieu dau thau", "bảng dữ liệu"]


def _pick(pages: list[dict], keywords: list[str]) -> list[dict]:
    out = [p for p in pages if any(k in p["text"].lower() for k in keywords)]
    return out


def locate_hsmt_sections(hsmt_pages: list[dict]) -> dict:
    tcdg = _pick(hsmt_pages, _TCDG_KW)
    bds = _pick(hsmt_pages, _BDS_KW)
    # Fallback: không định vị được -> dùng toàn bộ trang để extraction vẫn chạy
    if not tcdg:
        tcdg = hsmt_pages
    if not bds:
        bds = hsmt_pages
    return {"tcdg": tcdg, "bds": bds}
```

- [ ] **Step 4: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_hsmt_locator.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/hsmt_locator.py backend/tests/test_hsmt_locator.py
git commit -m "feat: HSMT section locator for TCDG and BDS"
```

---

### Task 4: `extract_de_cuong` + richer mock

**Files:**
- Modify: `backend/services/extraction.py` (thêm hàm, giữ `extract_criteria`)
- Modify: `backend/services/ai_client.py` (thêm mock key `extract_de_cuong`)
- Test: `backend/tests/test_extract_de_cuong.py`

**Interfaces:**
- Consumes: `ai_client.ai_json` (mock_key `"extract_de_cuong"`), `hsmt_locator` shape.
- Produces: `async def extract_de_cuong(sections: dict) -> list[dict]` — `sections` = `{"tcdg": [...], "bds": [...]}`. Trả list criterion: `{nhom, ten, yeu_cau, required_artifacts: list[str], kieu, trong_so, sub_checks: list[dict], proposed_artifacts: list[dict]}`. Mỗi sub_check: `{ten, check_type, thong_so: dict, required_artifact: str, blocking: bool}`.

- [ ] **Step 1: Thêm mock vào `backend/services/ai_client.py`**

Trong dict `MOCK_RESPONSES`, thêm key:
```python
    "extract_de_cuong": {
        "criteria": [
            {"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ", "yeu_cau": "Theo mẫu, có chữ ký",
             "required_artifacts": ["don_du_thau"], "kieu": "pass_fail", "trong_so": 0,
             "sub_checks": [
                 {"ten": "Có đơn dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "don_du_thau", "blocking": True},
                 {"ten": "Có chữ ký/đóng dấu", "check_type": "signature_stamp", "thong_so": {}, "required_artifact": "don_du_thau", "blocking": True},
             ], "proposed_artifacts": []},
            {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "yeu_cau": "Giá trị và hiệu lực theo HSMT",
             "required_artifacts": ["bao_dam_du_thau"], "kieu": "pass_fail", "trong_so": 0,
             "sub_checks": [
                 {"ten": "Có bảo đảm dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": True},
                 {"ten": "Giá trị ≥ ngưỡng", "check_type": "value_threshold",
                  "thong_so": {"gia_tri_so": 150000000, "don_vi": "VND", "nguon": "BDS", "can_review": False},
                  "required_artifact": "bao_dam_du_thau", "blocking": True},
                 {"ten": "Hiệu lực ≥ yêu cầu", "check_type": "date_validity",
                  "thong_so": {"so_ngay": 120, "nguon": "BDS", "can_review": False},
                  "required_artifact": "bao_dam_du_thau", "blocking": True},
             ], "proposed_artifacts": []},
        ]
    },
```

- [ ] **Step 2: Viết test fail** — `backend/tests/test_extract_de_cuong.py`

```python
import pytest
from services import extraction, ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_extract_de_cuong_shape():
    sections = {"tcdg": [{"page": 3, "text": "Tiêu chuẩn đánh giá"}],
                "bds": [{"page": 1, "text": "Giá trị bảo đảm: 150 triệu"}]}
    crit = await extraction.extract_de_cuong(sections)
    bdt = next(c for c in crit if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["required_artifacts"] == ["bao_dam_du_thau"]
    sc = {s["check_type"]: s for s in bdt["sub_checks"]}
    assert sc["value_threshold"]["thong_so"]["gia_tri_so"] == 150000000
    assert sc["value_threshold"]["thong_so"]["can_review"] is False
    assert all("required_artifact" in s and "blocking" in s for s in bdt["sub_checks"])
```

- [ ] **Step 3: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_extract_de_cuong.py -v`
Expected: FAIL (`extract_de_cuong` chưa có).

- [ ] **Step 4: Thêm hàm vào `backend/services/extraction.py`**

```python
# --- append to services/extraction.py ---
from services import artifact_catalog

_SYS_DE_CUONG = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc Tiêu chuẩn đánh giá (TCĐG) "
    "và Bảng dữ liệu đấu thầu (BDS) của HSMT. Với mỗi tiêu chí: xác định loại hồ sơ cần kiểm tra "
    "(required_artifacts theo danh mục cho sẵn), bóc tách thành các điểm kiểm con (sub_checks) kèm "
    "check_type và ngưỡng (thong_so). Khi tiêu chí tham chiếu 'theo yêu cầu HSMT', tra số cụ thể từ BDS "
    "và ghi nguồn (thong_so.nguon); nếu không tìm được, đặt thong_so.can_review=true. Chỉ trả JSON."
)


async def extract_de_cuong(sections: dict[str, Any]) -> list[dict[str, Any]]:
    catalog_codes = ", ".join(
        f"{c}={artifact_catalog.get_artifact(c)['label']}" for c in artifact_catalog.all_codes()
    )
    tcdg = _join(sections.get("tcdg", []))
    bds = _join(sections.get("bds", []))
    prompt = (
        f"Danh mục loại hồ sơ (code=label): {catalog_codes}\n\n"
        f"TIÊU CHUẨN ĐÁNH GIÁ:\n{tcdg}\n\n"
        f"BẢNG DỮ LIỆU ĐẤU THẦU:\n{bds}\n\n"
        'Trả JSON: {"criteria":[{"nhom","ten","yeu_cau","required_artifacts":[...],'
        '"kieu","trong_so","sub_checks":[{"ten","check_type","thong_so","required_artifact","blocking"}],'
        '"proposed_artifacts":[]}]}'
    )
    data = await ai_json(_SYS_DE_CUONG, prompt, mock_key="extract_de_cuong")
    return data.get("criteria", [])
```

- [ ] **Step 5: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_extract_de_cuong.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/extraction.py backend/services/ai_client.py backend/tests/test_extract_de_cuong.py
git commit -m "feat: extract_de_cuong with artifact mapping and cross-reference"
```

---

### Task 5: `validate_artifact` (AI kiểm khớp loại)

**Files:**
- Create: `backend/services/artifact_classify.py`
- Modify: `backend/services/ai_client.py` (mock key `validate_artifact`)
- Test: `backend/tests/test_artifact_classify.py`

**Interfaces:**
- Consumes: `ai_json` (mock_key `"validate_artifact"`), `artifact_catalog`.
- Produces: `async def validate_artifact(file_pages: list[dict], declared_type: str) -> dict` → `{match: bool, suggested_type: str, confidence: float, note: str}`. Khi mock: dùng `artifact_catalog.match_artifact` trên text file để cho kết quả thực tế (match nếu suggested == declared).

- [ ] **Step 1: Thêm mock vào `ai_client.py`** (giá trị placeholder, sẽ bị override bởi logic match thực tế trong hàm khi mock):
```python
    "validate_artifact": {"match": True, "suggested_type": "", "confidence": 1.0, "note": "Khớp loại khai báo"},
```

- [ ] **Step 2: Viết test fail** — `backend/tests/test_artifact_classify.py`

```python
import pytest
from services import artifact_classify, ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_validate_match_true_for_correct_file():
    pages = [{"page": 1, "text": "THƯ BẢO LÃNH dự thầu của ngân hàng ABC"}]
    out = await artifact_classify.validate_artifact(pages, "bao_dam_du_thau")
    assert out["match"] is True


@pytest.mark.asyncio
async def test_validate_match_false_for_wrong_file():
    pages = [{"page": 1, "text": "Đây là báo cáo tài chính năm 2025"}]
    out = await artifact_classify.validate_artifact(pages, "bao_dam_du_thau")
    assert out["match"] is False and out["suggested_type"] == "bao_cao_tai_chinh"
```

- [ ] **Step 3: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_artifact_classify.py -v`
Expected: ImportError.

- [ ] **Step 4: Viết `backend/services/artifact_classify.py`**

```python
"""Kiểm tra file HSDT có khớp loại hồ sơ người dùng khai báo không."""
from __future__ import annotations
from typing import Any

from services import artifact_catalog
from services.ai_client import ai_json, settings

_SYS = "Bạn là trợ lý phân loại hồ sơ thầu. Chỉ trả JSON."


def _text(pages: list[dict[str, Any]], limit: int = 6000) -> str:
    return "\n".join(p["text"] for p in pages)[:limit]


async def validate_artifact(file_pages: list[dict[str, Any]], declared_type: str) -> dict[str, Any]:
    text = _text(file_pages)
    if settings.ai_mock:
        # Mock tất định: dùng alias-matching thực tế của catalog
        code, conf = artifact_catalog.match_artifact(text)
        match = code is not None and code == declared_type
        return {"match": match, "suggested_type": code or "", "confidence": round(conf, 2),
                "note": "Khớp" if match else "Nội dung có thể không khớp loại khai báo", "_model": "mock"}
    declared = artifact_catalog.get_artifact(declared_type)
    label = declared["label"] if declared else declared_type
    prompt = (f"Loại khai báo: {label}. Nội dung file:\n{text}\n\n"
              'Trả JSON: {"match":true|false,"suggested_type":"<code hoặc rỗng>","confidence":0-1,"note":"..."}')
    return await ai_json(_SYS, prompt, mock_key="validate_artifact")
```

- [ ] **Step 5: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_artifact_classify.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/artifact_classify.py backend/services/ai_client.py backend/tests/test_artifact_classify.py
git commit -m "feat: validate_artifact with deterministic mock via catalog matching"
```

---

### Task 6: Deterministic check helpers

**Files:**
- Create: `backend/services/evaluation/checks.py`
- Test: `backend/tests/test_checks.py`

**Interfaces:**
- Produces:
  - `def run_deterministic_check(check_type: str, content: str, thong_so: dict) -> dict | None` — chỉ xử lý `value_threshold`, `date_validity`, `presence`; trả `{"result": "PASS|FAIL", "evidence": str}` hoặc `None` nếu không áp dụng được (→ caller fallback sang AI). Số liệu trích từ `content` bằng regex.
    - `presence`: PASS nếu `content.strip()` không rỗng, else FAIL.
    - `value_threshold`: trích số lớn nhất trong `content` (bỏ dấu chấm/phẩy ngăn cách), so với `thong_so["gia_tri_so"]`; PASS nếu ≥. None nếu thiếu `gia_tri_so` hoặc không trích được số.
    - `date_validity`: trích "<N> ngày" trong `content`, so với `thong_so["so_ngay"]`; PASS nếu ≥. None nếu thiếu hoặc không trích được.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_checks.py`

```python
from services.evaluation.checks import run_deterministic_check


def test_presence_pass_and_fail():
    assert run_deterministic_check("presence", "có nội dung", {})["result"] == "PASS"
    assert run_deterministic_check("presence", "   ", {})["result"] == "FAIL"


def test_value_threshold_pass():
    r = run_deterministic_check("value_threshold", "Giá trị bảo đảm 200.000.000 đồng", {"gia_tri_so": 150000000})
    assert r["result"] == "PASS"


def test_value_threshold_fail():
    r = run_deterministic_check("value_threshold", "Giá trị bảo đảm 100.000.000 đồng", {"gia_tri_so": 150000000})
    assert r["result"] == "FAIL"


def test_value_threshold_none_when_no_number():
    assert run_deterministic_check("value_threshold", "không có số", {"gia_tri_so": 150000000}) is None


def test_date_validity_pass_and_fail():
    assert run_deterministic_check("date_validity", "hiệu lực 150 ngày", {"so_ngay": 120})["result"] == "PASS"
    assert run_deterministic_check("date_validity", "hiệu lực 90 ngày", {"so_ngay": 120})["result"] == "FAIL"


def test_unsupported_type_returns_none():
    assert run_deterministic_check("semantic_match", "x", {}) is None
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_checks.py -v`
Expected: ImportError.

- [ ] **Step 3: Viết `backend/services/evaluation/checks.py`**

```python
"""Helper kiểm tra tất định (Python) cho các check_type có số/ngày — không phụ thuộc AI."""
from __future__ import annotations
import re
from typing import Any


def _max_number(text: str) -> int | None:
    """Trích số lớn nhất (bỏ '.'/',' ngăn cách hàng nghìn)."""
    candidates = re.findall(r"\d[\d.,]*", text)
    nums: list[int] = []
    for c in candidates:
        digits = c.replace(".", "").replace(",", "")
        if digits.isdigit():
            nums.append(int(digits))
    return max(nums) if nums else None


def _days(text: str) -> int | None:
    m = re.search(r"(\d+)\s*ngày", text.lower())
    return int(m.group(1)) if m else None


def run_deterministic_check(check_type: str, content: str, thong_so: dict[str, Any]) -> dict[str, Any] | None:
    if check_type == "presence":
        ok = bool(content.strip())
        return {"result": "PASS" if ok else "FAIL",
                "evidence": "Có nội dung hồ sơ" if ok else "Hồ sơ rỗng"}
    if check_type == "value_threshold":
        nguong = thong_so.get("gia_tri_so")
        val = _max_number(content)
        if nguong is None or val is None:
            return None
        ok = val >= int(nguong)
        return {"result": "PASS" if ok else "FAIL",
                "evidence": f"Giá trị trích được {val:,} so với ngưỡng {int(nguong):,}"}
    if check_type == "date_validity":
        nguong = thong_so.get("so_ngay")
        d = _days(content)
        if nguong is None or d is None:
            return None
        ok = d >= int(nguong)
        return {"result": "PASS" if ok else "FAIL",
                "evidence": f"Hiệu lực {d} ngày so với yêu cầu {int(nguong)} ngày"}
    return None
```

- [ ] **Step 4: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_checks.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/evaluation/checks.py backend/tests/test_checks.py
git commit -m "feat: deterministic check helpers for value/date/presence"
```

---

### Task 7: `evaluate_criterion` + aggregation

**Files:**
- Modify: `backend/services/evaluation/base.py` (thêm hàm, giữ `eval_one`)
- Modify: `backend/services/ai_client.py` (mock key `eval_subcheck`)
- Test: `backend/tests/test_evaluate_criterion.py`

**Interfaces:**
- Consumes: `checks.run_deterministic_check`, `ai_json` (mock_key `"eval_subcheck"`).
- Produces:
  - `SubResult` TypedDict: `{sub_check_ten, result, evidence, page_ref: list[int], nguon_file, ai_model}`.
  - `async def evaluate_criterion(criterion: dict, artifact_content_map: dict[str, str]) -> list[SubResult]` — với mỗi sub_check: nếu `required_artifact` không có trong map (hoặc rỗng) → FAIL "Thiếu hồ sơ"; elif `run_deterministic_check` trả khác None → dùng; else AI (`mock_key="eval_subcheck"`).
  - `def aggregate_subresults(criterion: dict, sub_results: list[SubResult]) -> dict` → `{result, score}`: FAIL nếu có sub_check `blocking` FAIL; PASS nếu tất cả PASS; else PARTIAL. score = % PASS.

- [ ] **Step 1: Thêm mock vào `ai_client.py`:**
```python
    "eval_subcheck": {"result": "PASS", "evidence": "Đáp ứng yêu cầu", "page_ref": [1]},
```

- [ ] **Step 2: Viết test fail** — `backend/tests/test_evaluate_criterion.py`

```python
import pytest
from services.evaluation import base
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


CRIT = {
    "ten": "Bảo đảm dự thầu", "required_artifacts": ["bao_dam_du_thau"],
    "sub_checks": [
        {"ten": "Có bảo đảm dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": True},
        {"ten": "Giá trị ≥ ngưỡng", "check_type": "value_threshold", "thong_so": {"gia_tri_so": 150000000}, "required_artifact": "bao_dam_du_thau", "blocking": True},
    ],
}


@pytest.mark.asyncio
async def test_missing_artifact_fails_without_ai():
    subs = await base.evaluate_criterion(CRIT, {})  # không có file loại bao_dam_du_thau
    assert all(s["result"] == "FAIL" for s in subs)
    assert "Thiếu hồ sơ" in subs[0]["evidence"]


@pytest.mark.asyncio
async def test_deterministic_value_threshold_used():
    content = {"bao_dam_du_thau": "Thư bảo lãnh giá trị 200.000.000 đồng"}
    subs = await base.evaluate_criterion(CRIT, content)
    vt = next(s for s in subs if s["sub_check_ten"] == "Giá trị ≥ ngưỡng")
    assert vt["result"] == "PASS" and "200" in vt["evidence"]


def test_aggregate_fail_when_blocking_fail():
    subs = [{"sub_check_ten": "Có", "result": "FAIL", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""}]
    agg = base.aggregate_subresults(CRIT, subs)
    assert agg["result"] == "FAIL"


def test_aggregate_pass_when_all_pass():
    subs = [{"sub_check_ten": s["ten"], "result": "PASS", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""}
            for s in CRIT["sub_checks"]]
    agg = base.aggregate_subresults(CRIT, subs)
    assert agg["result"] == "PASS" and agg["score"] == 100.0
```

- [ ] **Step 3: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_evaluate_criterion.py -v`
Expected: FAIL (`evaluate_criterion`/`aggregate_subresults` chưa có).

- [ ] **Step 4: Thêm vào `backend/services/evaluation/base.py`**

```python
# --- append to services/evaluation/base.py ---
from services.evaluation.checks import run_deterministic_check
from services import artifact_catalog

_SYS_SUB = "Bạn là chuyên gia đánh giá HSDT theo Luật Đấu thầu VN. Chỉ trả JSON."


class SubResult(TypedDict):
    sub_check_ten: str
    result: str
    evidence: str
    page_ref: list[int]
    nguon_file: str
    ai_model: str


def _label(code: str) -> str:
    a = artifact_catalog.get_artifact(code)
    return a["label"] if a else code


async def evaluate_criterion(criterion: dict[str, Any], artifact_content_map: dict[str, str]) -> list[SubResult]:
    out: list[SubResult] = []
    for sc in criterion.get("sub_checks", []):
        art = sc.get("required_artifact", "")
        content = artifact_content_map.get(art, "")
        if not art or art not in artifact_content_map:
            out.append(SubResult(sub_check_ten=sc["ten"], result="FAIL",
                                  evidence=f"Thiếu hồ sơ: {_label(art)}", page_ref=[],
                                  nguon_file=art, ai_model=""))
            continue
        det = run_deterministic_check(sc.get("check_type", ""), content, sc.get("thong_so", {}))
        if det is not None:
            out.append(SubResult(sub_check_ten=sc["ten"], result=det["result"],
                                  evidence=det["evidence"], page_ref=[], nguon_file=art, ai_model="python"))
            continue
        prompt = (f"Điểm kiểm: {sc['ten']} (loại {sc.get('check_type')})\n"
                  f"Nội dung hồ sơ '{_label(art)}':\n{content[:6000]}\n\n"
                  'Trả JSON: {"result":"PASS|FAIL|PARTIAL","evidence":"...","page_ref":[...]}')
        data = await ai_json(_SYS_SUB, prompt, mock_key="eval_subcheck")
        res = data.get("result", "PARTIAL")
        if res not in {"PASS", "FAIL", "PARTIAL"}:
            res = "PARTIAL"
        out.append(SubResult(sub_check_ten=sc["ten"], result=res,
                             evidence=data.get("evidence") or "Không có dẫn chứng",
                             page_ref=data.get("page_ref") or [], nguon_file=art,
                             ai_model=data.get("_model", "")))
    return out


def aggregate_subresults(criterion: dict[str, Any], sub_results: list[SubResult]) -> dict[str, Any]:
    by_ten = {sc["ten"]: sc for sc in criterion.get("sub_checks", [])}
    blocking_fail = any(
        r["result"] == "FAIL" and by_ten.get(r["sub_check_ten"], {}).get("blocking", True)
        for r in sub_results
    )
    all_pass = bool(sub_results) and all(r["result"] == "PASS" for r in sub_results)
    if blocking_fail:
        result = "FAIL"
    elif all_pass:
        result = "PASS"
    else:
        result = "PARTIAL"
    passed = sum(1 for r in sub_results if r["result"] == "PASS")
    score = round(100.0 * passed / len(sub_results), 1) if sub_results else 0.0
    return {"result": result, "score": score}
```

- [ ] **Step 5: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_evaluate_criterion.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/evaluation/base.py backend/services/ai_client.py backend/tests/test_evaluate_criterion.py
git commit -m "feat: evaluate_criterion with sub-check routing and aggregation"
```

---

### Task 8: Legality routing + completeness

**Files:**
- Modify: `backend/services/evaluation/legality.py` (thêm hàm, giữ `evaluate_legality`)
- Test: `backend/tests/test_legality_routed.py`

**Interfaces:**
- Consumes: `base.evaluate_criterion`, `base.aggregate_subresults`, `artifact_catalog`.
- Produces:
  - `async def evaluate_legality_routed(criteria: list[dict], artifact_content_map: dict[str, str]) -> list[dict]` — chỉ tiêu chí `nhom=="hop_le"`; trả mỗi tiêu chí `{criteria_ten, result, score, sub_results: list[SubResult]}`.
  - `def compute_completeness(criteria: list[dict], present_artifacts: set[str]) -> dict` — tập artifact yêu cầu = hợp `required_artifacts` các tiêu chí; trả `{percent: float, missing: list[str], required: list[str]}`.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_legality_routed.py`

```python
import pytest
from services.evaluation import legality
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


CRITERIA = [
    {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "required_artifacts": ["bao_dam_du_thau"],
     "sub_checks": [
         {"ten": "Có bảo đảm", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": True},
         {"ten": "Giá trị ≥ ngưỡng", "check_type": "value_threshold", "thong_so": {"gia_tri_so": 150000000}, "required_artifact": "bao_dam_du_thau", "blocking": True},
     ]},
    {"nhom": "ky_thuat", "ten": "Bỏ qua", "required_artifacts": [], "sub_checks": []},
]


@pytest.mark.asyncio
async def test_routed_only_hop_le_and_pass():
    amap = {"bao_dam_du_thau": "Thư bảo lãnh giá trị 200.000.000 đồng"}
    res = await legality.evaluate_legality_routed(CRITERIA, amap)
    assert len(res) == 1 and res[0]["criteria_ten"] == "Bảo đảm dự thầu"
    assert res[0]["result"] == "PASS"
    assert len(res[0]["sub_results"]) == 2


@pytest.mark.asyncio
async def test_routed_missing_artifact_fails():
    res = await legality.evaluate_legality_routed(CRITERIA, {})
    assert res[0]["result"] == "FAIL"


def test_compute_completeness():
    out = legality.compute_completeness(CRITERIA, present_artifacts={"bao_dam_du_thau"})
    assert out["required"] == ["bao_dam_du_thau"]
    assert out["missing"] == [] and out["percent"] == 100.0
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_legality_routed.py -v`
Expected: FAIL.

- [ ] **Step 3: Thêm vào `backend/services/evaluation/legality.py`**

```python
# --- append to services/evaluation/legality.py ---
from services.evaluation.base import evaluate_criterion, aggregate_subresults


async def evaluate_legality_routed(
    criteria: list[dict[str, Any]], artifact_content_map: dict[str, str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in criteria:
        if c.get("nhom") != "hop_le":
            continue
        subs = await evaluate_criterion(c, artifact_content_map)
        agg = aggregate_subresults(c, subs)
        out.append({"criteria_ten": c["ten"], "result": agg["result"],
                    "score": agg["score"], "sub_results": subs})
    return out


def compute_completeness(
    criteria: list[dict[str, Any]], present_artifacts: set[str]
) -> dict[str, Any]:
    required: list[str] = []
    for c in criteria:
        for a in c.get("required_artifacts", []):
            if a not in required:
                required.append(a)
    missing = [a for a in required if a not in present_artifacts]
    percent = round(100.0 * (len(required) - len(missing)) / len(required), 1) if required else 100.0
    return {"percent": percent, "missing": missing, "required": required}
```

- [ ] **Step 4: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_legality_routed.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/evaluation/legality.py backend/tests/test_legality_routed.py
git commit -m "feat: legality artifact routing and completeness computation"
```

---

### Task 9: Documents router — artifact_type + validate

**Files:**
- Modify: `backend/routers/documents.py`
- Test: `backend/tests/test_documents_artifact_api.py`

**Interfaces:**
- Consumes: `artifact_classify.validate_artifact`, `models.TenderDocument.artifact_type/artifact_validation`.
- Produces: `POST /api/v1/packages/{id}/documents` thêm form `artifact_type: str | None`. Sau khi extract text: nếu `loai=="HSDT"` và có `artifact_type` → chạy `validate_artifact(pages, artifact_type)` → lưu `doc.artifact_type` + `doc.artifact_validation`. `_doc_out` trả thêm `artifact_type`, `artifact_validation`.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_documents_artifact_api.py`

```python
import fitz
from services import ai_client


def _pdf(t):
    d = fitz.open(); d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>"); return d.tobytes()


def test_upload_hsdt_with_artifact_validation(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    p = client.post("/api/v1/packages", json={"ma_so": "G-A", "ten": "g", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    files = {"file": ("bl.pdf", _pdf("THƯ BẢO LÃNH dự thầu ngân hàng ABC giá trị lớn"), "application/pdf")}
    r = client.post(f"/api/v1/packages/{pid}/documents", files=files,
                    data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "bao_dam_du_thau"})
    doc = r.json()["data"]
    assert doc["artifact_type"] == "bao_dam_du_thau"
    assert doc["artifact_validation"]["match"] is True
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_documents_artifact_api.py -v`
Expected: FAIL (artifact_type không lưu / không có trong output).

- [ ] **Step 3: Sửa `backend/routers/documents.py`**

Thêm import đầu file: `from services.artifact_classify import validate_artifact`.
Sửa chữ ký `upload_document` thêm tham số: `artifact_type: str | None = Form(None),`.
Trong khối `try` sau khi set `extracted_text` thành công, trước `db.commit()` cuối, thêm:
```python
        if loai == "HSDT" and artifact_type:
            doc.artifact_type = artifact_type
            doc.artifact_validation = await validate_artifact(pages, artifact_type)
```
Sửa `_doc_out` thêm 2 khóa:
```python
        "artifact_type": d.artifact_type,
        "artifact_validation": d.artifact_validation,
```

- [ ] **Step 4: Chạy test — PASS** (+ full suite không hồi quy)

Run: `cd backend && python3 -m pytest tests/test_documents_artifact_api.py tests/test_documents_api.py -v`
Expected: tất cả pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/documents.py backend/tests/test_documents_artifact_api.py
git commit -m "feat: accept artifact_type and validate on HSDT upload"
```

---

### Task 10: Đề cương router — extract / edit / confirm

**Files:**
- Create: `backend/routers/de_cuong.py`
- Modify: `backend/main.py` (đăng ký router)
- Test: `backend/tests/test_de_cuong_api.py`

**Interfaces:**
- Consumes: `hsmt_locator.locate_hsmt_sections`, `extraction.extract_de_cuong`, models `EvaluationCriteria`/`EvaluationSubCheck`, HSMT `extracted_text`.
- Produces:
  - `POST /api/v1/packages/{id}/de-cuong` — đọc HSMT pages → locate → `extract_de_cuong` → xóa+tạo `EvaluationCriteria` (+`required_artifacts`) và `EvaluationSubCheck`; trả đề cương.
  - `GET /api/v1/packages/{id}/de-cuong` — trả `{criteria:[{id,nhom,ten,required_artifacts,sub_checks:[{id,ten,check_type,thong_so,required_artifact,blocking}]}]}`.
  - `PUT /api/v1/packages/{id}/de-cuong` body `{criteria:[...]}` — cập nhật (xóa+tạo lại) đề cương theo chỉnh sửa chuyên gia.
  - `POST /api/v1/packages/{id}/de-cuong/confirm` — set `package.trang_thai="dang_xu_ly"` (đề cương đã chốt). Trả `{confirmed: true}`.
- Envelope luôn.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_de_cuong_api.py`

```python
import fitz
from services import ai_client


def _pdf(t):
    d = fitz.open(); d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>"); return d.tobytes()


def _pkg_with_hsmt(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-D", "ten": "g"}).json()["data"]["id"]
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("hsmt.pdf", _pdf("Tiêu chuẩn đánh giá tính hợp lệ và Bảng dữ liệu đấu thầu"), "application/pdf")},
                data={"loai": "HSMT"})
    return pid


def test_extract_edit_confirm_de_cuong(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    pid = _pkg_with_hsmt(client)
    ext = client.post(f"/api/v1/packages/{pid}/de-cuong").json()["data"]
    assert any(c["ten"] == "Bảo đảm dự thầu" for c in ext["criteria"])
    bdt = next(c for c in ext["criteria"] if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["required_artifacts"] == ["bao_dam_du_thau"]
    assert any(s["check_type"] == "value_threshold" for s in bdt["sub_checks"])

    # chuyên gia sửa: đổi tên một sub-check rồi PUT
    bdt["sub_checks"][0]["ten"] = "Có bảo đảm dự thầu (đã sửa)"
    client.put(f"/api/v1/packages/{pid}/de-cuong", json={"criteria": ext["criteria"]})
    got = client.get(f"/api/v1/packages/{pid}/de-cuong").json()["data"]
    bdt2 = next(c for c in got["criteria"] if c["ten"] == "Bảo đảm dự thầu")
    assert bdt2["sub_checks"][0]["ten"] == "Có bảo đảm dự thầu (đã sửa)"

    conf = client.post(f"/api/v1/packages/{pid}/de-cuong/confirm").json()["data"]
    assert conf["confirmed"] is True
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_de_cuong_api.py -v`
Expected: FAIL (404 route).

- [ ] **Step 3: Viết `backend/routers/de_cuong.py`**

```python
"""Router đề cương chấm: trích từ HSMT, chuyên gia sửa, chốt."""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import get_db
from responses import ok, fail
from services.hsmt_locator import locate_hsmt_sections
from services.extraction import extract_de_cuong

router = APIRouter(prefix="/api/v1/packages", tags=["de-cuong"])


def _pages(doc: models.TenderDocument) -> list[dict]:
    return json.loads(doc.extracted_text) if doc.extracted_text else []


def _persist(db: Session, package_id: int, criteria: list[dict]) -> None:
    olds = db.scalars(select(models.EvaluationCriteria).where(
        models.EvaluationCriteria.package_id == package_id)).all()
    old_ids = [c.id for c in olds]
    if old_ids:
        db.query(models.EvaluationSubCheck).filter(
            models.EvaluationSubCheck.criteria_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(models.EvaluationCriteria).filter_by(package_id=package_id).delete()
    for c in criteria:
        row = models.EvaluationCriteria(
            package_id=package_id, nhom=c.get("nhom", "hop_le"), ten=c.get("ten", ""),
            yeu_cau=c.get("yeu_cau", ""), trong_so=float(c.get("trong_so") or 0),
            kieu=c.get("kieu", "pass_fail"), required_artifacts=c.get("required_artifacts", []))
        db.add(row); db.flush()
        for i, s in enumerate(c.get("sub_checks", [])):
            db.add(models.EvaluationSubCheck(
                criteria_id=row.id, ten=s.get("ten", ""), check_type=s.get("check_type", ""),
                thong_so=s.get("thong_so", {}), required_artifact=s.get("required_artifact", ""),
                thu_tu=i, blocking=bool(s.get("blocking", True))))
    db.commit()


def _read(db: Session, package_id: int) -> dict:
    crits = db.scalars(select(models.EvaluationCriteria).where(
        models.EvaluationCriteria.package_id == package_id)).all()
    out = []
    for c in crits:
        subs = db.scalars(select(models.EvaluationSubCheck).where(
            models.EvaluationSubCheck.criteria_id == c.id).order_by(models.EvaluationSubCheck.thu_tu)).all()
        out.append({"id": c.id, "nhom": c.nhom, "ten": c.ten, "yeu_cau": c.yeu_cau,
                    "required_artifacts": c.required_artifacts, "kieu": c.kieu, "trong_so": c.trong_so,
                    "sub_checks": [{"id": s.id, "ten": s.ten, "check_type": s.check_type,
                                    "thong_so": s.thong_so, "required_artifact": s.required_artifact,
                                    "blocking": s.blocking} for s in subs]})
    return {"criteria": out}


@router.post("/{package_id}/de-cuong")
async def extract(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    hsmt = next((d for d in pkg.documents if d.loai == "HSMT"), None)
    if not hsmt:
        return fail("Chưa upload HSMT", 400)
    sections = locate_hsmt_sections(_pages(hsmt))
    criteria = await extract_de_cuong(sections)
    _persist(db, package_id, criteria)
    return ok(_read(db, package_id))


@router.get("/{package_id}/de-cuong")
async def get_de_cuong(package_id: int, db: Session = Depends(get_db)):
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    return ok(_read(db, package_id))


@router.put("/{package_id}/de-cuong")
async def update_de_cuong(package_id: int, payload: dict, db: Session = Depends(get_db)):
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    _persist(db, package_id, payload.get("criteria", []))
    return ok(_read(db, package_id))


@router.post("/{package_id}/de-cuong/confirm")
async def confirm_de_cuong(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    pkg.trang_thai = "dang_xu_ly"
    db.commit()
    return ok({"confirmed": True})
```

- [ ] **Step 4: Đăng ký router trong `backend/main.py`** (thêm sau evaluation router):
```python
    from routers import de_cuong as de_cuong_router
    app.include_router(de_cuong_router.router)
```

- [ ] **Step 5: Chạy test — PASS**

Run: `cd backend && python3 -m pytest tests/test_de_cuong_api.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/de_cuong.py backend/main.py backend/tests/test_de_cuong_api.py
git commit -m "feat: de-cuong router extract/edit/confirm"
```

---

### Task 11: Evaluation router — artifact routing + sub-check results

**Files:**
- Modify: `backend/routers/evaluation.py`
- Test: `backend/tests/test_evaluation_routed_api.py`

**Interfaces:**
- Consumes: `legality.evaluate_legality_routed`, `legality.compute_completeness`, models `EvaluationSubCheck`/`SubCheckResult`, đề cương đã chốt (Task 10).
- Produces:
  - `POST /api/v1/packages/{id}/evaluate` (sửa): **không** tự trích tiêu chí nữa — dùng `EvaluationCriteria`+`EvaluationSubCheck` đã có (từ đề cương). Với mỗi vendor: build `artifact_content_map` = `{artifact_type: text}` từ `TenderDocument` của vendor; chạy `evaluate_legality_routed`; lưu `SubCheckResult` (map sub_result→sub_check theo `ten`); roll-up vào `EvaluationResult` (1 dòng/criteria×vendor); tính completeness. Trả `{vendors:[{vendor_id, completeness, criteria:[{criteria_ten,result,score}]}]}`.
  - `GET /api/v1/packages/{id}/results` (sửa): trả thêm `sub_results` lồng trong mỗi tiêu chí của mỗi vendor.

- [ ] **Step 1: Viết test fail** — `backend/tests/test_evaluation_routed_api.py`

```python
import fitz
from services import ai_client


def _pdf(t):
    d = fitz.open(); d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>"); return d.tobytes()


def _setup(client):
    p = client.post("/api/v1/packages", json={"ma_so": "G-E", "ten": "g", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("hsmt.pdf", _pdf("Tiêu chuẩn đánh giá hợp lệ; Bảng dữ liệu đấu thầu"), "application/pdf")},
                data={"loai": "HSMT"})
    # HSDT: file bảo đảm dự thầu giá trị đạt ngưỡng
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("bl.pdf", _pdf("Thư bảo lãnh dự thầu giá trị 200.000.000 đồng hiệu lực 150 ngày"), "application/pdf")},
                data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "bao_dam_du_thau"})
    # HSDT: đơn dự thầu
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("don.pdf", _pdf("Đơn dự thầu có chữ ký và đóng dấu hợp lệ"), "application/pdf")},
                data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "don_du_thau"})
    return pid, vid


def test_evaluate_routed_with_subresults(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    pid, vid = _setup(client)
    client.post(f"/api/v1/packages/{pid}/de-cuong")          # tạo đề cương từ HSMT (mock)
    client.post(f"/api/v1/packages/{pid}/de-cuong/confirm")
    ev = client.post(f"/api/v1/packages/{pid}/evaluate").json()["data"]
    v = ev["vendors"][0]
    assert v["completeness"]["percent"] >= 0
    bdt = next(c for c in v["criteria"] if c["criteria_ten"] == "Bảo đảm dự thầu")
    assert bdt["result"] == "PASS"

    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    vr = res["vendors"][0]
    crit = next(c for c in vr["criteria"] if c["criteria_ten"] == "Bảo đảm dự thầu")
    assert len(crit["sub_results"]) >= 2
    assert any("Giá trị" in s["sub_check_ten"] for s in crit["sub_results"])
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `cd backend && python3 -m pytest tests/test_evaluation_routed_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Sửa `backend/routers/evaluation.py`** — thay thế thân hàm `evaluate` và `results` bằng bản định tuyến.

Thêm imports đầu file:
```python
from services.evaluation.legality import evaluate_legality_routed, compute_completeness
```
Thêm helper:
```python
def _artifact_map(pkg: models.ProcurementPackage, vendor_id: int) -> tuple[dict[str, str], set[str]]:
    amap: dict[str, str] = {}
    present: set[str] = set()
    for d in pkg.documents:
        if d.vendor_id != vendor_id or not d.artifact_type:
            continue
        present.add(d.artifact_type)
        pages = json.loads(d.extracted_text) if d.extracted_text else []
        text = "\n".join(p.get("text", "") for p in pages)
        amap[d.artifact_type] = (amap.get(d.artifact_type, "") + "\n" + text).strip()
    return amap, present
```
Thay hàm `evaluate`:
```python
@router.post("/packages/{package_id}/evaluate")
async def evaluate(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    crit_rows = list(pkg.criteria)
    if not crit_rows:
        return fail("Chưa có đề cương — hãy tạo và chốt đề cương trước", 400)
    # build criterion dicts kèm sub_checks (từ DB)
    crit_dicts: list[dict] = []
    sub_by_crit_ten: dict[str, dict[str, int]] = {}
    for c in crit_rows:
        subs = db.scalars(select(models.EvaluationSubCheck).where(
            models.EvaluationSubCheck.criteria_id == c.id).order_by(models.EvaluationSubCheck.thu_tu)).all()
        sub_by_crit_ten[c.ten] = {s.ten: s.id for s in subs}
        crit_dicts.append({"nhom": c.nhom, "ten": c.ten, "required_artifacts": c.required_artifacts,
                           "sub_checks": [{"ten": s.ten, "check_type": s.check_type, "thong_so": s.thong_so,
                                           "required_artifact": s.required_artifact, "blocking": s.blocking} for s in subs]})
    crit_id_by_ten = {c.ten: c.id for c in crit_rows}
    # dọn kết quả cũ
    all_sub_ids = [sid for m in sub_by_crit_ten.values() for sid in m.values()]
    if all_sub_ids:
        db.query(models.SubCheckResult).filter(
            models.SubCheckResult.sub_check_id.in_(all_sub_ids)).delete(synchronize_session=False)
    db.query(models.EvaluationResult).filter(
        models.EvaluationResult.criteria_id.in_(list(crit_id_by_ten.values()))).delete(synchronize_session=False)

    vendors_out = []
    for vendor in pkg.vendors:
        amap, present = _artifact_map(pkg, vendor.id)
        routed = await evaluate_legality_routed(crit_dicts, amap)
        comp = compute_completeness(crit_dicts, present)
        crit_summ = []
        for r in routed:
            cid = crit_id_by_ten.get(r["criteria_ten"])
            db.add(models.EvaluationResult(criteria_id=cid, vendor_id=vendor.id, ket_qua=r["result"],
                                           diem_so=r["score"], dan_chung="; ".join(s["evidence"] for s in r["sub_results"][:3]),
                                           so_trang=[], ghi_chu="", ai_model="mix"))
            sub_ids = sub_by_crit_ten.get(r["criteria_ten"], {})
            for s in r["sub_results"]:
                sid = sub_ids.get(s["sub_check_ten"])
                if sid is None:
                    continue
                db.add(models.SubCheckResult(sub_check_id=sid, vendor_id=vendor.id, ket_qua=s["result"],
                                             evidence=s["evidence"], page_ref=s["page_ref"], nguon_file=s["nguon_file"],
                                             ai_model=s["ai_model"]))
            crit_summ.append({"criteria_ten": r["criteria_ten"], "result": r["result"], "score": r["score"]})
        vendors_out.append({"vendor_id": vendor.id, "completeness": comp, "criteria": crit_summ})
    pkg.trang_thai = "cho_review"
    db.commit()
    return ok({"vendors": vendors_out})
```
Thay hàm `results` để lồng `sub_results`:
```python
@router.get("/packages/{package_id}/results")
async def results(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    crits = list(pkg.criteria)
    vendors_out = []
    for v in pkg.vendors:
        crit_out = []
        for c in crits:
            er = db.scalars(select(models.EvaluationResult).where(
                models.EvaluationResult.criteria_id == c.id,
                models.EvaluationResult.vendor_id == v.id)).first()
            subs = db.scalars(select(models.EvaluationSubCheck).where(
                models.EvaluationSubCheck.criteria_id == c.id)).all()
            sub_ids = [s.id for s in subs]
            srs = db.scalars(select(models.SubCheckResult).where(
                models.SubCheckResult.sub_check_id.in_(sub_ids),
                models.SubCheckResult.vendor_id == v.id)).all() if sub_ids else []
            sub_ten = {s.id: s.ten for s in subs}
            crit_out.append({"criteria_id": c.id, "criteria_ten": c.ten,
                             "result": er.ket_qua if er else None, "score": er.diem_so if er else 0,
                             "sub_results": [{"id": r.id, "sub_check_ten": sub_ten.get(r.sub_check_id, ""),
                                              "result": r.ket_qua, "evidence": r.evidence, "page_ref": r.page_ref,
                                              "nguon_file": r.nguon_file, "overridden": r.overridden} for r in srs]})
        vendors_out.append({"vendor_id": v.id, "ten": v.ten, "criteria": crit_out})
    return ok({"vendors": vendors_out})
```
**Lưu ý:** giữ nguyên route `PUT /evaluation/{result_id}/override` hiện có (override mức tiêu chí). Bổ sung route override mức sub-check:
```python
@router.put("/sub-check-result/{sub_result_id}/override")
async def override_sub(sub_result_id: int, payload: dict, db: Session = Depends(get_db)):
    row = db.get(models.SubCheckResult, sub_result_id)
    if not row:
        return fail("Không tìm thấy kết quả sub-check", 404)
    if "ket_qua" in payload:
        row.ket_qua = payload["ket_qua"]
    row.ghi_chu = payload.get("ghi_chu", row.ghi_chu)
    row.overridden = True
    db.add(models.AuditLog(action="override_sub", entity_type="sub_check_result",
                           entity_id=sub_result_id, detail=json.dumps(payload, ensure_ascii=False)))
    db.commit(); db.refresh(row)
    return ok({"id": row.id, "ket_qua": row.ket_qua, "overridden": row.overridden})
```

- [ ] **Step 4: Chạy test — PASS** (+ kiểm tra không vỡ test evaluation cũ — lưu ý test cũ `test_evaluation_api.py` dựa trên luồng tự-trích-tiêu-chí; xem Step 4b)

Run: `cd backend && python3 -m pytest tests/test_evaluation_routed_api.py -v`
Expected: 1 passed.

- [ ] **Step 4b: Cập nhật test evaluation cũ cho luồng mới**

Luồng `evaluate` cũ tự trích tiêu chí; nay yêu cầu đề cương trước. Sửa `backend/tests/test_evaluation_api.py`: trong `_setup`, sau khi upload HSMT/HSDT, thêm 2 dòng trước khi gọi evaluate:
```python
    client.post(f"/api/v1/packages/{package_id}/de-cuong")
    client.post(f"/api/v1/packages/{package_id}/de-cuong/confirm")
```
Và cập nhật assertion: `ev["so_tieu_chi"]` không còn — đổi thành `assert ev["vendors"]`. Kết quả `results` nay có `vendors[].criteria[].sub_results`; sửa phần lấy `result_id` để override: lấy từ `EvaluationResult` qua route override tiêu chí cũ (giữ nguyên) hoặc chuyển sang dùng route override sub-check mới. Đơn giản nhất: đổi assertion override sang sub-check:
```python
    res = client.get(f"/api/v1/packages/{package_id}/results").json()["data"]
    crit = res["vendors"][0]["criteria"][0]
    sub_id = crit["sub_results"][0]["id"]
    ov = client.put(f"/api/v1/evaluation/sub-check-result/{sub_id}/override",
                    json={"ket_qua": "FAIL", "ghi_chu": "Chuyên gia bác bỏ"})
    assert ov.json()["data"]["overridden"] is True
```

- [ ] **Step 5: Chạy full suite — PASS**

Run: `cd backend && python3 -m pytest -q`
Expected: tất cả pass (test report router cũ dùng `_rebuild_evals` theo nhom vẫn hoạt động vì `EvaluationResult` vẫn được tạo).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/evaluation.py backend/tests/test_evaluation_routed_api.py backend/tests/test_evaluation_api.py
git commit -m "feat: evaluation routing by artifact with sub-check results and override"
```

---

### Task 12: Frontend — artifact_type khi upload + cảnh báo nhầm

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/PackageDetail.tsx`

**Interfaces:**
- Consumes: `POST /packages/:id/documents` với form `artifact_type`; response `artifact_validation`.
- Produces: types `ArtifactValidation`, hằng `LEGALITY_ARTIFACTS`.

- [ ] **Step 1: Thêm vào `frontend/src/api/types.ts`**

```typescript
export interface ArtifactValidation { match: boolean; suggested_type: string; confidence: number; note: string; }
export interface SubCheck {
  id?: number; ten: string; check_type: string; thong_so: Record<string, unknown>;
  required_artifact: string; blocking: boolean;
}
export interface DeCuongCriteria {
  id?: number; nhom: string; ten: string; yeu_cau: string; required_artifacts: string[];
  kieu: string; trong_so: number; sub_checks: SubCheck[];
}
export interface SubResult {
  id: number; sub_check_ten: string; result: string; evidence: string;
  page_ref: number[]; nguon_file: string; overridden: boolean;
}
export const ARTIFACT_TYPES: { value: string; label: string }[] = [
  { value: "don_du_thau", label: "Đơn dự thầu" },
  { value: "bao_dam_du_thau", label: "Bảo đảm dự thầu (thư BL)" },
  { value: "thoa_thuan_lien_danh", label: "Thỏa thuận liên danh" },
  { value: "tu_cach_phap_ly", label: "Tài liệu tư cách hợp lệ" },
  { value: "bao_cao_tai_chinh", label: "Báo cáo tài chính" },
  { value: "hop_dong_tuong_tu", label: "Hợp đồng tương tự" },
  { value: "bang_gia", label: "Bảng giá dự thầu" },
];
```

- [ ] **Step 2: Sửa `frontend/src/pages/PackageDetail.tsx`**

Thêm import: `import { ARTIFACT_TYPES } from "../api/types";` và state:
```tsx
  const [artifactType, setArtifactType] = useState<string | undefined>();
```
Trong khối upload control, sau Select vendor (khi `loai === "HSDT"`), thêm Select loại hồ sơ:
```tsx
          {loai === "HSDT" && (
            <Select placeholder="Loại hồ sơ" value={artifactType} onChange={setArtifactType}
              className="min-w-48" options={ARTIFACT_TYPES} />
          )}
```
Sửa hàm `upload` để gửi `artifact_type` và cảnh báo khi không khớp:
```tsx
  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("loai", loai);
    if (loai === "HSDT" && vendorId) fd.append("vendor_id", String(vendorId));
    if (loai === "HSDT" && artifactType) fd.append("artifact_type", artifactType);
    try {
      const res = await api.post(`/packages/${id}/documents`, fd);
      const doc = res.data.data;
      if (doc?.artifact_validation && doc.artifact_validation.match === false) {
        message.warning(`Nghi tải nhầm loại: ${doc.artifact_validation.note}`);
      } else {
        message.success("Đã tải lên & xử lý");
      }
      load();
    } catch (e: any) { message.error(e.message); }
    return false;
  };
```
Thêm cột "Loại hồ sơ" vào bảng documents: trong `columns`, thêm `{ title: "Loại hồ sơ", dataIndex: "artifact_type" }`.

- [ ] **Step 3: Verify tĩnh** (node không có trong WSL)

Đọc kỹ: import `ARTIFACT_TYPES` đúng path; `artifactType` khai báo; `res.data.data` khớp envelope; Select options đúng shape. (Người dùng chạy `npm run dev` để kiểm thực tế.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/PackageDetail.tsx
git commit -m "feat: artifact_type select and mismatch warning on HSDT upload"
```

---

### Task 13: Frontend — màn Đề cương chấm

**Files:**
- Create: `frontend/src/pages/DeCuong.tsx`
- Modify: `frontend/src/App.tsx` (route `/packages/:id/de-cuong`)
- Modify: `frontend/src/pages/PackageDetail.tsx` (nút "Tạo đề cương")

**Interfaces:**
- Consumes: `POST/GET/PUT /packages/:id/de-cuong`, `POST .../confirm`; types `DeCuongCriteria`, `ARTIFACT_TYPES`.

- [ ] **Step 1: Viết `frontend/src/pages/DeCuong.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Button, Card, Input, Select, Table, Tag, message } from "antd";
import { useParams, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { ARTIFACT_TYPES, type DeCuongCriteria } from "../api/types";

const CHECK_TYPES = ["presence", "form_match", "signature_stamp", "authority",
  "value_threshold", "date_validity", "quantity_match", "semantic_match"]
  .map((v) => ({ value: v, label: v }));

export default function DeCuong() {
  const { id } = useParams();
  const nav = useNavigate();
  const [criteria, setCriteria] = useState<DeCuongCriteria[]>([]);

  const load = () => api.get(`/packages/${id}/de-cuong`)
    .then((r) => setCriteria(unwrap<{ criteria: DeCuongCriteria[] }>(r).criteria));
  useEffect(() => { load(); }, [id]);

  const extract = async () => {
    setCriteria(unwrap<{ criteria: DeCuongCriteria[] }>(await api.post(`/packages/${id}/de-cuong`)).criteria);
    message.success("Đã bóc tách đề cương từ HSMT");
  };
  const save = async () => {
    await api.put(`/packages/${id}/de-cuong`, { criteria });
    message.success("Đã lưu đề cương");
  };
  const confirm = async () => {
    await api.put(`/packages/${id}/de-cuong`, { criteria });
    await api.post(`/packages/${id}/de-cuong/confirm`);
    message.success("Đã chốt đề cương");
    nav(`/packages/${id}`);
  };

  const setSub = (ci: number, si: number, key: string, val: unknown) => {
    setCriteria((prev) => {
      const next = structuredClone(prev);
      (next[ci].sub_checks[si] as any)[key] = val;
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between">
        <h2 className="text-xl font-semibold">Đề cương chấm</h2>
        <div className="flex gap-2">
          <Button onClick={extract}>Bóc tách từ HSMT</Button>
          <Button onClick={save}>Lưu</Button>
          <Button type="primary" onClick={confirm}>Chốt đề cương</Button>
        </div>
      </div>
      {criteria.map((c, ci) => (
        <Card key={ci} title={`${c.ten}`} extra={
          <span>Loại HS: {c.required_artifacts.map((a) => <Tag key={a}>{a}</Tag>)}</span>}>
          <Table rowKey={(_, i) => String(i)} pagination={false} dataSource={c.sub_checks}
            columns={[
              { title: "Điểm kiểm", dataIndex: "ten",
                render: (t, _s, si) => <Input value={t} onChange={(e) => setSub(ci, si, "ten", e.target.value)} /> },
              { title: "Loại kiểm", dataIndex: "check_type",
                render: (t, _s, si) => <Select value={t} options={CHECK_TYPES} className="min-w-40"
                  onChange={(v) => setSub(ci, si, "check_type", v)} /> },
              { title: "Loại hồ sơ", dataIndex: "required_artifact",
                render: (t, _s, si) => <Select value={t} options={ARTIFACT_TYPES} className="min-w-44"
                  onChange={(v) => setSub(ci, si, "required_artifact", v)} /> },
              { title: "Ngưỡng (JSON)", dataIndex: "thong_so",
                render: (t, _s, si) => <Input value={JSON.stringify(t)}
                  onChange={(e) => { try { setSub(ci, si, "thong_so", JSON.parse(e.target.value)); } catch { /* giữ nguyên */ } }} /> },
              { title: "Bắt buộc", dataIndex: "blocking",
                render: (t: boolean, _s, si) => <Select value={t ? "1" : "0"}
                  options={[{ value: "1", label: "Có" }, { value: "0", label: "Không" }]}
                  onChange={(v) => setSub(ci, si, "blocking", v === "1")} /> },
            ]} />
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Thêm route trong `frontend/src/App.tsx`**

Import: `import DeCuong from "./pages/DeCuong";` và thêm route:
```tsx
          <Route path="/packages/:id/de-cuong" element={<DeCuong />} />
```

- [ ] **Step 3: Thêm nút trong `frontend/src/pages/PackageDetail.tsx`**

Cạnh nút "Chạy đánh giá AI", thêm:
```tsx
          <Button onClick={() => nav(`/packages/${id}/de-cuong`)}>Đề cương chấm</Button>
```

- [ ] **Step 4: Verify tĩnh** — import paths, `structuredClone` có sẵn trình duyệt hiện đại; types khớp; antd Table render param `(value, record, index)`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DeCuong.tsx frontend/src/App.tsx frontend/src/pages/PackageDetail.tsx
git commit -m "feat: de-cuong review/edit screen"
```

---

### Task 14: Frontend — breakdown sub-check + override

**Files:**
- Create: `frontend/src/components/SubCheckTable.tsx`
- Modify: `frontend/src/pages/Evaluation.tsx`

**Interfaces:**
- Consumes: `GET /packages/:id/results` (nay có `vendors[].criteria[].sub_results`), `PUT /evaluation/sub-check-result/:id/override`; type `SubResult`.

- [ ] **Step 1: Viết `frontend/src/components/SubCheckTable.tsx`**

```tsx
import { useState } from "react";
import { Button, Input, Modal, Select, Table, Tag, message } from "antd";
import { api } from "../api/client";
import type { SubResult } from "../api/types";

const COLOR: Record<string, string> = { PASS: "green", FAIL: "red", PARTIAL: "orange" };

export default function SubCheckTable({ subs, onChanged }: { subs: SubResult[]; onChanged: () => void }) {
  const [editing, setEditing] = useState<SubResult | null>(null);
  const [ketQua, setKetQua] = useState("FAIL");
  const [ghiChu, setGhiChu] = useState("");

  const save = async () => {
    if (!editing) return;
    try {
      await api.put(`/evaluation/sub-check-result/${editing.id}/override`, { ket_qua: ketQua, ghi_chu: ghiChu });
      message.success("Đã override"); setEditing(null); onChanged();
    } catch (e: any) { message.error(e.message); }
  };

  return (
    <>
      <Table rowKey="id" pagination={false} size="small" dataSource={subs} columns={[
        { title: "Điểm kiểm", dataIndex: "sub_check_ten" },
        { title: "Kết quả", dataIndex: "result",
          render: (r: string, s) => <><Tag color={COLOR[r] ?? "default"}>{r}</Tag>{s.overridden && <Tag color="purple">override</Tag>}</> },
        { title: "Dẫn chứng", dataIndex: "evidence" },
        { title: "Trang", dataIndex: "page_ref", render: (p: number[]) => p.join(", ") },
        { title: "", render: (_t, s) => <Button size="small" onClick={() => { setEditing(s); setKetQua(s.result); setGhiChu(""); }}>Sửa</Button> },
      ]} />
      <Modal title="Override sub-check" open={!!editing} onOk={save} onCancel={() => setEditing(null)}>
        <Select value={ketQua} onChange={setKetQua} className="w-full mb-2"
          options={["PASS", "FAIL", "PARTIAL"].map((x) => ({ value: x, label: x }))} />
        <Input.TextArea placeholder="Lý do" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} rows={3} />
      </Modal>
    </>
  );
}
```

- [ ] **Step 2: Sửa `frontend/src/pages/Evaluation.tsx`** để render breakdown sub-check

Thay phần hiển thị kết quả: với mỗi vendor và mỗi criteria, render `SubCheckTable`. Thêm import:
```tsx
import SubCheckTable from "../components/SubCheckTable";
```
Thay khối hiển thị kết quả bằng (giả định `data.vendors[].criteria[]` từ results mới):
```tsx
      {data.vendors.map((v: any) => (
        <Card key={v.vendor_id} title={`Nhà thầu: ${v.ten}`}>
          {v.criteria.map((c: any) => (
            <Card key={c.criteria_id} type="inner" className="mb-3"
              title={`${c.criteria_ten} — ${c.result ?? "—"} (${c.score})`}>
              <SubCheckTable subs={c.sub_results} onChanged={load} />
            </Card>
          ))}
        </Card>
      ))}
```
(Giữ phần "Xuất Word/Excel" nếu còn dùng; bảng xếp hạng cũ có thể để nguyên hoặc ẩn — tuỳ, không bắt buộc cho task này. Đảm bảo `load` và `data` vẫn được khai báo như trước.)

- [ ] **Step 3: Verify tĩnh** — `SubResult` type khớp; `api.put` đúng endpoint; antd Modal/Select/Table props đúng.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SubCheckTable.tsx frontend/src/pages/Evaluation.tsx
git commit -m "feat: sub-check breakdown with per-sub-check override"
```

---

## Self-Review

**1. Spec coverage:**
- Catalog hybrid (§3.1) → Task 1 (catalog + match). Hybrid `proposed_artifacts` được sinh ở Task 4 extract + chuyên gia duyệt ở Task 13. ✅
- Mô hình dữ liệu (§3.2): artifact_type/validation, required_artifacts, sub_check tables → Task 2. `thong_so.nguon/can_review` → mang trong JSON, sinh ở Task 4. ✅
- Định vị mục HSMT (§4.6) → Task 3. ✅
- `extract_de_cuong` + giải tham chiếu (§4.1, §4.7) → Task 4 (mock chứa `nguon`/`can_review`). ✅
- `validate_artifact` (§4.2) → Task 5. ✅
- Tách tất định/AI (§4.4) → Task 6 (checks) + Task 7 (evaluate_criterion route). ✅
- Tổng hợp (§4.5) → Task 7 `aggregate_subresults`. ✅
- Luồng định tuyến + thiếu hồ sơ + completeness (§5.1, §5.2) → Task 7 (missing→FAIL), Task 8 (routed + completeness), Task 11 (router). ✅
- File nhầm loại (§5.2) → Task 5 + Task 9 (cảnh báo) + Task 12 (UI warning). ✅
- Đề cương review (§5, decision 5) → Task 10 (API) + Task 13 (UI). ✅
- Override sub-check → Task 11 (route) + Task 14 (UI). ✅
- Mock/thật (§6.1) → mock keys thêm ở Task 4/5/7. ✅
- Phạm vi & test (§6.2, §6.3) → các task tương ứng; test định vị/cross-ref (Task 3/4), missing→FAIL không gọi AI (Task 7), value/date tất định (Task 6). ✅
- **Ngoài phạm vi (đúng):** RAG/Qdrant, sub-check đầy đủ 3 nhóm còn lại, auth — không có task, đúng spec §6.4.

**2. Placeholder scan:** Không có "TBD/handle edge cases" trừu tượng — mỗi step có code thật. Frontend verify tĩnh (node thiếu) đã ghi rõ lý do, không phải placeholder.

**3. Type consistency:** `SubResult` keys (`sub_check_ten, result, evidence, page_ref, nguon_file, ai_model`) định nghĩa ở Task 7, dùng nhất quán ở Task 8/11. `EvaluationSubCheck`/`SubCheckResult` cột khớp giữa Task 2 (model) ↔ Task 10/11 (router). `evaluate_criterion(criterion, artifact_content_map: dict[str,str])` khớp giữa Task 7 (định nghĩa) ↔ Task 8 (gọi). `compute_completeness` trả `{percent, missing, required}` khớp Task 8 ↔ Task 11. Catalog `match_artifact -> (code, conf)` khớp Task 1 ↔ Task 5. Frontend types (`SubResult`, `DeCuongCriteria`, `ARTIFACT_TYPES`) định nghĩa Task 12 ↔ dùng Task 13/14. ✅
