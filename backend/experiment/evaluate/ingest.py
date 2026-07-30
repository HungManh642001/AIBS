"""Tầng A — ingest HSDT: mỗi trang -> text (+ cờ thị giác nếu phải đọc ảnh).

Loại hồ sơ (loai_ho_so) ĐÃ BIẾT khi tải file (truyền vào theo từng file), KHÔNG để LLM phân loại.

HAI ĐƯỜNG ĐỌC, chọn theo TỪNG TRANG (một file hay có cả hai: 5 trang bảng sạch + 1 trang ký):
- trang có text nhúng và KHÔNG có ảnh nhúng -> `pdf_text.trich_trang_tat_dinh`: chính xác 100%,
  tái lập tuyệt đối, 0 call, KHÔNG render ảnh. Đây là cách diệt gốc chuyện vision đọc bảng lúc
  đúng lúc sai (đo trên hồ sơ thật: 34/126 trang, gồm TOÀN BỘ bảng giá có text nhúng);
- còn lại (bản scan, hoặc trang có ảnh = có thể có chữ ký/dấu) -> vision đọc ảnh như trước.

CACHE (tùy chọn, inject qua `cache`): vision đọc ảnh là bước ĐẮT NHẤT — mỗi trang 1 call, chấm
lại một nhà thầu là OCR lại toàn bộ hồ sơ. Khóa cache lấy theo NỘI DUNG file (sha256) + dpi +
prompt ingest, nên:
- tài liệu mới / tải lại bản khác  -> khóa khác -> OCR lại (đúng thứ người dùng mong đợi);
- sửa SYS_INGEST/ingest_prompt     -> khóa khác -> OCR lại (không ăn nhầm dữ liệu prompt cũ);
- còn lại                          -> đọc cache, 0 call.

Hai bất biến của cache:
1. TRANG LỖI VISION KHÔNG BAO GIỜ ĐƯỢC GHI CACHE — proxy hỏng 1 lần mà cache lại thì text rỗng
   đóng băng vĩnh viễn, tệ hơn hẳn việc OCR lại. Trang chỉ có CẢNH BÁO (nghi bóc thiếu) thì
   NGƯỢC LẠI: vẫn cache, kèm cả chuỗi `canh_bao` — cảnh báo là thông tin để chuyên gia soi, không
   phải lỗi cần chữa; khóa cache theo FILE nên chặn một trang là bắt OCR lại cả file mỗi lần chấm.
2. Ảnh PNG KHÔNG nằm trong cache (nặng, và không có consumer nào ngoài ingest) — khi hit vẫn
   render lại từ PDF bằng pdf_to_images: rẻ, không tốn LLM, nên PageRecord luôn đủ field.
"""
from __future__ import annotations

import hashlib
from typing import Any, Protocol

import fitz  # PyMuPDF

from config import get_settings

from experiment.evaluate.pdf_text import trich_trang_tat_dinh
from experiment.evaluate.tu_kiem import kiem_tra_bang
from experiment.evaluate.prompts import SYS_INGEST, ingest_prompt
from experiment.evaluate.schema import (
    NGUON_PDF_TEXT, NGUON_VISION, PageRecord, validate_ingest_page,
)
from experiment.evaluate.vision import VisionFn, page_to_png

from experiment.logger_config import setup_logger
log = setup_logger('EVALUATE', 'evaluate.log')

# dpi render PDF -> ảnh. Là MỘT NGUỒN SỰ THẬT: nơi băm khóa cache (router) phải dùng đúng giá trị
# ingest dùng, lệch một chút là cache không bao giờ hit mà không có lỗi nào báo ra.
DPI_MAC_DINH = 200
TRICH_VERSION = "t2"    # đổi khi sửa logic trích -> khóa cache đổi, không ăn lại text cách cũ
_MAX_TOKENS_INGEST = 8192   # trang bảng dày chạm trần là model tự kết thúc sớm -> THIẾU DÒNG


class PageCache(Protocol):
    """Kho text đã OCR theo khóa nội dung. Triển khai thật: services/ocr_cache.py (DB)."""

    def get(self, key: str) -> list[dict[str, Any]] | None: ...

    def put(self, key: str, pages: list[dict[str, Any]]) -> None: ...


def ingest_cache_key(data: bytes, dpi: int) -> str:
    """Khóa = nội dung file + dpi + prompt ingest + phiên bản logic trích. Prompt vào khóa để sửa
    prompt là cache tự hết hiệu lực — không phụ thuộc việc nhớ tăng số phiên bản bằng tay."""
    prompt_ver = hashlib.sha256((SYS_INGEST + ingest_prompt()).encode("utf-8")).hexdigest()[:8]
    return f"{hashlib.sha256(data).hexdigest()[:32]}-d{dpi}-p{prompt_ver}-{TRICH_VERSION}"


def _record(name: str, loai_ho_so: str, trang: int, d: dict[str, Any], png: bytes,
            nguon: str = NGUON_VISION, canh_bao: str = "") -> PageRecord:
    return PageRecord(file=name, trang=trang, loai_ho_so=loai_ho_so, text=d.get("text", ""),
                      co_chu_ky=bool(d.get("co_chu_ky")), co_dau=bool(d.get("co_dau")), image=png,
                      nguon_trich=d.get("nguon_trich", nguon),
                      canh_bao=d.get("canh_bao", canh_bao))


async def _doc_trang_vision(name: str, png: bytes, vision_fn: VisionFn) -> tuple[Any, list[str]]:
    """Đọc 1 trang bằng vision + tự kiểm. CHỈ thử lại khi text bị CẮT (chạm trần token).

    Nghi bóc thiếu do `kiem_tra_bang` (lệch cột, dấu hiệu tóm tắt) thì CHỈ cảnh báo: seed đã cố
    định nên gọi lại chỉ đổi được seed, mà đo trên hồ sơ thật (logs/evaluate.log) là 21 lần thử
    lại chỉ cứu được 1 — không đáng 2x call. Cảnh báo vẫn đi trọn đường vào `PageRecord.canh_bao`
    -> `pages_text` -> prompt luật/eval -> `EvalResult.canh_bao_doc`, nên không mất tín hiệu nào.

    Chạm trần thì khác hẳn: tăng gấp đôi max_tokens là một call THỰC SỰ khác, có cơ hội lấy lại
    phần bị cắt. Giữ bản ÍT vấn đề hơn, không mù quáng lấy bản cuối.
    """
    out = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                          validate=validate_ingest_page, max_tokens=_MAX_TOKENS_INGEST,
                          seed=get_settings().ai_seed)
    if out.status != "ok":
        return out, []

    van_de = kiem_tra_bang((out.data or {}).get("text", ""))
    if out.finish_reason != "length":
        if van_de:
            log.warning("[ingest] %s: nghi bóc thiếu (%s) — chỉ cảnh báo, KHÔNG đọc lại",
                        name, "; ".join(van_de))
        return out, van_de

    log.warning("[ingest] %s: chạm trần token — thử lại 1 lần với max_tokens gấp đôi", name)
    lai = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                          validate=validate_ingest_page, max_tokens=_MAX_TOKENS_INGEST * 2,
                          seed=get_settings().ai_seed)
    if lai.status != "ok":
        return out, van_de

    van_de_lai = kiem_tra_bang((lai.data or {}).get("text", ""))
    if lai.finish_reason == "length":
        van_de_lai = van_de_lai + ["vẫn chạm trần token — text có thể bị cắt"]
    if not van_de_lai:
        return lai, []
    return (lai, van_de_lai) if len(van_de_lai) < len(van_de) else (out, van_de)


async def _doc_file(name: str, loai_ho_so: str, data: bytes, vision_fn: VisionFn,
                    dpi: int) -> tuple[list[PageRecord], bool]:
    """Đọc từng trang: có text nhúng -> TẤT ĐỊNH (0 call); còn lại -> vision đọc ảnh.

    Trả (records, du_de_cache); du_de_cache=False nếu có BẤT KỲ trang vision nào LỖI (cảnh báo
    không tính — cảnh báo vẫn được cache kèm theo).
    """
    records: list[PageRecord] = []
    du_de_cache = True
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for i, page in enumerate(doc, 1):
            tat_dinh = trich_trang_tat_dinh(page)
            if tat_dinh is not None:
                # Không render ảnh: trang này không cần vision, cũng không cần cờ thị giác.
                records.append(_record(name, loai_ho_so, i, {"text": tat_dinh}, b"",
                                       NGUON_PDF_TEXT))
                continue
            png = page_to_png(page, dpi=dpi)
            out, van_de = await _doc_trang_vision(f"{name} tr{i}", png, vision_fn)
            if out.status == "ok":
                if van_de:
                    # KHÔNG im lặng: cảnh báo vào text để luật/eval hạ kết luận xuống 'cần làm rõ'.
                    # Nhưng KHÔNG chặn cache: cache theo FILE, một trang cảnh báo mà chặn thì mọi
                    # lần chấm sau phải OCR lại toàn bộ file.
                    log.warning("[ingest] %s tr%d nghi bóc thiếu: %s", name, i, "; ".join(van_de))
                records.append(_record(name, loai_ho_so, i, out.data, png,
                                       canh_bao="; ".join(van_de)))
            else:
                log.warning("[ingest] %s tr%d lỗi vision: %s", name, i, out.error)
                du_de_cache = False
                records.append(_record(name, loai_ho_so, i, {}, png))
    finally:
        doc.close()
    n_td = sum(1 for r in records if r.nguon_trich == NGUON_PDF_TEXT)
    log.info("[ingest] %s (%s): %d trang — %d đọc thẳng từ PDF, %d qua vision",
             name, loai_ho_so, len(records), n_td, len(records) - n_td)
    return records, du_de_cache


def _anh_theo_trang(data: bytes, trang: list[int], dpi: int) -> dict[int, bytes]:
    """Render lại ảnh cho các trang cache đánh dấu là đọc bằng vision (ảnh không nằm trong cache)."""
    if not trang:
        return {}
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return {t: page_to_png(doc[t - 1], dpi=dpi) for t in trang if 1 <= t <= doc.page_count}
    finally:
        doc.close()


async def ingest_hsdt(
    files: list[tuple[str, str, bytes]], vision_fn: VisionFn, dpi: int = DPI_MAC_DINH,
    cache: PageCache | None = None,
) -> list[PageRecord]:
    """(tên_file, loai_ho_so, data pdf) -> PageRecord. loai_ho_so gán theo file; vision chỉ bóc text."""
    records: list[PageRecord] = []
    for name, loai_ho_so, data in files:
        key = ingest_cache_key(data, dpi)
        luu = cache.get(key) if cache is not None else None
        if luu is not None:
            log.info("[ingest] %s (%s): %d trang — dùng cache (0 call vision)", name, loai_ho_so,
                     len(luu))
            for d in luu:
                if d.get("canh_bao"):
                    log.warning("[ingest] %s tr%s (cache) nghi bóc thiếu: %s", name,
                                d.get("trang", "?"), d["canh_bao"])
            anh = _anh_theo_trang(
                data, [int(d.get("trang", i)) for i, d in enumerate(luu, 1)
                       if d.get("nguon_trich", NGUON_VISION) == NGUON_VISION], dpi)
            records.extend(
                _record(name, loai_ho_so, int(d.get("trang", i)), d,
                        anh.get(int(d.get("trang", i)), b""))
                for i, d in enumerate(luu, 1))
            continue
        recs, du_de_cache = await _doc_file(name, loai_ho_so, data, vision_fn, dpi)
        records.extend(recs)
        if cache is not None and du_de_cache and recs:
            cache.put(key, [{"trang": r.trang, "text": r.text, "co_chu_ky": r.co_chu_ky,
                             "co_dau": r.co_dau, "nguon_trich": r.nguon_trich,
                             "canh_bao": r.canh_bao} for r in recs])
    return records
