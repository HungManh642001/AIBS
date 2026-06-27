"""Mẫu prompt Chain-of-Thought dùng chung cho trích xuất & đánh giá."""
from __future__ import annotations

SCALE_DEF = (
    "Thang kết quả: "
    "PASS = đáp ứng đầy đủ yêu cầu; "
    "FAIL = vi phạm điều kiện tiên quyết hoặc thiếu yêu cầu bắt buộc; "
    "PARTIAL = đáp ứng một phần. "
    "Trích đúng nguyên văn câu/điều khoản làm dẫn chứng (evidence). "
)


def cot_block(schema_hint: str, scale: str = "") -> str:
    """Trả khối hướng dẫn: suy luận trước, rồi xuất DUY NHẤT một khối JSON trong fence."""
    parts = [
        "Hãy suy luận ngắn gọn theo các bước: "
        "(1) đọc yêu cầu, (2) đối chiếu nội dung hồ sơ, (3) kết luận.",
    ]
    if scale:
        parts.append(scale)
    parts.append(
        "Sau phần suy luận, xuất DUY NHẤT một khối JSON đặt trong ```json ... ```. "
        "Trong JSON, ghi evidence/lý do TRƯỚC result. "
        f"Cấu trúc JSON: {schema_hint}"
    )
    return "\n".join(parts)
