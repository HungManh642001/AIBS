# Trích nội dung tiêu chuẩn 4 nhóm (Chương III) — Bản thiết kế

> Bước 3 của lõi Agentic RAG. **Phạm vi hẹp (chốt với user):** chỉ **trích NỘI DUNG tiêu chuẩn
> của 4 nhóm chính (Mục 1–4) như được quy định trong Chương III. TIÊU CHUẨN ĐÁNH GIÁ**.
> KHÔNG phân rã thành tiêu chí nguyên tử, KHÔNG chấm — phân rã/đánh giá để các bước sau.

## 1. Mục tiêu

Từ HSMT PDF-text → định vị Chương III → gom **nội dung từng nhóm** (mỗi nhóm = 1 Mục):

| Nhóm | Mục | Nội dung (đã soi dữ liệu thật) |
|---|---|---|
| hop_le | Mục 1. Đánh giá tính hợp lệ | text điều kiện |
| nang_luc | Mục 2. …năng lực và kinh nghiệm | text dẫn nhập + **bảng** tiêu chí |
| ky_thuat | Mục 3. …kỹ thuật | (doc này) câu **tham chiếu** "Theo Phần 4" |
| tai_chinh | Mục 4. …tài chính | text **phương pháp** giá thấp nhất + các bước |

Đầu ra: nội dung gọn, có cấu trúc, **con người đọc/đối chiếu được**, làm đầu vào cho bước phân rã.

## 2. Không cần LLM — hoàn toàn xác định

Đây chỉ là gom + giữ nguyên nội dung, không diễn giải → **không gọi LLM** (giải tỏa ràng buộc máy
dev không có LLM). Chạy & test thật ngay trên file mẫu.

## 3. Tái dùng thư viện chunking để lấy nội dung CÓ CẤU TRÚC

KHÔNG đọc từ `chunks.jsonl` (bảng đã serialize mất hàng). Thay vào đó import
`experiment.chunking.{layout,headings,structure,tree}` để dựng view theo Mục:
- `extract_lines` + `extract_tables` → dòng text + `TableRegion` (giữ `rows` gốc).
- `classify_heading` + `drop_toc_clusters` + `keep_monotonic_chapters` → heading sạch.
- `build_outline` → tìm node Chương III và 4 node Mục con (dải trang).
- `iter_blocks_with_context` → gán mỗi block (text line / table) về Mục đang mở.

Với mỗi Mục 1–4: gom **text_blocks** (các dòng text liên tiếp nối lại) + **tables** (`rows` gốc),
theo đúng thứ tự đọc.

## 4. Map Mục → nhóm

Dùng đúng quy tắc `_norm` (đ→d) trên tiêu đề Mục (tái dùng `chunker.group_hint` hoặc helper tương
đương): "hop le"→hop_le, "nang luc"/"kinh nghiem"→nang_luc, "ky thuat"→ky_thuat, "tai chinh"→
tai_chinh. Chỉ giữ **Mục 1–4** (4 nhóm chính); bỏ Mục 5/6/7.

## 5. Mục 3 tham chiếu — đánh dấu, CHƯA lần theo

Nội dung Mục 3 ở doc này chỉ là pointer ("Theo tài liệu đính kèm tại Phần 4. CÁC PHỤ LỤC").
Bước này:
- Giữ nguyên text Mục 3 làm nội dung.
- Nhận diện pointer (text ngắn + regex "theo … tại (Phần|Chương|Mục) <số>") → set `is_reference=true`
  và bóc `ref_target` (vd `{"kind":"phan","number":"4"}`).
- **Chưa** nhảy sang Phần 4 (việc lần theo + trích đích gộp vào bước phân rã sau).
- Trường hợp HSMT khác mà Mục 3 có nội dung inline → `is_reference=false`, lấy nội dung như Mục
  thường. Cùng một code path.

## 6. Schema đầu ra (`chuong3_groups.json`)

```jsonc
{
  "doc": "E-HSMT",
  "chuong3_page": [27, 42],
  "groups": [
    {
      "group": "hop_le",
      "muc": "Mục 1. Đánh giá tính hợp lệ của E-HSDT",
      "muc_page": [27, 27],
      "is_reference": false,
      "ref_target": null,
      "blocks": [
        {"type": "text",  "page": [27, 27], "text": "E-HSDT … hợp lệ khi …"},
        {"type": "table", "page": [28, 39], "rows": [["TT","Mô tả", "..."], ["1","…","…"]]}
      ]
    }
    // … nang_luc, ky_thuat, tai_chinh
  ]
}
```

Kèm `chuong3_groups.md` (người đọc): mỗi nhóm = heading + text + bảng render dạng markdown.

## 7. Bố cục module — `backend/experiment/extract/`

```
extract/
  schema.py        Block, GroupContent + serialize (json)
  sections.py      build_chuong3_groups(pdf) -> list[GroupContent]  (reuse chunking lib)
  refs.py          detect_reference(text) -> (is_ref, ref_target)
  render.py        groups_to_markdown(groups) -> str  (bảng -> md)
  cli_extract.py   CLI: pdf -> chuong3_groups.json + .md + report
  tests/
    conftest.py    sample_pdf fixture = glob samples/*.pdf (skip nếu vắng)
    test_refs.py           (inline, không cần PDF)
    test_sections.py       (sample-gated: đúng 4 nhóm, Mục 2 có table rows, Mục 3 is_reference)
    test_render.py         (inline)
    test_end_to_end.py     (sample-gated: json + md + report)
```

## 8. Nghiệm thu

- `chuong3_groups.json` + `.md` + `report.md`.
- Đúng **4 nhóm** hop_le/nang_luc/ky_thuat/tai_chinh, mỗi nhóm gắn đúng Mục + dải trang.
- **nang_luc** có ≥1 block `table` với `rows` gốc (header "TT/Mô tả/Yêu cầu/…", có hàng "1","2",
  "3.1"…) — bảng KHÔNG bị mất hàng.
- **hop_le** có text điều kiện (p27).
- **ky_thuat** `is_reference=true`, `ref_target={kind:phan, number:4}`.
- **tai_chinh** có text phương pháp (giá thấp nhất, Bước 1/2/3).
- Test xác định xanh, không cần LLM.

## 9. Ghi chú dữ liệu (đã xác minh)

- File mẫu hiện là `samples/E-HSMT.pdf` (đã đổi tên) → fixture dùng **glob `samples/*.pdf`**.
- Bảng năng lực: `extract_tables` trả `rows` 7 cột, 3 hàng header (gộp ô), hàng dữ liệu `col0` khớp
  `^\d+(\.\d+)?$`. Bước này **giữ nguyên `rows`** (không parse thành tiêu chí — để bước phân rã).
- Chương III ở p27–42; Mục 1@27, Mục 2@27–40, Mục 3@40, Mục 4@40–41.
