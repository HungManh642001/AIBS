"""B1 — hạ tầng luật nghiệp vụ liên-tài-liệu.

Luật = handler Python + metadata khai báo (id/ten/ho_so_can/can_vendor/kich_hoat) — mô hình
Agent Skills "code-defined trước, khai báo-ready" (spec 2026-07-03). Mỗi luật đọc NHIỀU loại
hồ sơ (pages_by_type) + ngữ cảnh nhà thầu (nếu can_vendor), trả verdict phụ gắn vào tiêu chí
khớp kich_hoat. Mỗi luật bắn 1 lần/vendor — ở tiêu chí ĐẦU TIÊN khớp (thứ tự criteria ổn định
theo thu_tu); caller giữ `fired` xuyên các tiêu chí.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from experiment.evaluate.schema import KET_QUA_LOI, KET_QUA_SOI, PageRecord, VendorContext, Verdict

log = logging.getLogger("experiment.evaluate")

# handler(by_type, vendor_ctx, criterion, vision_fn) -> Verdict
RuleHandler = Callable[..., Awaitable[Verdict]]


@dataclass(frozen=True)
class RuleSkill:
    id: str                                  # vd "chu_ky_khop_dkkd"
    ten: str                                 # nhãn người đọc
    ho_so_can: list[str]                     # mã catalog các hồ sơ luật cần (đã _norm-stable)
    can_vendor: bool                         # cần danh tính nhà thầu?
    kich_hoat: Callable[[dict[str, Any]], bool]  # predicate trên criterion dict
    handler: RuleHandler


class RuleRegistry:
    def __init__(self) -> None:
        self._skills: list[RuleSkill] = []

    def register(self, skill: RuleSkill) -> None:
        self._skills.append(skill)

    def matching(self, criterion: dict[str, Any]) -> list[RuleSkill]:
        return [s for s in self._skills if s.kich_hoat(criterion)]


def default_registry() -> RuleRegistry:
    """Registry mặc định — các luật built-in đăng ký tại đây (import cục bộ, tránh vòng import)."""
    from experiment.evaluate.rules.chu_ky_khop_dkkd import SKILL as chu_ky

    reg = RuleRegistry()
    reg.register(chu_ky)
    return reg


def _rule_verdict(skill: RuleSkill, ket_qua: str, bang_chung: str = "", ghi_chu: str = "") -> Verdict:
    return Verdict(noi_dung_kiem_tra=skill.ten, hsdt_kiem_tra=skill.ho_so_can[0] if skill.ho_so_can else "",
                   yeu_cau=skill.ten, thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=[], do_tin=0.0, ghi_chu=ghi_chu, nguon_doc=list(skill.ho_so_can))


async def dispatch_rules(registry: RuleRegistry, criterion: dict[str, Any],
                         by_type: dict[str, list[PageRecord]],
                         vendor_ctx: VendorContext | None, vision_fn: Any,
                         fired: set[str]) -> list[Verdict]:
    """Chạy các luật khớp criterion chưa bắn; lỗi handler -> verdict 'lỗi' (không nuốt)."""
    out: list[Verdict] = []
    for skill in registry.matching(criterion):
        if skill.id in fired:
            continue
        fired.add(skill.id)
        if skill.can_vendor and vendor_ctx is None:
            out.append(_rule_verdict(skill, KET_QUA_SOI,
                                     ghi_chu="thiếu ngữ cảnh nhà thầu (tên/MST) — không đối chiếu được"))
            continue
        log.info("    [rule] %s", skill.id)
        try:
            out.append(await skill.handler(by_type, vendor_ctx, criterion, vision_fn))
        except Exception as exc:  # no-silent-mock: lộ lỗi thành verdict 'lỗi'
            log.warning("    [rule] %s -> lỗi: %s", skill.id, exc)
            out.append(_rule_verdict(skill, KET_QUA_LOI, bang_chung=f"AI/handler lỗi: {exc}",
                                     ghi_chu="cần soi lại"))
    return out
