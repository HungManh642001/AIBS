"""Tự kiểm text vision bóc từ trang scan — bắt dấu hiệu bóc THIẾU trước khi đem đi chấm.

Bảng giá scan là chỗ duy nhất còn phải nhờ model đọc (trang có text nhúng đã đi đường tất định).
Kiểu hỏng nguy hiểm nhất ở đây là model tự rút gọn: JSON vẫn hợp lệ, text vẫn đọc được, chỉ là
thiếu vài hàng hoặc lệch cột — không có lỗi nào báo ra, và tổng tiền sai theo.

Chỉ dùng tín hiệu NỘI TẠI trong chính text (không cần thêm call): số ô giữa các hàng phải đều
theo quy ước ' | ' mà SYS_INGEST đã yêu cầu, và không được có dấu hiệu tóm tắt.
"""
from __future__ import annotations

_O = "|"
_TOI_THIEU_HANG = 2       # dưới 2 hàng thì không có gì để so số cột
_DAU_TOM_TAT = ("...", "…", "v.v", "vv.", "tương tự", "còn tiếp", "như trên")


def _hang_bang(text: str) -> list[str]:
    return [d for d in (text or "").splitlines() if _O in d]


def kiem_tra_bang(text: str) -> list[str]:
    """Trả danh sách VẤN ĐỀ nghi ngờ (rỗng = không thấy dấu hiệu bất thường)."""
    hang = _hang_bang(text)
    if len(hang) < _TOI_THIEU_HANG:
        return []      # không phải bảng (hoặc quá ít hàng) -> không áp quy tắc cột

    van_de: list[str] = []
    so_o = [d.count(_O) + 1 for d in hang]
    pho_bien = max(set(so_o), key=so_o.count)
    lech = [i + 1 for i, n in enumerate(so_o) if n != pho_bien]
    if lech:
        van_de.append(f"số cột không đều: {len(lech)}/{len(hang)} hàng lệch "
                      f"(chuẩn {pho_bien} cột) — có thể bóc thiếu ô hoặc gộp hàng")

    thap = "\n".join(hang).lower()
    thay = [d for d in _DAU_TOM_TAT if d in thap]
    if thay:
        van_de.append(f"có dấu hiệu tóm tắt trong bảng ({', '.join(thay)}) — model có thể đã "
                      f"bỏ bớt hàng thay vì bóc hết")
    return van_de
