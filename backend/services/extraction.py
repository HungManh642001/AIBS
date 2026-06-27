"""Trích xuất tiêu chí từ HSMT và mapping nội dung HSDT vào tiêu chí."""
from __future__ import annotations
from typing import Any

from services.ai_client import ai_call, AiOutcome
from services import artifact_catalog
from services.prompts import cot_block, SCALE_DEF
from services.ai_schemas import validate_criteria_list, validate_criterion_detail
from config import get_settings

_settings = get_settings()

_SYS_RUBRIC_LIST = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc Tiêu chuẩn đánh giá (TCĐG) "
    "và LIỆT KÊ các tiêu chí đánh giá. Mỗi tiêu chí gồm: nhom (hop_le/nang_luc/ky_thuat/tai_chinh), "
    "ten, và required_artifacts (mã loại hồ sơ theo danh mục cho sẵn)."
)
_SYS_RUBRIC_DETAIL = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Với MỘT tiêu chí đánh giá, bóc tách "
    "thành các điểm kiểm con (sub_checks) kèm check_type và ngưỡng (thong_so). Khi tiêu chí tham chiếu "
    "'theo yêu cầu HSMT', tra số cụ thể trong BẢNG DỮ LIỆU ĐẤU THẦU (BDS) và ghi nguồn (thong_so.nguon); "
    "nếu không tìm được, đặt thong_so.can_review=true."
)


def chunk_pages(pages: list[dict[str, Any]], max_chars: int, overlap: int) -> list[str]:
    """Cắt danh sách trang thành các chunk theo ranh giới TRANG (không cắt giữa trang), có overlap."""
    blocks = [f"[Trang {p['page']}]\n{p.get('text', '')}" for p in pages]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for b in blocks:
        if cur and cur_len + len(b) > max_chars:
            chunks.append("\n".join(cur))
            # overlap: giữ lại phần đuôi của chunk trước
            tail = "\n".join(cur)[-overlap:] if overlap else ""
            cur = [tail] if tail else []
            cur_len = len(tail)
        cur.append(b)
        cur_len += len(b)
    if cur:
        chunks.append("\n".join(cur))
    return chunks or [""]


def _norm_ten(ten: str) -> str:
    import unicodedata
    # Xử lý "đ" (U+0111) riêng vì NFD không phân rã ký tự này thành d + combining stroke
    s = (ten or "").lower().strip().replace("đ", "d")
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _merge_criteria(lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Gộp danh sách tiêu chí từ nhiều chunk, khử trùng theo ten (chuẩn hoá bỏ dấu)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lst in lists:
        for c in lst:
            key = _norm_ten(c.get("ten", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def _catalog_codes() -> str:
    return ", ".join(
        f"{c}={artifact_catalog.get_artifact(c)['label']}" for c in artifact_catalog.all_codes()
    )


async def _list_criteria(tcdg_pages: list[dict[str, Any]]) -> AiOutcome:
    """Bước 1: liệt kê tiêu chí từ dải TCĐG; chunk + merge nếu quá ngân sách."""
    chunks = chunk_pages(tcdg_pages, _settings.ai_chunk_chars, _settings.ai_chunk_overlap)
    lists: list[list[dict[str, Any]]] = []
    for ch in chunks:
        prompt = (
            f"Danh mục loại hồ sơ (code=label): {_catalog_codes()}\n\n"
            f"TIÊU CHUẨN ĐÁNH GIÁ:\n{ch}\n\n"
            + cot_block('{"criteria":[{"nhom","ten","required_artifacts":[...]}]}')
        )
        out = await ai_call(_SYS_RUBRIC_LIST, prompt, mock_key="extract_rubric",
                            validate=validate_criteria_list,
                            max_tokens=_settings.ai_max_tokens_extract)
        if out.status == "error":
            return out
        lists.append(out.data.get("criteria", []))
    return AiOutcome("ok", {"criteria": _merge_criteria(lists)}, "qwen3-27b")


async def _detail_criterion(
    crit: dict[str, Any], tcdg_text: str, bds_text: str
) -> AiOutcome:
    """Bước 2: chi tiết sub_checks + ngưỡng cho MỘT tiêu chí."""
    prompt = (
        f"Danh mục loại hồ sơ (code=label): {_catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n\n"
        f"TIÊU CHUẨN ĐÁNH GIÁ:\n{tcdg_text}\n\n"
        f"BẢNG DỮ LIỆU ĐẤU THẦU:\n{bds_text}\n\n"
        + cot_block(
            '{"nhom","ten","yeu_cau","required_artifacts":[...],"kieu","trong_so",'
            '"sub_checks":[{"ten","check_type","thong_so","required_artifact","blocking"}],'
            '"proposed_artifacts":[]}',
            scale=SCALE_DEF,
        )
    )
    out = await ai_call(_SYS_RUBRIC_DETAIL, prompt, mock_key="extract_rubric",
                        validate=validate_criterion_detail,
                        max_tokens=_settings.ai_max_tokens_extract)
    return out


async def extract_rubric(sections: dict[str, Any]) -> AiOutcome:
    """Điều phối trích xuất 2 bước. sections = output locator mới.

    Mock chủ ý: trả thẳng mock 'extract_rubric'. Chế độ thật: liệt kê -> chi tiết từng tiêu chí.
    """
    if _settings.ai_mock:
        return await ai_call("", "", mock_key="extract_rubric")

    tcdg = sections.get("tcdg", {})
    bds = sections.get("bds", {})
    tcdg_pages = tcdg.get("pages", [])
    bds_pages = bds.get("pages", [])

    listed = await _list_criteria(tcdg_pages)
    if listed.status == "error":
        return listed

    tcdg_text = "\n".join(f"[Trang {p['page']}]\n{p.get('text', '')}" for p in tcdg_pages)
    bds_text = "\n".join(f"[Trang {p['page']}]\n{p.get('text', '')}" for p in bds_pages)

    detailed: list[dict[str, Any]] = []
    for crit in listed.data.get("criteria", []):
        d = await _detail_criterion(crit, tcdg_text, bds_text)
        if d.status == "error":
            # Lỗi 1 tiêu chí: đánh dấu can_review, vẫn giữ tiêu chí để chuyên gia xử lý.
            detailed.append({**crit, "sub_checks": [], "proposed_artifacts": [],
                             "can_review": True, "loi_ai": d.error})
            continue
        item = d.data
        if not bds.get("located", False):
            for sc in item.get("sub_checks", []):
                sc.setdefault("thong_so", {})["can_review"] = True
        detailed.append(item)

    return AiOutcome("ok", {"criteria": detailed}, "qwen3-27b")
