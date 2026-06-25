# ABES - AI Bid Evaluation System (Demo)

## Mục tiêu dự án
Hệ thống demo hỗ trợ đánh giá hồ sơ dự thầu bằng AI, phục vụ tổ chuyên gia đấu thầu nội bộ.

## Tech Stack
- Backend: Python + FastAPI
- Frontend: React + Vite + TailwindCSS + Ant Design
- AI: LiteLLM Proxy -> Qwen3 27B (local via vLLM, fallback: mock responses)
- OCR: PyMuPDF (pdf text) + Tesseract (pdf scan)
- DB: SQLite (demo) -> PostgreSQL (production)
- Storage: local filesystem (demo) -> MinIO (production)
- Report: python-docx + openpyxl

## Luồng nghiệp vụ chính (demo)
1. Upload HSMT (PDF) -> OCR -> trích xuất tiêu chí đánh giá
2. Upload HSDT từng nhà thầu (PDF/Excel)
3. AI đánh giá 4 module: Hợp lệ / Năng lực / Kỹ thuật / Tài chính
4. Tổng hợp kết quả, sinh báo cáo Word + Excel

## Conventions
- Python: snake_case, type hints bắt buộc, tuân thủ chuẩn PEP 8
- API: RESTful, response format {"success": bool, "data": ..., "error": ...}
- Async: dùng async/await cho tất cả I/O
- Luôn viết unit test cho business logic
- Tiếng Việt trong UI/comments, tiếng Anh trong code

## Commands
- Start backend: cd backend && uvicorn main:app --reload --port 8000
- Start frontend: cd frontend && npm run dev
- Run tests: cd backend && pytest
- Install backend: cd backend && pip install -r requirements.txt