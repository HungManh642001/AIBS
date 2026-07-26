"""Hạ tầng luật nghiệp vụ liên-tài-liệu — kích hoạt TẤT ĐỊNH theo dữ liệu, không predicate viết tay.

Luật = handler Python + metadata khai báo (id/ten/ho_so_can/can_vendor/pham_vi). Hai phạm vi:

- `pham_vi="tieu_chi"` — luật PHỤC VỤ một nội dung kiểm tra: khớp tiêu chí khi tiêu chí KHAI ĐỦ bộ
  hồ sơ luật cần (`set(ho_so_can) ⊆ hsdt_can_kiem_tra`), rồi THAY THẾ kết luận của nội dung route
  tới `ho_so_can[0]` (hồ sơ chính). Thay thế chứ không bổ sung: eval chung chỉ đọc được hồ sơ chính
  nên sẽ trả "cần làm rõ", mà roll-up cho 'cần làm rõ' thắng 'đạt' -> verdict luật bị vô hiệu.
- `pham_vi="goi"` — kiểm tra thường trực (standing): chạy 1 lần/nhà thầu bất kể HSMT có nêu hay
  không, verdict ra `EvalResult.phat_hien_bo_sung`, NGOÀI roll-up (không tự kéo 'loại' — chuyên gia
  quyết định).

Khớp theo `ho_so_can` chứ không theo predicate tay: predicate tay ("tiêu chí có nội dung nào dùng
bang_gia") khớp MỌI tiêu chí đụng bảng giá -> luật bắn nhầm tiêu chí đầu tiên theo thứ tự, quy kết
sai và bỏ sót tiêu chí thật. Metadata là nguồn sự thật duy nhất.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from experiment.evaluate.route import _norm
from experiment.evaluate.schema import (
    KET_QUA_LOI, KET_QUA_SOI, PackageContext, PageRecord, VendorContext, Verdict,
)

log = logging.getLogger("experiment.evaluate")

PHAM_VI_TIEU_CHI = "tieu_chi"
PHAM_VI_GOI = "goi"

# handler(by_type, vendor_ctx, criterion, vision_fn, *, nd=None, pkg=None) -> Verdict
RuleHandler = Callable[..., Awaitable[Verdict]]


@dataclass(frozen=True)
class RuleSkill:
    id: str                       # vd "bang_gia_khop_webform"
    ten: str                      # nhãn người đọc
    ho_so_can: list[str]          # mã catalog; ho_so_can[0] = hồ sơ CHÍNH (nội dung route tới nó)
    can_vendor: bool              # cần danh tính nhà thầu?
    handler: RuleHandler
    pham_vi: str = PHAM_VI_TIEU_CHI
    can_pkg: bool = False         # cần ngữ cảnh gói thầu (tên/mã số)?


class RuleRegistry:
    def __init__(self) -> None:
        self._skills: list[RuleSkill] = []

    def register(self, skill: RuleSkill) -> None:
        self._skills.append(skill)

    def matching(self, criterion: dict[str, Any]) -> list[RuleSkill]:
        """Luật phạm vi tiêu chí khớp khi tiêu chí KHAI ĐỦ bộ hồ sơ luật cần (⊆, cho phép khai thừa)."""
        khai = {_norm(str(x)) for x in criterion.get("hsdt_can_kiem_tra", [])}
        return [s for s in self._skills
                if s.pham_vi == PHAM_VI_TIEU_CHI and {_norm(h) for h in s.ho_so_can} <= khai]

    def standing(self) -> list[RuleSkill]:
        return [s for s in self._skills if s.pham_vi == PHAM_VI_GOI]


def default_registry() -> RuleRegistry:
    """Registry mặc định — các luật built-in đăng ký tại đây (import cục bộ, tránh vòng import)."""
    from experiment.evaluate.rules.bang_gia_khop_webform import SKILL as bang_gia
    from experiment.evaluate.rules.bao_dam_uy_quyen import SKILL as bao_dam
    from experiment.evaluate.rules.chu_ky_khop_dkkd import SKILL as chu_ky
    from experiment.evaluate.rules.lien_danh_phan_cong import SKILL as lien_danh
    from experiment.evaluate.rules.ten_goi_thau_khop import SKILL as ten_goi

    reg = RuleRegistry()
    reg.register(chu_ky)
    reg.register(ten_goi)
    reg.register(bao_dam)
    reg.register(lien_danh)
    reg.register(bang_gia)
    return reg


def _rule_verdict(skill: RuleSkill, ket_qua: str, bang_chung: str = "", ghi_chu: str = "") -> Verdict:
    return Verdict(noi_dung_kiem_tra=skill.ten, hsdt_kiem_tra=skill.ho_so_can[0] if skill.ho_so_can else "",
                   yeu_cau=skill.ten, thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=[], do_tin=0.0, ghi_chu=ghi_chu, nguon_doc=list(skill.ho_so_can))


async def run_skill(skill: RuleSkill, by_type: dict[str, list[PageRecord]],
                    vendor_ctx: VendorContext | None, criterion: dict[str, Any], vision_fn: Any,
                    *, nd: dict[str, Any] | None = None,
                    pkg: PackageContext | None = None) -> Verdict:
    """Chạy 1 luật -> verdict. Thiếu ngữ cảnh (nhà thầu/gói thầu) -> SOI (KHÔNG gọi handler);
    lỗi -> 'lỗi'."""
    if skill.can_vendor and vendor_ctx is None:
        return _rule_verdict(skill, KET_QUA_SOI,
                             ghi_chu="thiếu ngữ cảnh nhà thầu (tên/MST) — không đối chiếu được")
    if skill.can_pkg and pkg is None:
        return _rule_verdict(skill, KET_QUA_SOI,
                             ghi_chu="thiếu ngữ cảnh gói thầu (tên/mã số) — không đối chiếu được")
    log.info("    [rule] %s", skill.id)
    try:
        return await skill.handler(by_type, vendor_ctx, criterion, vision_fn, nd=nd, pkg=pkg)
    except Exception as exc:  # no-silent-mock: lộ lỗi thành verdict 'lỗi'
        log.warning("    [rule] %s -> lỗi: %s", skill.id, exc)
        return _rule_verdict(skill, KET_QUA_LOI, bang_chung=f"AI/handler lỗi: {exc}",
                             ghi_chu="cần soi lại")


async def dispatch_standing(registry: RuleRegistry, by_type: dict[str, list[PageRecord]],
                            vendor_ctx: VendorContext | None, vision_fn: Any,
                            *, pkg: PackageContext | None = None) -> list[Verdict]:
    """Kiểm tra thường trực — 1 lần/nhà thầu, verdict NGOÀI roll-up tiêu chí."""
    return [await run_skill(s, by_type, vendor_ctx, {}, vision_fn, pkg=pkg)
            for s in registry.standing()]
