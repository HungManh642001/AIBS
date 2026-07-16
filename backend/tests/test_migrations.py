"""Migration ADD COLUMN idempotent — vá bảng cũ khi thêm cột, KHÔNG mất dữ liệu (không Alembic)."""
from sqlalchemy import create_engine, text

from migrations import ensure_columns


def _cols(engine, table: str) -> set[str]:
    with engine.connect() as c:
        return {r[1] for r in c.exec_driver_sql(f"PRAGMA table_info({table})")}


def test_ensure_columns_adds_missing_and_preserves_data(tmp_path):
    db = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db}")
    # Dựng schema CŨ: vendor thiếu hinh_thuc, có sẵn 1 dòng dữ liệu.
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE vendor (id INTEGER PRIMARY KEY, ten VARCHAR, ma_so_thue VARCHAR)")
        c.exec_driver_sql("INSERT INTO vendor (id, ten, ma_so_thue) VALUES (1, 'Cty A', '0312')")
        c.exec_driver_sql("CREATE TABLE hsdt_verdict (id INTEGER PRIMARY KEY, ket_qua VARCHAR)")
        c.exec_driver_sql("CREATE TABLE hsdt_criterion_eval (id INTEGER PRIMARY KEY, ten VARCHAR)")

    ensure_columns(engine)

    assert "hinh_thuc" in _cols(engine, "vendor")
    assert {"nguon_hsmt", "nguon_doc"} <= _cols(engine, "hsdt_verdict")
    assert "yeu_cau_goc" in _cols(engine, "hsdt_criterion_eval")
    # Dữ liệu cũ CÒN NGUYÊN
    with engine.connect() as c:
        row = c.exec_driver_sql("SELECT ten, ma_so_thue FROM vendor WHERE id=1").fetchone()
    assert row == ("Cty A", "0312")


def test_ensure_columns_idempotent(tmp_path):
    db = tmp_path / "x.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE vendor (id INTEGER PRIMARY KEY, ten VARCHAR)")
        c.exec_driver_sql("CREATE TABLE hsdt_verdict (id INTEGER PRIMARY KEY)")
        c.exec_driver_sql("CREATE TABLE hsdt_criterion_eval (id INTEGER PRIMARY KEY)")
    ensure_columns(engine)
    ensure_columns(engine)   # lần 2 KHÔNG lỗi
    assert "hinh_thuc" in _cols(engine, "vendor")


def test_ensure_columns_skips_missing_tables(tmp_path):
    """Bảng chưa tồn tại (DB trống trước create_all) -> bỏ qua, không lỗi."""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    ensure_columns(engine)   # không có bảng nào -> im lặng
