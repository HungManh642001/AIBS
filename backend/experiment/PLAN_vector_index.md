# Vector index Qdrant cho HSMT — Bản thiết kế

> Bước 2 của lõi Agentic RAG (theo `README.md`): **Embedding + index (Qdrant) + Hybrid Search**.
> Đầu vào: `out/chunks.jsonl` (185 chunk toàn HSMT). Đầu ra: collection Qdrant on-disk truy hồi
> được, phục vụ **bước phân rã tiêu chuẩn** và **lần tham chiếu** (Mục 3→Phần 4, TCĐG→BDS) sau này.

## 1. Mục tiêu

Biến chunk phân cấp đã có thành chỉ mục vector **hybrid** (dense + sparse), lưu kèm metadata đủ để
**lọc** (theo Phần/Chương, theo `node_type`, theo `group_hint`…). Bước sau dùng nó để:
- Lần `Mục 3 → Phần 4` (kỹ thuật) và `TCĐG → BDS` (tham chiếu ẩn) bằng truy hồi ngữ nghĩa + từ khóa.
- Cấp ngữ cảnh (RAG) cho việc phân rã từng nhóm thành tiêu chí nguyên tử.

## 2. Quyết định đã chốt (với user)

| Trục | Chốt |
|---|---|
| Orchestration | **LlamaIndex** (TextNode → QdrantVectorStore → VectorStoreIndex) |
| Nguồn **dense** embedding | Qua **LiteLLM proxy** `/v1/embeddings` (model `bge-m3`), nối bằng LlamaIndex **`OpenAILikeEmbedding`** — KHÔNG dùng lib litellm → giữ pin `litellm==1.41.0` & `ai_client` |
| Nguồn **sparse** (BM25) | **FastEmbed `Qdrant/bm25`**, chạy local, xác định, KHÔNG cần proxy |
| Phạm vi index | **Chỉ chương MANG GIÁ TRỊ** (E-BDL + E-CDNT + Yêu cầu kỹ thuật). Cập nhật 2026-06-30: BỎ **TCĐG (Chương III)** — nguồn tiêu chí, đã bóc ở list/analyze qua `chuong3_groups.json`, KHÔNG dùng index — và **Biểu mẫu** (mẫu trống, ~44% chunk, không có giá trị) vì gây nhiễu retrieve. `keep_for_index` lọc theo tiêu đề chương; `--all-sections` để tắt. (252→104 chunk, cắt ~45% đối thủ nhiễu cho query giá trị.) |
| Kiểu tìm kiếm | **Hybrid** dense + sparse, hợp nhất bằng **RRF** |
| Triển khai Qdrant | **Embedded on-disk** `QdrantClient(path="out/qdrant/")` — zero infra |
| Vị trí deps | `experiment/requirements-experiment.txt` (KHÔNG đụng `services/`) |

## 3. Ràng buộc then chốt: proxy đang TẮT ở máy dev

Dense embedding cần proxy sống. Thiết kế tách để **mọi thứ trừ dense đều thật & chạy offline**:

- **Dense**: `ProxyEmbedder` gọi `litellm.embedding(model="openai/bge-m3", api_base=ai_base_url …)`.
  Lỗi (proxy tắt) → **báo lỗi rõ, KHÔNG bịa vector** (đúng triết lý no-silent-mock của `ai_client`).
- **Sparse / BM25**: local, xác định → chạy & test được ngay hôm nay.
- **Test**: tiêm `FakeEmbedder` (hash văn bản → vector cố định, dim 256) để **toàn pipeline xanh
  offline**. `FakeEmbedder` CHỈ dùng trong test, không bao giờ trong chế độ thật.

Hệ quả nghiệm thu (xem §9): **chất lượng từ khóa (BM25/sparse) nghiệm thu THẬT & offline ngay**;
chất lượng **dense + hybrid** soi mắt khi proxy bật (lệnh + kỳ vọng ghi sẵn).

## 4. Bố cục module — `backend/experiment/index/`

```
index/
  schema.py        chunk dict -> TextNode (id_=uuid5(chunk_id) → idempotent; metadata = payload;
                   excluded_embed_metadata_keys = tất cả key metadata → CHỈ embed text chunk).
                   Hằng số: COLLECTION="hsmt_chunks", FAKE_DIM=256
  embedder.py      build_embedder(settings) -> OpenAILikeEmbedding(model_name="bge-m3",
                   api_base=ai_base_url, api_key=…, is_chat_model=False)
                   DeterministicEmbedding(BaseEmbedding): hash text -> unit vector dim FAKE_DIM (chỉ test)
  store.py         build_vector_store(client) -> QdrantVectorStore(enable_hybrid=True,
                   fastembed_sparse_model="Qdrant/bm25"); build_index(nodes, store, embed)
                   -> VectorStoreIndex; open_index(store, embed) -> from_vector_store;
                   hybrid_retriever(index, k) -> retriever(vector_store_query_mode="hybrid")
  build_index.py   CLI: chunks.jsonl -> nodes -> VectorStoreIndex (out/qdrant/) + out/index_report.md
  query_index.py   CLI: query -> hybrid retrieve top-k ; in score/page/section_path/snippet
  tests/
    conftest.py        sample_chunks fixture (đọc out/chunks.jsonl, skip nếu vắng); det_embedder
    test_schema.py     uuid5 ổn định/idempotent; metadata round-trip; embed-exclusion phủ hết key
    test_store.py      :memory: + DeterministicEmbedding + BM25 thật: build + hybrid_retriever trả node
    test_hybrid.py     node khớp keyword nổi top (BM25 thật, dense xác định) → sparse kéo recall
    test_build_e2e.py  sample-gated, det embedder: build -> 185 điểm, query trả kết quả, có report
```

## 5. Luồng dữ liệu

```
chunks.jsonl ──> [build_index]
   mỗi chunk -> TextNode(text, metadata, id_=uuid5(chunk_id))
        ▼
   VectorStoreIndex(nodes, storage=QdrantVectorStore(enable_hybrid), embed_model)
        ├─ dense  = OpenAILikeEmbedding(bge-m3)  (proxy; thật khi bật / det khi test)
        └─ sparse = FastEmbed Qdrant/bm25        (local; luôn chạy)
        ▼
   Qdrant on-disk (out/qdrant/) collection "hsmt_chunks"  (LlamaIndex tự tạo 2 vector + IDF)

query ──> [query_index] ──> open_index(store).as_retriever(mode="hybrid", top_k=k)
          ──> top-k NodeWithScore {score, node.text, node.metadata}  ──> in bảng người soi
```

## 6. Cơ chế Hybrid (LlamaIndex + Qdrant native)

- `QdrantVectorStore(enable_hybrid=True, fastembed_sparse_model="Qdrant/bm25")` tự dựng collection 2
  vector (dense COSINE + sparse BM25/IDF) và hợp nhất bằng **RRF** — không phải tự gọi `query_points`.
- Truy hồi: `index.as_retriever(vector_store_query_mode="hybrid", similarity_top_k=k)`.
- Dim dense do LlamaIndex/QdrantVectorStore tự suy từ embedding (không hardcode); DeterministicEmbedding = 256.

## 7. Payload schema (lưu nguyên metadata chunk để lọc)

```jsonc
{
  "chunk_id": "E-HSMT-0001", "doc": "E-HSMT", "text": "…",
  "section_path": [...], "chapter_no": null, "section_title": null,
  "level": 0, "heading_number": null,
  "page_start": 1, "page_end": 3,
  "node_type": "text", "group_hint": "unknown", "char_len": 1800
}
```
Bước sau lọc được: `node_type=="table"`, `group_hint=="ky_thuat"`, theo dải trang Phần 4, v.v.

## 8. Config & deps

- `experiment/requirements-experiment.txt`: `llama-index-core`, `llama-index-vector-stores-qdrant`,
  `llama-index-embeddings-openai-like`, `qdrant-client`, `fastembed` (CPU; KHÔNG dùng lib litellm).
- `config.py`: **chỉ thêm** `ai_embed_model: str = "bge-m3"`; **tái dùng** `ai_base_url`, `ai_api_key`.
  (Lưu ý: `config.py` đang có thay đổi chưa commit — chỉ thêm field, không sửa dòng khác.)
- FastEmbed `Qdrant/bm25` tải artefact nhỏ (~vài MB) lần đầu (cần internet 1 lần; proxy tắt ≠ mất net).

## 9. Nghiệm thu

**Offline (làm ngay, THẬT trừ dense):**
- Toàn bộ test xanh không cần proxy (FakeEmbedder + BM25 thật + Qdrant `:memory:`).
- `build_index` với FakeEmbedder: collection `hsmt_chunks` có **185 điểm**, `out/index_report.md`
  ghi {n_points, dense_dim, sparse=true, elapsed}.
- `query_index` BM25/sparse THẬT: ví dụ "bảo đảm dự thầu" → nổi section hợp lệ (Chương III/Mục 1);
  "phụ lục kỹ thuật" → nổi chunk Phần 4. (Soi mắt, không cần proxy.)

**Khi proxy bật (ghi sẵn lệnh, soi mắt sau):**
- `build_index` thật → dense thật; `query_index` hybrid: truy vấn ngữ nghĩa (vd "doanh thu bình
  quân 3 năm") trả đúng mục năng lực tài chính dù không trùng từ khóa.
- Nếu proxy tắt mà chạy chế độ thật → CLI **exit lỗi rõ ràng**, KHÔNG tạo collection rỗng/giả.

## 10. Ngoài phạm vi (YAGNI — để bước sau)

- Lần tham chiếu thực tế (Mục 3→Phần 4, TCĐG→BDS) và phân rã tiêu chí — bước 4/5.
- Tinh chỉnh tokenizer tiếng Việt cho BM25, re-ranker, tối ưu trọng số fusion — khi có nhu cầu thật.
- Đẩy embedding/index vào `services/` (production) — chỉ sau khi bước này được nghiệm thu & chốt.
- Bảng tách ô (đang dùng text serialize của chunk; truy hồi để định vị là đủ, cấu trúc do extract lib).
```
