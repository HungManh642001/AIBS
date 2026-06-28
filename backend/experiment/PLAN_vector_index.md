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
| Nguồn **dense** embedding | Qua **LiteLLM proxy** `/v1/embeddings` (model `bge-m3`) — như `ai_client` |
| Nguồn **sparse** (BM25) | **FastEmbed `Qdrant/bm25`**, chạy local, xác định, KHÔNG cần proxy |
| Phạm vi index | **Toàn bộ HSMT** (185 chunk) — vì đích tham chiếu nằm NGOÀI Chương III |
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
  schema.py        IndexPoint, payload schema, hằng số collection (tên, dim fake, tên vector)
                   point id = uuid5(NAMESPACE, chunk_id) → upsert idempotent (build lại không nhân đôi)
  embedder.py      ProxyEmbedder (litellm.embedding; batch; retry 1 lần; raise khi fail; probe dim)
                   FakeEmbedder (xác định, offline, chỉ test)
  sparse.py        Bm25Encoder (FastEmbed "Qdrant/bm25") -> SparseVector (indices, values)
  store.py         VectorStore: create_collection / upsert_points / hybrid_search
  build_index.py   CLI: chunks.jsonl -> collection + out/index_report.md ; run()/main()
  query_index.py   CLI: query string -> top-k hybrid ; in score/page/section_path/snippet
  tests/
    conftest.py        sample_chunks fixture (đọc out/chunks.jsonl, skip nếu vắng); fake_embedder
    test_schema.py     point id ổn định/idempotent; payload round-trip (inline)
    test_sparse.py     BM25 ra sparse khác rỗng; cùng input -> cùng output (offline, THẬT)
    test_store.py      :memory: + FakeEmbedder + BM25 thật: create/upsert/search trả đúng số điểm
    test_hybrid.py     fusion RRF: điểm khớp keyword nổi lên (BM25 thật, dense fake)
    test_build_e2e.py  sample-gated, FakeEmbedder: build -> 185 điểm, query trả kết quả, có report
```

## 5. Luồng dữ liệu

```
chunks.jsonl ──> [build_index]
   mỗi chunk: text + payload(metadata)
        │
        ├─ dense  = ProxyEmbedder.embed([text...])      (proxy; thật khi bật)
        ├─ sparse = Bm25Encoder.encode([text...])       (local; luôn chạy)
        └─ id     = uuid5(chunk_id)
        ▼
   VectorStore.upsert_points(points)  ──>  Qdrant on-disk (out/qdrant/)
                                            collection "hsmt_chunks"
                                              vectors: { dense: cosine, size=dim }
                                              sparse_vectors: { sparse: Modifier.IDF }

query ──> [query_index] ──> VectorStore.hybrid_search(q, k)
            dense_q  = embed(q)        sparse_q = bm25(q)
            query_points(prefetch=[dense NN, sparse NN], FusionQuery(RRF))
          ──> top-k {score, payload}  ──> in bảng người soi
```

## 6. Cơ chế Hybrid (Qdrant native)

- Collection 2 vector có tên: `dense` (Distance.COSINE, size = dim probe được; Fake=256) và
  `sparse` (sparse vector với `models.Modifier.IDF` → Qdrant tự tính IDF kiểu BM25 server-side).
- Truy vấn: `client.query_points(collection, prefetch=[Prefetch(query=dense, using="dense", limit=k*4),
  Prefetch(query=SparseVector, using="sparse", limit=k*4)], query=FusionQuery(fusion=RRF), limit=k)`.
- Dim dense **probe** từ 1 lần embed lúc tạo collection (không hardcode), trừ FakeEmbedder = 256.

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

- `experiment/requirements-experiment.txt`: `qdrant-client`, `fastembed` (CPU; litellm đã có).
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
