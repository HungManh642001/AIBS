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
[Step 2 analyze] (song song)  CHỈ từ tiêu chí (KHÔNG đưa source toàn nhóm -> tránh nhiễu). LLM xác định
                tien_quyet + **noi_dung_can_kiem_tra** — checklist cần kiểm trên hsdt_can_kiem_tra. Mỗi
                nội dung {noi_dung, yeu_cau, can_tra_cuu}: yeu_cau = chuẩn HSMT để đối chiếu;
                nếu là giá trị HSMT định nghĩa ở CHỖ KHÁC (E-BDL) -> để trống yeu_cau + can_tra_cuu=true.
                (KHÔNG bịa số.)
  ▼  SearchEvent(crit, item)
[Step 3 search] (song song)  Với MỖI nội dung can_tra_cuu còn TRỐNG thong_tin_bo_sung -> ĐỘC LẬP: sinh 1
                query cho **can_lam_ro** (LLM MỞ RỘNG nghiệp vụ: đồng nghĩa/nơi-nằm, 'đơn vị thụ hưởng'≈
                'chủ đầu tư') + NEO mã điều khoản (vd '18.3'+'18'). Truy hồi: **ưu tiên E-BDL**
                (clause_doc='bdl', k=8) GỘP tra chung (k=3) -> resolve RIÊNG -> điền **thong_tin_bo_sung**
                (tự đủ + quan hệ so sánh) + **nguon** (mã điều khoản). Vẫn trống -> can_review (no-fab).
  ▼  collect tất cả DoneEvent
[Step 4 collect] -> StopEvent(GroupDecomposition)
```

> **Sửa (2026-06-30):** (a) output PHẲNG — bỏ `sub_checks/thong_so` máy-so-sánh (Qwen3 tự đánh giá
> thông số). Tiêu chí: nhom, ten, **yeu_cau_goc**, **hsdt_can_kiem_tra**, tien_quyet,
> **noi_dung_can_kiem_tra**[{noi_dung, yeu_cau, can_tra_cuu, can_review}]. (b) workflow gọn:
> `yeu_cau_goc` lên **step 1**; tách `detail` thành **analyze**+**search**; **critique có điều kiện**
> (chỉ nhóm bảng). (c) **step 2 bỏ source** (chỉ dùng yeu_cau_goc của tiêu chí — source toàn nhóm gây
> nhiễu); `noi_dung` schema dùng **can_tra_cuu** (bool) thay `nguon` (trigger tra cứu rõ ràng, vẫn chỉ
> tra phía HSMT). (d) **step 3 tra ĐỘC LẬP từng need** (query+retrieve+resolve riêng mỗi need, 1 call 1
> việc — hết nhiễu chéo do gộp evidence). max_tokens=8192 (Qwen3 có khối &lt;think&gt;).

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
        "hsdt_can_kiem_tra": ["bao_lanh_du_thau"], "tien_quyet": true,
        "noi_dung_can_kiem_tra": [
          {"noi_dung_kiem_tra":"Giá trị bảo lãnh","hsdt_kiem_tra":"bao_lanh_du_thau","yeu_cau":"Thỏa mãn giá trị bảo lãnh theo HSMT","can_lam_ro":"","can_tra_cuu":true,"thong_tin_bo_sung":"Giá trị bảo lãnh: 6.100.000 VNĐ","nguon":"E-BDL 18.2","can_review":false},
          {"noi_dung_kiem_tra":"Thời gian hiệu lực","hsdt_kiem_tra":"bao_lanh_du_thau","yeu_cau":"Thỏa mãn thời gian hiệu lực theo HSMT","can_lam_ro":"","can_tra_cuu":true,"thong_tin_bo_sung":"Thời gian hiệu lực: ≥ 120 ngày","nguon":"E-BDL 18.2","can_review":false},
          {"noi_dung_kiem_tra":"Đơn vị thụ hưởng","hsdt_kiem_tra":"bao_lanh_du_thau","yeu_cau":"Thỏa mãn đơn vị thụ hưởng theo HSMT","thong_tin_bo_sung":"Đơn vị thụ hưởng: Liên doanh Việt - Nga Vietsovpetro","nguon":"E-BDL 1.1","can_review":false}
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
  retrieval.py     RetrieveFn; default từ experiment.index (open index 1 lần, hybrid top-k)
  refs.py          extract_clause_refs(text) -> mã điều khoản (E-CDNT/E-BDL/Mục N) để neo vào query
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
