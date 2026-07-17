"""Di trú SQLite nhẹ — ADD COLUMN idempotent (demo không dùng Alembic).

`Base.metadata.create_all` chỉ TẠO bảng thiếu, KHÔNG thêm cột vào bảng đã tồn tại. Khi model thêm
cột mới, DB cũ sẽ thiếu -> hàm này vá bằng `ALTER TABLE ADD COLUMN`. Chạy mỗi lần khởi động, sau
create_all: idempotent (kiểm PRAGMA trước mỗi ALTER), giữ nguyên dữ liệu, bỏ qua bảng chưa có.
"""
from __future__ import annotations

from sqlalchemy import Engine

# {bảng: {cột: mệnh đề kiểu + default cho ADD COLUMN}}. Default hằng đơn giản (SQLite ADD COLUMN
# không nhận default động).
_COLUMNS: dict[str, dict[str, str]] = {
    "vendor": {"hinh_thuc": "VARCHAR(32) DEFAULT ''",
               "ten_viet_tat": "VARCHAR(255) DEFAULT ''"},
    "rubric_noi_dung": {"ap_dung": "VARCHAR(16) DEFAULT ''"},
    "hsdt_criterion_eval": {"yeu_cau_goc": "TEXT DEFAULT ''"},
    "hsdt_verdict": {"nguon_hsmt": "TEXT DEFAULT ''", "nguon_doc": "JSON DEFAULT '[]'"},
}


def _existing_cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def ensure_columns(engine: Engine) -> None:
    """Thêm các cột còn thiếu (idempotent). Bảng chưa tồn tại -> bỏ qua."""
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
