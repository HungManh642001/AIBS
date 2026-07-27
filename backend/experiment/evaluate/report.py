"""Báo cáo đánh giá HSDT cho TỔ CHUYÊN GIA — ưu tiên kiểm chứng được, không phải ngắn gọn.

Nguyên tắc: mỗi kết luận phải tra được CẢ HAI chiều — HSMT (yêu cầu gốc, chuẩn, mã điều khoản
nguồn) và HSDT (trích nguyên văn, đúng file + trang). Việc máy BỎ QUA (không áp dụng) luôn hiện
kèm lý do; số trang thiếu thì nói rõ chứ không bịa.
"""
from __future__ import annotations

from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    NHOM_PHAT_HIEN, CriterionEval, EvalResult, Verdict,
)

_CAN_XU_LY = {KET_QUA_KHONG, KET_QUA_SOI, KET_QUA_THIEU, KET_QUA_LOI}
_THU_TU = {KET_QUA_KHONG: 1, KET_QUA_SOI: 2, KET_QUA_THIEU: 2, KET_QUA_LOI: 2, KET_QUA_DAT: 3}


def _rank(c: CriterionEval) -> int:
    """Không đạt > cần làm rõ > đạt — thứ tự người review muốn đọc."""
    return _THU_TU.get(c.ket_qua, 4)


def _files_map(r: EvalResult) -> dict[str, list[str]]:
    return {h.loai_ho_so: h.files for h in r.ho_so_nhan_duoc}


def _nguon_hsdt(v: Verdict, files: dict[str, list[str]]) -> str:
    """'bao_dam_du_thau (bl.pdf) tr.1,3' — đủ để mở đúng file, đúng trang mà đối chiếu."""
    loai = [v.hsdt_kiem_tra] if not v.nguon_doc else list(v.nguon_doc)
    parts = []
    for t in loai:
        fs = files.get(t) or []
        parts.append(f"{t} ({', '.join(fs)})" if fs else t)
    trang = f"tr.{','.join(str(t) for t in v.trang)}" if v.trang else "tr.(không nêu)"
    return f"{'; '.join(parts)} {trang}"


def _verdict_block(v: Verdict, files: dict[str, list[str]], idx: str) -> list[str]:
    rows = [
        ("HSMT — yêu cầu", v.yeu_cau or "—"),
        ("HSMT — chuẩn", v.thong_tin_bo_sung or "(không có)"),
        ("HSMT — điều khoản nguồn", v.nguon_hsmt or "(không nêu)"),
        ("HSDT — hồ sơ", _nguon_hsdt(v, files)),
        ("HSDT — trích dẫn", v.bang_chung or "—"),
        ("Ghi chú", v.ghi_chu or "—"),
    ]
    out = [f"**{idx} {v.noi_dung_kiem_tra} — {v.ket_qua}** (độ tin {v.do_tin})", "", "| | |",
           "|---|---|"]
    out += [f"| **{k}** | {val} |" for k, val in rows]
    out.append("")
    return out


def _header(r: EvalResult) -> list[str]:
    out = [f"# Đánh giá HSDT (hợp lệ) — {r.doc}", "", "## Nhà thầu"]
    if r.vendor is not None:
        mst = f" (MST {r.vendor.ma_so_thue})" if r.vendor.ma_so_thue else ""
        out.append(f"- **Tên**: {r.vendor.ten}{mst}")
    p = r.vendor_profile
    if p is not None:
        ht = p.hinh_thuc or "**không rõ**"
        out.append(f"- **Hình thức dự thầu**: {ht} — căn cứ: {p.nguon} (độ tin {p.do_tin:.2f})")
        if p.bang_chung:
            tr = f" [tr.{','.join(str(t) for t in p.trang)}]" if p.trang else ""
            out.append(f"- **Bằng chứng**: {p.bang_chung}{tr}")
    out.append("")
    if p is not None and p.mau_thuan:
        out += ["> ### ⚠️ CẢNH BÁO MÂU THUẪN", f"> {p.ghi_chu}",
                "> Hình thức đặt **không rõ** → mọi nội dung liên danh **VẪN được chấm đầy đủ**.",
                "> **Tổ chuyên gia cần xác minh trước khi kết luận.**", ""]
    return out


def _ho_so(r: EvalResult) -> list[str]:
    out = ["## Hồ sơ nhận được", "", "| Loại hồ sơ | File | Số trang |", "|---|---|---|"]
    if not r.ho_so_nhan_duoc:
        out.append("| (không có) | — | 0 |")
    out += [f"| {h.loai_ho_so} | {', '.join(h.files) or '—'} | {h.n_trang} |"
            for h in r.ho_so_nhan_duoc]
    return out + [""]


def _tong_ket(r: EvalResult) -> list[str]:
    s = r.summary
    nhan = [("Tổng tiêu chí", "n_tieu_chi"), ("Đạt", "n_dat"), ("Không đạt", "n_khong_dat"),
            ("Cần làm rõ", "n_can_lam_ro"), ("Không áp dụng", "n_khong_ap_dung")]
    return ["## Tổng kết", "", "| Chỉ số | SL |", "|---|---|"] + \
           [f"| {ten} | {s[k]} |" for ten, k in nhan] + [""]


def _can_xu_ly(criteria: list[CriterionEval], files: dict[str, list[str]]) -> list[str]:
    can = [c for c in criteria if c.ket_qua in _CAN_XU_LY]
    out = [f"## ⚠️ CẦN XỬ LÝ ({len(can)})", ""]
    if not can:
        return out + ["_Không có tiêu chí nào cần xử lý._", ""]
    for c in sorted(can, key=_rank):
        # Nêu xuất xứ: tiêu chí này do hệ thống tự kiểm, HSMT không yêu cầu — trọng số ngang nhau
        # nhưng chuyên gia phải biết căn cứ đến từ đâu.
        nguon = "🔎 *(hệ thống tự kiểm)* " if c.nhom == NHOM_PHAT_HIEN else ""
        for v in c.verdicts:
            if v.ket_qua not in _CAN_XU_LY:
                continue
            ly_do = v.bang_chung or v.ghi_chu or "—"
            out.append(f"- {nguon}{c.ten} · *{v.ket_qua}* — {v.noi_dung_kiem_tra}: {ly_do} "
                       f"[{_nguon_hsdt(v, files)}]")
    return out + [""]


def _chi_tiet(criteria: list[CriterionEval], files: dict[str, list[str]]) -> list[str]:
    out = ["## Chi tiết theo tiêu chí", ""]
    for i, c in enumerate(sorted(criteria, key=_rank), 1):
        out.append(f"### {i}. {c.ten} — **{c.ket_qua}**")
        if c.yeu_cau_goc:
            out += ["", f"> **Yêu cầu gốc (HSMT)**: {c.yeu_cau_goc}"]
        out.append("")
        for j, v in enumerate(c.verdicts, 1):
            out += _verdict_block(v, files, f"{i}.{j}")
    return out


def _khong_ap_dung(criteria: list[CriterionEval], files: dict[str, list[str]]) -> list[str]:
    na = [c for c in criteria if c.ket_qua == KET_QUA_KHONG_AP_DUNG]
    out = [f"## Không áp dụng ({len(na)})", ""]
    if not na:
        return out + ["_Không có._", ""]
    for c in na:
        for v in c.verdicts:
            out.append(f"- **{c.ten}** / {v.noi_dung_kiem_tra} — *{v.ket_qua}* "
                       f"(độ tin {v.do_tin})")
            out.append(f"    · **Lý do**: {v.ghi_chu or '(không nêu)'}")
    return out + [""]


def _canh_bao_doc(r: EvalResult) -> list[str]:
    """Trang nghi đọc thiếu — đặt NGAY sau danh mục hồ sơ: mọi con số phía dưới phụ thuộc vào việc
    đọc có đủ hay không, chuyên gia cần biết trước khi đọc kết luận."""
    if not r.canh_bao_doc:
        return []
    return ["## ⚠️ CẢNH BÁO ĐỌC HỒ SƠ (bản scan, có thể bóc thiếu)", ""] \
        + [f"- {c}" for c in r.canh_bao_doc] \
        + ["", "_Số liệu trên các trang này chưa chắc đầy đủ — nên đối chiếu tay với bản gốc._", ""]


def to_markdown(r: EvalResult) -> str:
    """Báo cáo: nhà thầu -> hồ sơ -> cảnh báo đọc -> tổng kết -> CẦN XỬ LÝ -> chi tiết -> N/A.

    Kiểm tra thường trực của hệ thống nay là TIÊU CHÍ như mọi tiêu chí HSMT (không còn mục riêng);
    xuất xứ được nêu bằng nhãn 🔎 ngay trên dòng cần xử lý.
    """
    files = _files_map(r)
    # N/A tách khỏi phần chi tiết: máy đã bỏ qua có chủ đích, đọc ở mục riêng kèm lý do.
    xet = [c for c in r.criteria if c.ket_qua != KET_QUA_KHONG_AP_DUNG]
    lines = _header(r) + _ho_so(r) + _canh_bao_doc(r) + _tong_ket(r) \
        + _can_xu_ly(xet, files) \
        + _chi_tiet(xet, files) + _khong_ap_dung(r.criteria, files)
    return "\n".join(lines)
