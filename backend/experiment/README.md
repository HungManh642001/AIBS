# experiment/ — Lõi thử nghiệm Agentic RAG (ABES)

Nơi prototype & nghiệm thu từng bước của pipeline Agentic RAG **trước khi** tích hợp
vào phần mềm chính (`backend/services/...`). Code ở đây được phép "bẩn", chạy bằng CLI,
in ra artefact để con người soi mắt thường — mục tiêu là **chứng minh từng bước hoạt
động** chứ chưa cần API/DB/test đầy đủ.

## Thứ tự các bước (theo blueprint đã thống nhất)
1. **Chunking phân cấp HSMT** ← đang ở bước này. Xem `PLAN_chunking_hierarchical.md`.
2. Embedding + index (Qdrant) + Hybrid Search — *sau*.
3. Định vị 4 nhóm TCĐG bằng RAG — *sau*.
4. Phân rã tiêu chuẩn nguyên tử — *sau*.
5. Truy vết tham chiếu ẩn (TCĐG→BDS) bằng sub-query — *sau*.
6. Đánh giá HSDT + audit trail — *sau*.

Mỗi bước: viết kế hoạch → người dùng review → triển khai → nghiệm thu bằng artefact →
mới sang bước kế.

## Quy ước
- Không đụng vào `services/` cho tới khi một bước được nghiệm thu và chốt tích hợp.
- Artefact đầu ra để trong `experiment/out/` (đã .gitignore khi cần).
- HSMT mẫu để trong `experiment/samples/` (KHÔNG commit file thầu thật/nhạy cảm).
