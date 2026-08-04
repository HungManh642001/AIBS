"""Lưu trữ file trên local filesystem (demo). Production -> MinIO."""
from pathlib import Path

from config import get_settings

STORAGE_DIR: Path = get_settings().storage_dir

# Cấm trên NTFS/Windows (ext4 chỉ cấm '/' và NUL, nhưng storage demo hay nằm trên ổ Windows).
_KY_TU_CAM = set('<>:"|?*')
TEN_DU_PHONG = "tai_lieu"
TRAN_BYTE_TEN = 200   # dưới trần 255 byte của ext4/NTFS, chừa chỗ cho hậu tố chống trùng về sau


def _safe(name: str) -> str:
    """Tên file an toàn cho filesystem mà GIỮ NGUYÊN chữ người dùng đặt.

    Trước đây whitelist [A-Za-z0-9._-] nên mọi ký tự có dấu VÀ dấu cách đều thành '_':
    "1. ĐƠN DỰ THẦU.pdf" -> "1.__N_D__TH_U.pdf". Chuyên gia không nhận ra file mình vừa tải, và
    tên hỏng đó còn theo `Path(file_path).name` đi thẳng vào bằng chứng của báo cáo.

    Chỉ chặn đúng thứ nguy hiểm: mọi thành phần đường dẫn (chống path traversal), ký tự cấm của
    filesystem, và ký tự điều khiển. Tiếng Việt có dấu, dấu cách, ngoặc... đều giữ nguyên.
    """
    ten = name.replace("\\", "/").split("/")[-1]          # bỏ MỌI thành phần đường dẫn
    ten = "".join(c for c in ten if c.isprintable() and c not in _KY_TU_CAM)
    ten = ten.strip().strip(".")                          # '..' và '.' hết là tên hợp lệ
    if not ten:
        return TEN_DU_PHONG
    return _cat_theo_byte(ten)


def _cat_theo_byte(ten: str) -> str:
    """Cắt cho vừa trần byte của filesystem, cắt THÂN tên và giữ phần mở rộng.

    Tiếng Việt 3 byte/ký tự nên tên dài vượt trần rất dễ; cắt nhầm vào đuôi thì file mất phần mở
    rộng và không mở được nữa. Cắt thẳng bằng slice ký tự (không phải byte) để không xé đôi ký tự.
    """
    if len(ten.encode("utf-8")) <= TRAN_BYTE_TEN:
        return ten
    duoi = Path(ten).suffix[:20]                          # đuôi lạ dài bất thường -> cắt bớt
    than = ten[: len(ten) - len(Path(ten).suffix)]
    while than and len((than + duoi).encode("utf-8")) > TRAN_BYTE_TEN:
        than = than[:-1]
    return (than + duoi) or TEN_DU_PHONG


def save_upload(package_id: int, filename: str, content: bytes, subdir: str) -> str:
    rel_dir = Path(str(package_id)) / subdir
    target_dir = STORAGE_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    rel = rel_dir / _safe(filename)
    (STORAGE_DIR / rel).write_bytes(content)
    return str(rel).replace("\\", "/")


def abs_path(rel: str) -> Path:
    return STORAGE_DIR / rel.replace("\\", "/")


def read_bytes(rel: str) -> bytes:
    return (STORAGE_DIR / rel.replace("\\", "/")).read_bytes()


def remove(rel: str) -> None:
    """Xóa file (bỏ qua nếu không tồn tại) — dùng khi xóa tài liệu/nhà thầu."""
    abs_path(rel).unlink(missing_ok=True)
