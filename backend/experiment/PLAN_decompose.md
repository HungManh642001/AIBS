# Phân rã tiêu chí nguyên tử (Agentic Workflow) — Bản thiết kế

> Bước 4 của lõi Agentic RAG (theo `README.md`). **Phạm vi:** phân rã nội dung 4 nhóm
> (`chuong3_groups.json`) thành **tiêu chí nguyên tử + sub_checks**, lần tham chiếu **Mục 3 → Phần 4**,
> truy số ngưỡng **TCĐG → BDS** bằng sub-query. Đây là **phiên bản agentic thay thế** cho
> `services/extraction.py::extract_rubric` (hiện cắt trang lossy, 1-pass).

## 1. Mục tiêu & rủi ro chốt

Đầu vào: `out/chuong3_groups.json` (4 nhóm, nội dung CÓ CẤU TRÚC + bảng nguyên văn) + **vector index**
(`experiment/index`, đã dựng). Đầu ra: mỗi nhóm → danh sách **`CriterionDetailModel`** (khớp schema
production) + báo cáo coverage + danh sách needs-review.

**Rủi ro #1 (đã chốt với user) phải chặn bằng thiết kế:**
1. **Sót tiêu chí im lặng (recall):** thêm bước **critique coverage** đối chiếu lại nguồn.
2. **Bịa verdict cho tiêu chí khuyết:** số ngưỡng không tra được → **`thong_so.can_review=true`**, KHÔNG
   bịa; lỗi LLM 1 tiêu chí → giữ tiêu chí + `can_review` + `loi_ai` (như extraction.py hiện tại).

## 2. Tái dùng (read-only) — KHÔNG sửa services/

User đã cho phép tái dùng schema services. Import **read-only** (không sửa) các module production để DRY
và hướng tích hợp (bước này sẽ thay `extract_rubric`):
- `services.ai_schemas`: `validate_criteria_list`, `validate_criterion_detail`, `CriterionDetailModel`,
  `SubCheckModel` — schema đầu ra.
- `services.ai_client.ai_call` (+ `AiOutcome`): gọi LLM qua LiteLLM proxy, **no-silent-mock** + retry +
  trích JSON + validate. (LLM steps đi qua đây → giữ pin litellm, không cần dep LLM mới.)
- `services.prompts.cot_block`, `SCALE_DEF`: ép **Chain-of-Thought** + gợi ý schema (đúng remediation).
- `services.artifact_catalog.all_codes/get_artifact`: từ vựng `required_artifacts`.
- `services.json_utils.extract_json`: dự phòng parse.

**Không dep mới.** Orchestration dùng `llama_index.core.workflow` (đã có trong llama-index-core).

## 3. Vì sao "Agentic Workflow có kiểm soát" (không phải agent tự hành)

Agent tự hành (ReAct) dễ **sót tiêu chí** và khó test — ngược rủi ro #1. Ta dùng **LlamaIndex Workflow**:
các bước rõ ràng, orchestration xác định (đảm bảo MỌI nhóm + bước coverage đều chạy), nhưng vẫn
"agentic": **dùng tool retrieve, đa bước, tự phản biện (critique), sinh sub-query động**.

## 4. Luồng Workflow (chạy 1 lần / nhóm)

```
StartEvent(group)
  │  (nếu group.is_reference, vd Mục 3→Phần 4: retrieve_fn(ref_target) kéo nội dung Phần 4 làm nguồn)
  ▼
[Step 1 list]   LLM liệt kê tiêu chí cụ thể: {nhom, ten, yeu_cau_goc (trích HSMT), hsdt_can_kiem_tra}.
                NGUYÊN TỬ: 1 loại hồ sơ + 1 nội dung; 1 loại hồ sơ nhiều nội dung -> TÁCH; không trùng.
                + critique (chống sót) CHỈ khi nhóm có BẢNG (vd năng lực) — free-text thì BỎ.
  ▼  fan-out: mỗi tiêu chí -> AnalyzeEvent
[Step 2 analyze] (song song)  LLM xác định tien_quyet + **noi_dung_can_kiem_tra** — ô HẠNG NHẤT buộc
                model liệt kê "cần kiểm tra nội dung gì". Mỗi nội dung {ten, gia_tri, nguon, kieu_check}:
                nguon='hsmt' = giá trị HSMT quy định để đối chiếu (gia_tri TRỐNG nếu nguồn chưa có = "chưa
                đủ"); nguon='hsdt' = dữ liệu nhà thầu (đánh giá sau). (KHÔNG bịa số.)
  ▼  SearchEvent(crit, item)
[Step 3 search] (song song)  Với nội dung nguon='hsmt' còn TRỐNG gia_tri -> LLM **sinh query** -> retrieve
                -> **điền gia_tri** (chỉ khi có bằng chứng). Vẫn trống -> can_review (no-fab).
                Lỗi LLM ở analyze -> giữ tiêu chí + loi_ai.
  ▼  collect tất cả DoneEvent
[Step 4 collect] -> StopEvent(GroupDecomposition)
```

> **Sửa (2026-06-30):** (a) output PHẲNG — bỏ `sub_checks/thong_so` máy-so-sánh (Qwen3 tự đánh giá
> thông số). Mỗi tiêu chí: nhom, ten, **yeu_cau_goc**, **hsdt_can_kiem_tra**, tien_quyet,
> **noi_dung_can_kiem_tra**[{ten, gia_tri, nguon, kieu_check, can_review}]. Đưa "cần kiểm tra gì" thành
> trường BẮT BUỘC (sửa bug step không xác định được nội dung — trước bị chôn trong thong_so._need).
> (b) workflow gọn lại theo phản hồi "lan man": `yeu_cau_goc` chuyển lên **step 1**; tách `detail` thành
> **analyze (step 2)** + **search (step 3)** (mỗi step một việc); **critique có điều kiện** (chỉ nhóm
> bảng lớn — nơi liệt kê 1 lượt dễ sót; free-text bỏ). max_tokens=8192 (Qwen3 có khối &lt;think&gt;).

`run_decompose` lặp 4 nhóm, gọi workflow mỗi nhóm, gom thành `DecomposeResult`.

## 5. Hai cổng tiêm (injectable) — để test offline khi proxy TẮT

LLM phân rã **bắt buộc cần proxy** (máy dev đang tắt). Tách 2 cổng tiêm để test wiring/recall/needs-review
xác định offline; nghiệm thu ngữ nghĩa khi proxy bật:
- `llm_fn(system, prompt, validate) -> AiOutcome` — mặc định bọc `ai_call` (real, no-silent-mock);
  test tiêm `ScriptedLlm` (trả JSON kịch bản theo từng bước).
- `retrieve_fn(query, k) -> list[hit]` — mặc định bọc `experiment.index` (hybrid); test tiêm
  scripted/in-memory (BM25 thật + DeterministicEmbedding) — KHÔNG phụ thuộc MOCK_RESPONSES của services.

## 6. Schema đầu ra (`decomposition.json`)

```jsonc
{
  "doc": "E-HSMT",
  "groups": [
    {
      "group": "hop_le", "muc": "Mục 1...", "is_reference": false, "ref_target": null,
      "criteria": [{
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu đúng yêu cầu E-HSMT",
        "yeu_cau_goc": "Giá trị bảo lãnh, thời gian hiệu lực, đơn vị thụ hưởng theo E-HSMT",
        "hsdt_can_kiem_tra": ["Thư bảo lãnh"], "tien_quyet": true,
        "noi_dung_can_kiem_tra": [
          {"ten":"Giá trị bảo lãnh","gia_tri":"6.100.000 VNĐ","nguon":"hsmt","kieu_check":"đối chiếu","can_review":false},
          {"ten":"Thời gian hiệu lực","gia_tri":">= 120 ngày","nguon":"hsmt","kieu_check":"đối chiếu","can_review":false},
          {"ten":"Đơn vị thụ hưởng","gia_tri":"Liên doanh Việt Nga Vietsovpetro","nguon":"hsmt","kieu_check":"đối chiếu","can_review":false}
        ]
      }],
      "coverage": {"listed_n": 5, "final_n": 6, "added_by_critique": ["..."], "notes": "..."},
      "needs_review": [{"ten": "...", "ly_do": "chưa tra được giá trị HSMT cho: ..."}]
    }
    // nang_luc, ky_thuat (is_reference=true, criteria từ Phần 4), tai_chinh
  ],
  "summary": {"n_groups": 4, "n_criteria": 0, "n_needs_review": 0}
}
```
Kèm `decomposition.md` (người soi: mỗi nhóm → tiêu chí + noi_dung_can_kiem_tra + cờ cần soi) và `decompose_report.md`.

## 7. Bố cục module — `backend/experiment/decompose/`

```
decompose/
  schema.py        Schema PHẲNG experiment-local: CriterionModel/NoiDungKiemTra + validate_*;
                   GroupDecomposition, DecomposeResult, to_json helpers (KHÔNG dùng CriterionDetailModel)
  llm.py           LlmFn protocol; default_llm_fn (bọc ai_call, no-silent-mock); ScriptedLlm (test)
  retrieval.py     RetrieveFn; default từ experiment.index (open index 1 lần, hybrid top-k);
                   resolve_reference(ref_target)->text ; subquery_bds(query)->hits
  prompts.py       system prompt: list / critique / structure / subquery / resolve (cot_block)
  workflow.py      DecomposeWorkflow (LlamaIndex Workflow): list(+critique nếu bảng)/fan_out/
                   analyze/search/collect + events
  run_decompose.py CLI: chuong3_groups.json + index -> decomposition.json/.md + report ; run()/main()
  tests/
    conftest.py        scripted_llm, scripted_retrieve, sample_groups (chuong3_groups.json) fixtures
    test_schema.py     GroupDecomposition/DecomposeResult round-trip; criteria validate
    test_retrieval.py  adapter thật trên index in-memory (BM25 + DeterministicEmbedding) — offline
    test_workflow.py   ScriptedLlm+scripted retrieve: list->critique THÊM tiêu chí sót;
                       detail -> can_review khi không tra được số (KHÔNG bịa); lỗi LLM -> can_review+loi_ai
    test_run_e2e.py    sample-gated + ScriptedLlm: sinh decomposition.json/.md/report, 4 nhóm đúng thứ tự
```

## 8. Nghiệm thu

**Offline (proxy tắt) — xác định, làm ngay:**
- Test xanh: workflow list→critique→detail→assemble chạy với ScriptedLlm.
- **Recall guard:** critique thêm được tiêu chí "sót" vào danh sách (test khẳng định final_n > listed_n).
- **No-fabrication:** sub_check cần số mà retrieve không thấy → `thong_so.can_review=true`; lỗi LLM →
  tiêu chí giữ lại + `can_review` + `loi_ai` (KHÔNG có verdict bịa).
- Đầu ra mọi tiêu chí **validate** qua `validate_criterion_detail`.
- `retrieval.py` truy hồi thật offline (BM25) trên index in-memory.

**Khi proxy bật (ghi sẵn lệnh, soi mắt sau):**
- `run_decompose` thật trên `chuong3_groups.json` + `out/qdrant` → 4 nhóm có tiêu chí hợp lý;
  ky_thuat lần được Phần 4 và phân rã; tai_chinh ra phương pháp; số bảo đảm dự thầu tra từ BDS hoặc
  can_review nếu không có.
- Proxy tắt ở chế độ thật → `llm_fn` báo lỗi (no-silent-mock), tiêu chí can_review, KHÔNG bịa.

## 9. Ngoài phạm vi (YAGNI)

- Tích hợp thay `services/extraction.py` vào pipeline chính — sau khi bước này nghiệm thu & chốt.
- Đánh giá HSDT theo rubric (bước 6).
- Tinh chỉnh prompt/loop critique nhiều vòng, re-ranker — khi có dữ liệu thật để đo.
- HSDT scan.
