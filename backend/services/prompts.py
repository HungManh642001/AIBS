"""Mẫu prompt Chain-of-Thought dùng chung cho trích xuất & đánh giá."""
from __future__ import annotations


def cot_block(schema_hint: str) -> str:
    """Trả khối hướng dẫn: suy luận trước, rồi xuất DUY NHẤT một khối JSON trong fence."""
    return "\n".join([
        "Hãy suy luận ngắn gọn theo các bước: "
        "(1) đọc yêu cầu, (2) đối chiếu nội dung hồ sơ, (3) kết luận.",
        "Sau phần suy luận, xuất DUY NHẤT một khối JSON đặt trong ```json ... ```. "
        "Trong JSON, ghi evidence/lý do TRƯỚC result. "
        f"Cấu trúc JSON: {schema_hint}",
    ])
