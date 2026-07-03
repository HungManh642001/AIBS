# Thiết kế: đánh giá thầu đa nguồn + luật nghiệp vụ liên-tài-liệu ("skills")

> Spec kiến trúc tổng (design). Sau khi duyệt → viết plan riêng cho từng sub-project (A trước, B sau).
> Ngày: 2026-07-03.

## Context
Pipeline hiện tại (decompose + evaluate) giả định: **1 nguồn HSMT**, **mỗi nội dung soi đúng 1 loại
hồ sơ**, **không có ngữ cảnh nhà thầu**, **mọi luật nằm trong Chương III**. Ba vấn đề nghiệp vụ thực tế
làm vỡ các giả định đó:
1. Thời gian đóng/phát hành thầu công bố ở **"Thông báo mời thầu" (pdf scan riêng)** → decompose không
   bóc được (chỉ index HSMT).
2. Đối chiếu **chữ ký/dấu đơn dự thầu ↔ Giấy phép ĐKKD** — luật nghiệp vụ **ngầm**, không có trong tiêu chí.
3. **Bảng giá ↔ Webform** theo từng nhà thầu — Webform chứa giá **mọi nhà thầu**, cần lọc đúng nhà thầu
   đang chấm → cần ngữ cảnh nhà thầu + tài liệu dùng chung cả gói.

Mục tiêu: một kiến trúc thống nhất mở 3 năng lực còn thiếu, để các luật nghiệp vụ ngầm về sau cắm thêm
được mà ít sửa lõi.

## Ba lỗ hổng → ba năng lực
| Lỗ hổng | Năng lực cần thêm | Fix vấn đề |
|---|---|---|
| Corpus 1 nguồn | **Đa nguồn** (HSMT text + TBMT scan→OCR + phụ lục), index chung, gắn `source_doc` | #1 |
| 1 nội dung ↔ 1 hồ sơ | **Luật liên-tài-liệu** = registry "skill" khai báo hồ sơ cần + logic đối chiếu | #2, #3 |
| Không có nhà thầu / hồ sơ chung | **Ngữ cảnh nhà thầu** vào evaluate + tài liệu **dùng chung cả gói** | #3 |

---

## Thành phần A — Rubric đa nguồn (fix #1)
Hiện: `services/rubric_pipeline.build_decomposition(pdf_path, workdir)` nạp **một** HSMT (extract Chương III
+ chunk + Qdrant). Đổi thành nạp **danh sách nguồn**:
- Đầu vào: `sources: list[(role, file_path, file_kind)]` — vd `("hsmt", ..., "pdf_text")`, `("tbmt", ..., "pdf_scan")`.
- **Cầu nối OCR cho scan**: nguồn `pdf_scan` → OCR bằng vision (tái dùng `experiment/evaluate/vision.pdf_to_images`
  + prompt OCR kiểu `SYS_INGEST`) → text → đưa vào chunker như nguồn text. (HSMT text giữ nguyên nhánh cũ.)
- Chunk metadata thêm `source_doc` (hsmt/tbmt/...) → `nguon` của `thong_tin_bo_sung` ghi rõ **tài liệu + điều khoản**.
- **Trích tiêu chí (Chương III) vẫn chỉ từ HSMT** (tiêu chí sống ở đó); TBMT chỉ góp vào **index tra giá trị**
  (step-3 search) → "thời gian có hiệu lực ≥ X" với X công bố ở TBMT giờ resolve được thay vì `can_review`.
- Data-model: tài liệu mời thầu ngoài HSMT (TBMT/phụ lục) — thêm role phía "mời thầu" (giá trị `loai` mới
  hoặc `artifact_type` phía HSMT). Corpus decompose = mọi tài liệu mời thầu của gói.

**Files chạm:** `services/rubric_pipeline.py`, `experiment/chunking/*` (nhận nguồn text đã OCR + field
`source_doc`), `experiment/index/*` (metadata source), `routers/rubric.py` (gom nhiều nguồn), UI upload TBMT.

---

## Thành phần B — Registry "luật nghiệp vụ" liên-tài-liệu (fix #2, #3)
Cái thiếu: nơi chứa **luật ngoài tiêu chí**, đọc **nhiều loại hồ sơ**. Mô hình Agent Skills:

```python
@dataclass
class RuleSkill:
    id: str                    # "chu_ky_khop_dkkd"
    ten: str                   # "Người ký đơn khớp người đại diện pháp luật (ĐKKD)"
    ho_so_can: list[str]       # ["don_du_thau", "tu_cach_phap_ly"]  -> cho phép LIÊN tài liệu
    can_vendor: bool           # cần danh tính nhà thầu?
    kich_hoat(criterion) -> bool   # áp cho tiêu chí/nhóm/hồ sơ nào
    handler(pages_by_type, vendor_ctx, criterion) -> Verdict   # trích + đối chiếu (prompt riêng)
```

- **Dispatch**: trong `evaluate` (sau các verdict theo nội dung của tiêu chí), chạy mọi `RuleSkill` khớp
  `kich_hoat` → mỗi skill tự lấy `pages_by_type[ho_so_can]` (nhiều hồ sơ) + (nếu cần) `vendor_ctx` →
  sinh **verdict phụ** gắn vào tiêu chí liên quan. Biến evaluate từ "1 nội dung ↔ 1 hồ sơ" thành "1 luật ↔ N hồ sơ".
- **Verdict tái dùng `Verdict`/`HsdtVerdict`** sẵn có: `noi_dung_kiem_tra` = tên luật; `bang_chung` trích
  từ nhiều tài liệu; thêm (nhỏ) `nguon_doc: list[str]` để ghi các hồ sơ đã đối chiếu. Không cần bảng mới.
- 3 luật đầu tiên: `chu_ky_khop_dkkd` (#2), `bang_gia_khop_webform` (#3, `can_vendor=True`),
  và tận dụng cho `bao_lanh_dung_don_vi_thu_huong` về sau.

### Mức "skills" — QUYẾT ĐỊNH: *code-defined trước, khai báo-ready*
Mỗi luật = **handler Python** đăng ký kèm **metadata khai báo** (`id/ten/ho_so_can/can_vendor/kich_hoat`).
Lý do (thay vì markdown/JSON thuần ngay):
- 3 luật đầu cần logic trích + đối chiếu thật (tên người ký, dò dòng nhà thầu trong bảng nhiều nhà thầu) —
  viết & test bằng code chắc hơn để chuyên gia tự soạn prompt.
- Metadata đã là **data** → về sau nạp luật từ markdown/JSON để **chuyên gia tự thêm không cần code**
  (đích Agent Skills). Không over-engineer lúc đầu (YAGNI).
- Lộ trình mở: `registry.load_from_dir()` đọc thêm luật khai báo khi cần.

**Files chạm:** `experiment/evaluate/rules/` (registry + 3 handler), `experiment/evaluate/evaluate.py`
(gọi dispatch trong `evaluate_criterion`), `experiment/evaluate/ingest.py`/`route.py` (nhóm pages theo
loai_ho_so cho handler dùng), `services/hsdt_pipeline.py` + `routers/evaluation.py` (truyền registry + ctx).

---

## Thành phần C — Ngữ cảnh nhà thầu + tài liệu dùng chung (fix #3)
- **VendorContext**: `evaluate_vendor(criteria, docs, vendor_ctx: {ten, ma_so_thue, aliases})`. Router
  `routers/evaluation.py` đã lặp theo từng vendor → dựng ctx từ `Vendor`. Luật `can_vendor=True` nhận ctx.
- **Tài liệu dùng chung cả gói (webform)**: `TenderDocument.vendor_id = NULL` = **dùng chung** (thuộc mọi
  nhà thầu). `_hsdt_files(pkg, vendor_id)` khi gom hồ sơ của 1 vendor **kèm cả tài liệu shared** của gói.
  Upload webform 1 lần/gói (UI: cho phép HSDT không chọn nhà thầu = dùng chung; hiện đang bắt buộc vendor_id).
- Luật `bang_gia_khop_webform`: nhận `{bang_gia (của vendor), webform (shared)}` + `vendor_ctx` → dò
  **đúng dòng nhà thầu** trong webform theo tên/MST (+ alias) → so giá với bảng giá → verdict (kèm bằng
  chứng 2 nguồn + trang). Không dò được dòng → `cần làm rõ` (no-fab).

---

## Luồng dữ liệu hợp nhất
```
Corpus mời thầu (HSMT text + TBMT scan→OCR + phụ lục)
   │ extract Chương III (HSMT) + index MỌI nguồn (gắn source_doc)
   ▼
decomposition (tiêu chí + thong_tin_bo_sung resolve từ BẤT KỲ nguồn, nguon = tài liệu+điều khoản)
   │  mỗi nhà thầu:
   ▼
evaluate_vendor(criteria, docs_by_type[vendor + shared], vendor_ctx, rule_registry)
   ├─ verdict theo nội dung tiêu chí (hiện có, text-only, 1 hồ sơ/nội dung)
   └─ verdict theo LUẬT skill (mới, liên-tài-liệu, lọc theo nhà thầu nếu cần)
   ▼
HsdtCriterionEval / HsdtVerdict (+ verdict luật)  → UI Kết quả (có sẵn)
```

## Ràng buộc (kế thừa)
Máy dev không có proxy (LLM/embeddings/vision đều Qwen3.6 27B) → test offline bằng ScriptedVision/ScriptedLlm
+ monkeypatch; no-silent-mock (tra/đối chiếu không ra → `cần làm rõ`/`can_review`, KHÔNG bịa); ảnh base64
inline; verdict/bằng chứng đủ audit.

## Lộ trình (tách 2 sub-project, mỗi cái spec+plan riêng)
- **A — Rubric đa nguồn** (làm trước, độc lập, nhanh có kết quả): fix #1; đẻ ra "cầu nối OCR scan → index"
  tái dùng cho B.
- **B — Registry luật + ngữ cảnh nhà thầu + hồ sơ dùng chung**: fix #2 + #3; phần lớn & mới. Chia tiếp:
  - **B1** hạ tầng: VendorContext + `pages_by_type` + shared docs (`vendor_id NULL`) + registry rỗng + dispatch.
  - **B2** luật `chu_ky_khop_dkkd` (đơn dự thầu ↔ ĐKKD).
  - **B3** luật `bang_gia_khop_webform` (`can_vendor=True`, dò dòng nhà thầu trong webform).

## Xác minh (khi thực thi từng sub-project)
- Offline: unit cho OCR-bridge (fitz sinh "scan" giả + ScriptedVision), cho từng RuleSkill (ScriptedVision
  2 tài liệu → verdict đúng / đối chiếu lệch → `không đạt`/`cần làm rõ`), cho dò dòng nhà thầu trong webform
  (bảng nhiều dòng + alias). Router: monkeypatch pipeline như hiện tại.
- Server (có proxy): TBMT scan → tiêu chí thời gian resolve được; đơn dự thầu ký sai người → luật báo
  không đạt kèm bằng chứng 2 nguồn; bảng giá lệch webform → báo đúng nhà thầu.

## Câu hỏi thiết kế còn mở (giải quyết ở spec từng sub-project)
- Role tài liệu mời thầu: thêm giá trị `loai` mới (TBMT) hay tái dùng `artifact_type` phía HSMT?
- Skill gắn vào tiêu chí qua `kich_hoat` predicate (khuyến nghị — verdict hiện dưới tiêu chí tự nhiên) hay
  một pass toàn cục riêng?
- Webform: đánh dấu shared bằng `vendor_id NULL` + `artifact_type="webform"` (khuyến nghị) hay thêm cột/bảng?
