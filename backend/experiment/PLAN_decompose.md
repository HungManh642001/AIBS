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
[ListCriteria]  LLM đọc TRỌN nội dung nhóm (text + bảng nguyên văn) -> liệt kê tiêu chí
                NGUYÊN TỬ: mỗi tiêu chí = ĐÁNH GIÁ 1 loại hồ sơ (required_artifacts = 1 mã) ứng
                với 1 nội dung kiểm; 1 loại hồ sơ nhiều nội dung -> TÁCH nhiều tiêu chí; không
                gộp, không trùng. (nhom, ten, required_artifacts). validate_criteria_list.
  ▼  ListEvent(criteria, source_text)
[CritiqueCoverage]  LLM đối chiếu LẠI nguồn vs danh sách -> trả missing[] + ghi chú
                (chặn recall). Gộp missing vào danh sách (đánh dấu added_by_critique).
  ▼  fan-out: mỗi tiêu chí -> DetailEvent
[DetailCriterion] (song song) — 3 lượt, RETRIEVAL THEO CÁI CÒN THIẾU (không theo tên tiêu chí):
   3a structure : LLM bóc sub_checks + check_type; điền thong_so KHI nguồn có sẵn số; số còn thiếu
                  -> đánh dấu **thong_so._need='<mô tả>'** + **_need_source** (PHÂN BIỆT NGUỒN):
                    · 'hsmt' = giá trị THAM CHIẾU do HSMT quy định (mốc/ngưỡng, vd thời điểm phát
                      hành HSMT) -> truy hồi bổ sung ở 3b/3c.
                    · 'hsdt' = dữ liệu NHÀ THẦU nộp (vd thời gian ký đơn dự thầu) -> ĐÁNH GIÁ Ở
                      BƯỚC SAU, hiện chưa có -> KHÔNG coi là thiếu, đặt thong_so._danh_gia_sau=true.
                  (KHÔNG bịa số.)
   3b sub-query : CHỈ cho sub_check có _need nguồn **hsmt** -> LLM **sinh sub-query** theo từng _need
                  -> retrieve_fn(query) nhắm đúng số thiếu (TCĐG→BDS). (bỏ qua nếu không có)
   3c resolve   : CHỈ khi có _need(hsmt) VÀ có bằng chứng -> LLM điền thong_so, bỏ _need; không
                  thấy/mơ hồ -> thong_so.can_review=true. _need(hsmt) còn sót -> ép can_review;
                  sub_check hsdt -> _danh_gia_sau (KHÔNG can_review). Lỗi LLM -> giữ tiêu chí +
                  can_review + loi_ai.
  ▼  collect tất cả DetailDoneEvent
[Assemble] -> StopEvent(GroupDecomposition)
```

> **Sửa (2026-06-29):** bản đầu dùng MỘT truy vấn ghép từ `crit.ten` *trước khi* biết sub_check
> nào cần ngưỡng -> query quá chung, không kéo đúng số, LLM phải vừa-đoán-cấu-trúc-vừa-điền ->
> kết quả kém. Bản này tách structure → sub-query theo `_need` → resolve để truy hồi bám đúng
> tham số còn thiếu. Có **logging tiến độ** ra console (stderr, `--quiet` để tắt).

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
      "criteria": [ /* CriterionDetailModel: nhom,ten,yeu_cau,required_artifacts,kieu,trong_so,
                       sub_checks:[{ten,check_type,thong_so,required_artifact,blocking}],proposed_artifacts */ ],
      "coverage": {"listed_n": 5, "final_n": 6, "added_by_critique": ["..."], "notes": "..."},
      "needs_review": [{"ten": "...", "ly_do": "không tra được giá trị bảo đảm dự thầu"}]
    }
    // nang_luc, ky_thuat (is_reference=true, criteria từ Phần 4), tai_chinh
  ],
  "summary": {"n_groups": 4, "n_criteria": 0, "n_needs_review": 0}
}
```
Kèm `decomposition.md` (người soi: mỗi nhóm → tiêu chí + sub_checks + cờ needs-review) và `decompose_report.md`.

## 7. Bố cục module — `backend/experiment/decompose/`

```
decompose/
  schema.py        GroupDecomposition, DecomposeResult, to_json/markdown helpers;
                   re-dùng CriterionDetailModel/validate_* từ services.ai_schemas
  llm.py           LlmFn protocol; default_llm_fn (bọc ai_call, no-silent-mock); ScriptedLlm (test)
  retrieval.py     RetrieveFn; default từ experiment.index (open index 1 lần, hybrid top-k);
                   resolve_reference(ref_target)->text ; subquery_bds(query)->hits
  prompts.py       system prompt: list / critique / structure / subquery / resolve (cot_block + SCALE_DEF)
  workflow.py      DecomposeWorkflow (LlamaIndex Workflow): ListCriteria/CritiqueCoverage/
                   DetailCriterion(fan-out)/Assemble + events
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
