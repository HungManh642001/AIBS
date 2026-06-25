# ABES Demo — AI Bid Evaluation System

Demo hệ thống đánh giá hồ sơ dự thầu bằng AI (xem `docs/ABES_PRD_v1.0.docx`).

## Chạy backend
```bash
cd backend
pip install -r requirements.txt
ABES_AI_MOCK=1 uvicorn main:app --reload --port 8000   # mock, không cần GPU
```
Bỏ `ABES_AI_MOCK=1` và đặt `ABES_AI_BASE_URL` tới LiteLLM proxy (Qwen3 qua vLLM) để chạy AI thật.

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
