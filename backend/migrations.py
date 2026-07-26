"""Di trú SQLite nhẹ — ADD/DROP COLUMN idempotent (demo không dùng Alembic).

`Base.metadata.create_all` chỉ TẠO bảng thiếu, KHÔNG sửa bảng đã tồn tại. Hàm này vá hai chiều:

- THÊM cột model mới có mà DB cũ thiếu (`_COLUMNS`) — `ALTER TABLE ADD COLUMN`.
- XÓA cột model đã bỏ mà DB cũ còn (`_DROPPED`) — `ALTER TABLE DROP COLUMN` (SQLite ≥ 3.35).

Chiều xóa là bắt buộc chứ không phải dọn dẹp: cột cũ khai báo `NOT NULL` mà model không còn biết
tới sẽ làm MỌI INSERT thất bại (ca thật: vendor.ma_so_thue đổi tên thành ten_viet_tat ->
IntegrityError khi thêm nhà thầu). Test luôn chạy trên DB mới nên không bắt được lớp lỗi này.

Cột cần xóa phải KHAI BÁO RÕ trong `_DROPPED`, không tự suy ra bằng cách so với model: tự suy sẽ
xóa luôn cột do người vận hành cố ý thêm ngoài ORM. Chạy mỗi lần khởi động, sau create_all.
"""
from __future__ import annotations

import logging

from sqlalchemy import Engine

log = logging.getLogger("abes.migrations")

# {bảng: {cột: mệnh đề kiểu + default cho ADD COLUMN}}. Default hằng đơn giản (SQLite ADD COLUMN
# không nhận default động).
_COLUMNS: dict[str, dict[str, str]] = {
    "vendor": {"hinh_thuc": "VARCHAR(32) DEFAULT ''",
               "ten_viet_tat": "VARCHAR(255) DEFAULT ''"},
    "rubric_noi_dung": {"ap_dung": "VARCHAR(16) DEFAULT ''"},
    "hsdt_criterion_eval": {"yeu_cau_goc": "TEXT DEFAULT ''"},
    "hsdt_verdict": {"nguon_hsmt": "TEXT DEFAULT ''", "nguon_doc": "JSON DEFAULT '[]'"},
    "tender_document": {"ocr_key": "VARCHAR(96) DEFAULT ''", "ocr_pages": "JSON DEFAULT '[]'"},
}

# {bảng: {cột đã bỏ khỏi model}}. Khai báo khi XÓA/ĐỔI TÊN một cột, kèm cột thay thế ở _COLUMNS.
_DROPPED: dict[str, set[str]] = {
    "vendor": {"ma_so_thue"},   # -> ten_viet_tat (mã số thuế không còn dùng để khớp webform)
}


def _existing_cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def ensure_columns(engine: Engine) -> None:
    """Đồng bộ cột DB với model: thêm cột thiếu, xóa cột đã bỏ. Idempotent; bảng chưa có -> bỏ qua."""
    with engine.begin() as conn:
        tables = {r[0] for r in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, cols in _COLUMNS.items():
            if table not in tables:
                continue
            have = _existing_cols(conn, table)
            for col, ddl in cols.items():
                if col not in have:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

        for table, stale in _DROPPED.items():
            if table not in tables:
                continue
            for col in stale & _existing_cols(conn, table):
                # DROP COLUMN thất bại nếu cột nằm trong index/UNIQUE/PK. Không chặn khởi động:
                # báo rõ để xử lý tay, vì bỏ qua im lặng sẽ để lại lỗi INSERT khó truy.
                try:
                    conn.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {col}")
                    log.warning("[migrations] đã xóa cột cũ %s.%s", table, col)
                except Exception as exc:
                    log.error("[migrations] KHÔNG xóa được cột cũ %s.%s: %s — "
                              "nếu cột này NOT NULL, mọi INSERT vào %s sẽ lỗi",
                              table, col, exc, table)
