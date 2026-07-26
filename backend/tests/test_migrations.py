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
    # Dữ liệu ở các cột CÒN LẠI vẫn nguyên (ma_so_thue bị xóa theo _DROPPED — xem test riêng bên dưới).
    with engine.connect() as c:
        row = c.exec_driver_sql("SELECT id, ten FROM vendor WHERE id=1").fetchone()
    assert row == (1, "Cty A")


def test_ensure_columns_them_cot_cache_ocr_giu_nguyen_tai_lieu(tmp_path):
    """DB cũ (trước tính năng cache OCR) phải được vá cột, tài liệu đã tải KHÔNG mất dữ liệu."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as c:
        c.exec_driver_sql(
            "CREATE TABLE tender_document (id INTEGER PRIMARY KEY, file_path VARCHAR, "
            "artifact_type VARCHAR)")
        c.exec_driver_sql(
            "INSERT INTO tender_document (id, file_path, artifact_type) "
            "VALUES (1, '1/hsdt/1/don.pdf', 'don_du_thau')")

    ensure_columns(engine)

    assert {"ocr_key", "ocr_pages"} <= _cols(engine, "tender_document")
    with engine.connect() as c:
        row = c.exec_driver_sql(
            "SELECT file_path, artifact_type, ocr_key, ocr_pages FROM tender_document").fetchone()
    assert row == ("1/hsdt/1/don.pdf", "don_du_thau", "", "[]")   # cache rỗng -> OCR lần chấm tới


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


def test_ensure_columns_drops_stale_column(tmp_path):
    """Cột đã bỏ khỏi model nhưng còn NOT NULL trong DB cũ -> chặn mọi INSERT -> phải xóa.

    Ca thật: vendor.ma_so_thue đổi tên thành ten_viet_tat; ADD COLUMN không gỡ cột cũ nên
    INSERT thiếu ma_so_thue là IntegrityError.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
    with engine.begin() as c:
        c.exec_driver_sql(
            "CREATE TABLE vendor (id INTEGER PRIMARY KEY, package_id INTEGER, ten VARCHAR, "
            "ma_so_thue VARCHAR(32) NOT NULL)")
        c.exec_driver_sql(
            "INSERT INTO vendor (id, package_id, ten, ma_so_thue) VALUES (1, 1, 'Cty A', '0312')")

    ensure_columns(engine)

    assert "ma_so_thue" not in _cols(engine, "vendor")
    assert {"ten_viet_tat", "hinh_thuc"} <= _cols(engine, "vendor")
    # Dữ liệu của các cột CÒN LẠI phải nguyên vẹn.
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT ten FROM vendor WHERE id=1").fetchone() == ("Cty A",)
    # INSERT theo model mới (không có ma_so_thue) phải chạy được.
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO vendor (package_id, ten, ten_viet_tat, hinh_thuc) VALUES (1, 'B', 'B', '')")


def test_ensure_columns_giu_cot_ngoai_model(tmp_path):
    """Chỉ xóa cột nằm trong danh sách khai báo rõ — KHÔNG tự ý xóa cột lạ."""
    engine = create_engine(f"sqlite:///{tmp_path / 'keep.db'}")
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE vendor (id INTEGER PRIMARY KEY, ten VARCHAR, ghi_chu_rieng VARCHAR)")
    ensure_columns(engine)
    assert "ghi_chu_rieng" in _cols(engine, "vendor")
