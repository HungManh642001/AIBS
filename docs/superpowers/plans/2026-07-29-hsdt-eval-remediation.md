# HSDT Eval Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa 3 lỗi phần đánh giá HSDT — luật `bang_gia_khop_webform` bắn nhầm nội dung kiểm tra, luật chữ ký đơn dự thầu neo sai văn bản với nhà thầu liên danh, và ingest gọi lại vision vô ích khi trang scan có cảnh báo.

**Architecture:** Ba phần độc lập, không phần nào chặn phần nào. Phần 3 (ingest) chỉ bỏ hành vi sửa chữa và mở cache. Phần 1 thêm một bước **phân xử** ở cấp tiêu chí khi nhiều nội dung cùng là ứng viên của một luật (metadata trước, từ khóa sau, fail-safe cuối) — không đổi phép khớp hiện có. Phần 2 thêm nhánh liên danh cho luật `chu_ky_khop_dkkd`: LLM chỉ **bóc dữ liệu**, mọi phán quyết nằm trong hàm thuần ở code (đúng khuôn `lien_danh_phan_cong.doi_chieu_phan_cong`).

**Tech Stack:** Python 3 + pydantic (`_Base` với `extra="ignore"`), pytest (`asyncio_mode = auto`), PyMuPDF (fitz), LLM qua `VisionFn` — test dùng `ScriptedVision` / vision giả tự viết. Không có network trong test.

**Spec:** `docs/superpowers/specs/2026-07-29-hsdt-eval-remediation-design.md`

## Global Constraints

- Thư mục làm việc mọi lệnh: `backend/`. Chạy test: `cd backend && python -m pytest <path> -q`.
- **Baseline có sẵn 5 test đỏ, KHÔNG liên quan tới plan này** — đừng tưởng mình làm hỏng, cũng đừng sửa chúng:
  `test_rules_bao_dam_uy_quyen.py::test_prompt_marker_cap_and_sys_mentions_uy_quyen`,
  `test_rules_lien_danh.py::test_prompt_ttld_van_cap_con_bang_gia_thi_khong`,
  `test_vendor_profile.py::test_detect_from_don_du_thau_via_llm`,
  `test_vendor_profile.py::test_detect_llm_low_confidence_is_khong_ro`,
  `test_vendor_profile.py::test_detect_llm_error_is_khong_ro_not_guess`.
  Số liệu baseline: `255 passed, 5 failed` cho `python -m pytest experiment/evaluate/tests -q`.
- Quy ước code (CLAUDE.md): Python snake_case, **type hints bắt buộc**, PEP 8. **Tiếng Việt trong comment/docstring/thông điệp người đọc, tiếng Anh trong tên code.**
- **no-silent-mock:** lỗi AI → verdict `"lỗi"` kèm nguyên văn lỗi, TUYỆT ĐỐI không bịa dữ liệu. Không đủ căn cứ → `"cần làm rõ"`, không đoán.
- **LLM bóc dữ liệu, code phán quyết.** Mọi if/else nghiệp vụ nằm trong hàm thuần testable, không nhét vào prompt.
- Hằng kết quả import từ `experiment.evaluate.schema`: `KET_QUA_DAT` `"đạt"`, `KET_QUA_KHONG` `"không đạt"`, `KET_QUA_SOI` `"cần làm rõ"`, `KET_QUA_THIEU` `"thiếu hồ sơ"`, `KET_QUA_LOI` `"lỗi"`.
- Commit sau mỗi task, tiếng Việt, theo dạng `fix(<scope>): <mô tả>` / `feat(<scope>): <mô tả>` như lịch sử repo.

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/experiment/evaluate/ingest.py` | Sửa `_doc_trang_vision` (chỉ retry khi chạm trần token), `_doc_file` (bỏ chặn cache), `ingest_hsdt` (lưu + khôi phục + log `canh_bao`) | 1 |
| `backend/experiment/evaluate/tests/test_ingest_tu_kiem.py` | Cập nhật 3 test cũ + thêm 3 test mới | 1 |
| `backend/services/artifact_catalog.py` | Thêm `nhac_toi(text, code)` — đoạn text có nhắc loại hồ sơ nào không | 2 |
| `backend/tests/test_artifact_catalog.py` | Test cho `nhac_toi` (file có sẵn, xem bước 1 Task 2) | 2 |
| `backend/experiment/evaluate/evaluate.py` | Thêm `_phan_luat_cho_nd` (phân xử ứng viên) + dùng trong `evaluate_criterion` | 3 |
| `backend/experiment/evaluate/tests/test_evaluate.py` | 4 test mới cho phân xử | 3 |
| `backend/experiment/decompose/schema.py` | Thêm field `hsdt_doi_chieu` vào `NoiDungKiemTra` | 4 |
| `backend/experiment/decompose/prompts.py` | Dạy `SYS_STRUCT` khai `hsdt_doi_chieu` + thêm vào schema JSON mẫu | 4 |
| `backend/experiment/decompose/tests/test_routing.py` | Test schema + prompt | 4 |
| `backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py` | Nhánh liên danh: 2 schema bóc, 2 prompt, 2 hàm thuần, 2 hàm async, rẽ nhánh trong `handler` | 5, 6, 7 |
| `backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py` | **File mới** — toàn bộ test nhánh liên danh | 5, 6, 7 |

---

### Task 1: Ingest — cảnh báo chỉ log, không đọc lại, và được cache

**Files:**
- Modify: `backend/experiment/evaluate/ingest.py:74-106` (`_doc_trang_vision`), `:109-146` (`_doc_file`), `:160-185` (`ingest_hsdt`), `:1-23` (docstring module)
- Test: `backend/experiment/evaluate/tests/test_ingest_tu_kiem.py`

**Interfaces:**
- Consumes: không có (task đầu, độc lập)
- Produces: không có API mới. `_doc_trang_vision(name: str, png: bytes, vision_fn: VisionFn) -> tuple[Any, list[str]]` giữ nguyên chữ ký; payload cache thêm khóa `"canh_bao": str`.

**Bối cảnh (đọc trước khi sửa):** hôm nay `_doc_trang_vision` gọi lại vision khi `kiem_tra_bang()` nghi bóc thiếu **hoặc** khi `finish_reason == "length"`. Đo trên `backend/experiment/logs/evaluate.log`: 21 lần thử lại, 20 lần vẫn nghi ngờ (~5% cứu được). Ngoài ra `_doc_file` đặt `du_de_cache = False` khi còn cảnh báo, mà khóa cache là **theo FILE**, nên một trang cảnh báo làm cả file phải OCR lại ở mọi lần chấm sau.

- [ ] **Step 1: Sửa 3 test cũ trong `test_ingest_tu_kiem.py` cho khớp hành vi mới**

Xoá hẳn `test_lech_cau_truc_thi_thu_lai_voi_seed_khac` (không còn thử lại theo seed nữa). Thay 3 test dưới đây vào đúng chỗ của `test_van_lech_sau_khi_thu_lai_thi_canh_bao`, `test_trang_co_canh_bao_thi_khong_ghi_cache`, `test_giu_ban_it_van_de_hon`:

```python
async def test_lech_cau_truc_chi_canh_bao_khong_doc_lai():
    """Nghi bóc thiếu -> CHỈ cảnh báo. Đo thực tế: thử lại cứu được ~5%, không đáng 2x call."""
    vision = VisionGhiNhan([{"text": _BANG_LECH}])
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 1                    # KHÔNG đọc lại
    assert "cột" in pages[0].canh_bao
    assert pages[0].text == _BANG_LECH               # vẫn giữ phần đọc được


async def test_trang_co_canh_bao_van_duoc_ghi_cache():
    """Cảnh báo là thông tin, không phải lỗi -> vẫn cache (kèm theo canh_bao), khỏi OCR lại cả file."""
    class Store:
        def __init__(self):
            self.puts: list[tuple[str, list[dict]]] = []

        def get(self, key):
            return None

        def put(self, key, pages):
            self.puts.append((key, pages))

    store = Store()
    vision = VisionGhiNhan([{"text": _BANG_LECH}])
    await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72, cache=store)
    assert len(store.puts) == 1
    assert "cột" in store.puts[0][1][0]["canh_bao"]   # cảnh báo phải nằm TRONG payload cache


async def test_giu_ban_it_van_de_hon():
    """Thử lại (do chạm trần) tệ hơn -> giữ bản ĐẦU, không mù quáng lấy bản cuối."""
    vision = VisionGhiNhan([{"text": _BANG_LECH, "finish_reason": "length"},
                            {"text": "STT | Ten\n1 | ... \n2"}])   # lệch + tóm tắt
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 2
    assert pages[0].text == _BANG_LECH
```

- [ ] **Step 2: Thêm 2 test mới vào cuối `test_ingest_tu_kiem.py`**

```python
async def test_trang_loi_vision_van_khong_ghi_cache():
    """Bất biến #1 giữ nguyên: LỖI vision không bao giờ được đóng băng vào cache."""
    from services.ai_client import AiOutcome

    class VisionLoi:
        def __init__(self):
            self.calls: list[dict] = []

        async def __call__(self, system, prompt, images=(), validate=None, max_tokens=None,
                           seed=None, **kw):
            self.calls.append({"max_tokens": max_tokens})
            return AiOutcome("error", None, "fake", error="proxy hỏng")

    class Store:
        def __init__(self):
            self.puts: list[str] = []

        def get(self, key):
            return None

        def put(self, key, pages):
            self.puts.append(key)

    store = Store()
    await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], VisionLoi(), dpi=72, cache=store)
    assert store.puts == []


async def test_canh_bao_khoi_phuc_dung_khi_doc_tu_cache():
    """Cache mà nuốt mất canh_bao thì lần chấm thứ hai luật hết thấy cảnh báo -> sai âm thầm."""
    class Store:
        def __init__(self):
            self.data: dict[str, list[dict]] = {}

        def get(self, key):
            return self.data.get(key)

        def put(self, key, pages):
            self.data[key] = pages

    store = Store()
    pdf = _pdf_scan()
    v1 = VisionGhiNhan([{"text": _BANG_LECH}])
    p1 = await ingest_hsdt([("bg.pdf", "bang_gia", pdf)], v1, dpi=72, cache=store)
    v2 = VisionGhiNhan([{"text": _BANG_LECH}])
    p2 = await ingest_hsdt([("bg.pdf", "bang_gia", pdf)], v2, dpi=72, cache=store)
    assert v2.calls == []                            # lần 2 đọc cache, 0 call
    assert p2[0].canh_bao == p1[0].canh_bao and "cột" in p2[0].canh_bao


async def test_entry_cache_cu_khong_co_khoa_canh_bao_van_doc_duoc():
    """Tương thích ngược: entry ghi trước thay đổi này không có khoá canh_bao -> ra '', không nổ."""
    from experiment.evaluate.ingest import ingest_cache_key

    pdf = _pdf_scan()
    key = ingest_cache_key(pdf, 72)

    class Store:
        def __init__(self):
            self.data = {key: [{"trang": 1, "text": "text cũ", "co_chu_ky": False,
                                "co_dau": False, "nguon_trich": "vision"}]}

        def get(self, k):
            return self.data.get(k)

        def put(self, k, pages):
            self.data[k] = pages

    vision = VisionGhiNhan([{"text": _BANG_DU}])
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", pdf)], vision, dpi=72, cache=Store())
    assert vision.calls == [] and pages[0].text == "text cũ" and pages[0].canh_bao == ""
```

- [ ] **Step 3: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_ingest_tu_kiem.py -q`
Expected: FAIL — `test_lech_cau_truc_chi_canh_bao_khong_doc_lai` báo `assert 2 == 1`; `test_trang_co_canh_bao_van_duoc_ghi_cache` báo `assert 0 == 1`; `test_canh_bao_khoi_phuc_dung_khi_doc_tu_cache` báo `KeyError`/`assert '' == '...cột...'`. `test_trang_loi_vision_van_khong_ghi_cache` XANH sẵn (bất biến cũ).

- [ ] **Step 4: Sửa `_doc_trang_vision` — chỉ thử lại khi chạm trần token**

Thay toàn bộ thân hàm `_doc_trang_vision` (`ingest.py:74-106`) bằng:

```python
async def _doc_trang_vision(name: str, png: bytes, vision_fn: VisionFn) -> tuple[Any, list[str]]:
    """Đọc 1 trang bằng vision + tự kiểm. CHỈ thử lại khi text bị CẮT (chạm trần token).

    Nghi bóc thiếu do `kiem_tra_bang` (lệch cột, dấu hiệu tóm tắt) thì CHỈ cảnh báo: seed đã cố
    định nên gọi lại chỉ đổi được seed, mà đo trên hồ sơ thật (logs/evaluate.log) là 21 lần thử
    lại chỉ cứu được 1 — không đáng 2x call. Cảnh báo vẫn đi trọn đường vào `PageRecord.canh_bao`
    -> `pages_text` -> prompt luật/eval -> `EvalResult.canh_bao_doc`, nên không mất tín hiệu nào.

    Chạm trần thì khác hẳn: tăng gấp đôi max_tokens là một call THỰC SỰ khác, có cơ hội lấy lại
    phần bị cắt. Giữ bản ÍT vấn đề hơn, không mù quáng lấy bản cuối.
    """
    out = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                          validate=validate_ingest_page, max_tokens=_MAX_TOKENS_INGEST,
                          seed=get_settings().ai_seed)
    if out.status != "ok":
        return out, []

    van_de = kiem_tra_bang((out.data or {}).get("text", ""))
    if out.finish_reason != "length":
        if van_de:
            log.warning("[ingest] %s: nghi bóc thiếu (%s) — chỉ cảnh báo, KHÔNG đọc lại",
                        name, "; ".join(van_de))
        return out, van_de

    log.warning("[ingest] %s: chạm trần token — thử lại 1 lần với max_tokens gấp đôi", name)
    lai = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                          validate=validate_ingest_page, max_tokens=_MAX_TOKENS_INGEST * 2,
                          seed=get_settings().ai_seed)
    if lai.status != "ok":
        return out, van_de

    van_de_lai = kiem_tra_bang((lai.data or {}).get("text", ""))
    if lai.finish_reason == "length":
        van_de_lai = van_de_lai + ["vẫn chạm trần token — text có thể bị cắt"]
    if not van_de_lai:
        return lai, []
    return (lai, van_de_lai) if len(van_de_lai) < len(van_de) else (out, van_de)
```

- [ ] **Step 5: Sửa `_doc_file` — cảnh báo không còn chặn cache**

Trong `_doc_file`, thay nguyên khối `if out.status == "ok": ... else: ...` (`ingest.py:128-140`) bằng:

```python
            if out.status == "ok":
                if van_de:
                    # KHÔNG im lặng: cảnh báo vào text để luật/eval hạ kết luận xuống 'cần làm rõ'.
                    # Nhưng KHÔNG chặn cache: cache theo FILE, một trang cảnh báo mà chặn thì mọi
                    # lần chấm sau phải OCR lại toàn bộ file.
                    log.warning("[ingest] %s tr%d nghi bóc thiếu: %s", name, i, "; ".join(van_de))
                records.append(_record(name, loai_ho_so, i, out.data, png,
                                       canh_bao="; ".join(van_de)))
            else:
                log.warning("[ingest] %s tr%d lỗi vision: %s", name, i, out.error)
                du_de_cache = False
                records.append(_record(name, loai_ho_so, i, {}, png))
```

Sửa docstring của `_doc_file` cho khớp: `du_de_cache=False` nếu có BẤT KỲ trang vision nào **lỗi** (cảnh báo không tính).

- [ ] **Step 6: Sửa `ingest_hsdt` — lưu `canh_bao` vào cache + log lại khi đọc cache**

Trong `ingest_hsdt`, ngay sau dòng `log.info("[ingest] %s (%s): %d trang — dùng cache ...")`, thêm:

```python
            for d in luu:
                if d.get("canh_bao"):
                    log.warning("[ingest] %s tr%s (cache) nghi bóc thiếu: %s", name,
                                d.get("trang", "?"), d["canh_bao"])
```

Và thêm khóa `canh_bao` vào payload `cache.put`:

```python
        if cache is not None and du_de_cache and recs:
            cache.put(key, [{"trang": r.trang, "text": r.text, "co_chu_ky": r.co_chu_ky,
                             "co_dau": r.co_dau, "nguon_trich": r.nguon_trich,
                             "canh_bao": r.canh_bao} for r in recs])
```

(`_record` đã đọc `d.get("canh_bao", canh_bao)` sẵn nên chiều đọc không cần sửa; entry cache cũ thiếu khóa này sẽ ra `""`, không nổ.)

- [ ] **Step 7: Cập nhật docstring module `ingest.py`**

Trong khối docstring đầu file (`ingest.py:1-23`), thay mục "Hai bất biến của cache" bằng:

```
Hai bất biến của cache:
1. TRANG LỖI VISION KHÔNG BAO GIỜ ĐƯỢC GHI CACHE — proxy hỏng 1 lần mà cache lại thì text rỗng
   đóng băng vĩnh viễn, tệ hơn hẳn việc OCR lại. Trang chỉ có CẢNH BÁO (nghi bóc thiếu) thì
   NGƯỢC LẠI: vẫn cache, kèm cả chuỗi `canh_bao` — cảnh báo là thông tin để chuyên gia soi, không
   phải lỗi cần chữa; khóa cache theo FILE nên chặn một trang là bắt OCR lại cả file mỗi lần chấm.
2. Ảnh PNG KHÔNG nằm trong cache (nặng, và không có consumer nào ngoài ingest) — khi hit vẫn
   render lại từ PDF bằng pdf_to_images: rẻ, không tốn LLM, nên PageRecord luôn đủ field.
```

- [ ] **Step 8: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_ingest_tu_kiem.py experiment/evaluate/tests/test_ingest.py experiment/evaluate/tests/test_ingest_cache.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 9: Chạy full suite evaluate để chắc không vỡ chỗ khác**

Run: `cd backend && python -m pytest experiment/evaluate/tests -q`
Expected: `5 failed` đúng 5 test baseline đã liệt kê ở Global Constraints, không thêm test đỏ nào.

- [ ] **Step 10: Commit**

```bash
git add backend/experiment/evaluate/ingest.py backend/experiment/evaluate/tests/test_ingest_tu_kiem.py
git commit -m "perf(ingest): cảnh báo bóc thiếu chỉ log, không đọc lại và vẫn được cache"
```

---

### Task 2: `artifact_catalog.nhac_toi` — đoạn text có nhắc loại hồ sơ nào không

**Files:**
- Modify: `backend/services/artifact_catalog.py` (thêm hàm sau `resolve_code`, khoảng dòng 170)
- Test: `backend/tests/test_artifact_catalog.py`

**Interfaces:**
- Consumes: `_norm_code(s: str) -> str` (đã có trong cùng file, dòng 129)
- Produces: `nhac_toi(text: str, code: str) -> bool` — Task 3 dùng để phân xử tầng 2.

- [ ] **Step 1: Tìm file test đúng chỗ**

Run: `cd backend && ls tests/ | grep -i catalog`
Nếu chưa có `tests/test_artifact_catalog.py` thì tạo mới với dòng đầu là docstring `"""Danh mục loại hồ sơ — tra mã và nhận diện tài liệu được nhắc trong văn bản."""`.

- [ ] **Step 2: Viết test thất bại**

Thêm vào `backend/tests/test_artifact_catalog.py`:

```python
from services.artifact_catalog import nhac_toi


def test_nhac_toi_bat_alias_bo_dau_va_dau_phan_cach():
    # nội dung 2 của gói 54 — có nhắc webform
    assert nhac_toi("Giá dự thầu trong Bảng chào giá chi tiết phải phù hợp với giá dự thầu "
                    "trên webform", "webform")
    assert nhac_toi("Đối chiếu với Kết quả mở thầu", "webform")
    assert nhac_toi("so với biên bản mở thầu", "webform")
    assert nhac_toi("theo web form của hệ thống", "webform")


def test_nhac_toi_khong_bat_khi_khong_nhac():
    # nội dung 1 của gói 54 — CHỈ nói về mẫu biểu, không nhắc webform
    assert not nhac_toi("Phải nộp Bảng chào giá chi tiết theo đúng Mẫu số 05C.1 Chương V",
                        "webform")
    assert not nhac_toi("", "webform")


def test_nhac_toi_ma_khong_co_trong_danh_muc_thi_false():
    assert not nhac_toi("bất kỳ nội dung nào", "khong_ton_tai")
```

- [ ] **Step 3: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_artifact_catalog.py -q`
Expected: FAIL với `ImportError: cannot import name 'nhac_toi'`

- [ ] **Step 4: Cài đặt `nhac_toi`**

Thêm vào `backend/services/artifact_catalog.py`, ngay sau hàm `resolve_code`:

```python
def nhac_toi(text: str, code: str) -> bool:
    """Đoạn text có NHẮC tới loại hồ sơ `code` không (khớp code/label/alias sau chuẩn hoá)?

    Dùng để phân xử luật ↔ nội dung kiểm tra khi metadata chưa đủ (xem evaluate.py::
    `_phan_luat_cho_nd`): "giá phải phù hợp với webform" có nhắc `webform`, "nộp bảng chào giá
    theo Mẫu 05C.1" thì không. `_norm_code` bỏ dấu và MỌI ký tự phân cách nên bắt được cả
    'web form', 'Kết quả mở thầu', 'ket qua mo thau'.
    """
    info = CATALOG.get(code)
    if not info:
        return False
    nt = _norm_code(text)
    if not nt:
        return False
    keys = {_norm_code(code), _norm_code(info["label"])}
    keys |= {_norm_code(a) for a in info["aliases"]}
    return any(k and k in nt for k in keys)
```

- [ ] **Step 5: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_artifact_catalog.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/artifact_catalog.py backend/tests/test_artifact_catalog.py
git commit -m "feat(catalog): nhac_toi() — nhận diện loại hồ sơ được nhắc trong một đoạn văn bản"
```

---

### Task 3: Phân xử luật ↔ nội dung khi có nhiều ứng viên

**Files:**
- Modify: `backend/experiment/evaluate/evaluate.py:116-130` (giữ `_skill_cho_nd`, thêm hàm mới bên dưới), `:190-243` (`evaluate_criterion`)
- Test: `backend/experiment/evaluate/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `artifact_catalog.nhac_toi(text: str, code: str) -> bool` (Task 2); `_norm(s: str) -> str` từ `experiment.evaluate.route`; `RuleSkill` từ `experiment.evaluate.rules.registry` (field `ho_so_can: list[str]`).
- Produces: `_phan_luat_cho_nd(skills: list[RuleSkill], nds: list[dict[str, Any]]) -> dict[int, RuleSkill]` — ánh xạ chỉ số nội dung → luật phục vụ nó.

**Bối cảnh (đọc trước khi sửa):** `_skill_cho_nd` khớp luật với nội dung khi `nd["hsdt_kiem_tra"] ∈ skill.ho_so_can`. Ở gói 54, tiêu chí `Bang_gia_va_phu_hop_webform` có 2 nội dung **cùng** `hsdt_kiem_tra="bang_gia"` (một về mẫu biểu 05C.1, một về đối chiếu giá) nên **cả hai** bị luật `bang_gia_khop_webform` thay thế kết luận. Cách chữa: **không đổi** phép khớp (để tiêu chí 1 nội dung giữ nguyên hành vi, kể cả ca `test_skill_serves_need_routed_to_reference_doc`), chỉ thêm bước phân xử khi từ 2 ứng viên trở lên.

- [ ] **Step 1: Viết 4 test thất bại**

Thêm vào cuối `backend/experiment/evaluate/tests/test_evaluate.py`:

```python
def _crit_54(nd1_extra: dict | None = None, nd2_extra: dict | None = None):
    """Đúng hình dạng tiêu chí gói 54: 1 yêu cầu gốc -> 2 nội dung CÙNG hsdt_kiem_tra='bang_gia'."""
    # Gộp bằng {**a, **b} chứ KHÔNG dùng dict(a, k=v, **b): nd_extra có thể chứa lại 'yeu_cau'
    # -> dict() sẽ nổ TypeError "got multiple values for keyword argument".
    nd1 = {**_nd("Bảng chào giá chi tiết theo Mẫu số 05C.1", "bang_gia"),
           "yeu_cau": "Phải nộp Bảng chào giá chi tiết theo đúng Mẫu số 05C.1 Chương V",
           **(nd1_extra or {})}
    nd2 = {**_nd("Giá dự thầu phù hợp giữa Webform và Bảng giá", "bang_gia"),
           "yeu_cau": "Giá dự thầu trong Bảng chào giá chi tiết phải phù hợp với giá dự thầu "
                      "trên webform",
           **(nd2_extra or {})}
    return {"nhom": "hop_le", "ten": "Bảng giá và phù hợp webform",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [nd1, nd2]}


async def _chay_54(crit, vision):
    return await evaluate_criterion(
        crit, [_page("bang_gia", "bảng chào giá 05C.1 — tổng 48.909.420.000")], vision,
        registry=_reg_gia(KET_QUA_DAT),
        by_type={"bang_gia": [_page("bang_gia", "48.909.420.000")],
                 "webform": [_page("webform", "OSB 48.909.420.000")]})


async def test_phan_xu_tang_2_tu_khoa_chi_noi_dung_nhac_webform_dung_luat():
    """Ca gói 54 với dữ liệu decompose CŨ: chỉ nội dung nhắc webform mới đi qua luật."""
    vision = ScriptedVision({"[EV:Bảng chào giá chi tiết theo Mẫu số 05C.1]":
                             {"ket_qua": "đạt", "bang_chung": "đủ 14 cột"}})
    ce = await _chay_54(_crit_54(), vision)
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT, KET_QUA_DAT]
    # nội dung 1 PHẢI đi eval chung (có call [EV:...]), nội dung 2 PHẢI không
    assert any("[EV:Bảng chào giá chi tiết theo Mẫu số 05C.1]" in hay for hay, _ in vision.calls)
    assert not any("[EV:Giá dự thầu phù hợp giữa Webform và Bảng giá]" in hay
                   for hay, _ in vision.calls)


async def test_phan_xu_tang_1_metadata_thang_tu_khoa():
    """Có hsdt_doi_chieu -> metadata quyết, KHÔNG cần tới từ khóa (nội dung 1 dù nhắc webform)."""
    crit = _crit_54(nd1_extra={"yeu_cau": "Bảng chào giá đúng mẫu 05C.1, đối chiếu webform sau"},
                    nd2_extra={"hsdt_doi_chieu": ["webform"]})
    vision = ScriptedVision({"[EV:Bảng chào giá chi tiết theo Mẫu số 05C.1]":
                             {"ket_qua": "đạt", "bang_chung": "đủ 14 cột"}})
    ce = await _chay_54(crit, vision)
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT, KET_QUA_DAT]
    assert any("[EV:Bảng chào giá chi tiết theo Mẫu số 05C.1]" in hay for hay, _ in vision.calls)
    assert not any("[EV:Giá dự thầu phù hợp giữa Webform và Bảng giá]" in hay
                   for hay, _ in vision.calls)


async def test_phan_xu_tang_3_fail_safe_giu_nguyen_moi_ung_vien():
    """Không phân xử được -> GIỮ hành vi hôm nay (cả hai dùng luật), thà thừa còn hơn mất luật."""
    crit = _crit_54(nd1_extra={"yeu_cau": "Bảng chào giá đúng mẫu"},
                    nd2_extra={"noi_dung_kiem_tra": "Giá dự thầu", "yeu_cau": "Giá phải phù hợp"})
    vision = ScriptedVision({})          # không kịch bản [EV:...] -> eval chung sẽ nổ thành 'lỗi'
    ce = await _chay_54(crit, vision)
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT, KET_QUA_DAT]
    assert vision.calls == []             # cả hai đều đi luật, 0 call eval chung


async def test_mot_noi_dung_duy_nhat_khong_bi_phan_xu():
    """Hồi quy: tiêu chí 1 nội dung -> giữ NGUYÊN hành vi cũ dù không nhắc webform."""
    crit = {"nhom": "hop_le", "ten": "Giá khớp webform",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [_nd("Bảng chào giá đúng mẫu", "bang_gia")]}
    vision = ScriptedVision({})
    ce = await evaluate_criterion(crit, [_page("bang_gia", "1.2 tỷ")], vision,
                                  registry=_reg_gia(KET_QUA_DAT))
    assert ce.ket_qua == KET_QUA_DAT and vision.calls == []
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_evaluate.py -q -k phan_xu`
Expected: FAIL — `test_phan_xu_tang_2_...` và `test_phan_xu_tang_1_...` đỏ vì cả hai nội dung đều đi luật nên `vision.calls` rỗng, `assert any(...)` thất bại. (`test_phan_xu_tang_3_...` và `test_mot_noi_dung_duy_nhat_...` xanh sẵn — chúng khoá hành vi phải GIỮ.)

- [ ] **Step 3: Thêm 3 hàm vào `evaluate.py`**

Thêm ngay dưới `_skill_cho_nd` (giữ nguyên `_skill_cho_nd`, nó vẫn là bước lọc ứng viên):

```python
def _bo_ho_so_nd(nd: dict[str, Any]) -> set[str]:
    """Bộ hồ sơ mà NỘI DUNG này tự khai: hồ sơ chính + tài liệu đối chiếu riêng của nó."""
    bo = {_norm(str(t)) for t in (nd.get("hsdt_doi_chieu") or [])}
    bo.add(_norm(nd.get("hsdt_kiem_tra", "")))
    return bo - {""}


def _nd_nhac_doi_chieu(skill: RuleSkill, nd: dict[str, Any]) -> bool:
    """Nội dung có NHẮC mọi tài liệu đối chiếu của luật (ngoài hồ sơ chính của chính nó) không?"""
    chinh = _norm(nd.get("hsdt_kiem_tra", ""))
    khac = [h for h in skill.ho_so_can if _norm(h) != chinh]
    if not khac:
        return True
    text = f"{nd.get('noi_dung_kiem_tra', '')} {nd.get('yeu_cau', '')}"
    return all(artifact_catalog.nhac_toi(text, str(h)) for h in khac)


def _phan_luat_cho_nd(skills: list[RuleSkill],
                      nds: list[dict[str, Any]]) -> dict[int, RuleSkill]:
    """Chỉ số nội dung -> luật phục vụ nó. Chỉ PHÂN XỬ khi một luật có NHIỀU ứng viên.

    Một yêu cầu gốc của HSMT có thể sinh nhiều nội dung trên CÙNG hồ sơ chính (gói 54: "phải nộp
    Bảng chào giá đúng Mẫu 05C.1" + "giá phải phù hợp webform" đều route tới bang_gia). Khớp theo
    thành viên `ho_so_can` thì cả hai cùng dính luật -> nội dung mẫu biểu bị chấm bằng phép so giá,
    và `thong_tin_bo_sung` (chuẩn 14 cột đã resolve từ HSMT) bị vứt bỏ.

    Chỉ có MỘT ứng viên -> KHÔNG đụng gì, giữ nguyên hành vi (kể cả khi STRUCT chọn hsdt_kiem_tra
    là tài liệu đối chiếu — rơi xuống eval chung thì prompt nuốt webform của MỌI nhà thầu).
    Từ HAI ứng viên -> phân xử 3 tầng: metadata nội dung tự khai -> từ khóa nhắc tài liệu đối
    chiếu -> fail-safe giữ tất cả (thà thừa còn hơn âm thầm mất luật).
    """
    gan: dict[int, RuleSkill] = {}
    for s in skills:
        ung_vien = [i for i, nd in enumerate(nds) if _skill_cho_nd([s], nd) is not None]
        if len(ung_vien) > 1:
            loc = [i for i in ung_vien if set(_norm(h) for h in s.ho_so_can) <= _bo_ho_so_nd(nds[i])]
            if not loc:
                loc = [i for i in ung_vien if _nd_nhac_doi_chieu(s, nds[i])]
            if loc:
                ung_vien = loc
            else:
                log.warning("  [eval] luật %s có %d nội dung ứng viên nhưng không phân xử được — "
                            "giữ tất cả", s.id, len(ung_vien))
        for i in ung_vien:
            gan.setdefault(i, s)
    return gan
```

- [ ] **Step 4: Thêm import `artifact_catalog` vào `evaluate.py`**

Trong khối import đầu file, thêm dòng `from services import artifact_catalog` ngay trước nhóm `from experiment...` (cùng nhóm với các import `services` khác nếu đã có).

- [ ] **Step 5: Dùng `_phan_luat_cho_nd` trong `evaluate_criterion`**

Trong `evaluate_criterion`, ngay sau dòng `skills = registry.matching(crit) if registry is not None else []`, thêm:

```python
    luat_cho_nd = _phan_luat_cho_nd(skills, nds)
```

Rồi trong vòng lặp, thay:

```python
        skill = _skill_cho_nd(skills, nd)
```

bằng:

```python
        skill = luat_cho_nd.get(i)
```

- [ ] **Step 6: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_evaluate.py -q`
Expected: PASS toàn bộ (gồm cả `test_skill_serves_need_routed_to_reference_doc`, `test_rule_only_serves_needs_routed_to_its_primary_doc`, `test_rule_REPLACES_need_verdict_no_generic_eval` — chúng đều là tiêu chí 1 ứng viên nên không bị phân xử).

- [ ] **Step 7: Chạy full suite**

Run: `cd backend && python -m pytest experiment/evaluate/tests -q`
Expected: chỉ 5 test baseline đỏ.

- [ ] **Step 8: Commit**

```bash
git add backend/experiment/evaluate/evaluate.py backend/experiment/evaluate/tests/test_evaluate.py
git commit -m "fix(eval): luật cấp tiêu chí chỉ phục vụ ĐÚNG nội dung cần phép đối chiếu"
```

---

### Task 4: Decompose khai `hsdt_doi_chieu` cho từng nội dung

**Files:**
- Modify: `backend/experiment/decompose/schema.py:58-70` (`NoiDungKiemTra`), `backend/experiment/decompose/prompts.py:50-105` (`SYS_STRUCT`) và schema JSON mẫu ở `prompts.py:159`
- Test: `backend/experiment/decompose/tests/test_routing.py`

**Interfaces:**
- Consumes: `_phan_luat_cho_nd` (Task 3) đọc `nd["hsdt_doi_chieu"]` — tên field phải khớp CHÍNH XÁC.
- Produces: field `hsdt_doi_chieu: list[str] = []` trên mỗi phần tử của `noi_dung_can_kiem_tra` trong output decompose.

- [ ] **Step 1: Xem schema JSON mẫu hiện tại để chèn field đúng chỗ**

Run: `cd backend && sed -n '150,200p' experiment/decompose/prompts.py`
Ghi lại chuỗi mẫu chứa `"noi_dung_can_kiem_tra"` — bước 4 sẽ chèn `"hsdt_doi_chieu":[...]` ngay sau `"hsdt_kiem_tra"`.

- [ ] **Step 2: Viết test thất bại**

Thêm vào cuối `backend/experiment/decompose/tests/test_routing.py`:

```python
def test_noi_dung_co_field_hsdt_doi_chieu():
    """Tài liệu ĐỐI CHIẾU khai ở CẤP NỘI DUNG -> luật biết nội dung nào cần phép đối chiếu."""
    from experiment.decompose.schema import validate_criterion

    out = validate_criterion({
        "ten": "Bảng giá và phù hợp webform",
        "hsdt_can_kiem_tra": ["bang_gia", "webform"],
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Bảng chào giá đúng Mẫu 05C.1", "hsdt_kiem_tra": "bang_gia"},
            {"noi_dung_kiem_tra": "Giá phù hợp webform", "hsdt_kiem_tra": "bang_gia",
             "hsdt_doi_chieu": ["webform"]},
        ],
    })
    nds = out["noi_dung_can_kiem_tra"]
    assert nds[0]["hsdt_doi_chieu"] == []          # mặc định rỗng, tương thích dữ liệu cũ
    assert nds[1]["hsdt_doi_chieu"] == ["webform"]


def test_sys_struct_day_khai_hsdt_doi_chieu():
    from experiment.decompose.prompts import SYS_STRUCT

    assert "hsdt_doi_chieu" in SYS_STRUCT
    assert "webform" in SYS_STRUCT                 # có ví dụ cụ thể, không chỉ nêu tên field
```

- [ ] **Step 3: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/decompose/tests/test_routing.py -q -k hsdt_doi_chieu`
Expected: FAIL với `KeyError: 'hsdt_doi_chieu'` và `assert 'hsdt_doi_chieu' in SYS_STRUCT`

- [ ] **Step 4: Thêm field vào `NoiDungKiemTra`**

Trong `backend/experiment/decompose/schema.py`, thêm dòng ngay sau `hsdt_kiem_tra`:

```python
    hsdt_doi_chieu: list[str] = []   # tài liệu ĐỐI CHIẾU riêng cho nội dung này (ngoài hồ sơ chính)
```

- [ ] **Step 5: Dạy `SYS_STRUCT` khai field mới**

Trong `backend/experiment/decompose/prompts.py`, thêm gạch đầu dòng ngay sau đoạn mô tả `hsdt_kiem_tra` (đoạn kết thúc bằng `"(chấm bảng giá của nhà thầu), KHÔNG phải 'webform'.\n"`):

```python
    "- hsdt_doi_chieu: các loại hồ sơ KHÁC (chọn trong hsdt_can_kiem_tra của tiêu chí) mà RIÊNG "
    "nội dung này phải đem ra so sánh mới kết luận được. Nội dung chỉ cần đọc hồ sơ chính -> để "
    "MẢNG RỖNG. Ví dụ MỘT yêu cầu gốc sinh hai nội dung cùng nằm trên bang_gia: 'phải nộp Bảng "
    "chào giá theo đúng Mẫu số 05C.1' -> hsdt_doi_chieu=[] (chỉ soi mẫu biểu); 'giá trong Bảng "
    "chào giá phải phù hợp giá trên webform' -> hsdt_doi_chieu=['webform'] (phải so hai tài "
    "liệu). Khai đúng field này quyết định nội dung nào được chấm bằng phép đối chiếu chuyên "
    "dụng — khai thừa sẽ làm nội dung soi mẫu biểu bị chấm nhầm bằng phép so giá.\n"
```

- [ ] **Step 6: Thêm field vào schema JSON mẫu**

Trong cùng file, tại chuỗi mẫu `'{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...],'` (dòng ~159) và mọi chỗ liệt kê khoá của một nội dung, chèn `"hsdt_doi_chieu":[...],` ngay sau `"hsdt_kiem_tra"`. Dùng lệnh này để tìm hết các chỗ cần sửa:

Run: `cd backend && grep -n 'hsdt_kiem_tra' experiment/decompose/prompts.py`

- [ ] **Step 7: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/decompose/tests -q`
Expected: PASS toàn bộ.

- [ ] **Step 8: Commit**

```bash
git add backend/experiment/decompose/schema.py backend/experiment/decompose/prompts.py backend/experiment/decompose/tests/test_routing.py
git commit -m "feat(decompose): khai tài liệu đối chiếu ở CẤP NỘI DUNG (hsdt_doi_chieu)"
```

---

### Task 5: Liên danh — hàm thuần đối chiếu chữ ký đơn ↔ thỏa thuận liên danh

**Files:**
- Modify: `backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py` (thêm hằng, 2 model, 1 dataclass, 2 hàm thuần — chưa đụng `handler`)
- Create: `backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py`

**Interfaces:**
- Consumes: `_norm` từ `experiment.evaluate.route`; `khop_phap_nhan(ten_don: str, ten_kia: str, llm_noi_khop: bool) -> bool | None` (đã có trong file, dòng 178); `_Base`, hằng `KET_QUA_*` từ `experiment.evaluate.schema`.
- Produces:
  - `_TTLD = "thoa_thuan_lien_danh"`
  - `class ChuKyLech` (frozen dataclass): `.phap_nhan: str`, `.nguoi_ky: str`, `.nguoi_dai_dien: str`
  - `doi_chieu_chu_ky_lien_danh(d: dict[str, Any]) -> tuple[str, str, str, list[ChuKyLech]]` → `(ket_qua, bang_chung, ghi_chu, lech)`; `ket_qua == ""` nghĩa là CHƯA kết luận, phải xét ủy quyền cho `lech`.
  - `ket_luan_uy_quyen_lien_danh(lech: list[ChuKyLech], muc: list[dict[str, Any]]) -> tuple[str, str]` → `(ket_qua, ghi_chu)`
  - `validate_lien_danh_ky(d)`, `validate_uy_quyen_lien_danh(d)` (Task 6/7 dùng)

**Bối cảnh nghiệp vụ:** đơn dự thầu của nhà thầu liên danh hợp lệ theo **một trong hai** cách: (A) thành viên đứng đầu ký thay mặt liên danh — một khối chữ ký; (B) tất cả thành viên cùng ký — mỗi thành viên một khối. Người ký mỗi khối phải là đại diện của **chính** thành viên đó theo TTLD; lệch thì phải có giấy ủy quyền do **chính thành viên đó** cấp, đúng người, đúng phạm vi.

- [ ] **Step 1: Viết test thất bại cho `doi_chieu_chu_ky_lien_danh`**

Tạo `backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py`:

```python
"""Nhánh LIÊN DANH của luật chữ ký đơn dự thầu: neo vào THỎA THUẬN LIÊN DANH, không phải ĐKKD."""
from experiment.evaluate.rules.chu_ky_khop_dkkd import (
    ChuKyLech, doi_chieu_chu_ky_lien_danh, ket_luan_uy_quyen_lien_danh,
)
from experiment.evaluate.schema import KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI

_OSB = "CÔNG TY CỔ PHẦN TẬP ĐOÀN OSB"
_OHT = "CÔNG TY TNHH CÔNG NGHỆ CAO OSB"


def _tv(ten, dai_dien, dung_dau=False):
    return {"ten_phap_nhan": ten, "nguoi_dai_dien": dai_dien, "la_dung_dau": dung_dau}


def _ck(phap_nhan, nguoi_ky, thanh_vien_ttld=""):
    return {"phap_nhan": phap_nhan, "nguoi_ky": nguoi_ky,
            "thanh_vien_ttld": thanh_vien_ttld or phap_nhan}


def test_dung_dau_ky_thay_mat_lien_danh_dung_nguoi_thi_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")]})
    assert kq == KET_QUA_DAT and lech == []
    assert "đứng đầu" in gc and "Nguyễn Hồng Sơn" in bc


def test_tat_ca_thanh_vien_cung_ky_dung_nguoi_thi_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn"), _ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_DAT and lech == []
    assert "tất cả thành viên" in gc


def test_ky_mot_phan_thi_khong_dat_va_neu_ten_thanh_vien_thieu():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường"),
                       _tv("CÔNG TY ABC", "Lê Văn C")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn"), _ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_KHONG and lech == []
    assert "CÔNG TY ABC" in gc


def test_chi_thanh_vien_khong_dung_dau_ky_thi_khong_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_KHONG and lech == []
    assert "đứng đầu" in gc


def test_phap_nhan_ky_khong_co_trong_ttld_thi_khong_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "CÔNG TY LẠ", "nguoi_ky": "X", "thanh_vien_ttld": ""}]})
    assert kq == KET_QUA_KHONG and "CÔNG TY LẠ" in gc


def test_llm_bo_trong_thanh_vien_ttld_van_khop_khi_ten_chuan_hoa_bang_nhau():
    """Guard MỘT CHIỀU: LLM không gán thì code tự so tên chuẩn hoá (hoa/thường/dấu)."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv("Công ty cổ phần Tập đoàn OSB", "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "CÔNG TY CỔ PHẦN TẬP ĐOÀN OSB", "nguoi_ky": "Nguyễn Hồng Sơn",
                    "thanh_vien_ttld": ""}]})
    assert kq == KET_QUA_DAT


def test_nguoi_ky_lech_dai_dien_thi_chua_ket_luan_va_tra_ve_lech():
    """Ca OSB gói 54: đơn đứng tên thành viên đứng đầu nhưng người ký là đại diện thành viên kia."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Trần Vũ Thường")]})
    assert kq == ""                                  # CHƯA kết luận -> phải xét ủy quyền
    assert lech == [ChuKyLech(phap_nhan=_OSB, nguoi_ky="Trần Vũ Thường",
                              nguoi_dai_dien="Nguyễn Hồng Sơn")]


def test_thieu_can_cu_thi_soi_khong_doan():
    assert doi_chieu_chu_ky_lien_danh({"thanh_vien": [], "chu_ky": [_ck(_OSB, "A")]})[0] == KET_QUA_SOI
    assert doi_chieu_chu_ky_lien_danh(
        {"thanh_vien": [_tv(_OSB, "A", dung_dau=True)], "chu_ky": []})[0] == KET_QUA_SOI
    # không đọc được tên người ký
    assert doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "A", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "")]})[0] == KET_QUA_SOI
    # TTLD không nêu thành viên đứng đầu, mà cũng không phải mọi thành viên cùng ký
    assert doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "A"), _tv(_OHT, "B")],
        "chu_ky": [_ck(_OSB, "A")]})[0] == KET_QUA_SOI
```

- [ ] **Step 2: Viết test thất bại cho `ket_luan_uy_quyen_lien_danh`**

Thêm tiếp vào cùng file:

```python
def _muc(phap_nhan, **kw):
    m = {"phap_nhan": phap_nhan, "nguoi_uy_quyen": "Nguyễn Hồng Sơn",
         "nguoi_duoc_uy_quyen": "Trần Vũ Thường", "phap_nhan_uy_quyen": phap_nhan,
         "phap_nhan_khop": True, "dung_nguoi": True, "dung_pham_vi": True, "ghi_chu": ""}
    m.update(kw)
    return m


_LECH = [ChuKyLech(phap_nhan=_OSB, nguoi_ky="Trần Vũ Thường",
                   nguoi_dai_dien="Nguyễn Hồng Sơn")]


def test_uy_quyen_du_ba_dieu_kien_thi_dat():
    assert ket_luan_uy_quyen_lien_danh(_LECH, [_muc(_OSB)]) == (KET_QUA_DAT, "")


def test_uy_quyen_tu_phap_nhan_khac_thi_khong_dat():
    """Ca OSB gói 54: GUQ do thành viên KHÁC (không phải thành viên đứng tên khối chữ ký) cấp."""
    kq, gc = ket_luan_uy_quyen_lien_danh(
        _LECH, [_muc(_OSB, phap_nhan_uy_quyen=_OHT, phap_nhan_khop=False)])
    assert kq == KET_QUA_KHONG and _OHT in gc and "vô hiệu" in gc


def test_khong_co_muc_uy_quyen_cho_chu_ky_lech_thi_khong_dat():
    kq, gc = ket_luan_uy_quyen_lien_danh(_LECH, [])
    assert kq == KET_QUA_KHONG and "không có giấy ủy quyền" in gc


def test_sai_nguoi_hoac_sai_pham_vi_thi_khong_dat():
    kq1, gc1 = ket_luan_uy_quyen_lien_danh(
        _LECH, [_muc(_OSB, dung_nguoi=False, nguoi_duoc_uy_quyen="Lê Văn X")])
    assert kq1 == KET_QUA_KHONG and "Lê Văn X" in gc1
    kq2, gc2 = ket_luan_uy_quyen_lien_danh(_LECH, [_muc(_OSB, dung_pham_vi=False)])
    assert kq2 == KET_QUA_KHONG and "phạm vi" in gc2


def test_khong_doc_duoc_ten_ben_uy_quyen_thi_soi():
    kq, gc = ket_luan_uy_quyen_lien_danh(_LECH, [_muc(_OSB, phap_nhan_uy_quyen="")])
    assert kq == KET_QUA_SOI and "không đọc được" in gc
```

- [ ] **Step 3: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py -q`
Expected: FAIL với `ImportError: cannot import name 'ChuKyLech'`

- [ ] **Step 4: Thêm hằng, model và dataclass vào `chu_ky_khop_dkkd.py`**

Thêm `from dataclasses import dataclass` vào đầu file. Thêm hằng cạnh `_GUQ` (dòng ~49):

```python
_TTLD = "thoa_thuan_lien_danh"   # hồ sơ TÙY CHỌN — có thì nhà thầu là LIÊN DANH, đổi hẳn cách kiểm
_TEN_LD = "Người ký đơn dự thầu đúng đại diện liên danh (thỏa thuận liên danh)"
```

Thêm model + dataclass sau `class UyQuyenOut` (dòng ~128):

```python
class ThanhVienLienDanh(_Base):
    ten_phap_nhan: str = ""
    nguoi_dai_dien: str = ""      # đại diện của CHÍNH thành viên đó, ghi trong thỏa thuận liên danh
    la_dung_dau: bool = False


class KhoiChuKy(_Base):
    phap_nhan: str = ""           # pháp nhân đứng tên khối chữ ký trên đơn
    nguoi_ky: str = ""
    thanh_vien_ttld: str = ""     # LLM gán khối này về thành viên nào trong TTLD; '' = không thuộc ai


class LienDanhKyOut(_Base):
    thanh_vien: list[ThanhVienLienDanh] = []
    chu_ky: list[KhoiChuKy] = []
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


class MucUyQuyenLienDanh(_Base):
    phap_nhan: str = ""           # thành viên liên danh của khối chữ ký đang xét
    nguoi_uy_quyen: str = ""
    nguoi_duoc_uy_quyen: str = ""
    phap_nhan_uy_quyen: str = ""  # BÊN ỦY QUYỀN ghi trong giấy ủy quyền
    phap_nhan_khop: bool = False
    dung_nguoi: bool = False      # người được ủy quyền = người đã ký đơn?
    dung_pham_vi: bool = False    # phạm vi ủy quyền gồm việc ký đơn dự thầu?
    ghi_chu: str = ""


class UyQuyenLienDanhOut(_Base):
    muc: list[MucUyQuyenLienDanh] = []
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


@dataclass(frozen=True)
class ChuKyLech:
    """Khối chữ ký mà người ký KHÁC đại diện của thành viên đó theo TTLD -> phải xét ủy quyền."""
    phap_nhan: str        # tên thành viên liên danh (theo TTLD)
    nguoi_ky: str         # người đã ký trên đơn
    nguoi_dai_dien: str   # đại diện của thành viên đó theo TTLD


def validate_lien_danh_ky(d: dict[str, Any]) -> dict[str, Any]:
    return LienDanhKyOut(**d).model_dump()


def validate_uy_quyen_lien_danh(d: dict[str, Any]) -> dict[str, Any]:
    return UyQuyenLienDanhOut(**d).model_dump()
```

- [ ] **Step 5: Cài đặt `doi_chieu_chu_ky_lien_danh` (hàm THUẦN)**

Thêm sau `khop_phap_nhan` (dòng ~188):

```python
def _tra_thanh_vien(tvs: list[dict[str, Any]], ck: dict[str, Any]) -> dict[str, Any] | None:
    """Khối chữ ký -> thành viên trong TTLD. None = pháp nhân KHÔNG có trong thỏa thuận.

    Ưu tiên phần gán của LLM (`thanh_vien_ttld`), sau đó so tên chuẩn hoá — cùng tinh thần guard
    MỘT CHIỀU của `khop_phap_nhan`: LLM bỏ trống mà hai tên chuẩn hoá bằng nhau thì tin code.
    """
    for khoa in (ck.get("thanh_vien_ttld", ""), ck.get("phap_nhan", "")):
        k = _norm(str(khoa)).strip()
        if not k:
            continue
        for tv in tvs:
            if _norm(str(tv.get("ten_phap_nhan", ""))).strip() == k:
                return tv
    return None


def _dong_chu_ky(ck: dict[str, Any], tv: dict[str, Any] | None) -> str:
    return (f"{ck.get('phap_nhan') or '(không rõ pháp nhân)'} — ký bởi "
            f"{ck.get('nguoi_ky') or '(không rõ)'}; thỏa thuận liên danh ghi đại diện là "
            f"{(tv or {}).get('nguoi_dai_dien') or '(không rõ)'}")


def doi_chieu_chu_ky_lien_danh(
        d: dict[str, Any]) -> tuple[str, str, str, list[ChuKyLech]]:
    """Dữ liệu đã bóc -> (ket_qua, bang_chung, ghi_chu, lech). Hàm THUẦN: mọi phán quyết ở đây.

    ket_qua = '' nghĩa là CHƯA kết luận được: có khối chữ ký lệch người, phải xét giấy ủy quyền
    cho danh sách `lech`. Hai hình thức ký hợp lệ của nhà thầu liên danh: thành viên đứng đầu ký
    thay mặt liên danh, HOẶC tất cả thành viên cùng ký.
    """
    tvs = [tv for tv in (d.get("thanh_vien") or [])
           if str(tv.get("ten_phap_nhan", "")).strip()]
    cks = list(d.get("chu_ky") or [])
    if not tvs:
        return KET_QUA_SOI, "", "không bóc được thành viên nào trong thỏa thuận liên danh", []
    if not cks:
        return KET_QUA_SOI, "", "không bóc được khối chữ ký nào trên đơn dự thầu", []

    cap = [(ck, _tra_thanh_vien(tvs, ck)) for ck in cks]
    bang_chung = "; ".join(_dong_chu_ky(ck, tv) for ck, tv in cap)

    la = [str(ck.get("phap_nhan") or "(không rõ)") for ck, tv in cap if tv is None]
    if la:
        return (KET_QUA_KHONG, bang_chung,
                f"đơn dự thầu có chữ ký đứng tên pháp nhân KHÔNG có trong thỏa thuận liên danh: "
                f"{', '.join(la)}", [])

    ten_ky = {_norm(str(tv.get("ten_phap_nhan", ""))) for _, tv in cap}
    ten_tv = {_norm(str(tv.get("ten_phap_nhan", ""))) for tv in tvs}
    dd = next((tv for tv in tvs if tv.get("la_dung_dau")), None)

    if ten_ky == ten_tv:
        hinh_thuc = "tất cả thành viên liên danh cùng ký"
    elif dd is None:
        return (KET_QUA_SOI, bang_chung,
                "thỏa thuận liên danh không nêu rõ thành viên đứng đầu — chưa đối chiếu được thẩm "
                "quyền ký đơn", [])
    elif ten_ky == {_norm(str(dd.get("ten_phap_nhan", "")))}:
        hinh_thuc = f"thành viên đứng đầu ({dd.get('ten_phap_nhan')}) ký thay mặt liên danh"
    else:
        thieu = [str(tv.get("ten_phap_nhan", "")) for tv in tvs
                 if _norm(str(tv.get("ten_phap_nhan", ""))) not in ten_ky]
        return (KET_QUA_KHONG, bang_chung,
                f"đơn dự thầu không do thành viên đứng đầu ({dd.get('ten_phap_nhan')}) ký thay mặt "
                f"liên danh, mà cũng không đủ chữ ký của mọi thành viên — thiếu chữ ký của: "
                f"{', '.join(thieu)}", [])

    if any(not str(ck.get("nguoi_ky", "")).strip()
           or not str((tv or {}).get("nguoi_dai_dien", "")).strip() for ck, tv in cap):
        return (KET_QUA_SOI, bang_chung,
                "không đọc được tên người ký trên đơn và/hoặc tên đại diện trong thỏa thuận liên "
                "danh — chưa đối chiếu được", [])

    lech = [ChuKyLech(phap_nhan=str(tv.get("ten_phap_nhan", "")),
                      nguoi_ky=str(ck.get("nguoi_ky", "")),
                      nguoi_dai_dien=str(tv.get("nguoi_dai_dien", "")))
            for ck, tv in cap
            if _norm(str(ck.get("nguoi_ky", ""))) != _norm(str(tv.get("nguoi_dai_dien", "")))]
    if lech:
        return "", bang_chung, "", lech
    return KET_QUA_DAT, bang_chung, f"đơn dự thầu hợp lệ theo hình thức: {hinh_thuc}", []
```

- [ ] **Step 6: Cài đặt `ket_luan_uy_quyen_lien_danh` (hàm THUẦN)**

Thêm ngay sau hàm trên:

```python
def ket_luan_uy_quyen_lien_danh(lech: list[ChuKyLech],
                                muc: list[dict[str, Any]]) -> tuple[str, str]:
    """(chữ ký lệch, mục ủy quyền đã bóc) -> (ket_qua, ghi_chu). Hàm THUẦN.

    MỖI khối chữ ký lệch phải có một mục ủy quyền thỏa CẢ BA: bên ủy quyền đúng là thành viên
    liên danh mà khối chữ ký đó đứng tên; người được ủy quyền đúng là người ký đơn; phạm vi bao
    gồm việc ký đơn dự thầu. Ủy quyền từ thành viên KHÁC là vô hiệu dù đúng người, đúng phạm vi.
    """
    theo_ten = {_norm(str(m.get("phap_nhan", ""))): m for m in muc}
    loi: list[str] = []
    soi: list[str] = []
    for l in lech:
        m = theo_ten.get(_norm(l.phap_nhan))
        if m is None:
            loi.append(f"{l.phap_nhan}: không có giấy ủy quyền cho người ký {l.nguoi_ky}")
            continue
        khop = khop_phap_nhan(l.phap_nhan, str(m.get("phap_nhan_uy_quyen", "")),
                              bool(m.get("phap_nhan_khop")))
        if khop is None:
            soi.append(f"{l.phap_nhan}: không đọc được tên pháp nhân bên ủy quyền")
            continue
        if not khop:
            loi.append(f"{l.phap_nhan}: giấy ủy quyền do pháp nhân KHÁC cấp "
                       f"({m.get('phap_nhan_uy_quyen') or '?'}), không phải thành viên liên danh "
                       f"đứng tên khối chữ ký này — ủy quyền vô hiệu")
            continue
        if not m.get("dung_nguoi"):
            loi.append(f"{l.phap_nhan}: người được ủy quyền "
                       f"({m.get('nguoi_duoc_uy_quyen') or '?'}) không phải người ký đơn "
                       f"({l.nguoi_ky})")
            continue
        if not m.get("dung_pham_vi"):
            loi.append(f"{l.phap_nhan}: phạm vi ủy quyền không bao gồm việc ký đơn dự thầu")
    if loi:
        return KET_QUA_KHONG, "; ".join(loi)
    if soi:
        return KET_QUA_SOI, "; ".join(soi)
    return KET_QUA_DAT, ""
```

- [ ] **Step 7: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 8: Commit**

```bash
git add backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py
git commit -m "feat(rule): hàm thuần đối chiếu chữ ký đơn dự thầu với thỏa thuận liên danh"
```

---

### Task 6: Liên danh — prompt bóc dữ liệu + rẽ nhánh trong `handler`

**Files:**
- Modify: `backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py` (2 hằng prompt, 1 hàm dựng prompt, `_verdict_ld`, `_xet_lien_danh`, rẽ nhánh trong `handler`, docstring module)
- Test: `backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py`

**Interfaces:**
- Consumes: `doi_chieu_chu_ky_lien_danh`, `validate_lien_danh_ky`, `_TTLD`, `_TEN_LD`, `ChuKyLech` (Task 5); `pages_text` từ `experiment.evaluate.route`; `cot_block` từ `services.prompts`; `_QUY_TAC_PHAP_NHAN` (đã có, dòng 53).
- Produces:
  - `SYS_RULE_LIEN_DANH_KY: str`, `lien_danh_ky_prompt(don_text: str, ttld_text: str) -> str` (marker `[RULE:chu_ky_lien_danh]`)
  - `_verdict_ld(ket_qua, bang_chung="", trang=None, do_tin=0.0, ghi_chu="", nguon_doc=None) -> Verdict`
  - `_xet_lien_danh(by_type, vision_fn) -> Verdict` — Task 7 nối bước 2 vào cuối hàm này.

- [ ] **Step 1: Viết test thất bại**

Gộp 3 dòng import dưới đây vào **khối import đầu file** (đừng để import giữa file), rồi thêm phần còn lại vào cuối `test_rules_chu_ky_lien_danh.py`:

```python
from experiment.evaluate.rules.chu_ky_khop_dkkd import SKILL, SYS_RULE_LIEN_DANH_KY, lien_danh_ky_prompt
from experiment.evaluate.schema import KET_QUA_LOI, KET_QUA_THIEU, PageRecord
from experiment.evaluate.vision import ScriptedVision


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


_BT_LD = {
    "don_du_thau": [_p(1, "don_du_thau", "ĐẠI DIỆN HỢP PHÁP CỦA NHÀ THẦU LIÊN DANH ...")],
    "thoa_thuan_lien_danh": [_p(1, "thoa_thuan_lien_danh", "Thành viên đứng đầu: ...")],
}


def test_prompt_lien_danh_co_marker_va_ca_hai_tai_lieu():
    p = lien_danh_ky_prompt("ĐƠN: ký bởi Trần Vũ Thường", "TTLD: đứng đầu là Tập đoàn OSB")
    assert "[RULE:chu_ky_lien_danh]" in p
    assert "ĐƠN: ký bởi Trần Vũ Thường" in p and "TTLD: đứng đầu là Tập đoàn OSB" in p
    assert "KHÔNG bịa" in SYS_RULE_LIEN_DANH_KY
    assert "thanh_vien_ttld" in SYS_RULE_LIEN_DANH_KY


async def test_co_ttld_thi_KHONG_doc_dkkd():
    """MẤU CHỐT: có thỏa thuận liên danh -> neo vào TTLD, tuyệt đối không đụng ĐKKD."""
    by_type = dict(_BT_LD, dang_ky_kinh_doanh=[_p(1, "dang_ky_kinh_doanh", "đại diện: Lê Văn X")])
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": {
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")], "trang": [1], "do_tin": 0.9}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT
    assert verdict.noi_dung_kiem_tra == "Người ký đơn dự thầu đúng đại diện liên danh (thỏa thuận liên danh)"
    assert verdict.nguon_doc == ["don_du_thau", "thoa_thuan_lien_danh"]
    assert len(v.calls) == 1                                  # 1 call duy nhất
    assert "[RULE:chu_ky_khop_dkkd]" not in v.calls[0][0]     # KHÔNG hề gọi nhánh ĐKKD
    assert v.calls[0][1] == 0                                 # text-only, không đính ảnh


async def test_khong_co_ttld_thi_giu_nhanh_dkkd_cu():
    """Hồi quy: nhà thầu độc lập vẫn đi nhánh ĐKKD như trước."""
    by_type = {
        "don_du_thau": [_p(1, "don_du_thau", "Người ký: Nguyễn Văn A")],
        "dang_ky_kinh_doanh": [_p(1, "dang_ky_kinh_doanh", "đại diện: Nguyễn Văn A")],
    }
    v = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {
        "ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A", "dai_dien_phap_luat": "Nguyễn Văn A",
        "nha_thau_don": "Công ty ABC", "doanh_nghiep_dkkd": "Công ty ABC", "phap_nhan_khop": True}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT
    assert verdict.nguon_doc == ["don_du_thau", "dang_ky_kinh_doanh"]


async def test_thieu_don_du_thau_van_thieu_ho_so_du_co_ttld():
    v = ScriptedVision({})
    verdict = await SKILL.handler({"thoa_thuan_lien_danh": _BT_LD["thoa_thuan_lien_danh"]},
                                  None, {}, v)
    assert verdict.ket_qua == KET_QUA_THIEU and v.calls == []


async def test_ai_loi_thi_verdict_loi_khong_bia():
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": RuntimeError("proxy hỏng")})
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_LOI and "proxy hỏng" in verdict.bang_chung


async def test_ky_mot_phan_ra_khong_dat_chi_mot_call():
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": {
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OHT, "Trần Vũ Thường")], "trang": [1]}})
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_KHONG and len(v.calls) == 1
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py -q`
Expected: FAIL với `ImportError: cannot import name 'SYS_RULE_LIEN_DANH_KY'`

- [ ] **Step 3: Thêm system prompt + hàm dựng prompt**

Thêm sau `SYS_RULE_UY_QUYEN_KHONG_DKKD` (dòng ~102):

```python
SYS_RULE_LIEN_DANH_KY = (
    "Bạn là chuyên gia chấm thầu. Nhà thầu dự thầu theo hình thức LIÊN DANH. Đọc THỎA THUẬN LIÊN "
    "DANH và ĐƠN DỰ THẦU rồi BÓC DỮ LIỆU (KHÔNG tính toán, KHÔNG kết luận đạt/không đạt — phần đó "
    "hệ thống tự làm):\n"
    "- thanh_vien: mỗi thành viên trong thỏa thuận liên danh gồm ten_phap_nhan (tên pháp nhân "
    "NGUYÊN VĂN), nguoi_dai_dien (người đại diện của CHÍNH thành viên đó ghi trong thỏa thuận), "
    "la_dung_dau = true nếu thỏa thuận ghi đây là THÀNH VIÊN ĐỨNG ĐẦU liên danh.\n"
    "- chu_ky: mỗi KHỐI CHỮ KÝ ở cuối đơn dự thầu gồm phap_nhan (pháp nhân đứng tên khối chữ ký "
    "đó), nguoi_ky (người đã ký), thanh_vien_ttld = chép ĐÚNG ten_phap_nhan của thành viên trong "
    "danh sách thanh_vien ở trên mà khối chữ ký này thuộc về; để RỖNG nếu khối chữ ký không thuộc "
    "thành viên nào. Đơn ghi 'ĐẠI DIỆN HỢP PHÁP CỦA NHÀ THẦU LIÊN DANH — <tên công ty>' thì đó là "
    "MỘT khối chữ ký đứng tên công ty đó.\n"
    + _QUY_TAC_PHAP_NHAN +
    "Không đọc được thì để chuỗi rỗng, TUYỆT ĐỐI KHÔNG bịa tên người hay tên công ty, KHÔNG suy "
    "đoán ai là thành viên đứng đầu khi thỏa thuận không ghi. bang_chung: trích nguyên văn phần "
    "chữ ký trên đơn và phần nêu thành viên/đại diện/thành viên đứng đầu trong thỏa thuận, kèm số "
    "trang. Chỉ trả JSON."
)


def lien_danh_ky_prompt(don_text: str, ttld_text: str) -> str:
    return (
        "[RULE:chu_ky_lien_danh]\n"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text}\n\n"
        f"THỎA THUẬN LIÊN DANH (bóc từ ảnh):\n{ttld_text}\n\n"
        + cot_block('{"thanh_vien":[{"ten_phap_nhan":"...","nguoi_dai_dien":"...",'
                    '"la_dung_dau":true}],"chu_ky":[{"phap_nhan":"...","nguoi_ky":"...",'
                    '"thanh_vien_ttld":"..."}],"bang_chung":"<trích 2 phía>","trang":[...],'
                    '"do_tin":0.0,"ghi_chu":""}')
    )
```

- [ ] **Step 4: Thêm `_verdict_ld` và `_xet_lien_danh`**

Thêm sau `_verdict` (dòng ~214):

```python
def _verdict_ld(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
                do_tin: float = 0.0, ghi_chu: str = "",
                nguon_doc: list[str] | None = None) -> Verdict:
    """Verdict nhánh LIÊN DANH — nhãn và nguồn KHÁC hẳn nhánh ĐKKD.

    Không trộn nhãn ĐKKD vào đây: báo cáo không được nói là đã đối chiếu ĐKKD trong khi nhánh này
    không hề đọc ĐKKD.
    """
    return Verdict(noi_dung_kiem_tra=_TEN_LD, hsdt_kiem_tra=_DON,
                   yeu_cau=("Đơn dự thầu của nhà thầu liên danh phải do thành viên đứng đầu ký "
                            "thay mặt liên danh hoặc do tất cả thành viên cùng ký, đúng đại diện "
                            "nêu trong thỏa thuận liên danh hoặc người được ủy quyền hợp lệ"),
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
                   nguon_doc=nguon_doc or [_DON, _TTLD])


async def _xet_lien_danh(by_type: dict[str, list[PageRecord]], vision_fn: Any) -> Verdict:
    """Nhà thầu LIÊN DANH: thẩm quyền ký đơn neo vào THỎA THUẬN LIÊN DANH, KHÔNG đọc ĐKKD.

    Bước 1 (1 call): LLM bóc thành viên + đại diện (TTLD) và các khối chữ ký (đơn);
    `doi_chieu_chu_ky_lien_danh` phán quyết. Còn chữ ký lệch người -> bước 2 xét giấy ủy quyền.
    """
    out = await vision_fn(SYS_RULE_LIEN_DANH_KY,
                          lien_danh_ky_prompt(pages_text(by_type[_DON]),
                                              pages_text(by_type[_TTLD])),
                          validate=validate_lien_danh_ky, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict_ld(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    trang = [int(t) for t in d.get("trang", []) if str(t).isdigit()]
    do_tin = float(d.get("do_tin", 0.0) or 0.0)
    ket_qua, bang_chung, ghi_chu, lech = doi_chieu_chu_ky_lien_danh(d)
    bang_chung = bang_chung or d.get("bang_chung", "")
    if ket_qua:
        return _verdict_ld(ket_qua, bang_chung=bang_chung, trang=trang, do_tin=do_tin,
                           ghi_chu=ghi_chu)
    return _verdict_ld(KET_QUA_SOI, bang_chung=bang_chung, trang=trang, do_tin=do_tin,
                       ghi_chu="người ký đơn khác đại diện nêu trong thỏa thuận liên danh")
```

(Nhánh cuối là tạm — Task 7 thay bằng lời gọi `_xet_uy_quyen_lien_danh`.)

- [ ] **Step 5: Rẽ nhánh trong `handler`**

Trong `handler`, ngay sau khối `if not by_type.get(_DON): ...` và **trước** khối `if not by_type.get(_DKKD): ...`, chèn:

```python
    if by_type.get(_TTLD):
        # Nhà thầu LIÊN DANH: văn bản quyết định ai được ký đơn là THỎA THUẬN LIÊN DANH, không
        # phải ĐKKD. Dùng SỰ CÓ MẶT của hồ sơ làm tín hiệu — cùng căn cứ vendor_profile dùng để
        # kết luận hình thức, nên không lệch với hình thức in trên báo cáo.
        return await _xet_lien_danh(by_type, vision_fn)
```

- [ ] **Step 6: Cập nhật docstring module**

Thêm khối này vào docstring đầu `chu_ky_khop_dkkd.py`, ngay trước đoạn "PHÁP NHÂN (kiểm TRƯỚC tên người)":

```
LIÊN DANH (rẽ nhánh ở CODE theo sự có mặt của thoa_thuan_lien_danh): với nhà thầu liên danh,
văn bản quyết định thẩm quyền ký đơn là THỎA THUẬN LIÊN DANH chứ không phải ĐKKD — nhánh này
KHÔNG đọc ĐKKD. Đơn hợp lệ theo MỘT trong hai cách: thành viên đứng đầu ký thay mặt liên danh,
hoặc TẤT CẢ thành viên cùng ký; mỗi khối chữ ký phải do đại diện của CHÍNH thành viên đó (theo
thỏa thuận) ký, lệch thì xét giấy ủy quyền do CHÍNH thành viên đó cấp, đúng người, đúng phạm vi.
```

- [ ] **Step 7: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py experiment/evaluate/tests/test_rules_chu_ky.py -q`
Expected: PASS toàn bộ (test nhánh ĐKKD cũ không được sửa dòng nào).

- [ ] **Step 8: Commit**

```bash
git add backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py
git commit -m "feat(rule): nhà thầu liên danh đối chiếu chữ ký đơn với thỏa thuận liên danh, bỏ ĐKKD"
```

---

### Task 7: Liên danh — bước 2 thẩm định giấy ủy quyền

**Files:**
- Modify: `backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py` (thêm `SYS_RULE_UY_QUYEN_LIEN_DANH`, `uy_quyen_lien_danh_prompt`, `_xet_uy_quyen_lien_danh`; nối vào `_xet_lien_danh`)
- Test: `backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py`

**Interfaces:**
- Consumes: `ket_luan_uy_quyen_lien_danh`, `validate_uy_quyen_lien_danh`, `ChuKyLech`, `_verdict_ld`, `_GUQ` (đã có, dòng 49)
- Produces: `SYS_RULE_UY_QUYEN_LIEN_DANH: str`, `uy_quyen_lien_danh_prompt(guq_text: str, lech: list[ChuKyLech]) -> str` (marker `[RULE:chu_ky_lien_danh_uy_quyen]`), `_xet_uy_quyen_lien_danh(by_type, vision_fn, lech, bang_chung_1, trang_1) -> Verdict`

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `test_rules_chu_ky_lien_danh.py`:

```python
_KB_LECH = {"[RULE:chu_ky_lien_danh]": {
    "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
    "chu_ky": [_ck(_OSB, "Trần Vũ Thường")], "trang": [1], "do_tin": 0.9}}


async def test_ca_that_goi_54_uy_quyen_tu_thanh_vien_khac_thi_khong_dat():
    """Ca OSB gói 54: đơn đứng tên OSB Tập đoàn, người ký là đại diện OSB Công nghệ cao,
    giấy ủy quyền lại do OSB Công nghệ cao cấp -> ủy quyền vô hiệu."""
    by_type = dict(_BT_LD, giay_uy_quyen=[_p(1, "giay_uy_quyen", "Nguyễn Hồng Sơn ủy quyền ...")])
    v = ScriptedVision({**_KB_LECH, "[RULE:chu_ky_lien_danh_uy_quyen]": {
        "muc": [{"phap_nhan": _OSB, "nguoi_uy_quyen": "Nguyễn Hồng Sơn",
                 "nguoi_duoc_uy_quyen": "Trần Vũ Thường", "phap_nhan_uy_quyen": _OHT,
                 "phap_nhan_khop": False, "dung_nguoi": True, "dung_pham_vi": True}],
        "bang_chung": "Giấy ủy quyền trang 1", "trang": [1], "do_tin": 0.95}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_KHONG
    assert "vô hiệu" in verdict.ghi_chu and _OHT in verdict.ghi_chu
    assert verdict.nguon_doc == ["don_du_thau", "thoa_thuan_lien_danh", "giay_uy_quyen"]
    assert len(v.calls) == 2


async def test_uy_quyen_hop_le_tu_dung_thanh_vien_thi_dat():
    by_type = dict(_BT_LD, giay_uy_quyen=[_p(1, "giay_uy_quyen", "ủy quyền ...")])
    v = ScriptedVision({**_KB_LECH, "[RULE:chu_ky_lien_danh_uy_quyen]": {
        "muc": [{"phap_nhan": _OSB, "nguoi_uy_quyen": "Nguyễn Hồng Sơn",
                 "nguoi_duoc_uy_quyen": "Trần Vũ Thường", "phap_nhan_uy_quyen": _OSB,
                 "phap_nhan_khop": True, "dung_nguoi": True, "dung_pham_vi": True}],
        "bang_chung": "Giấy ủy quyền trang 1", "trang": [1]}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT and len(v.calls) == 2


async def test_ky_lech_ma_khong_co_giay_uy_quyen_thi_khong_dat_khong_goi_llm_lan_2():
    v = ScriptedVision(dict(_KB_LECH))
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_KHONG
    assert len(v.calls) == 1                              # KHÔNG gọi LLM lần 2
    assert "không có giấy ủy quyền" in verdict.ghi_chu
    assert verdict.nguon_doc == ["don_du_thau", "thoa_thuan_lien_danh"]


def test_prompt_uy_quyen_lien_danh_neu_ro_tung_khoi_chu_ky():
    from experiment.evaluate.rules.chu_ky_khop_dkkd import (
        SYS_RULE_UY_QUYEN_LIEN_DANH, uy_quyen_lien_danh_prompt,
    )

    p = uy_quyen_lien_danh_prompt("GUQ: nội dung ủy quyền", _LECH)
    assert "[RULE:chu_ky_lien_danh_uy_quyen]" in p
    assert _OSB in p and "Trần Vũ Thường" in p and "Nguyễn Hồng Sơn" in p
    assert "GUQ: nội dung ủy quyền" in p
    assert "dung_pham_vi" in SYS_RULE_UY_QUYEN_LIEN_DANH
    assert "KHÔNG bịa" in SYS_RULE_UY_QUYEN_LIEN_DANH


def test_guard_phap_nhan_mot_chieu_trong_nhanh_uy_quyen():
    """LLM nói 'khác pháp nhân' mà hai tên chuẩn hoá giống hệt -> tin CODE, tránh báo động giả."""
    kq, gc = ket_luan_uy_quyen_lien_danh(
        _LECH, [_muc(_OSB, phap_nhan_uy_quyen=_OSB.lower(), phap_nhan_khop=False)])
    assert kq == KET_QUA_DAT and gc == ""
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py -q -k uy_quyen`
Expected: FAIL — `ImportError: cannot import name 'SYS_RULE_UY_QUYEN_LIEN_DANH'` và các test handler trả `KET_QUA_SOI` thay vì `KET_QUA_KHONG`/`KET_QUA_DAT`.

- [ ] **Step 3: Thêm system prompt + hàm dựng prompt**

Thêm sau `lien_danh_ky_prompt`:

```python
SYS_RULE_UY_QUYEN_LIEN_DANH = (
    "Bạn là chuyên gia chấm thầu. Trên ĐƠN DỰ THẦU của nhà thầu liên danh có khối chữ ký do người "
    "KHÁC với đại diện nêu trong thỏa thuận liên danh ký. Đọc GIẤY ỦY QUYỀN và BÓC DỮ LIỆU cho "
    "TỪNG khối chữ ký nêu ở đầu prompt (KHÔNG kết luận đạt/không đạt — hệ thống tự làm). Mỗi mục:\n"
    "- phap_nhan: chép ĐÚNG tên thành viên liên danh của khối chữ ký đang xét (nêu ở đầu prompt);\n"
    "- nguoi_uy_quyen / nguoi_duoc_uy_quyen: ai ủy quyền cho ai;\n"
    "- phap_nhan_uy_quyen: tên pháp nhân BÊN ỦY QUYỀN ghi trong giấy ủy quyền;\n"
    "- phap_nhan_khop: bên ủy quyền có CÙNG pháp nhân với thành viên liên danh nêu trên không;\n"
    "- dung_nguoi: người được ủy quyền có ĐÚNG là người đã ký đơn nêu trên không;\n"
    "- dung_pham_vi: nội dung/phạm vi ủy quyền có bao gồm việc KÝ ĐƠN DỰ THẦU không.\n"
    "Không tìm thấy giấy ủy quyền cho một khối chữ ký nào thì BỎ QUA mục đó, TUYỆT ĐỐI KHÔNG bịa "
    "tên hay phạm vi. "
    + _QUY_TAC_PHAP_NHAN +
    "bang_chung: trích nguyên văn giấy ủy quyền kèm số trang. Chỉ trả JSON."
)


def uy_quyen_lien_danh_prompt(guq_text: str, lech: list[ChuKyLech]) -> str:
    khoi = "\n".join(
        f"- Thành viên liên danh: {l.phap_nhan} | người đã ký đơn: {l.nguoi_ky} | "
        f"đại diện theo thỏa thuận liên danh: {l.nguoi_dai_dien}" for l in lech)
    return (
        "[RULE:chu_ky_lien_danh_uy_quyen]\n"
        f"CÁC KHỐI CHỮ KÝ CẦN THẨM ĐỊNH ỦY QUYỀN:\n{khoi}\n\n"
        f"GIẤY ỦY QUYỀN (bóc từ ảnh):\n{guq_text}\n\n"
        + cot_block('{"muc":[{"phap_nhan":"...","nguoi_uy_quyen":"...",'
                    '"nguoi_duoc_uy_quyen":"...","phap_nhan_uy_quyen":"...","phap_nhan_khop":true,'
                    '"dung_nguoi":true,"dung_pham_vi":true,"ghi_chu":""}],'
                    '"bang_chung":"<trích GUQ>","trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )
```

- [ ] **Step 4: Thêm `_xet_uy_quyen_lien_danh`**

Thêm ngay sau `_xet_lien_danh`:

```python
async def _xet_uy_quyen_lien_danh(by_type: dict[str, list[PageRecord]], vision_fn: Any,
                                  lech: list[ChuKyLech], bang_chung_1: str,
                                  trang_1: list[int]) -> Verdict:
    """Bước 2 (chỉ khi có chữ ký lệch người): thẩm định giấy ủy quyền của TỪNG khối chữ ký.

    Gộp mọi khối lệch vào MỘT call — giấy ủy quyền của liên danh thường nằm chung một file, tách
    nhiều call chỉ tốn thêm mà không thêm bằng chứng.
    """
    mo_ta = "; ".join(f"{l.phap_nhan}: đơn do {l.nguoi_ky} ký, thỏa thuận liên danh ghi đại diện "
                      f"là {l.nguoi_dai_dien}" for l in lech)
    if not by_type.get(_GUQ):
        return _verdict_ld(KET_QUA_KHONG, bang_chung=bang_chung_1, trang=trang_1,
                           ghi_chu=f"người ký đơn khác đại diện nêu trong thỏa thuận liên danh và "
                                   f"HSDT không có giấy ủy quyền — {mo_ta}")
    nguon = [_DON, _TTLD, _GUQ]
    out = await vision_fn(SYS_RULE_UY_QUYEN_LIEN_DANH,
                          uy_quyen_lien_danh_prompt(pages_text(by_type[_GUQ]), lech),
                          validate=validate_uy_quyen_lien_danh, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict_ld(KET_QUA_LOI, bang_chung=f"AI lỗi (thẩm định ủy quyền): {out.error}",
                           ghi_chu="cần soi lại", nguon_doc=nguon)
    d2 = out.data
    ket_qua, ly_do = ket_luan_uy_quyen_lien_danh(lech, d2.get("muc") or [])
    bang_chung = f"{bang_chung_1}; ủy quyền: {d2.get('bang_chung', '') or mo_ta}"
    ghi_chu = ly_do or ("người ký đơn ký theo ủy quyền hợp lệ của thành viên liên danh — "
                        f"{mo_ta}")
    return _verdict_ld(ket_qua, bang_chung=bang_chung, trang=trang_1,
                       do_tin=float(d2.get("do_tin", 0.0) or 0.0), ghi_chu=ghi_chu,
                       nguon_doc=nguon)
```

- [ ] **Step 5: Nối bước 2 vào `_xet_lien_danh`**

Thay dòng cuối tạm thời của `_xet_lien_danh` (nhánh `return _verdict_ld(KET_QUA_SOI, ...)` thêm ở Task 6) bằng:

```python
    return await _xet_uy_quyen_lien_danh(by_type, vision_fn, lech, bang_chung, trang)
```

- [ ] **Step 6: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 7: Chạy full suite**

Run: `cd backend && python -m pytest experiment/evaluate/tests experiment/decompose/tests tests -q`
Expected: chỉ 5 test baseline đỏ, không thêm test đỏ nào.

- [ ] **Step 8: Commit**

```bash
git add backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py backend/experiment/evaluate/tests/test_rules_chu_ky_lien_danh.py
git commit -m "feat(rule): thẩm định ủy quyền ký đơn theo đúng thành viên liên danh"
```

---

## Nghiệm thu cuối (sau khi xong cả 7 task)

- [ ] Chạy toàn bộ: `cd backend && python -m pytest -q` — chỉ 5 test baseline đỏ.
- [ ] Kiểm tra `git log --oneline` có đủ 7 commit, mỗi commit một task.
- [ ] Re-run decompose cho gói 54 (cần proxy AI) để `hsdt_doi_chieu` được điền thật, rồi chấm lại HSDT gói 54 và đối chiếu 3 điều:
  1. Tiêu chí "Bảng giá và phù hợp webform" có 2 verdict, verdict về Mẫu 05C.1 **không** mang bằng chứng so giá;
  2. Verdict chữ ký nhà thầu liên danh mang nhãn *"Người ký đơn dự thầu đúng đại diện liên danh (thỏa thuận liên danh)"* và `ghi_chu` nêu lý do đúng (ủy quyền từ thành viên không đứng đầu), **không** nhắc ĐKKD;
  3. `logs/evaluate.log` không còn dòng `— thử lại 1 lần` cho cảnh báo lệch cột, và lần chấm thứ hai của cùng bộ hồ sơ báo `dùng cache (0 call vision)` cho cả file từng có cảnh báo.
