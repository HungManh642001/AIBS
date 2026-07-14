"""CLI: decomposition.json + HSDT (pdf scan) -> evaluation.json/.md (nhóm hợp lệ)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.report import to_markdown
from experiment.evaluate.route import inventory_pages, pages_by_type
from experiment.evaluate.rules.registry import RuleRegistry, default_registry
from experiment.evaluate.schema import EvalResult, VendorContext, result_to_json
from experiment.evaluate.vendor_profile import canon_hinh_thuc, detect_vendor_profile
from experiment.evaluate.vision import default_vision_fn

log = logging.getLogger("experiment.evaluate")


def _parse_vendor(spec: str, hinh_thuc: str = "") -> VendorContext | None:
    """'Tên|MST|alias1;alias2' + hình thức khai báo -> VendorContext; cả hai rỗng -> None."""
    if not (spec or "").strip() and not (hinh_thuc or "").strip():
        return None
    parts = [p.strip() for p in (spec or "").split("|")]
    aliases = [a.strip() for a in (parts[2] if len(parts) > 2 else "").split(";") if a.strip()]
    return VendorContext(ten=parts[0], ma_so_thue=parts[1] if len(parts) > 1 else "",
                         aliases=aliases, hinh_thuc=canon_hinh_thuc(hinh_thuc))


def _legality_criteria(decomp: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in decomp.get("groups", []):
        for c in g.get("criteria", []):
            if c.get("nhom") == "hop_le" or g.get("group") == "hop_le":
                out.append(c)
    return out


async def run(decomposition_path: str, hsdt_files: list[tuple[str, str, bytes]], out_dir: str,
              doc: str = "HSDT", vision_fn: Any | None = None,
              vendor: VendorContext | None = None,
              registry: RuleRegistry | None = None) -> dict[str, Any]:
    # hsdt_files: (tên_file, loai_ho_so [mã catalog đã biết], data pdf); webform = file thường
    # với loai_ho_so="webform". vendor: danh tính nhà thầu cho luật can_vendor.
    vision_fn = vision_fn or default_vision_fn
    registry = registry if registry is not None else default_registry()
    decomp = json.loads(Path(decomposition_path).read_text(encoding="utf-8"))
    criteria = _legality_criteria(decomp)
    log.info("[run] %d tiêu chí hợp lệ, %d file HSDT", len(criteria), len(hsdt_files))

    pages = await ingest_hsdt(hsdt_files, vision_fn)
    by_type = pages_by_type(pages)   # build 1 lần cho mọi luật
    fired: set[str] = set()          # mỗi luật bắn 1 lần/vendor

    profile = await detect_vendor_profile(pages, vision_fn, vendor=vendor)
    log.info("[run] hình thức nhà thầu: %s (căn cứ: %s)", profile.hinh_thuc or "không rõ",
             profile.nguon)
    if profile.mau_thuan:
        log.warning("[run] ⚠️ MÂU THUẪN hình thức nhà thầu: %s", profile.ghi_chu)

    result = EvalResult(doc=doc, vendor=vendor, vendor_profile=profile,
                        ho_so_nhan_duoc=inventory_pages(pages))
    for c in criteria:
        result.criteria.append(await evaluate_criterion(
            c, pages, vision_fn, registry=registry, vendor_ctx=vendor, profile=profile,
            by_type=by_type, fired=fired))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(
        json.dumps(result_to_json(result), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "evaluation.md").write_text(to_markdown(result), encoding="utf-8")
    return {"doc": result.doc, "hinh_thuc": profile.hinh_thuc, "mau_thuan": profile.mau_thuan,
            **result.summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Đánh giá HSDT nhóm hợp lệ")
    ap.add_argument("--decomp", required=True, help="decomposition.json")
    ap.add_argument("--hsdt", nargs="+", required=True,
                    help="các file HSDT dạng <mã_catalog>=<đường_dẫn.pdf> (loại hồ sơ đã biết)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--doc", default="HSDT")
    ap.add_argument("--vendor", default="",
                    help='danh tính nhà thầu "Tên|MST[|alias1;alias2]" — luật webform cần')
    ap.add_argument("--hinh-thuc", default="", choices=["", "doc_lap", "lien_danh"],
                    help="hình thức dự thầu khai báo; bỏ trống -> tự dò từ HSDT")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr)
    files: list[tuple[str, str, bytes]] = []
    for spec in args.hsdt:
        if "=" not in spec:
            print(f"[run_evaluate] --hsdt cần dạng <mã>=<đường_dẫn>: {spec}", file=sys.stderr)
            return 2
        code, path = spec.split("=", 1)
        files.append((Path(path).name, code.strip(), Path(path).read_bytes()))
    try:
        metrics = asyncio.run(run(args.decomp, files, args.out, doc=args.doc,
                                  vendor=_parse_vendor(args.vendor, args.hinh_thuc)))
    except Exception as exc:  # no-silent-mock
        print(f"[run_evaluate] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy phục vụ model VL (đọc ảnh).", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
