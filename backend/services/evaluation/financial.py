"""F06 - Đánh giá Tài Chính: sửa lỗi số học, tính giá đánh giá (deterministic)."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict


class FinancialResult(TypedDict):
    corrected_rows: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    tong_gia: Decimal
    evaluated_price: Decimal


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def recalc_price_table(rows: list[list[Any]]) -> FinancialResult:
    corrected: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    tong = Decimal("0")
    for row in rows:
        if len(row) < 5:
            continue
        stt, ten, don_gia, so_luong, thanh_tien = row[:5]
        dg, sl, tt = _dec(don_gia), _dec(so_luong), _dec(thanh_tien)
        if dg is None or sl is None:
            continue
        dung = dg * sl
        if tt is None or tt != dung:
            errors.append({"stt": stt, "ten": ten, "gia_tri_khai": tt, "gia_tri_dung": dung})
        tong += dung
        corrected.append({"stt": stt, "ten": ten, "don_gia": dg, "so_luong": sl, "thanh_tien": dung})
    return FinancialResult(
        corrected_rows=corrected, errors=errors, tong_gia=tong, evaluated_price=tong
    )


def extract_price_rows(excel_pages: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for page in excel_pages:
        for line in page["text"].splitlines():
            cells = line.split("\t")
            if len(cells) >= 5 and _dec(cells[2]) is not None and _dec(cells[3]) is not None:
                rows.append(cells[:5])
    return rows
