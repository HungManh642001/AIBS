# Upload hết chờ + Thống kê thiếu hồ sơ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ call LLM vô nghĩa làm nghẽn luồng upload HSDT, và đưa thống kê thiếu hồ sơ ra trang Kết quả đánh giá.

**Architecture:** Hai phần độc lập. Phần A sửa điều kiện gọi `validate_artifact` trong router tài liệu (bản scan không có text thì không gọi LLM) và thêm phản hồi loading ở frontend. Phần B thêm hai con số vào payload `results`: `n_thieu_ho_so` (đếm tiêu chí có verdict "thiếu hồ sơ") và `ho_so_chua_nop` (loại hồ sơ HSMT đòi mà nhà thầu không nộp, đã trừ tài liệu dùng chung và loại chỉ áp dụng hình thức khác), rồi hiển thị chúng.

**Tech Stack:** Backend Python + FastAPI + SQLAlchemy, test bằng pytest + `TestClient` (fixture `client` trong `backend/tests/conftest.py`, dựng DB SQLite tạm mỗi test). Frontend React + Vite + TypeScript + Ant Design.

**Spec:** `docs/superpowers/specs/2026-07-30-upload-cho-va-thong-ke-thieu-ho-so-design.md`

## Global Constraints

- Thư mục làm việc mọi lệnh backend: `backend/`. Chạy test: `cd backend && python -m pytest <path> -q`.
- **Baseline có sẵn test đỏ, KHÔNG liên quan tới plan này** — đừng tưởng mình làm hỏng, đừng sửa chúng. Chạy `cd backend && python -m pytest -q` trước khi bắt đầu và ghi lại con số; so lại đúng con số đó khi xong. (Tại thời điểm viết plan: toàn bộ `experiment/evaluate/tests experiment/decompose/tests tests` cho `524 passed, 28 failed, 3 errors`.)
- Quy ước code (CLAUDE.md): Python snake_case, **type hints bắt buộc**, PEP 8. **Tiếng Việt trong UI/comment/docstring, tiếng Anh trong tên code.**
- API response format: `{"success": bool, "data": ..., "error": ...}` — dùng helper `ok()` / `fail()` có sẵn trong `backend/responses.py`.
- Async: dùng `async/await` cho mọi I/O.
- **no-silent-mock:** không dựng dữ liệu giả để lấp chỗ trống. Bỏ qua một phép kiểm thì để `None`, đừng bịa kết quả "đạt".
- **Máy KHÔNG kết luận loại/không loại nhà thầu** — chỉ trình số liệu và bằng chứng để chuyên gia tự quyết. Không thêm nhãn phán xét mới.
- Frontend: dùng CSS custom properties có sẵn (`var(--fail)`, `var(--partial)`, `var(--sp-2)`…), không hardcode màu/khoảng cách mới trừ khi plan chỉ rõ.
- Commit tiếng Việt, dạng `fix(<scope>): <mô tả>` / `feat(<scope>): <mô tả>` như lịch sử repo.

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/routers/documents.py` | Chỉ gọi `validate_artifact` khi có text (2 chỗ: `upload_document`, `update_document_type`) | 1 |
| `backend/tests/test_documents_api.py` | Test cho 2 chỗ trên | 1 |
| `frontend/src/pages/PackageDetail.tsx` | `uploadDoc` có chỉ báo loading + disable nút Upload | 2 |
| `backend/routers/evaluation.py` | `_summary` thêm `n_thieu_ho_so`; thêm `_ho_so_chua_nop`; `results` trả thêm 2 field | 3, 4 |
| `backend/tests/test_evaluation_api.py` | Test cho `n_thieu_ho_so` và `ho_so_chua_nop` | 3, 4 |
| `frontend/src/api/types.ts` | Thêm field vào `EvalSummary` + interface `HoSoChuaNop` | 3, 4 |
| `frontend/src/pages/Evaluation.tsx` | Tách pill "thiếu hồ sơ"; chip + cột "trong đó thiếu hồ sơ"; thẻ hồ sơ chưa nộp | 3, 4 |
| `frontend/src/index.css` | Class màu riêng cho pill "thiếu hồ sơ" | 3 |

---

### Task 1: Không gọi LLM kiểm loại hồ sơ khi tài liệu không có text

**Files:**
- Modify: `backend/routers/documents.py:74-82` (`upload_document`), `:110-115` (`update_document_type`)
- Test: `backend/tests/test_documents_api.py`

**Interfaces:**
- Consumes: `services.artifact_classify.validate_artifact(file_pages: list[dict], declared_type: str) -> dict` (đã có); `services.documents.extract_document(data: bytes, file_kind: str) -> list[PageText]` (đã có).
- Produces: không có API mới. Hợp đồng hành vi mà Task 2 dựa vào: upload PDF scan trả về **không có call LLM nào**, và `artifact_validation` trong response là `None`.

**Bối cảnh (đọc trước khi sửa):** `services/documents.py::extract_document` **cố ý trả `[]` cho `pdf_scan`** — HSDT scan không OCR ở bước upload, để Qwen vision đọc ảnh ở bước chấm. Nhưng `upload_document` vẫn gọi `validate_artifact(pages, artifact_type)` với `pages = []`, và `artifact_classify._text([])` cho chuỗi rỗng → prompt gửi LLM **không có nội dung gì để phán**. Hệ quả kép: người dùng chờ một call LLM (timeout 300s/lần, `ai_client` thử 2 lần) hoàn toàn vô ích, và kết quả `match=false` từ nội dung rỗng còn làm UI hiện cảnh báo "Nghi tải nhầm loại" cho một file bình thường.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_documents_api.py`:

```python
def _scan_pdf() -> bytes:
    """PDF KHÔNG có text nhúng -> classify_pdf trả 'pdf_scan' (ngưỡng 20 ký tự)."""
    doc = fitz.open()
    doc.new_page()          # trang trắng, không chèn chữ
    return doc.tobytes()


def test_upload_scan_khong_goi_llm_kiem_loai(client, monkeypatch):
    """Bản scan không có text để phán -> gọi LLM là vừa tốn thời gian chờ vừa sinh cảnh báo giả."""
    import routers.documents as rd

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": False, "suggested_type": "", "confidence": 0.0, "note": "x"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-SC", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    r = client.post(f"/api/v1/packages/{pid}/documents",
                    files={"file": ("scan.pdf", _scan_pdf(), "application/pdf")},
                    data={"loai": "HSDT", "vendor_id": str(vid),
                          "artifact_type": "don_du_thau"})
    assert r.status_code == 200
    doc = r.json()["data"]
    assert doc["file_kind"] == "pdf_scan"
    assert goi == []                              # KHÔNG call LLM nào
    assert doc["artifact_validation"] is None     # để None, KHÔNG bịa kết quả
    assert doc["artifact_type"] == "don_du_thau"  # loại hồ sơ vẫn được ghi


def test_upload_pdf_co_text_van_kiem_loai_nhu_cu(client, monkeypatch):
    """Hồi quy: file có text nhúng vẫn được kiểm loại — đây là ca kiểm thật sự có căn cứ."""
    import routers.documents as rd

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": True, "suggested_type": "don_du_thau", "confidence": 0.9, "note": "ok"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-TX", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    r = client.post(f"/api/v1/packages/{pid}/documents",
                    files={"file": ("don.pdf", _text_pdf("Đơn dự thầu của nhà thầu"),
                                    "application/pdf")},
                    data={"loai": "HSDT", "vendor_id": str(vid),
                          "artifact_type": "don_du_thau"})
    assert r.status_code == 200
    assert goi == ["don_du_thau"]
    assert r.json()["data"]["artifact_validation"]["match"] is True


def test_doi_loai_ho_so_tren_file_scan_khong_goi_llm(client, monkeypatch):
    """PATCH đổi loại: file scan có extracted_text='[]' -> mỗi lần đổi lại tốn 1 call vô ích."""
    import routers.documents as rd

    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-PT", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    doc_id = client.post(f"/api/v1/packages/{pid}/documents",
                         files={"file": ("scan.pdf", _scan_pdf(), "application/pdf")},
                         data={"loai": "HSDT", "vendor_id": str(vid),
                               "artifact_type": "don_du_thau"}).json()["data"]["id"]

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": True, "suggested_type": declared_type, "confidence": 0.9, "note": "ok"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    r = client.patch(f"/api/v1/packages/{pid}/documents/{doc_id}",
                     json={"artifact_type": "bao_dam_du_thau"})
    assert r.status_code == 200
    assert goi == []
    assert r.json()["data"]["artifact_type"] == "bao_dam_du_thau"
    assert r.json()["data"]["artifact_validation"] is None


def test_doi_loai_ho_so_tren_file_co_text_van_kiem_nhu_cu(client, monkeypatch):
    """Hồi quy chiều còn lại: file có text nhúng thì PATCH vẫn kiểm loại như trước."""
    import routers.documents as rd

    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-PX", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": True, "suggested_type": declared_type, "confidence": 0.9, "note": "ok"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    doc_id = client.post(f"/api/v1/packages/{pid}/documents",
                         files={"file": ("don.pdf", _text_pdf("Đơn dự thầu của nhà thầu"),
                                         "application/pdf")},
                         data={"loai": "HSDT", "vendor_id": str(vid),
                               "artifact_type": "don_du_thau"}).json()["data"]["id"]
    goi.clear()                                   # bỏ lần gọi lúc upload, chỉ đo lần PATCH
    r = client.patch(f"/api/v1/packages/{pid}/documents/{doc_id}",
                     json={"artifact_type": "bao_dam_du_thau"})
    assert r.status_code == 200
    assert goi == ["bao_dam_du_thau"]
    assert r.json()["data"]["artifact_validation"]["match"] is True
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_documents_api.py -q -k "khong_goi_llm or van_kiem"`
Expected: FAIL — `test_upload_scan_khong_goi_llm_kiem_loai` báo `assert ['don_du_thau'] == []`; `test_doi_loai_ho_so_tren_file_scan_khong_goi_llm` báo tương tự. Hai test `..._van_kiem_loai_nhu_cu` và `..._van_kiem_nhu_cu` XANH sẵn (chúng khoá hành vi phải GIỮ).

- [ ] **Step 3: Sửa `upload_document`**

Trong `backend/routers/documents.py`, thay khối `try` (dòng 74-82) bằng:

```python
    try:
        pages = documents.extract_document(content, file_kind)
        doc.extracted_text = json.dumps(pages, ensure_ascii=False)
        doc.trang_thai_ocr = "hoan_thanh"
        # `pages` rỗng = bản scan (extract_document cố ý không OCR ở bước upload, để vision đọc ảnh
        # lúc chấm). Gọi LLM kiểm loại trên nội dung RỖNG vừa bắt người dùng chờ vô ích, vừa sinh
        # cảnh báo "nghi tải nhầm loại" giả. Không có text thì không có gì để phán -> để None.
        if doc.artifact_type and pages:
            doc.artifact_validation = await validate_artifact(pages, doc.artifact_type)
    except Exception as exc:  # graceful degradation (NFR 5.3)
        doc.trang_thai_ocr = f"loi: {exc}"
```

- [ ] **Step 4: Sửa `update_document_type`**

Trong cùng file, thay khối gán `artifact_validation` (dòng 110-115) bằng:

```python
    doc.artifact_type = artifact_type or None
    pages = json.loads(doc.extracted_text or "[]")
    # Cùng lý do như lúc upload: file scan có extracted_text="[]" nên không có căn cứ để kiểm.
    doc.artifact_validation = (await validate_artifact(pages, artifact_type)
                               if artifact_type and pages else None)
```

- [ ] **Step 5: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_documents_api.py tests/test_documents_artifact_api.py -q`
Expected: PASS toàn bộ (gồm hồi quy `test_upload_hsdt_thieu_loai_ho_so_bi_tu_choi`, `test_upload_giu_loai_ho_so_khi_ocr_loi`).

- [ ] **Step 6: Chạy full suite backend**

Run: `cd backend && python -m pytest -q`
Expected: đúng con số baseline đã ghi ở đầu, không thêm test đỏ nào.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/documents.py backend/tests/test_documents_api.py
git commit -m "fix(documents): không gọi LLM kiểm loại hồ sơ khi tài liệu không có text"
```

---

### Task 2: Upload có chỉ báo đang xử lý

**Files:**
- Modify: `frontend/src/pages/PackageDetail.tsx:77-104` (`UploadDoc`, `UploadPlain`), `:144-157` (`uploadDoc`)

**Interfaces:**
- Consumes: hành vi từ Task 1 — upload PDF scan nay trả về gần như tức thì; PDF có text vẫn có thể chờ vì còn call LLM kiểm loại.
- Produces: không có API mới.

**Bối cảnh (đọc trước khi sửa):** `uploadDoc` hiện không có chỉ báo nào — không spinner, không disable nút, chỉ `message.success` sau khi xong. Ngay dưới nó, `runEval` (`:181`) đã dùng đúng khuôn cần áp dụng:

```tsx
message.loading({ content: "Đang chấm HSDT — có thể mất vài phút…", key: "eval", duration: 0 });
// … sau khi xong:
message.success({ content: "Đánh giá hoàn tất", key: "eval" });
```

`message` với cùng `key` sẽ **thay thế** thông báo cũ thay vì xếp chồng — đó là lý do phải dùng `key`.

- [ ] **Step 1: Thêm state `uploading` và dùng nó trong `uploadDoc`**

Trong component chứa `uploadDoc`, thêm state cạnh các state hiện có:

```tsx
  const [uploading, setUploading] = useState(false);
```

Rồi thay `uploadDoc` (dòng 144-157) bằng:

```tsx
  const uploadDoc = async (file: File, loai: string, vendorId?: number, artifactType?: string) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("loai", loai);
    if (vendorId) fd.append("vendor_id", String(vendorId));
    if (artifactType) fd.append("artifact_type", artifactType);
    // Cùng khuôn với nút "Chạy đánh giá": message có key cố định + duration 0 -> thông báo đứng
    // yên cho tới khi bị chính nó thay thế, không xếp chồng.
    message.loading({ content: `Đang tải "${file.name}" và xử lý…`, key: "upload", duration: 0 });
    setUploading(true);
    try {
      const res = await api.post(`/packages/${id}/documents`, fd);
      const doc = res.data.data;
      if (doc?.artifact_validation?.match === false)
        message.warning({ content: `Nghi tải nhầm loại: ${doc.artifact_validation.note}`, key: "upload" });
      else message.success({ content: "Đã tải lên & xử lý", key: "upload" });
      load();
    } catch (e: any) { message.error({ content: e.message, key: "upload" }); }
    finally { setUploading(false); }
  };
```

- [ ] **Step 2: Truyền `uploading` xuống hai component upload**

Đổi chữ ký `UploadDoc` và `UploadPlain` để nhận thêm `disabled`, và disable nút trong lúc chờ — bấm chồng sẽ tạo nhiều bản ghi tài liệu trùng:

```tsx
function UploadDoc({ artifactTypes, onUpload, label = "Tải hồ sơ", disabled = false }: {
  artifactTypes: ArtOpt[]; onUpload: (file: File, at: string) => Promise<void>;
  label?: string; disabled?: boolean;
}) {
```

Trong thân `UploadDoc`, thêm `disabled={disabled}` vào `<Upload>` và `loading={disabled}` vào `<Button>`:

```tsx
      <Upload showUploadList={false} accept=".pdf" disabled={disabled} beforeUpload={(f) => {
```
```tsx
        <Button icon={<UploadOutlined />} loading={disabled}>{label}</Button>
```

Làm y hệt cho `UploadPlain`:

```tsx
function UploadPlain({ onUpload, label, disabled = false }: {
  onUpload: (file: File) => Promise<void>; label: string; disabled?: boolean;
}) {
  return (
    <Upload showUploadList={false} accept=".pdf" disabled={disabled} beforeUpload={(f) => {
      if (!isPdf(f)) { message.error(PDF_ONLY); return false; }
      onUpload(f); return false;
    }}>
      <Button icon={<UploadOutlined />} loading={disabled}>{label}</Button>
    </Upload>
  );
}
```

- [ ] **Step 3: Truyền prop tại mọi chỗ dùng**

Run: `cd frontend && grep -n "<UploadDoc\|<UploadPlain" src/pages/PackageDetail.tsx`

Thêm `disabled={uploading}` vào **từng** chỗ tìm được.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi. (Nếu `node_modules` chưa có, chạy `npm install` trước — xem `frontend/package.json`.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PackageDetail.tsx
git commit -m "feat(frontend): upload hồ sơ có chỉ báo đang xử lý, chặn bấm chồng"
```

---

### Task 3: Đếm riêng "thiếu hồ sơ" trong tổng hợp

**Files:**
- Modify: `backend/routers/evaluation.py:94-105` (`_summary`), `frontend/src/api/types.ts:50-53` (`EvalSummary`), `frontend/src/pages/Evaluation.tsx:17-23` (`pillClass`), `:138-151` (`SummaryChips`), `:350-353` (cột "Cần làm rõ"), `frontend/src/index.css:284-288`
- Test: `backend/tests/test_evaluation_api.py`

**Interfaces:**
- Consumes: `models.HsdtCriterionEval` với quan hệ `.verdicts` (mỗi verdict có `.ket_qua`); hằng `KET_QUA_THIEU = "thiếu hồ sơ"` từ `experiment.evaluate.schema`.
- Produces: khoá `n_thieu_ho_so: int` trong dict `_summary(...)`, có mặt trong payload `results` dưới `vendors[].summary`. Task 4 không phụ thuộc khoá này.

**Bối cảnh (đọc trước khi sửa):** ở roll-up (`_rollup`, `routers/evaluation.py:80-92`), `KET_QUA_THIEU` bị cuộn vào `KET_QUA_SOI` — nên **tiêu chí không bao giờ mang kết quả "thiếu hồ sơ"**, chỉ verdict cấp nội dung mới mang. Vì vậy ô đếm mới phải định nghĩa là **số tiêu chí có ít nhất một verdict "thiếu hồ sơ"**, và trình bày như **khoản mục con của "cần làm rõ"** — mọi ô đếm hiện có đều đếm tiêu chí và cộng lại đúng bằng `n_tieu_chi`; thêm một ô ngang hàng sẽ phá đẳng thức đó và làm bảng tổng hợp nói dối.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_evaluation_api.py`:

```python
def _fake_eval_thieu():
    """evaluate_vendor giả: tiêu chí đầu có 1 verdict 'thiếu hồ sơ' + 1 'đạt', tiêu chí sau 'đạt'.

    Roll-up cuộn 'thiếu hồ sơ' thành 'cần làm rõ' -> chính là ca mà ô đếm mới phải bóc tách ra.
    """
    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1)])
        for i, c in enumerate(criteria):
            kqs = ["thiếu hồ sơ", "đạt"] if i == 0 else ["đạt"]
            verds = [Verdict(
                noi_dung_kiem_tra=f"nd{j}", hsdt_kiem_tra="don_du_thau", yeu_cau="", 
                thong_tin_bo_sung="", ket_qua=kq, bang_chung="", trang=[], do_tin=0.0,
                ghi_chu="", nguon_doc=[]) for j, kq in enumerate(kqs)]
            r.criteria.append(CriterionEval(
                nhom=c["nhom"], ten=c["ten"],
                ket_qua="cần làm rõ" if i == 0 else "đạt", verdicts=verds, yeu_cau_goc=""))
        return r
    return fake


def test_summary_dem_rieng_thieu_ho_so(client, monkeypatch):
    """'thiếu hồ sơ' (nhà thầu không nộp) khác hẳn 'cần làm rõ' (AI chưa đủ căn cứ) — phải bóc tách."""
    import routers.evaluation as re_

    pid = _seed(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_thieu())
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200

    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    s = v["summary"]
    assert s["n_thieu_ho_so"] == 1
    assert s["n_thieu_ho_so"] <= s["n_can_lam_ro"]        # là khoản mục CON, không ngang hàng
    # Đẳng thức tổng KHÔNG được vỡ khi thêm ô đếm mới.
    assert s["n_tieu_chi"] == (s["n_dat"] + s["n_khong_dat"]
                               + s["n_can_lam_ro"] + s["n_khong_ap_dung"])


def test_mot_tieu_chi_hai_verdict_thieu_van_dem_mot(client, monkeypatch):
    """Đếm TIÊU CHÍ, không đếm verdict — hai nội dung cùng thiếu vẫn là một tiêu chí."""
    import routers.evaluation as re_

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"))
        c = criteria[0]
        verds = [Verdict(noi_dung_kiem_tra=f"nd{j}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                         thong_tin_bo_sung="", ket_qua="thiếu hồ sơ", bang_chung="", trang=[],
                         do_tin=0.0, ghi_chu="", nguon_doc=[]) for j in range(2)]
        r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="cần làm rõ",
                                        verdicts=verds, yeu_cau_goc=""))
        return r

    pid = _seed(client)
    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    s = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]["summary"]
    assert s["n_thieu_ho_so"] == 1
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_evaluation_api.py -q -k thieu_ho_so`
Expected: FAIL với `KeyError: 'n_thieu_ho_so'`

- [ ] **Step 3: Sửa `_summary`**

Trong `backend/routers/evaluation.py`, thêm `KET_QUA_THIEU` vào khối import hằng từ `experiment.evaluate.schema` (kiểm bằng `grep -n "KET_QUA_" routers/evaluation.py | head -3`), rồi thay `_summary` bằng:

```python
def _summary(evals: list[models.HsdtCriterionEval]) -> dict[str, int]:
    """Đếm MỌI tiêu chí — kiểm tra thường trực của hệ thống có trọng số ngang tiêu chí HSMT.

    `n_thieu_ho_so` là KHOẢN MỤC CON của `n_can_lam_ro`, không ngang hàng: roll-up cuộn verdict
    'thiếu hồ sơ' thành tiêu chí 'cần làm rõ', nên đếm nó thành ô riêng sẽ phá đẳng thức
    n_tieu_chi = n_dat + n_khong_dat + n_can_lam_ro + n_khong_ap_dung. Đếm theo TIÊU CHÍ (không
    theo verdict) để cùng đơn vị với các ô còn lại.
    """
    tc = list(evals)

    def cnt(k: str) -> int:
        return sum(1 for e in tc if e.ket_qua == k)
    return {
        "n_tieu_chi": len(tc), "n_dat": cnt(KET_QUA_DAT), "n_khong_dat": cnt(KET_QUA_KHONG),
        "n_can_lam_ro": cnt(KET_QUA_SOI), "n_khong_ap_dung": cnt(KET_QUA_KHONG_AP_DUNG),
        "n_thieu_ho_so": sum(1 for e in tc
                             if any(v.ket_qua == KET_QUA_THIEU for v in e.verdicts)),
    }
```

- [ ] **Step 4: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_evaluation_api.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 5: Thêm field vào type frontend**

Trong `frontend/src/api/types.ts`, sửa `EvalSummary`:

```ts
export interface EvalSummary {
  n_tieu_chi: number; n_dat: number; n_khong_dat: number; n_can_lam_ro: number;
  n_khong_ap_dung?: number;
  /** Khoản mục CON của n_can_lam_ro: số tiêu chí có ít nhất một nội dung thiếu hồ sơ. */
  n_thieu_ho_so?: number;
}
```

Để optional (`?`) vì payload từ bản backend cũ không có khoá này.

- [ ] **Step 6: Tách màu pill "thiếu hồ sơ"**

Trong `frontend/src/index.css`, thêm ngay sau dòng `.verdict-result-pill.loi`:

```css
/* "Thiếu hồ sơ" (nhà thầu không nộp) và "cần làm rõ" (AI chưa đủ căn cứ) cần hai hành động khác
   nhau — trước đây dùng chung màu cam nên chuyên gia không phân biệt được khi quét mắt. */
.verdict-result-pill.thieu-ho-so  { background: var(--teal-tint);  color: var(--teal); }
```

Trong `frontend/src/pages/Evaluation.tsx`, sửa `pillClass`:

```tsx
function pillClass(kq: string): string {
  if (kq === "đạt") return "dat";
  if (kq === "không đạt") return "khong-dat";
  if (kq === "lỗi") return "loi";
  if (kq === "không áp dụng") return "khong-ap-dung";   // trung tính (xám), khác cam "cần làm rõ"
  if (kq === "thiếu hồ sơ") return "thieu-ho-so";       // nhà thầu không nộp, khác "AI chưa đủ căn cứ"
  return "can-lam-ro";
}
```

- [ ] **Step 7: Hiện khoản mục con ở chip tổng hợp và bảng so sánh**

Trong `SummaryChips`, thay dòng chip "cần làm rõ" bằng:

```tsx
      <Tag color={s.n_can_lam_ro > 0 ? "orange" : undefined}>
        {s.n_can_lam_ro} cần làm rõ
        {(s.n_thieu_ho_so ?? 0) > 0 && ` (${s.n_thieu_ho_so} thiếu hồ sơ)`}
      </Tag>
```

Trong `SummaryTable`, thay cột "Cần làm rõ" bằng:

```tsx
        { title: "Cần làm rõ", width: 130, align: "center",
          render: (_, v) => {
            const n = v.summary.n_can_lam_ro;
            const thieu = v.summary.n_thieu_ho_so ?? 0;
            return (
              <span>
                {n > 0 ? <span style={{ color: "var(--partial)", fontWeight: 600 }}>{n}</span> : 0}
                {thieu > 0 && (
                  <span style={{ color: "var(--ink-muted)", fontSize: "var(--fs-label)" }}>
                    {" "}(thiếu hồ sơ: {thieu})
                  </span>
                )}
              </span>
            );
          } },
```

- [ ] **Step 8: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi.

- [ ] **Step 9: Commit**

```bash
git add backend/routers/evaluation.py backend/tests/test_evaluation_api.py \
        frontend/src/api/types.ts frontend/src/pages/Evaluation.tsx frontend/src/index.css
git commit -m "feat(evaluation): đếm riêng 'thiếu hồ sơ' như khoản mục con của 'cần làm rõ'"
```

---

### Task 4: Danh sách loại hồ sơ nhà thầu chưa nộp

**Files:**
- Modify: `backend/routers/evaluation.py` (thêm `_ho_so_chua_nop` cạnh `_thieu_loai_ho_so` dòng 56; `results` dòng 249-271), `frontend/src/api/types.ts`, `frontend/src/pages/Evaluation.tsx:177-196` (`VendorSection`)
- Test: `backend/tests/test_evaluation_api.py`

**Interfaces:**
- Consumes: `models.RubricCriterion` (`.ten`, `.hsdt_can_kiem_tra: list[str]`, `.noi_dung` → mỗi phần tử có `.hsdt_kiem_tra`, `.ap_dung`); `models.HsdtVendorEval` (`.hinh_thuc: str`, `.ho_so_nhan_duoc: list[dict]`); `services.artifact_catalog.la_dung_chung(code: str) -> bool`; `experiment.evaluate.route._norm(s: str) -> str`.
- Produces: `_ho_so_chua_nop(db, package_id, ve) -> list[dict]`, mỗi phần tử `{"loai_ho_so": str, "tieu_chi": list[str]}`; có mặt trong payload `results` dưới `vendors[].ho_so_chua_nop`.

**Bối cảnh (đọc trước khi sửa):**

1. Trong file đã có `_thieu_loai_ho_so` (dòng 56) nhưng nghĩa **khác hẳn** — nó trả tên các *file* HSDT chưa gán loại hồ sơ. **Không tái dụng, không đặt tên gần giống.**
2. `ho_so_nhan_duoc[].loai_ho_so` được `inventory_pages` (`experiment/evaluate/route.py:63`) ghi ở dạng `_norm` (thường, bỏ dấu, `đ→d`, giữ gạch dưới), còn `hsdt_can_kiem_tra` là mã catalog do decompose sinh. **So hai tập phải đi qua cùng `_norm`.** Giữ mã gốc để hiển thị nhãn.
3. Hai phép trừ có lý do nghiệp vụ cụ thể:
   - **Tài liệu dùng chung** (`la_dung_chung`): `webform` là kết quả mở thầu do bên mời thầu công bố cho cả gói. Báo "nhà thầu chưa nộp webform" là quy kết sai.
   - **Loại chỉ áp dụng hình thức khác:** loại bị trừ khi **mọi** nội dung trỏ tới nó đều có `ap_dung` lệch `hinh_thuc` của nhà thầu. Nhà thầu độc lập không bị báo thiếu `thoa_thuan_lien_danh`. `hinh_thuc` rỗng (không rõ) → **không trừ gì** (fail-safe: thà báo thừa còn hơn giấu mất một loại hồ sơ thật sự thiếu).

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_evaluation_api.py`:

```python
def _seed_hai_loai(client) -> int:
    """Gói có 3 tiêu chí: đơn dự thầu; bảng giá ↔ webform (dùng chung); thỏa thuận liên danh."""
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-CN", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "Có đơn",
         "hsdt_can_kiem_tra": ["don_du_thau"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có đơn", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},
        {"nhom": "hop_le", "ten": "Giá khớp webform", "yeu_cau_goc": "Giá khớp",
         "hsdt_can_kiem_tra": ["bang_gia", "webform"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Giá khớp", "hsdt_kiem_tra": "bang_gia", "yeu_cau": "khớp",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},
        {"nhom": "hop_le", "ten": "Thỏa thuận liên danh", "yeu_cau_goc": "Có thỏa thuận",
         "hsdt_can_kiem_tra": ["thoa_thuan_lien_danh"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có thỏa thuận", "hsdt_kiem_tra": "thoa_thuan_lien_danh",
             "yeu_cau": "có", "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "",
             "nguon": "", "can_review": False, "ap_dung": "lien_danh"}]},
    ]})
    return pid


def _fake_eval_nhan_don(hinh_thuc: str = "độc lập"):
    """evaluate_vendor giả: nhà thầu CHỈ nộp đơn dự thầu, hình thức theo tham số."""
    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc=hinh_thuc, nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1)])
        for c in criteria:
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="đạt",
                                            verdicts=[], yeu_cau_goc=""))
        return r
    return fake


def test_ho_so_chua_nop_loai_webform_va_lien_danh_cho_nha_thau_doc_lap(client, monkeypatch):
    """webform là tài liệu bên mời thầu; thỏa thuận liên danh không áp dụng nhà thầu độc lập."""
    import routers.evaluation as re_

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200

    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    loais = [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]
    assert "bang_gia" in loais                    # thật sự thiếu
    assert "don_du_thau" not in loais             # đã nộp
    assert "webform" not in loais                 # tài liệu DÙNG CHUNG, không phải nhà thầu nộp
    assert "thoa_thuan_lien_danh" not in loais    # chỉ áp dụng liên danh
    # Mỗi mục nêu tiêu chí bị ảnh hưởng để chuyên gia thấy ngay hệ quả.
    bg = next(x for x in v["ho_so_chua_nop"] if x["loai_ho_so"] == "bang_gia")
    assert bg["tieu_chi"] == ["Giá khớp webform"]


def test_ho_so_chua_nop_bao_thoa_thuan_lien_danh_cho_nha_thau_lien_danh(client, monkeypatch):
    import routers.evaluation as re_

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("liên danh"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_hinh_thuc_khong_ro_thi_khong_tru_gi(client, monkeypatch):
    """Fail-safe: không dò được hình thức -> thà báo thừa còn hơn giấu mất hồ sơ thật sự thiếu."""
    import routers.evaluation as re_

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don(""))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_rong_khi_nop_du(client, monkeypatch):
    import routers.evaluation as re_

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1),
                                        HoSoNhanDuoc("bang_gia", ["bg.pdf"], 2)])
        for c in criteria:
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="đạt",
                                            verdicts=[], yeu_cau_goc=""))
        return r

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert v["ho_so_chua_nop"] == []
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_evaluation_api.py -q -k chua_nop`
Expected: FAIL với `KeyError: 'ho_so_chua_nop'`

- [ ] **Step 3: Thêm import cần dùng**

Ở đầu `backend/routers/evaluation.py`, thêm:

```python
from services import artifact_catalog
from experiment.evaluate.route import _norm
```

(Kiểm trước bằng `grep -n "^from\|^import" routers/evaluation.py` — nếu đã có thì bỏ qua.)

- [ ] **Step 4: Cài đặt `_ho_so_chua_nop`**

Thêm ngay sau `_thieu_loai_ho_so` trong `backend/routers/evaluation.py`:

```python
def _ho_so_chua_nop(db: Session, package_id: int,
                    ve: models.HsdtVendorEval | None) -> list[dict[str, Any]]:
    """Loại hồ sơ HSMT đòi mà nhà thầu CHƯA NỘP, kèm tiêu chí bị ảnh hưởng.

    Khác `_thieu_loai_ho_so` (file đã tải nhưng chưa gán loại) — đây là loại hồ sơ hoàn toàn vắng
    mặt. Trừ hai nhóm khỏi tập yêu cầu:

    - Tài liệu DÙNG CHUNG (webform = kết quả mở thầu) do bên mời thầu công bố cho cả gói, không
      phải thứ nhà thầu nộp — báo thiếu là quy kết sai.
    - Loại mà MỌI nội dung trỏ tới nó đều `ap_dung` lệch hình thức của nhà thầu (vd thỏa thuận
      liên danh với nhà thầu độc lập). Đọc cùng dữ liệu mà `_gate_khong_ap_dung` đọc, KHÔNG cài
      lại phép gate.

    Chưa dò được hình thức -> KHÔNG trừ theo hình thức (fail-safe: thà báo thừa còn hơn giấu mất
    một loại hồ sơ thật sự thiếu).

    So tập bằng `_norm` vì `ho_so_nhan_duoc.loai_ho_so` đã được inventory_pages chuẩn hoá, còn
    `hsdt_can_kiem_tra` là mã catalog nguyên bản. Giữ mã gốc để hiển thị nhãn.
    """
    crits = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)
        .order_by(models.RubricCriterion.thu_tu)).all()
    hinh_thuc = (ve.hinh_thuc if ve else "") or ""
    da_nhan = {_norm(str(h.get("loai_ho_so", ""))) for h in ((ve.ho_so_nhan_duoc if ve else []) or [])}

    # mã gốc -> {"tieu_chi": [...], "chi_hinh_thuc_khac": bool}
    can: dict[str, dict[str, Any]] = {}
    for c in crits:
        for raw in (c.hsdt_can_kiem_tra or []):
            ma = str(raw).strip()
            if not ma or artifact_catalog.la_dung_chung(_norm(ma)):
                continue
            muc = can.setdefault(ma, {"tieu_chi": [], "chi_hinh_thuc_khac": True})
            if c.ten not in muc["tieu_chi"]:
                muc["tieu_chi"].append(c.ten)
            # Loại này còn "áp dụng" nếu có ÍT NHẤT MỘT nội dung không bị lệch hình thức.
            nds = [n for n in c.noi_dung if _norm(n.hsdt_kiem_tra) == _norm(ma)]
            if not nds or not hinh_thuc:
                muc["chi_hinh_thuc_khac"] = False
            elif any(not _lech_hinh_thuc(n.ap_dung, hinh_thuc) for n in nds):
                muc["chi_hinh_thuc_khac"] = False

    return [{"loai_ho_so": ma, "tieu_chi": muc["tieu_chi"]}
            for ma, muc in can.items()
            if _norm(ma) not in da_nhan and not muc["chi_hinh_thuc_khac"]]


def _lech_hinh_thuc(ap_dung: str, hinh_thuc: str) -> bool:
    """Nội dung chỉ áp dụng một hình thức, mà nhà thầu thuộc hình thức KHÁC?"""
    ap = canon_hinh_thuc(ap_dung or "")
    return bool(ap) and ap != hinh_thuc
```

Thêm import `canon_hinh_thuc` ở đầu file:

```python
from experiment.evaluate.vendor_profile import canon_hinh_thuc
```

`canon_hinh_thuc` ép `"lien_danh"` / `"doc_lap"` về hằng `"liên danh"` / `"độc lập"`, và trả `""` khi không nhận diện được — cùng hàm mà lõi eval dùng, nên không sinh quy tắc so hình thức thứ hai.

- [ ] **Step 5: Trả field mới trong `results`**

Trong `results`, thay khối `vendors_out.append({...})` bằng:

```python
        vendors_out.append({
            "vendor_id": v.id, "ten": v.ten, "ten_viet_tat": v.ten_viet_tat, "hinh_thuc": v.hinh_thuc,
            "summary": _summary(evals), "criteria": crit_out,
            "vendor_profile": _profile_out(ve),
            "ho_so_nhan_duoc": ve.ho_so_nhan_duoc if ve else [],
            "ho_so_chua_nop": _ho_so_chua_nop(db, package_id, ve)})
```

- [ ] **Step 6: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_evaluation_api.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 7: Chạy full suite backend**

Run: `cd backend && python -m pytest -q`
Expected: đúng con số baseline, không thêm test đỏ nào.

- [ ] **Step 8: Thêm type frontend**

Trong `frontend/src/api/types.ts`, thêm interface và field:

```ts
export interface HoSoChuaNop { loai_ho_so: string; tieu_chi: string[]; }
```

và trong `VendorEval`:

```ts
  ho_so_chua_nop?: HoSoChuaNop[];
```

- [ ] **Step 9: Hiện thẻ hồ sơ chưa nộp**

Trong `frontend/src/pages/Evaluation.tsx`, thêm component ngay trước `VendorSection`:

```tsx
// Loại hồ sơ HSMT đòi mà nhà thầu chưa nộp. Rỗng thì KHÔNG hiện gì — ca đủ hồ sơ không cần thêm
// nhiễu, và một khối luôn hiện sẽ dạy mắt bỏ qua nó.
function HoSoChuaNopBanner({ v }: { v: VendorEval }) {
  const nhan = useArtifactLabel();
  const ds = v.ho_so_chua_nop ?? [];
  if (ds.length === 0) return null;
  return (
    <div style={{ marginTop: "var(--sp-3)", padding: "var(--sp-3)", borderRadius: 6,
                  background: "var(--partial-bg)", border: "1px solid var(--line)" }}>
      <div style={{ fontWeight: 600, color: "var(--partial)", marginBottom: "var(--sp-2)" }}>
        Chưa nộp {ds.length} loại hồ sơ
      </div>
      {ds.map((h) => (
        <div key={h.loai_ho_so} style={{ fontSize: "var(--fs-label)", color: "var(--ink)" }}>
          {nhan(h.loai_ho_so)}
          <span style={{ color: "var(--ink-muted)" }}> — cần cho: {h.tieu_chi.join("; ")}</span>
        </div>
      ))}
    </div>
  );
}
```

Rồi trong `VendorSection`, thêm ngay sau `<HinhThucBanner v={v} />`:

```tsx
        <HoSoChuaNopBanner v={v} />
```

- [ ] **Step 10: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi.

- [ ] **Step 11: Commit**

```bash
git add backend/routers/evaluation.py backend/tests/test_evaluation_api.py \
        frontend/src/api/types.ts frontend/src/pages/Evaluation.tsx
git commit -m "feat(evaluation): liệt kê loại hồ sơ nhà thầu chưa nộp ở trang Kết quả"
```

---

## Nghiệm thu cuối (sau khi xong cả 4 task)

- [ ] `cd backend && python -m pytest -q` — đúng con số baseline ghi ở đầu, không thêm test đỏ.
- [ ] `cd frontend && npx tsc --noEmit` — sạch.
- [ ] `git log --oneline` có đủ 4 commit, mỗi commit một task.
- [ ] Chạy app thật (`cd backend && uvicorn main:app --reload --port 8000` + `cd frontend && npm run dev`) và kiểm bằng tay:
  1. Tải một HSDT bản **scan** → có thông báo "Đang tải…" rồi trả về gần như tức thì, không còn cảnh báo "Nghi tải nhầm loại" sai;
  2. Trang Kết quả: chip tổng hợp hiện "(N thiếu hồ sơ)" khi có, pill "Thiếu hồ sơ" khác màu pill "Cần làm rõ";
  3. Nhà thầu độc lập không bị liệt `thoa_thuan_lien_danh` trong thẻ "Chưa nộp"; không nhà thầu nào bị liệt `webform`.
