"""Luật: bảng phân công trong THỎA THUẬN LIÊN DANH phải nêu rõ hạng mục và khớp tỷ lệ bảng giá.

Hai điều kiện (điều kiện 1 là TIỀN ĐỀ của điều kiện 2 — không nêu rõ hạng mục thì không có gì để
cộng tiền):
1. Nội dung công việc từng thành viên phải nêu RÕ hạng mục nào trong bảng giá (không chấp nhận
   "cung cấp hàng hóa", "phần thiết bị" chung chung).
2. Cột "tỷ lệ % giá trị đảm nhận" phải bằng: tổng thành tiền các hạng mục thành viên đó đảm nhận
   / tổng giá trị hàng hóa của liên danh, dung sai `DUNG_SAI_DIEM_PT` điểm phần trăm.

STANDING CHECK (pham_vi="goi"): verdict ra `EvalResult.phat_hien_bo_sung`, ngoài roll-up.
Không có thỏa thuận liên danh -> 'không áp dụng' (nhà thầu độc lập), KHÔNG gọi LLM.

PHÂN VAI: LLM chỉ BÓC dữ liệu (hạng mục, thành tiền, tỷ lệ khai) — KHÔNG tính, KHÔNG kết luận;
`doi_chieu_phan_cong` (hàm thuần) làm số học và ra kết luận. Số học của LLM không đáng tin, còn
việc đọc bảng scan thì code không làm được — mỗi bên làm đúng phần mạnh của mình.

BẢNG GIÁ DÀI — 3 giai đoạn (bản thật đo được: 15 trang ≈ 68.000 ký tự, trần 6.000 cũ chỉ nuốt 9%
rồi lặng lẽ kết luận trên phần thấy được):
1. Đọc thỏa thuận liên danh (1 call, text ngắn) -> thành viên + mô tả + tỷ lệ khai. Nếu KHÔNG ai
   nêu rõ hạng mục thì dừng luôn: điều kiện tiền đề hỏng, đọc bảng giá cũng vô nghĩa.
2. Chia bảng giá thành chunk theo RANH GIỚI TRANG (`chia_chunk_theo_trang`) rồi bóc từng chunk —
   toàn bộ trang đều được đọc, không cắt, không giới hạn số chunk. MỘT chunk lỗi -> verdict 'lỗi',
   KHÔNG kết luận trên dữ liệu thiếu (thiếu 1 chunk là tổng sai -> mọi tỷ lệ sai theo).
3. `gop_bang_gia` cộng dồn ở code rồi lắp vào đúng shape `doi_chieu_phan_cong` nhận.

KHÔNG nén text trước khi gửi: thử nghiệm cho thấy bỏ header lặp + dòng dài không chứa số ép được
68k xuống 8k, nhưng cả hai heuristic đều xóa nhầm dữ liệu thật (tên hạng mục dài không kèm số; tên
hàng trùng nhau — bảng thật có 'Nắp connector' 8 lần với 8 mã khác nhau). Sai thầm lặng đúng thứ
luật này sinh ra để chặn; chia chunk thì không mất gì.
"""
from __future__ import annotations

from typing import Any

from services.prompts import cot_block

from experiment.evaluate.route import _norm, pages_text
from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleSkill
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PageRecord, VendorContext, Verdict, _Base,
)

_TEN = "Phân công liên danh nêu rõ hạng mục và khớp tỷ lệ trong bảng giá"
_TTLD = "thoa_thuan_lien_danh"
_GIA = "bang_gia"
_HO_SO = [_TTLD, _GIA]
_TTLD_CAP = 3000        # trần text thỏa thuận liên danh (bảng phân công luôn ngắn)
_GIA_NGAN_SACH = 6000   # ngân sách MỖI CHUNK bảng giá — KHÔNG phải trần: bảng dài -> nhiều chunk
_MAX_TOKENS = 4096

DUNG_SAI_DIEM_PT = 0.1      # lệch tối đa cho phép giữa tỷ lệ khai và tỷ lệ tính (điểm %)
_LECH_TONG_TOI_DA = 0.02    # Σ tiền thành viên vs tổng liên danh: lệch >2% -> nghi bóc thiếu

SYS_RULE_TTLD = (
    "Bạn là chuyên gia chấm thầu. Đọc BẢNG PHÂN CÔNG TRÁCH NHIỆM trong thỏa thuận liên danh và "
    "BÓC DỮ LIỆU (KHÔNG tính toán, KHÔNG kết luận đạt/không đạt — phần đó hệ thống tự làm). "
    "Mỗi thành viên: ten; mo_ta_cong_viec (nguyên văn cột nội dung công việc đảm nhận); "
    "neu_ro_hang_muc = true CHỈ KHI mô tả chỉ đích danh được hạng mục trong bảng giá (tên/mã hạng "
    "mục), false nếu chỉ ghi chung chung ('cung cấp hàng hóa', 'phần thiết bị', 'thi công lắp "
    "đặt'); ty_le_khai: số % ghi ở cột tỷ lệ giá trị đảm nhận (chỉ con số, vd 60.0). "
    "TUYỆT ĐỐI KHÔNG bịa tên thành viên, không tự suy ra tỷ lệ khi thỏa thuận không ghi. "
    "Chỉ trả JSON."
)

SYS_RULE_BANG_GIA = (
    "Bạn là chuyên gia chấm thầu. Đây là MỘT PHẦN của bảng giá dự thầu (bảng dài được chia nhỏ). "
    "BÓC DỮ LIỆU trong phần này, KHÔNG tính tổng, KHÔNG kết luận:\n"
    "- hang_muc: CHỈ các DÒNG CHI TIẾT hàng hóa/dịch vụ (dòng có số thứ tự cụ thể), gồm stt, ten, "
    "thanh_tien (thành tiền của dòng đó), thanh_vien = tên thành viên liên danh đảm nhận hạng mục "
    "này theo BẢNG PHÂN CÔNG nêu ở đầu prompt; để thanh_vien rỗng nếu không xác định được — TUYỆT "
    "ĐỐI KHÔNG đoán bừa.\n"
    "- dong_tong: các DÒNG TỔNG (tổng nhóm như 'I. Hàng hóa/dịch vụ liên quan', và dòng 'Tổng "
    "cộng' toàn bảng) gồm nhan + gia_tri. Dòng tổng KHÔNG được đưa vào hang_muc (sẽ bị cộng đôi).\n"
    "Phần này không có dòng nào thì trả mảng rỗng. TUYỆT ĐỐI KHÔNG bịa hạng mục hay số tiền. "
    "Chỉ trả JSON."
)


class ThanhVienTTLD(_Base):
    ten: str = ""
    mo_ta_cong_viec: str = ""
    neu_ro_hang_muc: bool = False
    ty_le_khai: float = 0.0


class TtldOut(_Base):
    thanh_vien: list[ThanhVienTTLD] = []
    trang: list[int] = []
    ghi_chu: str = ""


class DongHangMuc(_Base):
    stt: str = ""
    ten: str = ""
    thanh_tien: float = 0.0
    thanh_vien: str = ""


class DongTong(_Base):
    nhan: str = ""
    gia_tri: float = 0.0


class BangGiaChunkOut(_Base):
    hang_muc: list[DongHangMuc] = []
    dong_tong: list[DongTong] = []


def validate_ttld(d: dict[str, Any]) -> dict[str, Any]:
    return TtldOut(**d).model_dump()


def validate_bang_gia_chunk(d: dict[str, Any]) -> dict[str, Any]:
    return BangGiaChunkOut(**d).model_dump()


def ttld_prompt(ttld_text: str) -> str:
    return (
        "[RULE:lien_danh_ttld]\n"
        f"THỎA THUẬN LIÊN DANH (bóc từ ảnh):\n{ttld_text[:_TTLD_CAP]}\n\n"
        + cot_block('{"thanh_vien":[{"ten":"...","mo_ta_cong_viec":"<nguyên văn>",'
                    '"neu_ro_hang_muc":true,"ty_le_khai":0.0}],"trang":[...],"ghi_chu":""}')
    )


def bang_gia_prompt(chunk_text: str, thanh_vien: list[dict[str, Any]]) -> str:
    """chunk_text KHÔNG cắt — độ dài đã do `chia_chunk_theo_trang` khống chế."""
    phan_cong = "; ".join(f"{t.get('ten', '?')}: {t.get('mo_ta_cong_viec', '')}"
                          for t in thanh_vien)
    return (
        "[RULE:lien_danh_bang_gia]\n"
        f"BẢNG PHÂN CÔNG LIÊN DANH (để gán hạng mục): {phan_cong}\n\n"
        f"PHẦN BẢNG GIÁ DỰ THẦU (bóc từ ảnh):\n{chunk_text}\n\n"
        + cot_block('{"hang_muc":[{"stt":"...","ten":"...","thanh_tien":0,"thanh_vien":"..."}],'
                    '"dong_tong":[{"nhan":"...","gia_tri":0}]}')
    )


def chia_chunk_theo_trang(pages: list[PageRecord], ngan_sach: int) -> list[str]:
    """Gom trang thành các khối <= ngân sách ký tự. KHÔNG BAO GIỜ cắt giữa trang.

    Cắt giữa trang là cách mất dữ liệu âm thầm (mất nửa dòng hạng mục -> tổng sai -> tỷ lệ sai);
    một trang dài hơn ngân sách thì thà gửi nguyên trang thành 1 khối to.
    """
    chunks: list[str] = []
    hien_tai: list[str] = []
    do_dai = 0
    for p in pages:
        khoi = pages_text([p])
        if hien_tai and do_dai + len(khoi) > ngan_sach:
            chunks.append("\n".join(hien_tai))
            hien_tai, do_dai = [], 0
        hien_tai.append(khoi)
        do_dai += len(khoi)
    if hien_tai:
        chunks.append("\n".join(hien_tai))
    return chunks


def _la_tong_cong(nhan: str) -> bool:
    """Dòng TỔNG CỘNG toàn bảng (khác tổng nhóm 'I. Hàng hóa...' — tổng nhóm không dùng làm mẫu số)."""
    k = _norm(nhan)
    return "tong cong" in k or "tong gia tri" in k or k.strip() in {"tong", "tong so"}


def gop_bang_gia(thanh_vien: list[dict[str, Any]],
                 chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Kết quả bóc từng chunk -> dữ liệu đúng shape `doi_chieu_phan_cong` nhận.

    Cộng dồn ở ĐÂY (không nhờ LLM): hạng mục của một thành viên nằm rải nhiều trang là chuyện
    thường. Chỉ cộng `hang_muc` — `dong_tong` (tổng nhóm/tổng cộng) tách riêng, cộng vào là cộng đôi.
    """
    theo_ten: dict[str, dict[str, Any]] = {}
    for tv in thanh_vien:
        theo_ten[_norm(str(tv.get("ten", "")))] = {
            "ten": tv.get("ten", ""), "mo_ta_cong_viec": tv.get("mo_ta_cong_viec", ""),
            "neu_ro_hang_muc": bool(tv.get("neu_ro_hang_muc")),
            "ty_le_khai": float(tv.get("ty_le_khai", 0.0) or 0.0),
            "hang_muc": [], "tong_tien": 0.0,
        }

    tong_hang_muc = 0.0
    tien_chua_phan_cong = 0.0
    tong_cong: list[float] = []
    for ch in chunks:
        for hm in ch.get("hang_muc") or []:
            tien = float(hm.get("thanh_tien", 0.0) or 0.0)
            tong_hang_muc += tien
            tv = theo_ten.get(_norm(str(hm.get("thanh_vien", ""))))
            if tv is None:
                tien_chua_phan_cong += tien
                continue
            tv["hang_muc"].append({"ten": hm.get("ten", ""), "thanh_tien": tien})
            tv["tong_tien"] += tien
        for dt in ch.get("dong_tong") or []:
            if _la_tong_cong(str(dt.get("nhan", ""))):
                tong_cong.append(float(dt.get("gia_tri", 0.0) or 0.0))

    ghi_chu = ""
    if tong_cong:
        tong = max(tong_cong)
    else:
        tong = tong_hang_muc
        ghi_chu = "bảng giá không có dòng tổng cộng — lấy tổng các hạng mục đã bóc làm mẫu số"
    return {"tong_gia_tri_lien_danh": tong, "thanh_vien": list(theo_ten.values()),
            "tien_chua_phan_cong": tien_chua_phan_cong, "ghi_chu": ghi_chu}


def _pt(x: float) -> str:
    """Số phần trăm kiểu Việt: 1 chữ số thập phân, dấu phẩy."""
    return f"{x:.1f}".replace(".", ",") + "%"


def _tien(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def doi_chieu_phan_cong(d: dict[str, Any],
                        dung_sai: float = DUNG_SAI_DIEM_PT) -> tuple[str, str, str]:
    """Dữ liệu đã bóc -> (ket_qua, bang_chung, ghi_chu). Hàm THUẦN: mọi số học nằm ở đây.

    Thứ tự kết luận: thiếu căn cứ (tổng/thành viên) -> SOI; Σ tiền lệch tổng liên danh -> SOI;
    có thành viên không nêu rõ hạng mục hoặc lệch tỷ lệ -> KHÔNG ĐẠT; còn lại -> ĐẠT.
    """
    tong = float(d.get("tong_gia_tri_lien_danh", 0.0) or 0.0)
    tvs = d.get("thanh_vien") or []
    if not tvs:
        return KET_QUA_SOI, "", "không bóc được thành viên nào trong bảng phân công liên danh"
    if tong <= 0:
        return KET_QUA_SOI, "", "không đọc được tổng giá trị hàng hóa của liên danh trong bảng giá"

    dong: list[str] = []
    mo_ho: list[str] = []
    lech: list[str] = []
    for tv in tvs:
        ten = tv.get("ten") or "(không rõ tên)"
        khai = float(tv.get("ty_le_khai", 0.0) or 0.0)
        if not tv.get("neu_ro_hang_muc"):
            mo_ho.append(ten)
            dong.append(f"{ten}: '{tv.get('mo_ta_cong_viec', '')}' — KHÔNG nêu rõ hạng mục trong "
                        f"bảng giá (khai {_pt(khai)}) ✗")
            continue
        tien = float(tv.get("tong_tien", 0.0) or 0.0)
        tinh = tien / tong * 100
        hm = " + ".join(h.get("ten", "?") for h in (tv.get("hang_muc") or [])) or "(không nêu)"
        dat = abs(tinh - khai) <= dung_sai
        dong.append(f"{ten}: {hm} = {_tien(tien)} / {_tien(tong)} = {_pt(tinh)} — khai "
                    f"{_pt(khai)} {'✓' if dat else f'✗ lệch {_pt(abs(tinh - khai))[:-1]} điểm %'}")
        if not dat:
            lech.append(ten)

    bang_chung = "; ".join(dong)
    tong_tv = sum(float(tv.get("tong_tien", 0.0) or 0.0) for tv in tvs)
    if abs(tong_tv - tong) / tong > _LECH_TONG_TOI_DA and not mo_ho:
        # Đọc bảng giá theo chunk thì biết CHÍNH XÁC phần chưa gán cho ai -> nêu thẳng số tiền,
        # khỏi bắt chuyên gia đoán giữa 'chưa phân công' và 'bóc thiếu'.
        chua_gan = float(d.get("tien_chua_phan_cong", 0.0) or 0.0)
        vi_sao = (f"hạng mục chưa gán cho thành viên nào: {_tien(chua_gan)}" if chua_gan
                  else "có thể còn hạng mục chưa phân công hoặc bảng giá bóc thiếu")
        return (KET_QUA_SOI, bang_chung,
                f"tổng tiền các thành viên ({_tien(tong_tv)}) lệch tổng giá trị liên danh "
                f"({_tien(tong)}) — {vi_sao}")
    if mo_ho:
        return (KET_QUA_KHONG, bang_chung,
                f"không nêu rõ hạng mục đảm nhận trong bảng giá: {', '.join(mo_ho)}")
    if lech:
        return (KET_QUA_KHONG, bang_chung,
                f"tỷ lệ khai khác tỷ lệ tính từ bảng giá: {', '.join(lech)}")
    return KET_QUA_DAT, bang_chung, ""


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             ghi_chu: str = "") -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra=_TTLD,
                   yeu_cau=("Bảng phân công liên danh phải nêu rõ hạng mục đảm nhận trong bảng giá "
                            "và tỷ lệ % giá trị đảm nhận phải khớp giá trị hạng mục đó"),
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=0.0, ghi_chu=ghi_chu, nguon_doc=list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd; không cần ngữ cảnh gói -> bỏ qua pkg.
    if not by_type.get(_TTLD):
        return _verdict(KET_QUA_KHONG_AP_DUNG,
                        ghi_chu="HSDT không có thỏa thuận liên danh — nhà thầu dự thầu độc lập")
    if not by_type.get(_GIA):
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_GIA}",
                        ghi_chu="thiếu bảng giá để đối chiếu tỷ lệ phân công")

    # Giai đoạn 1 — đọc bảng phân công (text ngắn, 1 call).
    out = await vision_fn(SYS_RULE_TTLD, ttld_prompt(pages_text(by_type[_TTLD])),
                          validate=validate_ttld, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi (đọc thỏa thuận liên danh): {out.error}",
                        ghi_chu="cần soi lại")
    d1 = out.data
    thanh_vien = d1.get("thanh_vien") or []
    trang = [int(t) for t in d1.get("trang", []) if str(t).isdigit()]

    # Không ai nêu rõ hạng mục -> điều kiện tiền đề đã hỏng, đọc bảng giá cũng vô nghĩa.
    if thanh_vien and not any(tv.get("neu_ro_hang_muc") for tv in thanh_vien):
        d = {"tong_gia_tri_lien_danh": 1.0,   # mẫu số giả: mọi tong_tien=0 nên không ảnh hưởng
             "thanh_vien": [{**tv, "hang_muc": [], "tong_tien": 0.0} for tv in thanh_vien]}
        ket_qua, bang_chung, ghi_chu = doi_chieu_phan_cong(d)
        return _verdict(ket_qua, bang_chung=bang_chung, trang=trang, ghi_chu=ghi_chu)

    # Giai đoạn 2 — quét TOÀN BỘ bảng giá theo chunk (không cắt, không bỏ trang nào).
    chunks = chia_chunk_theo_trang(by_type[_GIA], _GIA_NGAN_SACH)
    ket_qua_chunks: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, 1):
        o = await vision_fn(SYS_RULE_BANG_GIA, bang_gia_prompt(chunk, thanh_vien),
                            validate=validate_bang_gia_chunk, max_tokens=_MAX_TOKENS)
        if o.status == "error":
            # Thiếu 1 phần là tổng sai -> mọi tỷ lệ sai theo. KHÔNG kết luận trên dữ liệu thiếu.
            return _verdict(KET_QUA_LOI, trang=trang,
                            bang_chung=f"AI lỗi khi đọc bảng giá (phần {i}/{len(chunks)}): {o.error}",
                            ghi_chu="cần soi lại")
        ket_qua_chunks.append(o.data)

    # Giai đoạn 3 — cộng dồn + đối chiếu, toàn bộ ở code.
    d = gop_bang_gia(thanh_vien, ket_qua_chunks)
    ket_qua, bang_chung, ghi_chu = doi_chieu_phan_cong(d)
    them = "; ".join(x for x in (d.get("ghi_chu", ""), d1.get("ghi_chu", "")) if x)
    return _verdict(ket_qua, bang_chung=bang_chung, trang=trang,
                    ghi_chu=f"{ghi_chu}; {them}" if ghi_chu and them else (ghi_chu or them))


SKILL = RuleSkill(id="lien_danh_phan_cong_khop_bang_gia", ten=_TEN, ho_so_can=list(_HO_SO),
                  can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI)
