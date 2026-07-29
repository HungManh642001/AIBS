"""Cache vector embedding theo NỘI DUNG chunk — bỏ hẳn việc nhúng lại thứ đã nhúng.

Vì sao cần: index bị dựng LẠI TỪ ĐẦU mỗi lần chạy rubric. Khi sửa prompt rồi chạy lại (việc làm
liên tục lúc tinh chỉnh), chunk HSMT không đổi một chữ nhưng vẫn phải nhúng lại toàn bộ. Đo trên
gói 62: dựng index 60.49s, trong đó phần KHÔNG phải Ollama chỉ 4.25s -> Ollama chiếm 93%, tức
236ms cho MỖI embedding. Đó là 56s trả lại y nguyên kết quả cũ, mỗi lần chạy.

Vì sao KHÔNG phải chuyện batch: `embed_batch_size` 10 -> 64 (38 -> 6 round-trip HTTP) chỉ nhanh
7.6% (276 -> 255 ms/chunk). Chi phí nằm trong tính toán của Ollama chứ không ở vòng mạng, nên
đòn bẩy đúng là ĐỪNG TÍNH LẠI, không phải gộp request.

Chỗ nối: LlamaIndex `embed_nodes` BỎ QUA node đã có `.embedding`. Nên chỉ cần điền sẵn vector từ
cache vào node trước khi dựng index, phần còn thiếu để nó tự nhúng như thường.

KHÓA = hash(tên model + ĐÚNG chuỗi sẽ được nhúng). Chuỗi đó là
`node.get_content(metadata_mode=MetadataMode.EMBED)` — KHÔNG phải `node.text`: metadata cũng vào
embedding, dùng nhầm text sẽ trả về vector của một nội dung khác.
"""
from __future__ import annotations

import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any

from llama_index.core.schema import MetadataMode

log = logging.getLogger("experiment.index")

_TEN_FILE = "embed_cache.pkl"


def cache_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _TEN_FILE


def noi_dung_nhung(node: Any) -> str:
    """ĐÚNG chuỗi mà LlamaIndex sẽ đưa đi nhúng (gồm cả metadata theo chế độ EMBED)."""
    return node.get_content(metadata_mode=MetadataMode.EMBED)


def khoa_node(model: str, node: Any) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(noi_dung_nhung(node).encode("utf-8"))
    return h.hexdigest()


class EmbedCache:
    """{khóa: vector} trên một file pickle. Vector là list[float] nên không cần numpy."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict[str, list[float]] = {}
        if self.path.is_file():
            try:
                with open(self.path, "rb") as f:
                    d = pickle.load(f)
                if isinstance(d, dict):
                    self._data = d
            except (OSError, pickle.PickleError, EOFError, AttributeError) as exc:
                log.warning("[embed-cache] không đọc được %s (%s) -> bỏ qua cache", self.path, exc)

    def get(self, key: str) -> list[float] | None:
        return self._data.get(key)

    def put_nhieu(self, cap: dict[str, list[float]]) -> None:
        """Ghi theo LÔ (1 lần/run) — vector to, ghi từng cái sẽ tự bóp cổ chính nó."""
        if not cap:
            return
        self._data.update(cap)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as f:
                pickle.dump(self._data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError as exc:
            log.warning("[embed-cache] không ghi được %s: %s", self.path, exc)

    def __len__(self) -> int:
        return len(self._data)


def gan_embedding(nodes: list[Any], embed: Any, cache: EmbedCache) -> dict[str, int]:
    """Điền `.embedding` cho nodes: lấy từ cache, phần thiếu thì nhúng thật rồi lưu lại.

    Sửa nodes TẠI CHỖ. Trả {trung, nhung} để bên gọi ghi vào report.
    """
    model = getattr(embed, "model_name", "") or embed.__class__.__name__
    khoa = [khoa_node(model, n) for n in nodes]

    thieu_idx = []
    for i, (n, k) in enumerate(zip(nodes, khoa)):
        v = cache.get(k)
        if v is None:
            thieu_idx.append(i)
        else:
            n.embedding = list(v)

    if thieu_idx:
        texts = [noi_dung_nhung(nodes[i]) for i in thieu_idx]
        vecs = embed.get_text_embedding_batch(texts)
        moi: dict[str, list[float]] = {}
        for i, v in zip(thieu_idx, vecs):
            nodes[i].embedding = v
            moi[khoa[i]] = list(v)
        cache.put_nhieu(moi)

    return {"trung": len(nodes) - len(thieu_idx), "nhung": len(thieu_idx)}
