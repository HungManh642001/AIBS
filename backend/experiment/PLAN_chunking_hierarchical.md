# Kế hoạch: Chunking HSMT theo cấu trúc phân cấp (Bước 1)

> Trạng thái: **CHỜ REVIEW**. Đây là bản kế hoạch để bạn tự kiểm tra; chưa viết code.
> Sau khi bạn duyệt, mới sang bản kế hoạch triển khai chi tiết (TDD).

## 1. Mục tiêu & phạm vi

> **Chốt phạm vi:** Bước này **chỉ xử lý HSMT dạng PDF text** (đúng thực tế hiện tại).
> Đi thẳng **layout-aware** (`get_text("dict")` + `find_tables()`), không làm nhánh
> scan/OCR. HSDT là PDF scan — việc index/truy xuất HSDT scan thuộc bước đánh giá về
> sau, không nằm trong chunking HSMT này.

**Mục tiêu:** Biến 1 file HSMT (PDF text) thành:
- **Cây mục phân cấp** (outline): Phần → Chương → Mục → Điều → khoản.
- **Danh sách chunk lá** để embed sau này, mỗi chunk **không cắt ngang mục** và **mang
  đầy đủ metadata phả hệ** (chapter, section_path, page, loại nội dung, bảng…).

**Chỉ làm ở bước này** (YAGNI):
- Parse cấu trúc + cắt chunk + gắn metadata + xuất artefact để soi.
- **KHÔNG** làm: embedding, Qdrant, hybrid search, gọi LLM, sub-query. Để các bước sau.

**Vì sao tách riêng:** Toàn bộ pipeline Agentic RAG đứng trên chất lượng chunk + metadata
ở bước này. Sai ở đây → RAG/đánh giá sai theo. Phải nghiệm thu chắc rồi mới đi tiếp.

## 2. Hợp đồng dữ liệu (quan trọng nhất — quyết định mọi bước sau)

### Đầu vào
HSMT PDF text. **Không** dùng `extract_pdf` cũ (vì `get_text()` phẳng vứt mất font/bbox).
Experiment có extractor *layout-aware* riêng: `page.get_text("dict")` → block/line/span kèm
`size`/`flags`/`bbox`, và `page.find_tables()` cho bảng (xem §3, §5).

### Đầu ra — schema chunk (đề xuất, sẽ chốt khi review)
```jsonc
// 1 dòng trong chunks.jsonl
{
  "chunk_id": "c0007",
  "doc": "hsmt_goi_X.pdf",
  "text": "…nội dung thô của chunk (raw_text)…",

  // --- phả hệ cấu trúc ---
  "section_path": ["Phần 1. Thủ tục đấu thầu",
                   "Chương III. Tiêu chuẩn đánh giá HSDT",
                   "Mục 2. Đánh giá về năng lực và kinh nghiệm"],
  "chapter": "Chương III. Tiêu chuẩn đánh giá HSDT",  // chapter_name
  "chapter_no": "III",
  "section": "Mục 2. Đánh giá về năng lực và kinh nghiệm", // parent_section gần nhất
  "level": 2,                 // 0=Phần,1=Chương,2=Mục,3=Điều,4=khoản
  "heading_number": "2",

  // --- định vị ---
  "page_start": 41,
  "page_end": 42,
  "char_start": 0, "char_end": 1180,   // offset trong section (để truy vết)

  // --- loại nội dung ---
  "node_type": "text",        // text | table | table_row_group
  "group_hint": "nang_luc",   // hop_le|nang_luc|ky_thuat|tai_chinh|unknown (chỉ trong Chương III)

  // --- phục vụ cắt/embed ---
  "char_len": 1180,
  "overlap_prev": false
}
```
Đây là **superset** của metadata blueprint yêu cầu (`page_number`, `parent_section`,
`chapter_name`, `raw_text`) — thêm `section_path`, `level`, `node_type`, `group_hint`,
`char offset` để RAG/đánh giá/audit về sau dùng được ngay.

### Đầu ra phụ
- `outline.json`: cây mục đầy đủ (để soi mắt thường xem cấu trúc bắt có đúng không).
- `report.md`: bảng metric nghiệm thu (xem §8).

## 3. Tín hiệu nhận diện cấu trúc (layout + regex)

HSMT là PDF text nên **tận dụng tối đa layout**, dùng **bộ nhận diện 2 tầng kết hợp**:

**Tầng A — Layout:** `page.get_text("dict")` lấy block/line/span kèm `size`, `flags` (bold),
`bbox`. Heading thường: font lớn hơn body median, in đậm, đứng riêng dòng/căn giữa, có
khoảng trắng dọc phía trên. `page.find_tables()` bắt **bảng** (BDS, bảng TCĐG).

**Tầng B — Regex trên đầu dòng (xương sống ngữ nghĩa):**
| Cấp | Mẫu (rút gọn) | Ví dụ |
|----|----|----|
| 0 Phần | `^\s*PHẦN\s+(\d+|[IVX]+|THỨ\s+\S+)` | "Phần 1", "PHẦN THỨ NHẤT" |
| 1 Chương | `^\s*CHƯƠNG\s+([IVXLC]+|\d+)\b` | "Chương III", "CHƯƠNG V" |
| 2 Mục | `^\s*Mục\s+(\d+)\b` | "Mục 2" |
| 3 Điều | `^\s*Điều\s+(\d+)\b` | "Điều 5." |
| 4 Khoản/điểm | `^\s*(\d+(\.\d+)*)[\.\)]\s+` , `^\s*([a-zđ])\)\s+` | "1.1", "a)" |

**Quyết định cuối = bỏ phiếu:** một dòng là heading nếu regex khớp **và** (có cue layout
**hoặc** dòng ngắn **hoặc** tỉ lệ HOA cao). Mục đích: chặn false-positive kiểu
"…quy định tại **Chương III**…" nằm giữa câu.

**Chuẩn hoá tiếng Việt** tái dùng `_norm` của `hsmt_locator` (lowercase + bỏ dấu, xử lý `đ`)
để bền với lỗi OCR/biến thể chữ.

## 4. Thuật toán (3 pha)

1. **Tiền xử lý dòng:** ghép trang → danh sách `LineSpan{text, page, layout_cue?}`. Lọc bỏ
   **header/footer lặp** (dòng ngắn giống nhau ở đầu/cuối nhiều trang) và **trang Mục lục**
   (dòng có dấu chấm dẫn `....` + số trang) để khỏi nhận nhầm heading.
2. **Dựng cây:** duyệt dòng theo thứ tự đọc; giữ 1 **stack theo cấp**. Gặp heading cấp L →
   pop stack về L-1, push node mới (lưu page_start). Dòng nội dung gắn vào node sâu nhất.
   Sang trang thì cập nhật page hiện tại → suy ra page_start/page_end mỗi node.
3. **Phát chunk lá:** với mỗi node lá có nội dung:
   - nội dung ≤ `MAX_CHARS` → 1 chunk.
   - dài hơn → cắt tại ranh giới đoạn/câu, có `OVERLAP`, **không vượt khỏi node**.
   - Bảng → chunk riêng (xem §5).
   Mỗi chunk thừa kế `section_path`/metadata của node lá.

Tham số khởi điểm: `MAX_CHARS≈1500–2000`, `OVERLAP≈150–200` (đo lại khi gắn embedder).

## 5. Xử lý bảng (BDS & bảng tiêu chuẩn đánh giá)

Bảng là **điểm sống còn**: BDS (Chương II) chứa các thông số mà Chương III tham chiếu;
bảng TCĐG (năng lực) chứa tiêu chí theo hàng. Cắt vỡ hàng = hỏng đánh giá.

- `page.find_tables()` → lấy cell, serialize sang Markdown/TSV, gắn `node_type="table"`.
  Bảng to → cắt theo **nhóm hàng**, **lặp lại hàng tiêu đề** ở mỗi chunk
  (`node_type="table_row_group"`).
- Bảng nằm trong cây mục như một node lá, vẫn thừa kế `section_path` của mục chứa nó (nhờ
  bbox/vị trí), nên truy vết được "bảng này thuộc Chương II / BDS".

## 6. Các edge case phải lường

- Heading **cross-page** / page chứa cuối mục cũ + đầu mục mới (cắt theo dòng, không theo trang).
- **Mục lục** đầu tài liệu (false heading) → lọc ở pha 1.
- **Header/footer lặp** ("HỒ SƠ MỜI THẦU – Gói…") → strip ở pha 1.
- **Tham chiếu nội tuyến** ("theo Chương III") → bộ bỏ phiếu chặn.
- **Đánh số La Mã** I–X → ưu tiên khớp ngữ cảnh "Chương".
- **Multi-column** (ít gặp ở HSMT) → đọc theo cột nhờ bbox.
- **Thứ tự đọc theo bbox:** sắp xếp span theo (page, y, x) để ghép dòng đúng thứ tự, tránh
  lỗi đảo dòng khi block trả về không tuần tự.
- **Heading viết tắt/không chuẩn** → để hook mở rộng từ khoá.

## 7. Cấu trúc module đề xuất trong `experiment/`
```
experiment/
  README.md
  PLAN_chunking_hierarchical.md   ← file này
  chunking/
    schema.py          # LineSpan, SectionNode, Chunk (dataclass/TypedDict)
    extract_layout.py  # PDF -> LineSpan[] (+font/bbox nếu pdf_text) + bảng
    headings.py        # nhận diện heading (regex + layout) + map cấp + bỏ phiếu
    tree.py            # LineSpan[] -> cây SectionNode (+ page_start/end)
    chunker.py         # cây -> chunk lá + metadata + overlap + xử lý bảng
  cli_chunk.py         # chạy: python -m experiment.cli_chunk <file.pdf> -> out/
  samples/             # HSMT mẫu (bạn bỏ vào)
  out/                 # outline.json, chunks.jsonl, report.md
```

## 8. Cách bạn tự nghiệm thu (acceptance)

Chạy `python -m experiment.cli_chunk samples/hsmt_X.pdf`, rồi soi 3 artefact:

**a) `outline.json`** — mắt thường xác nhận cây mục đúng: có Phần/Chương/Mục, đặc biệt
**bắt được "Chương III. Tiêu chuẩn đánh giá"** và **4 mục con** (hợp lệ / năng lực / kỹ thuật /
tài chính), và **"Chương II/Bảng dữ liệu đấu thầu"**.

**b) `chunks.jsonl`** — kiểm tra metadata: page đúng, section_path đúng, không có chunk
nào `text` lẫn 2 mục khác nhau.

**c) `report.md`** — bảng metric tự động (ngưỡng đạt đề xuất):
| Metric | Ý nghĩa | Ngưỡng |
|---|---|---|
| Heading recall theo Mục lục | bắt đủ Chương/Mục | ≥ 95% |
| Cross-section chunks | chunk cắt ngang mục | = 0 |
| Coverage ký tự | tổng char chunk / tổng char tài liệu | ≥ 99% (không nuốt chữ) |
| Bắt được Chương III + 4 nhóm | điều kiện cho RAG | có / không |
| Bắt được BDS dạng bảng | giữ nguyên hàng | có / không |
| Chunk vượt MAX_CHARS | quá ngân sách | = 0 |

→ Bạn đối chiếu trực tiếp với file HSMT gốc. Đạt hết → chốt, sang Bước 2 (embedding/index).

## 9. Quyết định cần bạn chốt khi review

- **D1 — Layout-aware:** ✅ **ĐÃ CHỐT** — HSMT PDF text → dùng `get_text("dict")` +
  `find_tables()` + regex. (Bạn đã yêu cầu tập trung PDF text trước.)
- **D2 — Nhánh scan:** ✅ **ĐÃ CHỐT** — bỏ khỏi bước này. HSDT scan xử lý ở bước index/đánh
  giá sau.
- **D3 — Mẫu mục tiêu:** tối ưu cho **HSMT mẫu chuẩn theo Thông tư hiện hành** trước,
  chừa hook mở rộng cho HSMT phi chuẩn. Đồng ý?
- **D4 — Đơn vị kích thước chunk:** dùng **ký tự** ở bước này (đổi sang token khi gắn
  embedder ở Bước 2). Đồng ý?
- **D5 — Schema chunk §2:** có cần thêm/bớt field nào trước khi triển khai không?
- **D6 — HSMT mẫu (CẦN để đi tiếp):** bạn đưa 1–2 file **HSMT PDF text** thật vào
  `experiment/samples/` để bám dữ liệu thật; hay tôi tự dựng 1 file giả lập theo mẫu chuẩn
  để chạy thử trước?
