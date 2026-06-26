"""Trích xuất tiêu chí từ HSMT và mapping nội dung HSDT vào tiêu chí."""
from __future__ import annotations
from typing import Any

from services.ai_client import ai_json

_SYS_EXTRACT = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. "
    "Trích xuất toàn bộ tiêu chí đánh giá trong HSMT và phân vào 4 nhóm: "
    "hop_le, nang_luc, ky_thuat, tai_chinh. Chỉ trả về JSON."
)
_SYS_MAP = (
    "Bạn là chuyên gia đấu thầu. Với mỗi tiêu chí, tìm nội dung tương ứng "
    "trong HSDT kèm số trang. Chỉ trả về JSON."
)


def _join(pages: list[dict[str, Any]], limit: int = 12000) -> str:
    text = "\n".join(f"[Trang {p['page']}]\n{p['text']}" for p in pages)
    return text[:limit]


async def extract_criteria(hsmt_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt = (
        "HSMT:\n" + _join(hsmt_pages) +
        '\n\nTrả về JSON: {"criteria":[{"nhom","ten","yeu_cau","kieu","trong_so"}]}'
    )
    data = await ai_json(_SYS_EXTRACT, prompt, mock_key="extract_criteria")
    return data.get("criteria", [])


async def map_hsdt(
    criteria: list[dict[str, Any]], hsdt_pages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    names = ", ".join(c.get("ten", "") for c in criteria)
    prompt = (
        f"Tiêu chí: {names}\n\nHSDT:\n" + _join(hsdt_pages) +
        '\n\nTrả về JSON: {"mappings":[{"criteria_ten","page_ref","content"}]}'
    )
    data = await ai_json(_SYS_MAP, prompt, mock_key="map_hsdt")
    return data.get("mappings", [])


# --- append to services/extraction.py ---
from services import artifact_catalog

_SYS_DE_CUONG = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc Tiêu chuẩn đánh giá (TCĐG) "
    "và Bảng dữ liệu đấu thầu (BDS) của HSMT. Với mỗi tiêu chí: xác định loại hồ sơ cần kiểm tra "
    "(required_artifacts theo danh mục cho sẵn), bóc tách thành các điểm kiểm con (sub_checks) kèm "
    "check_type và ngưỡng (thong_so). Khi tiêu chí tham chiếu 'theo yêu cầu HSMT', tra số cụ thể từ BDS "
    "và ghi nguồn (thong_so.nguon); nếu không tìm được, đặt thong_so.can_review=true. Chỉ trả JSON."
)


async def extract_de_cuong(sections: dict[str, Any]) -> list[dict[str, Any]]:
    catalog_codes = ", ".join(
        f"{c}={artifact_catalog.get_artifact(c)['label']}" for c in artifact_catalog.all_codes()
    )
    tcdg = _join(sections.get("tcdg", []))
    bds = _join(sections.get("bds", []))
    prompt = (
        f"Danh mục loại hồ sơ (code=label): {catalog_codes}\n\n"
        f"TIÊU CHUẨN ĐÁNH GIÁ:\n{tcdg}\n\n"
        f"BẢNG DỮ LIỆU ĐẤU THẦU:\n{bds}\n\n"
        'Trả JSON: {"criteria":[{"nhom","ten","yeu_cau","required_artifacts":[...],'
        '"kieu","trong_so","sub_checks":[{"ten","check_type","thong_so","required_artifact","blocking"}],'
        '"proposed_artifacts":[]}]}'
    )
    data = await ai_json(_SYS_DE_CUONG, prompt, mock_key="extract_de_cuong")
    return data.get("criteria", [])
