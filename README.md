# ABES Demo — AI Bid Evaluation System

Demo hệ thống đánh giá hồ sơ dự thầu bằng AI (xem `docs/ABES_PRD_v1.0.docx`).

## Chạy backend
```bash
cd backend
pip install -r requirements.txt
ABES_AI_MOCK=1 uvicorn main:app --reload --port 8000   # mock, không cần GPU
```
Để chạy AI thật qua **LiteLLM Proxy** (OpenAI-compatible), đặt các biến môi trường (xem `backend/.env.example`):
```bash
export ABES_AI_MOCK=0
export ABES_AI_BASE_URL=https://proxy-cua-ban/v1   # URL kết thúc bằng /v1
export ABES_AI_API_KEY=sk-...                       # API key của proxy
export ABES_AI_MODEL=qwen3-27b                       # tên model trên proxy
uvicorn main:app --reload --port 8000
```
Nếu không đặt `ABES_AI_MOCK=0` (hoặc proxy lỗi/không kết nối được), hệ thống tự fallback sang mock.

## Chạy frontend
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Test
```bash
cd backend && pytest
```

## Luồng demo
Tạo gói thầu → upload HSMT + HSDT từng nhà thầu → "Chạy đánh giá AI" →
xem bảng xếp hạng & ma trận tiêu chí → override nếu cần → xuất báo cáo Word/Excel.

> OCR PDF scan yêu cầu cài Tesseract (`apt-get install tesseract-ocr tesseract-ocr-vie`).
