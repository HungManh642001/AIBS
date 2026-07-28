"""CLI: chuong3_groups.json + vector index -> decomposition.json/.md + report.

Chế độ thật cần LiteLLM proxy (LLM phân rã). Truy hồi qua index Qdrant on-disk.
Test offline tiêm llm_fn/retrieve_fn kịch bản (xem tests/).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
import pickle
import os

from experiment.logger_config import setup_logger
log = setup_logger('DECOMPOSE', 'decompose.log')

from config import get_settings

from experiment.decompose.anchors import build_anchors
from experiment.decompose.llm import default_llm_fn
from experiment.decompose.retrieval import open_disk_index
from experiment.decompose.schema import DecomposeResult, GroupDecomposition, result_to_json
from experiment.decompose.workflow import DecomposeWorkflow
from experiment.index.build_index import _DEFAULT_NODES

_DEFAULT_GROUPS = "experiment/out/chuong3_groups.json"
_DEFAULT_DB = "experiment/out/qdrant"
_DEFAULT_OUT = "experiment/out"
_DEFAULT_CHUNKS = "experiment/out/chunks.jsonl"
_DEFAULT_SUMMARIES = "experiment/out/source_summaries.json"
_HSMT_SUMMARY = ("Hồ sơ mời thầu chính: gồm nội dung chỉ dẫn nhà thầu A-CDNT; bảng dữ liệu mời thầu A-BDL (gồm một số thông tin dữ liệu yêu cầu về gói thầu); "
                 "tiêu chuẩn đánh giá; quy đinh hình thức, nội dung các biểu mẫu, hợp đồng; yêu cầu kỹ thuật")

os.environ["OPENAI_API_KEY"] = "mock-key-b25-llamaindex-retriever"


def _read_chunks(chunks_path: str | None) -> list[dict[str, Any]]:
    if not chunks_path:
        return []
    p = Path(chunks_path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_bdl_rows(chunks_path: str | None) -> list[dict[str, Any]]:
    """Đọc chunks.jsonl -> các dòng Bảng dữ liệu (clause_doc='bdl') cho phụ lục resolve."""
    return [c for c in _read_chunks(chunks_path) if c.get("clause_doc") == "bdl"]


def _load_scan_texts(chunks_path: str | None) -> dict[str, str]:
    """chunks.jsonl -> {source_doc: nguyên văn} các nguồn NGOÀI hsmt"""
    out: dict[str, list[str]] = {}
    for c in _read_chunks(chunks_path):
        src = c.get("source_doc") or "hsmt"
        if src != "hsmt" and (c.get("text") or "").strip():
            out.setdefault(src, []).append(c["text"])
    return {k: "\n".join(v) for k, v in out.items()}


def _fmt_summary(v: Any) -> str:
    """Giá trị summaries -> chuỗi hiển thị: thẻ {tom_tat, cac_truong} phẳng hóa; chuỗi giữ nguyên"""
    if isinstance(v, dict):
        tom_tat = str(v.get("tom_tat", "") or "").strip()
        truong = [s for s in (str(t).strip() for t in (v.get("cac_truong") or [])) if s]
        if truong:
            return f"{tom_tat} (chứa: {', '.join(truong)})" if tom_tat else f"chứa: {', '.join(truong)}"
        return tom_tat
    return str(v).strip()


def _load_form_texts(chunks_path: str | None) -> dict[str, str]:
    """chunks.jsonl -> {mã mẫu: nguyên văn TRỌN BỘ} cho phụ lục resolve của need 'đúng mẫu sô N'

    Chunk con của sub-form (05C.1) thường tham chiếu parent (05C). Logic KHÔNG cho phép
    current revert từ sub-form về parent: nếu detected < current (prefix ngắn hơn) => giữ current.
    """
    from experiment.index.schema import form_id_of, is_form_chunk

    out: dict[str, list[str]] = {}
    current = ""
    for c in _read_chunks(chunks_path):
        if not is_form_chunk(c):
            current = ""
            continue
        detected = form_id_of(c)
        if detected:
            # Chỉ đổi form khi ID mới khác VÀ KHÔNG là parent của current
            # vd: current=05c.1, detected=05c -> giữ 05c.1 (05c là parent)
            # vd: current=05c, detected=06 -> đổi 06 (khác hẳn)
            # vd: current=05c, detected=05c.1 -> đổi 05c.1 (child mới)
            if detected != current and (not current or not current.startswith(detected)):
                current = detected
        if current and (c.get("text") or "").strip():
            out.setdefault(current, []).append(c["text"])
    return {k: "\n".join(v) for k, v in out.items()}


def _load_summaries(path: str | None) -> dict[str, str]:
    """source_summarires.json -> {source_doc: tóm tắt}"""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    out =  {str(k): _fmt_summary(v) for k, v in data.items()}
    return {k: v for k, v in out.items() if v}


def _to_markdown(r: DecomposeResult) -> str:
    lines = [f"# Phân rã tiêu chí — {r.doc}", "", f"Tổng: {r.summary}", ""]
    for g in r.groups:
        lines.append(f"## {g.group} — {g.muc}")
        if g.is_reference:
            lines.append(f"> tham chiếu: {g.ref_target}")
        lines.append(
            f"- coverage: listed={g.coverage.listed_n} final={g.coverage.final_n} "
            f"added={g.coverage.added_by_critique}"
        )
        for c in g.criteria:
            nds = c.get("noi_dung_can_kiem_tra", [])
            flag = " ⚠️cần review" if (any(n.get("can_review") for n in nds) or c.get("loi_ai")) else ""
            lines.append(f"- **{c.get('ten')}** ({c.get('nhom')}){flag}")
            if c.get("yeu_cau_goc"):
                lines.append(f"    - yêu cầu gốc: {c.get('yeu_cau_goc')}")
            if c.get("hsdt_can_kiem_tra"):
                lines.append(f"    - HSDT cần kiểm tra: {', '.join(map(str, c.get('hsdt_can_kiem_tra')))}")
            for n in nds:
                if n.get("thong_tin_bo_sung"):
                    val = n["thong_tin_bo_sung"]
                    if n.get("nguon"):
                        val += f" [nguồn: {n['nguon']}]"
                elif n.get("can_review"):
                    val = "⚠️cần review"
                elif n.get("can_tra_cuu"):
                    val = f"(cần tra cứu: {n.get('can_lam_ro', '')})"
                else:
                    val = "—"
                hs = f" ·HSDT:{n['hsdt_kiem_tra']}" if n.get("hsdt_kiem_tra") else ""
                lines.append(f"        - {n.get('noi_dung_kiem_tra')}{hs}")
                lines.append(f"            · yêu cầu: {n.get('yeu_cau', '')}")
                lines.append(f"            · thông tin bổ sung: {val}")
        if g.needs_review:
            lines.append(f"- needs_review: {g.needs_review}")
        lines.append("")
    return "\n".join(lines)


async def run(
    groups_path: str = _DEFAULT_GROUPS,
    db_path: str = _DEFAULT_DB,
    out_dir: str = _DEFAULT_OUT,
    llm_fn: Any | None = None,
    retrieve_fn: Any | None = None,
    settings: Any | None = None,
    chunks_path: str | None = None,
    summaries_path: str | None = None,
) -> dict[str, Any]:
    """Phân rã 4 nhóm; ghi decomposition.json/.md + report; trả metrics.

    chunks_path (tùy chọn): chunks.jsonl để nạp dòng A-BDL làm phụ lục resolve (recall tất định).
    """
    settings = settings or get_settings()
    gp = Path(groups_path)
    if not gp.exists():
        raise FileNotFoundError(f"Không thấy {gp} (chạy bước extract trước)")
    data = json.loads(gp.read_text(encoding="utf-8"))

    bdl_rows = _load_bdl_rows(chunks_path)
    if chunks_path:
        log.info("Phụ lục A-BDL: %d dòng (từ %s)", len(bdl_rows), chunks_path)

    scan_texts = _load_scan_texts(chunks_path)
    sources: dict[str, str] | None = None
    if scan_texts:
        summaries = _load_summaries(summaries_path)
        sources = {"hsmt": _HSMT_SUMMARY}
        for s in scan_texts:
            sources[s] = summaries.get(s) or s
        log.info(f"Danh mục nguồn route: {list(sources)}")

    form_texts = _load_form_texts(chunks_path)
    # log.info(f"[FORM TEXT]: {form_texts}")
    # log.info(f"[FORM TEXT]: {form_texts.get('02')}")

    llm_fn = llm_fn or default_llm_fn
    
    # Bảng neo gói thầu (hướng A): 1 call/run trích mốc chung -> mọi RESOLVE tự đủ.
    anchors: dict[str, dict[str, str]] = {}
    if bdl_rows or scan_texts:
        anchors = await build_anchors(llm_fn, bdl_rows, scan_texts)
        if anchors:
            log.info("Bảng neo gói thầu: %s", list(anchors))
            log.info("Bảng neo gói thầu: %s", anchors)

    close_client = None
    if retrieve_fn is None:
        with open(_DEFAULT_NODES, 'rb') as f:
            nodes = pickle.load(f)
        close_client, retrieve_fn = open_disk_index(db_path, nodes, settings)
    

    # query = 'ngày phát hành hồ sơ mời thầu hoặc thời điểm ký thư bảo lãnh dự thầu'
    # query = 'thời điểm phát hành hồ sơ mời thầu ngày bắt đầu cung cấp hồ sơ mời thầu'
    # query = 'Mục 17.3 A-CDNT các trường hợp vi phạm không dự thầu'
    # res = retrieve_fn(query, k=10, clause_doc="cdnt")
    # log.info(len(res))
    # for i in res:
    #     log.info(i)
    # return

    try:
        result = DecomposeResult(doc=data.get("doc", "HSMT"))
        groups = data.get("groups", [])
        for i, g in enumerate(groups, 1):
            log.info("=== Nhóm %d/%d: %s ===", i, len(groups), g.get("group", ""))
            wf = DecomposeWorkflow(llm_fn=llm_fn, retrieve_fn=retrieve_fn, timeout=600,
                                   bdl_rows=bdl_rows or None, source_summaries=sources,
                                   scan_texts=scan_texts or None, 
                                   form_texts=form_texts or None,
                                   anchors=anchors or None)
            gd: GroupDecomposition = await wf.run(group=g)
            result.groups.append(gd)
            break
    finally:
        if close_client is not None:
            close_client.close()

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decomposition.json").write_text(
        json.dumps(result_to_json(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "decomposition.md").write_text(_to_markdown(result), encoding="utf-8")
    metrics = {"doc": result.doc, **result.summary,
               "groups": [g.group for g in result.groups]}
    (out / "decompose_report.md").write_text(
        f"# Decompose report\n\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
    )
    return metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phân rã tiêu chí (agentic workflow)")
    ap.add_argument("--groups", default=_DEFAULT_GROUPS)
    ap.add_argument("--db", default=_DEFAULT_DB)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    ap.add_argument("--chunks", default=_DEFAULT_CHUNKS,
                    help="chunks.jsonl để nạp dòng A-BDL làm phụ lục resolve")
    ap.add_argument("--summaries", default=_DEFAULT_SUMMARIES, 
                    help="source_summaries.json ({nguồn: tóm tắt}) bật route theo nguồn (đa nguồn)")
    ap.add_argument("--quiet", action="store_true", help="tắt log tiến độ")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    try:
        metrics = asyncio.run(run(groups_path=args.groups, db_path=args.db, out_dir=args.out,
                                  chunks_path=args.chunks, summaries_path=args.summaries))
    except Exception as exc:  # no-silent-mock: báo lỗi rõ
        print(f"[run_decompose] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy chạy & phục vụ model. ", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
