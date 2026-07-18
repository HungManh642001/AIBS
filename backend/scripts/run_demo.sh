#!/usr/bin/env bash
# Chạy backend ở chế độ DEMO (không cần LiteLLM proxy) — dùng khi xem thử giao diện.
#
#   cd backend && bash scripts/run_demo.sh
#
# ABES_AI_MOCK=1: các bước cần AI trả lỗi NGAY thay vì chờ timeout 300s tới proxy không tồn tại.
# Không có nghĩa là AI chạy được — bóc tiêu chí và chấm HSDT vẫn cần proxy thật.
#
# --host 0.0.0.0 là bắt buộc khi frontend chạy trên Windows còn backend trong WSL: cổng chỉ bind
# 127.0.0.1 trong WSL thì trình duyệt Windows không tới được.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f abes_demo.db ]; then
  echo "Chưa có DB — chạy seed trước..."
  python3 scripts/seed_demo.py
fi

echo "Backend: http://localhost:8000/api/v1  (docs: http://localhost:8000/docs)"
ABES_AI_MOCK=1 exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
