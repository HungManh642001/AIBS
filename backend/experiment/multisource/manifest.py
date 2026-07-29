"""Bỏ qua các bước CHUẨN BỊ khi đầu vào không đổi — chunk HSMT / extract Chương III / OCR scan.

Ba bước đó là HÀM THUẦN của file PDF đầu vào, nhưng đang chạy lại mỗi lần bóc tiêu chí. Đo trên
gói 54: chunk 33s + extract 32s + OCR 20s = 85s mỗi lần, cho ra đúng thứ đã có. Sau khi
embed_cache hạ bước dựng index xuống ~5s thì đây thành khối lãng phí lớn thứ hai sau decompose.

KHÓA VÔ HIỆU HOÁ gồm hai phần, thiếu phần nào cũng thành cache sai:

1. NỘI DUNG file PDF (hash bytes) — KHÔNG dùng mtime/tên: copy file làm mtime đổi mà nội dung y
   nguyên, và sửa file có thể giữ nguyên tên. Cache sai ở đây = dùng chunk của HSMT cũ cho HSMT
   mới, sai thầm lặng không gì báo.

2. MÃ NGUỒN của chính bước đó. Chunker và extractor đang được sửa liên tục; chỉ hash PDF thì sửa
   logic chunking xong chạy lại sẽ IM LẶNG dùng chunk cũ. Hash source sai về phía AN TOÀN: sửa cả
   comment cũng chạy lại — chậm hơn chứ không sai.

Bước OCR thêm TÊN MODEL vì nó gọi vision.

Bỏ qua chỉ khi khóa khớp VÀ artefact còn đủ trên đĩa — mất file là chạy lại, không tin khóa suông.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("experiment.multisource")

_TEN_FILE = "prepare_manifest.json"


def hash_file(path: str | Path) -> str:
    """Hash NỘI DUNG file (đọc theo khối, file HSMT có thể vài chục MB)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            h.update(khoi)
    return h.hexdigest()


def hash_ma_nguon(*thu_muc: str | Path) -> str:
    """Hash mọi file .py trong các thư mục — trừ tests và __pycache__.

    Sắp xếp theo đường dẫn để hash ổn định giữa các máy/hệ điều hành.
    """
    h = hashlib.sha256()
    files: list[Path] = []
    for d in thu_muc:
        p = Path(d)
        if p.is_file():
            files.append(p)
            continue
        files.extend(f for f in p.rglob("*.py")
                     if "__pycache__" not in f.parts and "tests" not in f.parts)
    for f in sorted(files, key=lambda x: x.as_posix()):
        h.update(f.as_posix().encode("utf-8"))
        h.update(b"\x00")
        h.update(f.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


class Manifest:
    """{tên bước: khóa} trên một file JSON trong workdir."""

    def __init__(self, out_dir: str | Path):
        self.path = Path(out_dir) / _TEN_FILE
        self._data: dict[str, str] = {}
        if self.path.is_file():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    self._data = {str(k): str(v) for k, v in d.items()}
            except (OSError, ValueError) as exc:
                log.warning("[manifest] không đọc được %s (%s) -> chạy lại mọi bước", self.path, exc)

    def con_moi(self, buoc: str, khoa: str, can_co: Iterable[str | Path]) -> bool:
        """Bước này bỏ qua được? Khóa phải khớp VÀ mọi artefact trong `can_co` phải còn."""
        if self._data.get(buoc) != khoa:
            return False
        thieu = [str(p) for p in can_co if not Path(p).exists()]
        if thieu:
            log.info("[manifest] %s: khóa khớp nhưng thiếu artefact %s -> chạy lại", buoc, thieu)
            return False
        return True

    def ghi(self, buoc: str, khoa: str) -> None:
        self._data[buoc] = khoa
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except OSError as exc:      # mất manifest chỉ tốn thời gian, không được làm hỏng run
            log.warning("[manifest] không ghi được %s: %s", self.path, exc)

    def bo(self, buoc: str) -> None:
        """Xoá khóa của một bước — dùng khi bước đó chạy lỗi, để lần sau không tin artefact dở."""
        if self._data.pop(buoc, None) is not None:
            self.ghi_lai()

    def ghi_lai(self) -> None:
        try:
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except OSError:
            pass


def khoa(*phan: Any) -> str:
    """Ghép các phần thành một khóa — có ngăn cách để 'ab'+'c' không đụng 'a'+'bc'."""
    h = hashlib.sha256()
    for p in phan:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()
