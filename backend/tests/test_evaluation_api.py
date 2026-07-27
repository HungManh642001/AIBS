"""Tests evaluation router — pipeline verdict (offline, monkeypatch evaluate_vendor).

Không gọi /rubric thật (decompose cần proxy) hay vision thật; seed tiêu chí qua PUT /rubric.
"""
from experiment.evaluate.schema import (
    CriterionEval, EvalResult, HoSoNhanDuoc, VendorContext, VendorProfile, Verdict,
)


def _fake_eval(ket_qua: str = "đạt", *, phat_hien: bool = False):
    """evaluate_vendor giả: verdict theo `ket_qua` cho mọi nội dung, roll-up + loại như thật.

    Nhận **kwargs (router giờ truyền vendor_ctx=) + trả EvalResult ĐỦ field (vendor_profile,
    ho_so_nhan_duoc, phat_hien_bo_sung) — chứng minh router lưu đủ chuỗi audit + hình thức.
    """
    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo",
                                                    bang_chung="dự thầu độc lập", do_tin=0.9),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1)])
        for c in criteria:
            verds = [Verdict(
                noi_dung_kiem_tra=nd["noi_dung_kiem_tra"], hsdt_kiem_tra=nd["hsdt_kiem_tra"],
                yeu_cau=nd["yeu_cau"], thong_tin_bo_sung=nd["thong_tin_bo_sung"],
                ket_qua=ket_qua, bang_chung="bằng chứng", trang=[1], do_tin=0.9, ghi_chu="",
                nguon_hsmt=nd.get("nguon", ""), nguon_doc=[])
                for nd in c["noi_dung_can_kiem_tra"]]
            loai = ket_qua == "không đạt" and c["tien_quyet"]
            r.criteria.append(CriterionEval(
                nhom=c["nhom"], ten=c["ten"], tien_quyet=c["tien_quyet"], ket_qua=ket_qua,
                loai=loai, verdicts=verds, yeu_cau_goc=c.get("yeu_cau_goc", "")))
        if phat_hien:   # kiểm tra thường trực nay là TIÊU CHÍ như mọi tiêu chí khác
            from experiment.evaluate.schema import NHOM_PHAT_HIEN
            r.criteria.append(CriterionEval(
                nhom=NHOM_PHAT_HIEN, ten="Người ký khớp ĐKKD", tien_quyet=False, ket_qua="đạt",
                loai=False, yeu_cau_goc="",
                verdicts=[Verdict(
                    noi_dung_kiem_tra="Người ký khớp ĐKKD", hsdt_kiem_tra="don_du_thau",
                    yeu_cau="", thong_tin_bo_sung="", ket_qua="đạt", bang_chung="khớp",
                    trang=[1], do_tin=0.9, ghi_chu="",
                    nguon_doc=["don_du_thau", "dang_ky_kinh_doanh"])]))
        return r
    return fake


def _seed(client, tien_quyet: bool = True) -> int:
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-EV", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [{
        "nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "Có đơn dự thầu hợp lệ",
        "hsdt_can_kiem_tra": ["don_du_thau"], "tien_quyet": tien_quyet,
        "noi_dung_can_kiem_tra": [{
            "noi_dung_kiem_tra": "Chữ ký & con dấu", "hsdt_kiem_tra": "don_du_thau",
            "yeu_cau": "có chữ ký", "can_lam_ro": "", "can_tra_cuu": False,
            "thong_tin_bo_sung": "", "nguon": "E-CDNT 1.1", "can_review": False}]}]})
    return pid


def _upload_pdf(client, pid: int, vendor_id: int, name: str = "don.pdf",
                text: str = "Đơn dự thầu") -> int:
    """Tải 1 PDF thật cho nhà thầu -> trả doc_id (cache OCR gắn vào tài liệu này)."""
    import fitz
    d = fitz.open(); d.new_page().insert_text((72, 72), text)
    r = client.post(f"/api/v1/packages/{pid}/documents",
                    files={"file": (name, d.tobytes(), "application/pdf")},
                    data={"loai": "HSDT", "vendor_id": str(vendor_id),
                          "artifact_type": "don_du_thau"})
    return r.json()["data"]["id"]


def test_evaluate_passes_ocr_cache_bound_to_documents(client, monkeypatch):
    """Router phải cấp cache gắn ĐÚNG tài liệu -> chấm lại không OCR lại (chỗ tốn nhất)."""
    from experiment.evaluate.ingest import DPI_MAC_DINH, ingest_cache_key

    seen = {}
    base = _fake_eval("đạt")

    async def fake(criteria, hsdt_files, *, cache=None, **kw):
        seen["cache"] = cache
        seen["files"] = hsdt_files
        return await base(criteria, hsdt_files, **kw)

    monkeypatch.setattr("routers.evaluation.evaluate_vendor", fake)
    pid = _seed(client)
    vid = client.get(f"/api/v1/packages/{pid}").json()["data"]["vendors"][0]["id"]
    _upload_pdf(client, pid, vid)
    client.post(f"/api/v1/packages/{pid}/evaluate")

    cache = seen["cache"]
    assert cache is not None
    key = ingest_cache_key(seen["files"][0][2], DPI_MAC_DINH)
    assert cache.get(key) is None                       # lần đầu: chưa có gì
    cache.put(key, [{"trang": 1, "text": "đã OCR", "co_chu_ky": False, "co_dau": False}])
    assert cache.get(key)[0]["text"] == "đã OCR"        # lưu được và đọc lại đúng


def test_clear_ocr_cache_endpoint(client, monkeypatch):
    from experiment.evaluate.ingest import DPI_MAC_DINH, ingest_cache_key

    seen = {}
    base = _fake_eval("đạt")

    async def fake(criteria, hsdt_files, *, cache=None, **kw):
        seen["cache"] = cache
        seen["files"] = hsdt_files
        return await base(criteria, hsdt_files, **kw)

    monkeypatch.setattr("routers.evaluation.evaluate_vendor", fake)
    pid = _seed(client)
    vid = client.get(f"/api/v1/packages/{pid}").json()["data"]["vendors"][0]["id"]
    doc_id = _upload_pdf(client, pid, vid)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    key = ingest_cache_key(seen["files"][0][2], DPI_MAC_DINH)
    seen["cache"].put(key, [{"trang": 1, "text": "đã OCR", "co_chu_ky": False, "co_dau": False}])

    r = client.delete(f"/api/v1/packages/{pid}/cache?loai=ocr&doc_id={doc_id}")
    assert r.status_code == 200 and r.json()["data"]["n_tai_lieu"] == 1

    client.post(f"/api/v1/packages/{pid}/evaluate")     # chấm lại -> cache phải trống
    assert seen["cache"].get(key) is None


def test_cham_lai_khong_ocr_lai_qua_toan_bo_stack(client, monkeypatch):
    """E2E (evaluate_vendor THẬT): chấm lần 2 không phát sinh call vision ingest nào.

    Đây là test duy nhất bắt được lỗi lệch tham số giữa nơi băm khóa (router) và nơi dùng khóa
    (ingest) — lệch thì cache không bao giờ hit mà chẳng có lỗi nào báo ra.
    """
    from experiment.evaluate.vision import ScriptedVision

    vision = ScriptedVision({"[IN]": {"text": "Đơn dự thầu", "co_chu_ky": True, "co_dau": True},
                             "[VENDOR_FORM]": {"hinh_thuc": "độc lập", "bang_chung": "độc lập",
                                               "trang": [1], "do_tin": 0.9},
                             "[EV:": {"ket_qua": "đạt", "bang_chung": "ok", "trang": [1]},
                             "[RULE:": {"ket_qua": "đạt", "bang_chung": "ok", "trang": [1]}})
    monkeypatch.setattr("experiment.evaluate.pipeline.default_vision_fn", vision)

    pid = _seed(client)
    vid = client.get(f"/api/v1/packages/{pid}").json()["data"]["vendors"][0]["id"]
    _upload_pdf(client, pid, vid)

    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    lan_1 = sum(1 for c in vision.calls if "[IN]" in c[0])
    assert lan_1 > 0                                    # lần đầu: có OCR thật

    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    lan_2 = sum(1 for c in vision.calls if "[IN]" in c[0]) - lan_1
    assert lan_2 == 0                                   # lần sau: 0 call OCR

    # Xóa cache -> chấm lại phải OCR lại đúng số trang như lần đầu
    client.delete(f"/api/v1/packages/{pid}/cache")
    client.post(f"/api/v1/packages/{pid}/evaluate")
    lan_3 = sum(1 for c in vision.calls if "[IN]" in c[0]) - lan_1
    assert lan_3 == lan_1


def test_cham_lai_cho_ket_qua_giong_het(client, monkeypatch):
    """Chấm lại cùng hồ sơ + cùng tiêu chí -> verdict Y HỆT, dù model có đổi ý.

    Đây là thứ người dùng thấy trực tiếp: mỗi lần chấm lại một bảng kết quả khác nhau thì không
    đối chứng được với biên bản đã in.
    """
    from experiment.evaluate.vision import ScriptedVision

    def _vision(ket_qua: str, bang_chung: str):
        return ScriptedVision({
            "[IN]": {"text": "Đơn dự thầu", "co_chu_ky": True, "co_dau": True},
            "[VENDOR_FORM]": {"hinh_thuc": "độc lập", "bang_chung": "độc lập", "trang": [1],
                              "do_tin": 0.9},
            "[EV:": {"ket_qua": ket_qua, "bang_chung": bang_chung, "trang": [1]},
            "[RULE:": {"ket_qua": ket_qua, "bang_chung": bang_chung, "trang": [1]},
        })

    pid = _seed(client)
    vid = client.get(f"/api/v1/packages/{pid}").json()["data"]["vendors"][0]["id"]
    _upload_pdf(client, pid, vid)

    monkeypatch.setattr("experiment.evaluate.pipeline.default_vision_fn", _vision("đạt", "ok"))
    client.post(f"/api/v1/packages/{pid}/evaluate")
    lan_1 = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]

    # Model "đổi ý" hoàn toàn ở lần chấm sau — cache phải giữ kết quả cũ.
    doi_y = _vision("không đạt", "khác hẳn")
    monkeypatch.setattr("experiment.evaluate.pipeline.default_vision_fn", doi_y)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    lan_2 = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]

    assert lan_2["criteria"] == lan_1["criteria"]           # verdict giống HỆT
    assert not any("[EV:" in c[0] for c in doi_y.calls)     # không hỏi lại model


def test_xoa_cache_thi_cham_lai_hoi_lai_model(client, monkeypatch):
    """Xóa cache = ép AI làm lại từ đầu (dùng khi nghi verdict sai)."""
    from experiment.evaluate.vision import ScriptedVision

    def _vision(ket_qua: str):
        return ScriptedVision({
            "[IN]": {"text": "Đơn", "co_chu_ky": True, "co_dau": True},
            "[VENDOR_FORM]": {"hinh_thuc": "độc lập", "bang_chung": "x", "trang": [1],
                              "do_tin": 0.9},
            "[EV:": {"ket_qua": ket_qua, "bang_chung": "bc", "trang": [1]},
            "[RULE:": {"ket_qua": ket_qua, "bang_chung": "bc", "trang": [1]},
        })

    pid = _seed(client)
    vid = client.get(f"/api/v1/packages/{pid}").json()["data"]["vendors"][0]["id"]
    _upload_pdf(client, pid, vid)
    monkeypatch.setattr("experiment.evaluate.pipeline.default_vision_fn", _vision("đạt"))
    client.post(f"/api/v1/packages/{pid}/evaluate")

    r = client.delete(f"/api/v1/packages/{pid}/cache?loai=ai")
    assert r.status_code == 200 and r.json()["data"]["n_ket_qua_cham"] >= 1

    moi = _vision("không đạt")
    monkeypatch.setattr("experiment.evaluate.pipeline.default_vision_fn", moi)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert res["criteria"][0]["ket_qua"] == "không đạt"     # đã hỏi lại model


def test_endpoint_cache_xoa_ca_hai_loai(client):
    pid = _seed(client)
    r = client.delete(f"/api/v1/packages/{pid}/cache")
    assert r.status_code == 200
    assert {"n_tai_lieu", "n_ket_qua_cham"} <= set(r.json()["data"])


def test_clear_cache_package_not_found(client):
    r = client.delete("/api/v1/packages/9999/cache")
    assert r.status_code == 404


def test_evaluate_passes_pkg_ctx_to_pipeline(client, monkeypatch):
    """Router phải truyền ngữ cảnh gói thầu (tên/mã) — luật tên gói thầu cần để đối chiếu."""
    seen = {}
    base = _fake_eval("đạt")

    async def fake(criteria, hsdt_files, *, pkg_ctx=None, **kw):
        seen["pkg_ctx"] = pkg_ctx
        return await base(criteria, hsdt_files, **kw)

    monkeypatch.setattr("routers.evaluation.evaluate_vendor", fake)
    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    assert seen["pkg_ctx"] is not None
    assert seen["pkg_ctx"].ten == "g" and seen["pkg_ctx"].ma_so == "G-EV"


def test_kiem_tra_thuong_truc_la_tieu_chi_binh_thuong(client, monkeypatch):
    """Trên API: kiểm tra thường trực nằm CHUNG trong criteria, đếm vào summary, kéo được 'loại'."""
    from experiment.evaluate.schema import CriterionEval, NHOM_PHAT_HIEN

    base = _fake_eval("đạt")

    async def fake(criteria, hsdt_files, **kw):
        r = await base(criteria, hsdt_files, **kw)
        r.criteria.append(CriterionEval(
            nhom=NHOM_PHAT_HIEN, ten="Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)",
            tien_quyet=False, ket_qua="không đạt", loai=False, yeu_cau_goc="",
            verdicts=[Verdict(noi_dung_kiem_tra="Người ký đơn dự thầu khớp đại diện pháp luật",
                              hsdt_kiem_tra="don_du_thau", yeu_cau="", thong_tin_bo_sung="",
                              ket_qua="không đạt", bang_chung="ký A ≠ đại diện B", trang=[1],
                              do_tin=0.9, ghi_chu="", nguon_doc=["don_du_thau"])]))
        return r

    monkeypatch.setattr("routers.evaluation.evaluate_vendor", fake)
    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]

    ten = [c["ten"] for c in v["criteria"]]
    assert "Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)" in ten   # nằm chung danh sách
    assert "phat_hien_bo_sung" not in v                                    # không còn đường riêng
    assert v["summary"]["n_tieu_chi"] == 2                                 # đếm chung
    assert v["summary"]["n_loai"] == 0                                     # nhưng KHÔNG tự loại

    tt = next(c for c in v["criteria"] if c["nhom"] == NHOM_PHAT_HIEN)
    assert tt["tien_quyet"] is False and tt["loai"] is False
    assert tt["verdicts"][0]["bang_chung"] == "ký A ≠ đại diện B"


def test_evaluate_persists_audit_and_profile(client, monkeypatch):
    """Wiring: điều khoản nguồn + yêu cầu gốc + hình thức nhà thầu + kiểm tra thường trực."""
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt", phat_hien=True))
    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    v = res["vendors"][0]

    crit = v["criteria"][0]
    assert crit["yeu_cau_goc"] == "Có đơn dự thầu hợp lệ"
    assert crit["verdicts"][0]["nguon_hsmt"] == "E-CDNT 1.1"
    assert v["vendor_profile"]["hinh_thuc"] == "độc lập"
    # kiểm tra thường trực nằm CHUNG danh sách tiêu chí và đếm vào summary
    assert [c["ten"] for c in v["criteria"] if c["nhom"] == "phat_hien_bo_sung"] == \
        ["Người ký khớp ĐKKD"]
    assert v["summary"]["n_tieu_chi"] == 2


def test_evaluate_builds_vendor_context_with_abbreviation(client, monkeypatch):
    """Tên viết tắt của nhà thầu -> alias trong VendorContext (khớp webform tên đầy đủ HOẶC tắt)."""
    seen = {}

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        seen["ctx"] = vendor_ctx
        from experiment.evaluate.schema import EvalResult
        return EvalResult(doc=doc, vendor=vendor_ctx)

    monkeypatch.setattr("routers.evaluation.evaluate_vendor", fake)
    p = client.post("/api/v1/packages", json={"ma_so": "G-AB", "ten": "g"}).json()["data"]
    client.post(f"/api/v1/packages/{p['id']}/vendors",
                json={"ten": "Công ty TNHH Xây dựng ABC", "ten_viet_tat": "ABC"})
    client.put(f"/api/v1/packages/{p['id']}/rubric", json={"criteria": [{
        "nhom": "hop_le", "ten": "X", "yeu_cau_goc": "", "hsdt_can_kiem_tra": ["don_du_thau"],
        "tien_quyet": False, "noi_dung_can_kiem_tra": []}]})
    client.post(f"/api/v1/packages/{p['id']}/evaluate")

    ctx = seen["ctx"]
    assert ctx.ten == "Công ty TNHH Xây dựng ABC"
    assert "ABC" in ctx.aliases       # tên viết tắt -> alias để find_vendor_pages khớp webform


def _seed_two_vendors(client) -> tuple[int, int, int]:
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-2V", "ten": "g", "vendors": ["A", "B"]}).json()["data"]
    pkg_id = pid["id"]
    va, vb = pid["vendors"][0]["id"], pid["vendors"][1]["id"]
    client.put(f"/api/v1/packages/{pkg_id}/rubric", json={"criteria": [{
        "nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "", "hsdt_can_kiem_tra": ["don_du_thau"],
        "tien_quyet": True, "noi_dung_can_kiem_tra": [{
            "noi_dung_kiem_tra": "Chữ ký", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
            "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
            "can_review": False}]}]})
    return pkg_id, va, vb


def test_evaluate_single_vendor_only(client, monkeypatch):
    """Chạy đánh giá 1 nhà thầu -> chỉ nhà thầu đó có kết quả, nhà thầu khác chưa chạm."""
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt"))
    pid, va, vb = _seed_two_vendors(client)

    r = client.post(f"/api/v1/packages/{pid}/vendors/{va}/evaluate")
    assert r.status_code == 200 and r.json()["data"]["vendor"]["vendor_id"] == va

    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"]
    a = next(v for v in res if v["vendor_id"] == va)
    b = next(v for v in res if v["vendor_id"] == vb)
    assert a["summary"]["n_tieu_chi"] == 1 and a["criteria"]
    assert b["summary"]["n_tieu_chi"] == 0 and b["criteria"] == []   # B chưa đánh giá


def test_evaluate_single_vendor_preserves_others(client, monkeypatch):
    """Đánh giá lại B không xóa kết quả A."""
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt"))
    pid, va, vb = _seed_two_vendors(client)
    client.post(f"/api/v1/packages/{pid}/vendors/{va}/evaluate")
    client.post(f"/api/v1/packages/{pid}/vendors/{vb}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"]
    assert all(next(v for v in res if v["vendor_id"] == x)["criteria"] for x in (va, vb))


def test_evaluate_single_vendor_reeval_replaces(client, monkeypatch):
    """Chạy lại 1 nhà thầu -> thay kết quả cũ, KHÔNG nhân đôi."""
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt"))
    pid, va, _ = _seed_two_vendors(client)
    client.post(f"/api/v1/packages/{pid}/vendors/{va}/evaluate")
    client.post(f"/api/v1/packages/{pid}/vendors/{va}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"]
    a = next(v for v in res if v["vendor_id"] == va)
    assert a["summary"]["n_tieu_chi"] == 1      # không nhân đôi


def test_evaluate_single_vendor_404(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-1V4", "ten": "g"}).json()["data"]["id"]
    r = client.post(f"/api/v1/packages/{pid}/vendors/99999/evaluate")
    assert r.status_code == 404


def test_summary_counts_khong_ap_dung(client, monkeypatch):
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("không áp dụng"))
    pid = _seed(client, tien_quyet=True)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    s = res["vendors"][0]["summary"]
    assert s["n_khong_ap_dung"] == 1 and s["n_can_lam_ro"] == 0 and s["n_loai"] == 0


def test_evaluate_persists_and_reads(client, monkeypatch):
    # client fixture reload routers.evaluation mới -> patch theo đường dẫn chuỗi (module hiện tại).
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt"))
    pid = _seed(client)
    ev = client.post(f"/api/v1/packages/{pid}/evaluate")
    assert ev.status_code == 200
    assert ev.json()["data"]["vendors"][0]["summary"]["n_dat"] == 1

    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    crit = res["vendors"][0]["criteria"][0]
    assert crit["ket_qua"] == "đạt" and len(crit["verdicts"]) == 1
    assert crit["verdicts"][0]["bang_chung"] and crit["verdicts"][0]["trang"] == [1]


def test_evaluate_no_criteria_400(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-NC", "ten": "g"}).json()["data"]["id"]
    r = client.post(f"/api/v1/packages/{pid}/evaluate")
    assert r.status_code == 400


def test_override_verdict_recomputes(client, monkeypatch):
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt"))
    pid = _seed(client, tien_quyet=True)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    crit = res["vendors"][0]["criteria"][0]
    assert crit["ket_qua"] == "đạt" and crit["loai"] is False
    vid = crit["verdicts"][0]["id"]

    ov = client.put(f"/api/v1/evaluation/verdict/{vid}/override", json={"ket_qua": "không đạt"})
    assert ov.status_code == 200
    assert ov.json()["data"]["criterion"]["ket_qua"] == "không đạt"

    res2 = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    crit2 = res2["vendors"][0]["criteria"][0]
    assert crit2["ket_qua"] == "không đạt" and crit2["loai"] is True
    assert crit2["verdicts"][0]["overridden"] is True


def test_evaluate_batch_mot_nha_thau_loi_van_giu_ket_qua_con_lai(client, monkeypatch):
    """Batch: 1 nhà thầu lỗi KHÔNG được hủy kết quả của các nhà thầu đã chấm xong."""
    ok_eval = _fake_eval("đạt")

    async def flaky(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                    registry=None, pkg_ctx=None, cache=None, call_cache=None):
        if vendor_ctx and vendor_ctx.ten == "B":
            raise RuntimeError("proxy vision sập")
        return await ok_eval(criteria, hsdt_files, doc=doc, vision_fn=vision_fn,
                             vendor_ctx=vendor_ctx, registry=registry)

    monkeypatch.setattr("routers.evaluation.evaluate_vendor", flaky)
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-PF", "ten": "g", "vendors": ["A", "B", "C"]}).json()["data"]
    pid = p["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [{
        "nhom": "hop_le", "ten": "X", "yeu_cau_goc": "", "hsdt_can_kiem_tra": ["don_du_thau"],
        "tien_quyet": False, "noi_dung_can_kiem_tra": []}]})

    r = client.post(f"/api/v1/packages/{pid}/evaluate")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [v["ten"] for v in data["vendors"]] == ["A", "C"]      # 2 nhà thầu chấm được
    assert [e["ten"] for e in data["loi"]] == ["B"]               # nhà thầu lỗi báo rõ
    assert "proxy vision sập" in data["loi"][0]["error"]

    # Kết quả của A và C đã LƯU, không bị cuốn theo lỗi của B.
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    by_name = {v["ten"]: v for v in res["vendors"]}
    assert len(by_name["A"]["criteria"]) == 1 and len(by_name["C"]["criteria"]) == 1
    assert by_name["B"]["criteria"] == []


def test_evaluate_bao_loi_khi_ho_so_thieu_loai(client, monkeypatch):
    """Hồ sơ HSDT thiếu loại (dữ liệu cũ) -> báo rõ tên file, KHÔNG lặng lẽ chấm thiếu."""
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt"))
    pid = _seed(client)
    import models
    import database as _db
    sess = _db.SessionLocal()
    vid = sess.query(models.Vendor).filter_by(package_id=pid).first().id
    sess.add(models.TenderDocument(
        package_id=pid, loai="HSDT", vendor_id=vid, file_path=f"{pid}/hsdt/{vid}/bi_thieu.pdf",
        file_kind="pdf_scan", trang_thai_ocr="hoan_thanh", artifact_type=None))
    sess.commit()
    sess.close()

    r = client.post(f"/api/v1/packages/{pid}/vendors/{vid}/evaluate")
    assert r.status_code == 400
    assert "bi_thieu.pdf" in r.json()["error"]
