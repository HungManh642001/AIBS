import json
import fitz

from experiment.evaluate.run_evaluate import _parse_pkg, _parse_vendor, run
from experiment.evaluate.schema import PackageContext, VendorContext
from experiment.evaluate.vision import ScriptedVision


def _pdf(text):
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


async def test_run_e2e_legality(tmp_path):
    decomp = {"doc": "E-HSMT", "groups": [{"group": "hop_le", "muc": "Mục 1", "criteria": [{
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu",
        "noi_dung_can_kiem_tra": [{"noi_dung_kiem_tra": "Giá trị bảo lãnh",
            "hsdt_kiem_tra": "bao_dam_du_thau", "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ"}]}]},
        {"group": "tai_chinh", "criteria": [{"nhom": "tai_chinh", "ten": "Giá", "noi_dung_can_kiem_tra": []}]}]}
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps(decomp, ensure_ascii=False), encoding="utf-8")

    vision = ScriptedVision({
        "[IN]": {"text": "Thư bảo lãnh 6.100.000 VNĐ", "co_dau": True},   # vision chỉ bóc text
        "[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6.100.000", "trang": [1], "do_tin": 0.9},
    })
    out = tmp_path / "out"
    # file HSDT kèm mã catalog đã biết: (tên, loai_ho_so, data)
    metrics = await run(str(dp), [("bao_lanh.pdf", "bao_dam_du_thau", _pdf("bảo lãnh"))], str(out),
                        doc="HSDT-NhaThauA", vision_fn=vision)

    # 1 tiêu chí HSMT (chỉ nhóm hop_le) + 4 kiểm tra thường trực -> đếm CHUNG
    assert metrics["n_tieu_chi"] == 5 and metrics["n_dat"] == 1
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert data["doc"] == "HSDT-NhaThauA"
    assert data["criteria"][0]["ket_qua"] == "đạt"
    assert "image" not in str(data)                              # ảnh không lọt JSON
    assert (out / "evaluation.md").exists()


def test_parse_vendor():
    assert _parse_vendor("Công ty ABC|0312345678|abc jsc;lien danh abc") == VendorContext(
        ten="Công ty ABC", ma_so_thue="0312345678", aliases=["abc jsc", "lien danh abc"])
    assert _parse_vendor("Công ty ABC") == VendorContext(ten="Công ty ABC")
    assert _parse_vendor("") is None


def test_parse_vendor_with_hinh_thuc():
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, HINH_THUC_LIEN_DANH

    assert _parse_vendor("ABC", "doc_lap").hinh_thuc == HINH_THUC_DOC_LAP
    assert _parse_vendor("", "lien_danh") == VendorContext(ten="", hinh_thuc=HINH_THUC_LIEN_DANH)
    assert _parse_vendor("") is None                 # GIỮ hành vi cũ: cả hai rỗng -> None


def test_parse_pkg():
    assert _parse_pkg("Mua sắm thiết bị|G-01") == PackageContext(ten="Mua sắm thiết bị",
                                                                 ma_so="G-01")
    assert _parse_pkg("Mua sắm thiết bị") == PackageContext(ten="Mua sắm thiết bị")
    assert _parse_pkg("") is None


async def test_run_forwards_pkg_to_core(tmp_path):
    """--goi-thau phải xuống tới luật standing (luật tên gói thầu cần)."""
    from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleRegistry, RuleSkill
    from experiment.evaluate.schema import Verdict

    seen = {}

    async def handler(by_type, ctx, crit, vision_fn, *, nd=None, pkg=None):
        seen["pkg"] = pkg
        return Verdict(noi_dung_kiem_tra="x", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                       thong_tin_bo_sung="", ket_qua="đạt", bang_chung="", trang=[],
                       do_tin=1.0, ghi_chu="")

    reg = RuleRegistry()
    reg.register(RuleSkill(id="luat_gia", ten="Luật giả", ho_so_can=["don_du_thau"],
                           can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI))
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps({"doc": "E-HSMT", "groups": []}), encoding="utf-8")
    vision = ScriptedVision({"[IN]": {"text": "đơn"}})
    pkg = PackageContext(ten="Gói A", ma_so="01")
    await run(str(dp), [("don.pdf", "don_du_thau", _pdf("đơn"))], str(tmp_path / "out"),
              vision_fn=vision, registry=reg, pkg=pkg)
    assert seen["pkg"] == pkg


def _decomp_don(tmp_path):
    """3 tiêu chí, trong đó HAI tiêu chí cùng dùng bang_gia — tái hiện đúng bug user báo.

    Tiêu chí 2 "Bảng giá đúng mẫu" khai [bang_gia] -> eval chung. Tiêu chí 3 "Giá khớp webform"
    khai [bang_gia, webform] -> luật. Trước đây luật bắn ở tiêu chí 2 rồi `fired` chặn tiêu chí 3
    -> tiêu chí 3 ra "cần làm rõ".
    """
    decomp = {"doc": "E-HSMT", "groups": [{"group": "hop_le", "muc": "Mục 1", "criteria": [
        {"nhom": "hop_le", "ten": "Đơn dự thầu",
         "hsdt_can_kiem_tra": ["don_du_thau"],
         "noi_dung_can_kiem_tra": [
             {"noi_dung_kiem_tra": "Có đơn dự thầu", "hsdt_kiem_tra": "don_du_thau",
              "yeu_cau": "phải có", "thong_tin_bo_sung": ""}]},
        {"nhom": "hop_le", "ten": "Bảng giá đúng mẫu",
         "hsdt_can_kiem_tra": ["bang_gia"],
         "noi_dung_can_kiem_tra": [
             {"noi_dung_kiem_tra": "Bảng giá đúng mẫu", "hsdt_kiem_tra": "bang_gia",
              "yeu_cau": "đúng mẫu 05C.1", "thong_tin_bo_sung": ""}]},
        {"nhom": "hop_le", "ten": "Giá khớp webform",
         "hsdt_can_kiem_tra": ["bang_gia", "webform"],
         "noi_dung_can_kiem_tra": [
             {"noi_dung_kiem_tra": "Giá phải phù hợp với webform", "hsdt_kiem_tra": "bang_gia",
              "yeu_cau": "giá trong bảng giá phải phù hợp với webform", "thong_tin_bo_sung": "",
              "nguon": "E-BDL 26.1"}]}]}]}
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps(decomp, ensure_ascii=False), encoding="utf-8")
    return str(dp)


_FILES = [("don.pdf", "don_du_thau", None), ("dkkd.pdf", "dang_ky_kinh_doanh", None),
          ("bg.pdf", "bang_gia", None), ("webform.pdf", "webform", None)]


def _files():
    return [(n, c, _pdf(n)) for n, c, _ in _FILES]


def _vision_full():
    return ScriptedVision({
        "[IN]": {"text": "Công ty TNHH ABC | 1.200.000.000 | ký Nguyễn Văn A"},
        "[VENDOR_FORM]": {"hinh_thuc": "độc lập", "bang_chung": "Chúng tôi dự thầu độc lập",
                          "trang": [1], "do_tin": 0.9},
        "[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có đơn", "trang": [1]},
        "[EV:Bảng giá đúng mẫu]": {"ket_qua": "đạt", "bang_chung": "đúng mẫu", "trang": [1]},
        "[RULE:chu_ky_khop_dkkd]": {"ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A",
                                    "dai_dien_phap_luat": "Nguyễn Văn A", "bang_chung": "khớp", "trang": [1]},
        "[RULE:bang_gia_khop_webform]": {"ket_qua": "đạt", "bang_chung": "1.2 tỷ khớp", "trang": [1]},
    })


async def test_run_e2e_rules_with_vendor(tmp_path):
    """BUG USER BÁO: 2 tiêu chí cùng bang_gia -> tiêu chí 'giá khớp webform' phải do LUẬT trả lời.

    Trước đây luật bắn ở 'Bảng giá đúng mẫu' rồi `fired` chặn -> tiêu chí này ra 'cần làm rõ'.
    """
    out = tmp_path / "out"
    vision = _vision_full()
    metrics = await run(_decomp_don(tmp_path), _files(), str(out), doc="HSDT-A",
                        vision_fn=vision, vendor=VendorContext(ten="Công ty TNHH ABC"))
    # 3 tiêu chí HSMT + 4 kiểm tra thường trực (chữ ký đạt; tên gói SOI vì không pkg; bảo đảm
    # thiếu hồ sơ; liên danh không áp dụng) — nay đếm CHUNG.
    assert metrics["n_tieu_chi"] == 7 and metrics["n_dat"] == 3    # 3 HSMT đạt + chữ ký đạt...

    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    tc = {c["ten"]: c for c in data["criteria"]}
    # tiêu chí 'giá khớp webform' do luật trả lời, verdict mang danh tính NỘI DUNG + chuỗi audit
    v_gia = tc["Giá khớp webform"]["verdicts"][0]
    assert v_gia["noi_dung_kiem_tra"] == "Giá phải phù hợp với webform"
    assert v_gia["ket_qua"] == "đạt" and v_gia["nguon_doc"] == ["bang_gia", "webform"]
    assert v_gia["nguon_hsmt"] == "E-BDL 26.1"
    # tiêu chí 'đúng mẫu' vẫn do eval chung chấm — KHÔNG dính verdict luật
    assert tc["Bảng giá đúng mẫu"]["verdicts"][0]["nguon_doc"] == []

    # kiểm tra thường trực nay là TIÊU CHÍ riêng, nằm chung danh sách và mang nhãn nguồn gốc
    tt = [c for c in data["criteria"] if c["nhom"] == "phat_hien_bo_sung"]
    assert [c["ten"] for c in tt] == [
        "Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)",
        "Tên gói thầu ghi trong tài liệu khớp gói thầu đang xét",
        "Người ký bảo đảm dự thầu có thẩm quyền (đứng đầu hoặc ủy quyền hợp lệ)",
        "Phân công liên danh nêu rõ hạng mục và khớp tỷ lệ trong bảng giá",
    ]
    # Máy không kết luận loại: hai trường tien_quyet/loai đã bỏ khỏi hệ thống
    assert all("tien_quyet" not in c and "loai" not in c for c in tt)
    assert "phat_hien_bo_sung" not in data


def _decomp_lien_danh(tmp_path):
    """Tiêu chí hop_le về thỏa thuận liên danh — nhà thầu độc lập lẽ ra KHÔNG phải đối chiếu."""
    decomp = {"doc": "E-HSMT", "groups": [{"group": "hop_le", "muc": "Mục 1", "criteria": [{
        "nhom": "hop_le", "ten": "Thỏa thuận liên danh",
        "yeu_cau_goc": "Trường hợp liên danh, phải có thỏa thuận liên danh hợp lệ",
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Thỏa thuận liên danh hợp lệ",
             "hsdt_kiem_tra": "thoa_thuan_lien_danh", "yeu_cau": "phải có",
             "thong_tin_bo_sung": "", "nguon": "E-BDL 2.3"}]}]}]}
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps(decomp, ensure_ascii=False), encoding="utf-8")
    return str(dp)


async def test_run_e2e_doc_lap_gates_lien_danh_criterion(tmp_path):
    """Nhà thầu độc lập: tiêu chí TTLĐ -> 'không áp dụng', KHÔNG vào n_can_lam_ro, 0 call chấm."""
    vision = _vision_full()
    out = tmp_path / "out"
    metrics = await run(_decomp_lien_danh(tmp_path),
                        [("don.pdf", "don_du_thau", _pdf("đơn"))], str(out),
                        doc="HSDT-A", vision_fn=vision,
                        vendor=VendorContext(ten="Công ty TNHH ABC", hinh_thuc="doc_lap"))
    # 2 'không áp dụng': tiêu chí TTLĐ bị gate + kiểm tra phân công liên danh (nhà thầu độc lập)
    assert metrics["n_khong_ap_dung"] == 2
    assert metrics["hinh_thuc"] == "độc lập" and metrics["mau_thuan"] is False
    assert not any("[EV:Thỏa thuận liên danh" in hay for hay, _ in vision.calls)
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert data["vendor_profile"]["hinh_thuc"] == "độc lập"
    md = (out / "evaluation.md").read_text(encoding="utf-8")
    assert "Không áp dụng" in md and "chỉ áp dụng cho nhà thầu liên danh" in md


async def test_run_e2e_lien_danh_detected_from_file_no_gate(tmp_path):
    """Có file TTLĐ -> liên danh (0 call dò) -> tiêu chí TTLĐ VẪN được chấm đủ."""
    vision = ScriptedVision({
        "[IN]": {"text": "thỏa thuận liên danh A-B"},
        "[EV:Thỏa thuận liên danh hợp lệ]": {"ket_qua": "đạt", "bang_chung": "có thỏa thuận",
                                             "trang": [1]}})
    out = tmp_path / "out"
    metrics = await run(_decomp_lien_danh(tmp_path),
                        [("ld.pdf", "thoa_thuan_lien_danh", _pdf("ttld"))], str(out),
                        doc="HSDT-B", vision_fn=vision)
    assert metrics["hinh_thuc"] == "liên danh" and metrics["n_khong_ap_dung"] == 0
    assert metrics["n_dat"] == 1
    assert any("[EV:Thỏa thuận liên danh hợp lệ]" in hay for hay, _ in vision.calls)
    assert not any("[VENDOR_FORM]" in hay for hay, _ in vision.calls)   # tất định -> 0 call dò


async def test_run_e2e_conflict_declared_doc_lap_with_lien_danh_file(tmp_path):
    """MÂU THUẪN -> KHÔNG gate, chấm đủ + cảnh báo trong .md (fail-safe)."""
    vision = ScriptedVision({
        "[IN]": {"text": "thỏa thuận liên danh"},
        "[EV:Thỏa thuận liên danh hợp lệ]": {"ket_qua": "đạt", "bang_chung": "có", "trang": [1]}})
    out = tmp_path / "out"
    metrics = await run(_decomp_lien_danh(tmp_path),
                        [("ld.pdf", "thoa_thuan_lien_danh", _pdf("ttld"))], str(out),
                        doc="HSDT-C", vision_fn=vision,
                        vendor=VendorContext(ten="ABC", hinh_thuc="doc_lap"))
    assert metrics["mau_thuan"] is True and metrics["n_khong_ap_dung"] == 0
    assert metrics["hinh_thuc"] == ""              # fail-safe: không rõ -> không gate
    assert "MÂU THUẪN" in (out / "evaluation.md").read_text(encoding="utf-8")


async def test_run_e2e_rules_without_vendor_soi(tmp_path):
    """Không --vendor: luật can_vendor trả 'cần làm rõ' (không crash, không gọi handler)."""
    out = tmp_path / "out"
    await run(_decomp_don(tmp_path), _files(), str(out), doc="HSDT-A", vision_fn=_vision_full())
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    tc = {c["ten"]: c for c in data["criteria"]}
    v = tc["Giá khớp webform"]["verdicts"][0]
    assert v["ket_qua"] == "cần làm rõ" and "nhà thầu" in v["ghi_chu"]
    assert tc["Bảng giá đúng mẫu"]["ket_qua"] == "đạt"    # tiêu chí khác KHÔNG bị vạ lây
