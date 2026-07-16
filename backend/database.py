"""SQLAlchemy engine + session cho SQLite (demo)."""
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings

settings = get_settings()
engine = create_engine(
    settings.db_url, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    import models  # noqa: F401  (đăng ký mapping)
    from migrations import ensure_columns
    Base.metadata.create_all(bind=engine)   # tạo bảng mới
    ensure_columns(engine)                  # vá cột mới vào bảng cũ (không mất dữ liệu)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
