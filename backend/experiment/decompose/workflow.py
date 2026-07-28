"""Agentic Workflow (LlamaIndex) phân rã 1 nhóm — 4 bước, mỗi bước MỘT việc:

  1. list    : liệt kê tiêu chí {nhom, ten, yeu_cau_goc, hsdt_can_kiem_tra};
               critique (chống sót) CHỈ cho nhóm nhiều bảng (vd năng lực) — free-text thì bỏ.
  2. analyze : mỗi tiêu chí -> noi_dung_can_kiem_tra; mục nguon=hsmt trống gia_tri = "chưa đủ".
  3. search  : với mục chưa đủ -> sinh query -> retrieve -> điền gia_tri (no-fab -> can_review).
  4. collect : gom.

Nội dung nguon=hsdt = dữ liệu nhà thầu -> đánh giá ở bước sau, không tra.
"""
from __future__ import annotations

import asyncio
from typing import Any

from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step

from experiment.decompose.dieu_kien import doi_chieu_tieu_chi
from experiment.decompose.llm import LlmFn
from experiment.decompose.prompts import (
    SYS_CRITIQUE,
    SYS_LIST,
    SYS_QUERY,
    SYS_RESOLVE,
    SYS_STRUCT,
    critique_prompt,
    list_prompt,
    query_prompt,
    resolve_prompt,
    retry_query_prompt,
    struct_prompt,
)
from experiment.decompose.refs import extract_clause_refs, extract_form_refs
from experiment.decompose.retrieval import RetrieveFn
from experiment.decompose.schema import (
    Coverage,
    GroupDecomposition,
    norm_ten,
    validate_criteria_list,
    validate_criterion,
    validate_query,
    validate_resolved_value
)

from experiment.logger_config import setup_logger
# log = logging.getLogger("experiment.decompose")
log = setup_logger('DECOMPOSE', 'decompose.log')

# Step analyze/search sinh JSON + Qwen3 có khối <think> -> cần budget rộng (mặc định chỉ 4096).
_STRUCT_MAX_TOKENS = 8192
_EVIDENCE_CAP = 9000   # ký tự bằng chứng hits (NGUYÊN VĂN chunk, không cắt 300 kẻo mất giá trị)
_BDL_CAP = 15000       # trần phụ lục bảng A-BDL nạp kèm resolve
_SCAN_CAP = 12000
_FORM_CAP = 12000


class _Listed(Event):
    crits: list
    added: list
    listed_n: int


class _AnalyzeReq(Event):
    crit: dict


class _SearchReq(Event):
    crit: dict
    item: dict


class _Done(Event):
    detail: dict
    needs_review: dict | None


def _render_rows(rows: list[list[Any]]) -> str:
    return "\n".join(" | ".join(str(c) for c in (r or [])) for r in (rows or []))


class DecomposeWorkflow(Workflow):
    """Chạy 1 lần/nhóm. wf.run(group=<dict trong chuong3_groups.json>) -> GroupDecomposition."""

    def __init__(self, llm_fn: LlmFn, retrieve_fn: RetrieveFn | None = None,
                 bdl_rows: list[dict[str, Any]] | None = None, 
                 source_summaries: dict[str, str] | None = None,
                 scan_texts: dict[str, str] | None = None,
                 form_texts: dict[str, str] | None = None,
                 anchors: dict[str, dict[str, str]] | None = None,
                 max_song_song: int = 8, **kw: Any):
        super().__init__(**kw)
        self._llm = llm_fn
        self._retrieve = retrieve_fn
        self._bdl_rows = bdl_rows or []  # dòng Bảng dữ liệu (A-BDL) — phụ lục resolve, recall tất định
        self._sources = source_summaries or {}
        self._scan_texts = scan_texts or {}
        self._form_texts = form_texts or {}
        self._anchors = anchors or {}           # {tên neo: {gia_tri, nguon}} — mốc chung gói thầu
        # Trần need đang bay đồng thời (step search). @step vốn đã cho 4 tiêu chí chạy song song;
        # thả tự do thêm các need bên trong sẽ dội hàng chục call cùng lúc vào proxy.
        self._sem = asyncio.Semaphore(max_song_song)
        # Phụ lục là hằng trong suốt một run nhưng trước đây dựng lại cho MỖI need (A-BDL nối tới
        # 15k ký tự, bảng neo duyệt lại toàn bộ mốc). Nhớ kết quả — nội dung không đổi.
        self._cache_phu_luc: dict[tuple[str, tuple[str, ...]], str] = {}

    # ---- nguồn nội dung nhóm (kèm lần tham chiếu Mục 3 -> Phần 4) ----
    def _build_source(self, group: dict[str, Any]) -> str:
        parts: list[str] = []
        for b in group.get("blocks", []):
            if b.get("type") == "table":
                parts.append(_render_rows(b.get("rows", [])))
            else:
                parts.append(b.get("text", "") or "")
        src = "\n".join(p for p in parts if p)
        if group.get("is_reference") and self._retrieve:
            tgt = group.get("ref_target") or {}
            q = f"{tgt.get('kind', '')} {tgt.get('number', '')} yêu cầu kỹ thuật thông số hàng hóa"
            hits = self._retrieve(q, k=5)
            if hits:
                body = "\n".join(h["text"][:500] for h in hits)
                src += f"\n\n[NỘI DUNG THAM CHIẾU PHẦN {tgt.get('number', '')}]\n{body}"
        return src

    def _assemble(
        self, group: dict, criteria: list, added: list, listed_n: int, needs: list | None = None
    ) -> GroupDecomposition:
        needs = needs or []
        return GroupDecomposition(
            group=group.get("group", ""),
            muc=group.get("muc", ""),
            is_reference=bool(group.get("is_reference")),
            ref_target=group.get("ref_target"),
            criteria=criteria,
            coverage=Coverage(
                listed_n=listed_n,
                final_n=len(criteria),
                added_by_critique=list(added),
                notes="",
            ),
            needs_review=needs,
        )

    @staticmethod
    def _has_tables(group: dict[str, Any]) -> bool:
        """Nhóm nặng bảng (vd năng lực) -> bật critique chống sót; free-text -> bỏ qua."""
        return any(b.get("type") == "table" for b in group.get("blocks", []))
    
    _SOURCE_LABELS = {"tbmt": "Thông báo mời thầu"}  # source_doc -> nhãn người đọc

    @staticmethod
    def _hit_source(hits: list[dict]) -> str:
        """Backfill nguon: mã điều khoản của hit đầu tiên có clause_id (A-BDL/A-CDNT)."""
        for h in hits or []:
            m = h.get("metadata") or {}
            cid = m.get("clause_id")
            if cid:
                prefix = "A-BDL" if m.get("clause_doc") == "bdl" else "A-CDNT"
                return f"{prefix} {cid}"
        for h in hits or []:  # không có mã điều khoản -> nguồn theo tài liệu (không phải HSMT)
            m = h.get("metadata") or {}
            src = m.get("source_doc")
            if src and src != "hsmt":
                label = DecomposeWorkflow._SOURCE_LABELS.get(src, src)
                page = m.get("page_start")
                return f"{label} tr {page}" if page else label
        return ""
    
    @staticmethod
    def _merge_hits(*hit_lists: list[dict], cap: int = 8) -> list[dict]:
        """Gộp nhiều nguồn hit (A-BDL trước), khử trùng theo chunk_id, cắt còn `cap`."""
        seen: set = set()
        out: list[dict] = []
        for hits in hit_lists:
            for h in hits or []:
                cid = (h.get("metadata") or {}).get("chunk_id")
                key = cid if cid is not None else id(h)
                if key in seen:
                    continue
                seen.add(key)
                out.append(h)
        return out
    
    def _nho(self, khoa: tuple[str, tuple[str, ...]], dung) -> str:
        """Nhớ phụ lục theo khoá — chúng là hằng trong một run nhưng bị gọi lại mỗi need."""
        if khoa not in self._cache_phu_luc:
            self._cache_phu_luc[khoa] = dung()
        return self._cache_phu_luc[khoa]

    def _bdl_appendix(self) -> str:
        """Toàn bộ dòng A-BDL (nếu được cấp) — recall tất định cho giá trị data-sheet."""
        return self._nho(("bdl", ()), self._bdl_appendix_dung)

    def _bdl_appendix_dung(self) -> str:
        if not self._bdl_rows:
            return ""
        body = "\n".join(r.get("text", "") for r in self._bdl_rows)[:_BDL_CAP]
        return f"[BẢNG DỮ LIỆU (A-BDL) ĐẦY ĐỦ]\n{body}"

    def _scan_appendix(self, srcs: list[str]) -> str:
        return self._nho(("scan", tuple(srcs)), lambda: self._scan_appendix_dung(srcs))

    def _scan_appendix_dung(self, srcs: list[str]) -> str:
        """Nguyên văn các nguồn scan nhỏ (<= _SCAN_CAP)"""
        parts: list[str] = []
        for s in srcs:
            t = (self._scan_texts.get(s) or "").strip()
            if t and len(t) <= _SCAN_CAP:
                label = self._SOURCE_LABELS.get(s, s)
                parts.append(f"[{label.upper()} (NGUYÊN VĂN)]\n{t}")
        return "\n\n".join(parts)
    
    def _anchor_appendix(self) -> str:
        return self._nho(("anchor", ()), self._anchor_appendix_dung)

    def _anchor_appendix_dung(self) -> str:
        """Bảng neo mốc chung — giúp thong_tin_bo_sung TỰ ĐỦ khi chuẩn tham chiếu mốc."""
        lines: list[str] = []
        for ten, v in self._anchors.items():
            gia_tri = (v.get("gia_tri") or "").strip()
            if not gia_tri:
                continue
            nguon = (v.get("nguon") or "").strip()
            lines.append(f"- {ten}: {gia_tri}" + (f" [{nguon}]" if nguon else ""))
        return "[BẢNG NEO — MỐC CHUNG GÓI THẦU]\n" + "\n".join(lines) if lines else ""
    
    def _form_appendix(self, refs: list[str]) -> str:
        return self._nho(("form", tuple(refs)), lambda: self._form_appendix_dung(refs))

    def _form_appendix_dung(self, refs: list[str]) -> str:
        """Nguyên văn biểu mẫu theo mã"""
        parts: list[str] = []
        for f in refs:
            t = (self._form_texts.get(f) or "").strip()
            if t:
                parts.append(f"[{f.upper()} (NGUYÊN VĂN)]\n{t[:_FORM_CAP]}")
        return "\n\n".join(parts)
    
    @staticmethod
    def _evidence(hits: list[dict]) -> str:
        """Ghép NGUYÊN VĂN chunk (không cắt 300 — giá trị dễ nằm sau) trong trần _EVIDENCE_CAP."""
        out: list[str] = []
        used = 0
        for h in hits or []:
            t = h.get("text", "")
            take = t
            out.append(take)
            used += len(take)
            if used >= _EVIDENCE_CAP:
                break
        return "\n".join(out)
    
    async def _try_resolve(self, crit: dict, n: dict, hits: list[dict], appendix: str,
                           attempt: int) -> bool:
        """Resolve 1 lượt; True nếu điền được thong_tin_bo_sung (no-fab: can_review -> False)."""
        if not hits and not appendix:
            return False
        body = self._evidence(hits)
        if appendix:
            body = f"{body}\n\n{appendix}"
        anchor = self._anchor_appendix()  # neo KHÔNG tự kích hoạt resolve (guard ở trên giữ nguyên)
        if anchor:
            body = f"{body}\n\n{anchor}"
        rout = await self._llm(SYS_RESOLVE, resolve_prompt(crit, n, body, attempt=attempt),
                               validate=validate_resolved_value, max_tokens=_STRUCT_MAX_TOKENS)
        log.info(f"       [result] {rout}")

        if rout.status == "ok" and not rout.data.get("can_review") \
                and (rout.data.get("thong_tin_bo_sung") or "").strip():
            n["thong_tin_bo_sung"] = rout.data["thong_tin_bo_sung"]
            n["nguon"] = rout.data.get("nguon", "") or self._hit_source(hits)
            return True
        if rout.status == "error":
            log.warning("    [search] %s/%s -> lỗi resolve(%d): %s",
                        crit.get("ten", ""), n.get("noi_dung_kiem_tra", ""), attempt, rout.error)
        return False

    # ---- Step 1: liệt kê tiêu chí (+ critique CHỈ cho nhóm bảng lớn) ----
    @step
    async def list_criteria(self, ctx: Context, ev: StartEvent) -> _Listed | StopEvent:
        group = ev.group
        log.info("[nhóm %s] %s", group.get("group", ""), group.get("muc", ""))
        source = self._build_source(group)
        await ctx.store.set("group", group)
        await ctx.store.set("source", source)
        log.info(f'[Step1] source: {source}')
        out = await self._llm(SYS_LIST, list_prompt(source), validate=validate_criteria_list,
                              max_tokens=_STRUCT_MAX_TOKENS)
        
        log.info(f'[Step1] out: {out}')

        if out.status == "error":
            # Cả nhóm lỗi liệt kê -> không bịa, trả needs_review.
            gd = self._assemble(group, [], [], 0, [{"ten": "(toàn nhóm)", "ly_do": f"lỗi AI liệt kê: {out.error}"}])
            return StopEvent(result=gd)

        listed = list(out.data.get("criteria", []))
        listed_n = len(listed)
        added: list[str] = []

        # Critique (chống sót) chỉ cho nhóm nhiều bảng — nơi liệt kê 1 lượt dễ sót dòng.
        if self._has_tables(group):
            seen = {norm_ten(c.get("ten", "")) for c in listed}
            cout = await self._llm(SYS_CRITIQUE, critique_prompt(source, listed),
                                   validate=validate_criteria_list)
            if cout.status == "ok":
                for m in cout.data.get("criteria", []):
                    key = norm_ten(m.get("ten", ""))
                    if key and key not in seen:
                        seen.add(key)
                        listed.append(m)
                        added.append(m.get("ten", ""))
            log.info("  [list] %d tiêu chí; [critique] +%d sót", listed_n, len(added))
        else:
            log.info("  [list] %d tiêu chí (bỏ critique: nhóm free-text)", listed_n)
        return _Listed(crits=listed, added=added, listed_n=listed_n)

    # ---- fan-out: mỗi tiêu chí -> phân tích ----
    @step
    async def fan_out(self, ctx: Context, ev: _Listed) -> _AnalyzeReq | StopEvent:
        await ctx.store.set("added", ev.added)
        await ctx.store.set("listed_n", ev.listed_n)
        group = await ctx.store.get("group")
        if not ev.crits:
            return StopEvent(result=self._assemble(group, [], ev.added, ev.listed_n))
        log.info("  [fan-out] %d tiêu chí", len(ev.crits))
        await ctx.store.set("n", len(ev.crits))
        for c in ev.crits:
            ctx.send_event(_AnalyzeReq(crit=c))
        return None

    # ---- Step 2: phân tích 1 tiêu chí -> noi_dung_can_kiem_tra (CHỈ từ tiêu chí, không source) ----
    @step
    async def analyze(self, ctx: Context, ev: _AnalyzeReq) -> _SearchReq | _Done:
        crit = ev.crit
        ten = crit.get("ten", "")
        log.info("    [analyze] %s", ten)

        log.info(f'[Step2] crit: {crit}')

        out = await self._llm(SYS_STRUCT, struct_prompt(crit),
                              validate=validate_criterion, max_tokens=_STRUCT_MAX_TOKENS)
        if out.status == "error":
            log.warning("    [analyze] %s -> lỗi: %s", ten, out.error)
            item = {
                "nhom": crit.get("nhom", "hop_le"),
                "ten": ten,
                "yeu_cau_goc": crit.get("yeu_cau_goc", ""),
                "hsdt_can_kiem_tra": crit.get("hsdt_can_kiem_tra", []),
                "noi_dung_can_kiem_tra": [],
                "loi_ai": out.error,
            }
            return _Done(detail=item, needs_review={"ten": ten, "ly_do": f"lỗi AI: {out.error}"})

        item = out.data
        # Bù field từ step 1 nếu structure bỏ trống (yeu_cau_goc/hsdt đã xác định ở list).
        if not item.get("yeu_cau_goc"):
            item["yeu_cau_goc"] = crit.get("yeu_cau_goc", "")
        if not item.get("hsdt_can_kiem_tra"):
            item["hsdt_can_kiem_tra"] = crit.get("hsdt_can_kiem_tra", [])
        # Bù hsdt_kiem_tra per item (1 hồ sơ) nếu LLM để trống -> lấy hồ sơ đầu của tiêu chí.
        default_hsdt = str((item.get("hsdt_can_kiem_tra") or [""])[0] or "")
        for n in item.get("noi_dung_can_kiem_tra", []):
            if not (n.get("hsdt_kiem_tra") or "").strip():
                n["hsdt_kiem_tra"] = default_hsdt

        log.info(f'[Step2] item: {item}')
        
        return _SearchReq(crit=crit, item=item)

    async def _tra(self, *args: Any, **kw: Any) -> list[dict]:
        """retrieve trong THREAD RIÊNG.

        `self._retrieve` là hàm ĐỒNG BỘ: embed query qua HTTP tới Ollama + dựng/chạy BM25 + truy
        Qdrant. Gọi thẳng trong step async sẽ đóng băng event loop — mọi need và mọi tiêu chí đang
        chạy song song đều đứng chờ, kể cả những cái chỉ đang đợi mạng.
        """
        return await asyncio.to_thread(self._retrieve, *args, **kw)

    async def _xu_ly_need(self, crit: dict, n: dict, ten: str) -> None:
        """Tra cứu + resolve cho MỘT nội dung — sửa `n` tại chỗ. Nuốt lỗi theo đúng lối cũ.

        Semaphore chặn trần số need đang bay: 6 tiêu chí x 7 need có thể bắn ~28 call đồng thời
        vào proxy nếu thả tự do.
        """
        async with self._sem:
            nd = n.get("noi_dung_kiem_tra", "")
            lam_ro = n.get("can_lam_ro", "") or nd
            # 1) sinh query RIÊNG cho need này
            qout = await self._llm(SYS_QUERY, query_prompt(crit, n, sources=self._sources or None),
                                   validate=validate_query)

            base = (qout.data.get("query") if qout.status == "ok" else "") or f"{lam_ro}"
            sugg = qout.data.get("nguon_goi_y", []) if qout.status == "ok" else []
            route = [str(s) for s in sugg if str(s) in self._sources and str(s) != 'hsmt']
            # 2) định tuyến theo need: tham chiếu mẫu -> tra VÀO Biểu mẫu; còn lại -> giá trị.
            form_refs = extract_form_refs(f"{lam_ro} {n.get('yeu_cau', '')}")

            if form_refs:
                query = base.strip()
                log.info("      [retrieve|mẫu] %s | %s", nd, query)
                hits = self._merge_hits(
                    await self._tra(query, k=10, is_form=True),  # VÀO chunk Biểu mẫu
                )
                appendix = self._form_appendix(form_refs)  # need mẫu: bảng dữ liệu không liên quan
            elif route:
                query = base.strip()
                log.info("      [retrieve|nguon %s] %s | %s", ",".join(route), nd, query)
                hits = self._merge_hits(
                    await self._tra(query, k=6),
                )
                appendix = self._scan_appendix(route)
            else:
                query = base.strip()
                log.info("      [retrieve] %s | %s", nd, query)
                hits = self._merge_hits(
                    await self._tra(query, k=6, clause_doc="cdnt"),
                )
                appendix = self._bdl_appendix()
            log.debug("         [hits] %s | %s", nd, hits)

            # 3) resolve bậc 1 (kèm phụ lục A-BDL nếu là need giá trị)
            if await self._try_resolve(crit, n, hits, appendix, attempt=1):
                return
            # 4) bậc retry: query GÓC KHÁC, bỏ mọi filter, nới k (phủ Biểu mẫu/A-CDNT/TBMT)
            q2out = await self._llm(SYS_QUERY, retry_query_prompt(crit, n, query),
                                    validate=validate_query)
            base2 = (q2out.data.get("query") if q2out.status == "ok" else "") or f"{lam_ro} {ten}"
            query2 = base2.strip()
            log.info("      [retrieve|retry] %s | %s", nd, query2)
            hits2 = await self._tra(query2, k=20)
            retry_appendix = "\n\n".join(a for a in (
                self._bdl_appendix(),
                self._scan_appendix(list(self._scan_texts)),
                self._form_appendix(form_refs)
            ) if a)
            log.debug("         [hits|retry] %s | %s", nd, hits2)

            if not await self._try_resolve(crit, n, hits2, retry_appendix, attempt=2):
                n["_queries_da_thu"] = [query, query2]  # đo lường; pop ở đoạn no-fab

    # ---- Step 3: tìm giá trị cho nội dung can_tra_cuu — ĐỘC LẬP từng need, 1 call/1 việc ----
    @step
    async def search(self, ctx: Context, ev: _SearchReq) -> _Done:
        crit, item = ev.crit, ev.item
        ten = crit.get("ten", "")

        needs = [
            n for n in item.get("noi_dung_can_kiem_tra", [])
            if n.get("can_tra_cuu") and not (n.get("thong_tin_bo_sung") or "").strip()
        ]

        # NEO MÃ ĐIỀU KHOẢN VÀO QUERY ĐANG TẮT. Trước đây query = base + refs điều khoản
        # (extract_clause_refs) + "mẫu số N" (extract_form_refs) để BM25 khớp đúng dòng A-BDL/biểu
        # mẫu; nay chỉ gửi query thô của LLM. Ba biến crit_refs/refs/anchors vẫn được TÍNH rồi VỨT
        # -> đã bỏ hẳn (2 lượt regex/need cho không việc gì). Muốn bật lại: nối chúng vào `query`
        # trong _xu_ly_need. test_search_query_anchored_with_clause_ref và
        # test_search_form_need_routes_into_bieu_mau đang đỏ vì đúng chỗ này.
        if needs and self._retrieve:
            log.info("    [search] %s -> %d nội dung cần tra cứu (song song)", ten, len(needs))
            # Các need ĐỘC LẬP: _sources/_scan_texts/_form_texts chỉ đọc, _try_resolve chỉ ghi vào
            # chính `n` của nó. Chạy song song ra prompt và kết quả Y HỆT tuần tự, chỉ khác thứ tự
            # thời gian. Đây là đường găng: tiêu chí nhiều need nhất (7) tốn 14 call nối đuôi.
            await asyncio.gather(*(self._xu_ly_need(crit, n, ten) for n in needs))

        # No-fab: nội dung can_tra_cuu vẫn trống thong_tin_bo_sung -> can_review (KHÔNG bịa).
        flagged: list[str] = []
        chi_tiet: dict[str, list[str]] = {}
        for n in item.get("noi_dung_can_kiem_tra", []):
            tried = n.pop("_queries_da_thu", None)
            if n.get("can_tra_cuu") and not (n.get("thong_tin_bo_sung") or "").strip():
                n["can_review"] = True
                flagged.append(n.get("noi_dung_kiem_tra", ""))
                if tried:
                    chi_tiet[n.get("noi_dung_kiem_tra", "")] = tried
        nr = None
        if flagged:
            nr = {"ten": ten, "ly_do": f"chưa tra được thông tin HSMT cho: {', '.join(flagged)} — cần soi"}
            if chi_tiet:
                nr["queries_da_thu"] = chi_tiet
                # # 2) truy hồi RIÊNG -> bằng chứng riêng của need
                # hits = self._retrieve(query, k=20)
                # if not hits:
                #     continue
                # body = "\n".join(h["text"] for h in hits)
                # # log.info(f'[Step3] {len(hits)} hits: {hits}')
                
                # # 3) resolve RIÊNG: trích đúng 1 giá trị từ bằng chứng của need (không nhiễu chéo)
                # rout = await self._llm(SYS_RESOLVE, resolve_prompt(crit, n, body),
                #                        validate=validate_resolved_value, max_tokens=_STRUCT_MAX_TOKENS)
                # log.info(f'[Step3] rout: {rout}')
                
        #         if rout.status == "ok" and not rout.data.get("can_review") \
        #                 and (rout.data.get("thong_tin_bo_sung") or "").strip():
        #             n["thong_tin_bo_sung"] = rout.data["thong_tin_bo_sung"]
        #             n["nguon"] = rout.data.get("nguon", "") or self._hit_source(hits)
        #         elif rout.status == "error":
        #             log.warning("    [search] %s/%s -> lỗi resolve: %s", ten, nd, rout.error)

        # # No-fab: nội dung can_tra_cuu vẫn trống yeu_cau -> can_review (KHÔNG bịa).
        # flagged: list[str] = []
        # for n in item.get("noi_dung_can_kiem_tra", []):
        #     if n.get("can_tra_cuu") and not (n.get("thong_tin_bo_sung") or "").strip():
        #         n["can_review"] = True
        #         flagged.append(n.get("noi_dung_kiem_tra", ""))
        # nr = None
        # if flagged:
        #     nr = {"ten": ten, "ly_do": f"chưa tra được thông tin HSMT cho: {', '.join(flagged)} — cần soi"}
        return _Done(detail=item, needs_review=nr)

    # ---- Step 4: gom ----
    @step
    async def collect(self, ctx: Context, ev: _Done) -> StopEvent | None:
        n = await ctx.store.get("n")
        done = ctx.collect_events(ev, [_Done] * n)
        if done is None:
            return None
        group = await ctx.store.get("group")
        added = await ctx.store.get("added")
        listed_n = await ctx.store.get("listed_n")
        criteria = [d.detail for d in done]
        needs = [d.needs_review for d in done if d.needs_review]
        # Điều kiện áp dụng theo GIÁ TRỊ — đối chiếu ở đây (không ở search) vì analyze cũng có
        # đường trả _Done thẳng, và tới đây mọi thong_tin_bo_sung của tiêu chí đã tra xong.
        n_bo = sum(doi_chieu_tieu_chi(c, self._anchors) for c in criteria)
        log.info("  [collect] %d tiêu chí, %d cần soi, %d nội dung KHÔNG áp dụng (điều kiện HSMT)",
                 len(criteria), len(needs), n_bo)
        return StopEvent(result=self._assemble(group, criteria, added, listed_n, needs))
