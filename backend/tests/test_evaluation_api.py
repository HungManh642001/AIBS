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
            r.criteria.append(CriterionEval(
                nhom=c["nhom"], ten=c["ten"], ket_qua=ket_qua, verdicts=verds, yeu_cau_goc=c.get("yeu_cau_goc", "")))
        if phat_hien:   # kiểm tra thường trực nay là TIÊU CHÍ như mọi tiêu chí khác
            from experiment.evaluate.schema import NHOM_PHAT_HIEN
            r.criteria.append(CriterionEval(
                nhom=NHOM_PHAT_HIEN, ten="Người ký khớp ĐKKD", ket_qua="đạt", yeu_cau_goc="",
                verdicts=[Verdict(
                    noi_dung_kiem_tra="Người ký khớp ĐKKD", hsdt_kiem_tra="don_du_thau",
                    yeu_cau="", thong_tin_bo_sung="", ket_qua="đạt", bang_chung="khớp",
                    trang=[1], do_tin=0.9, ghi_chu="",
                    nguon_doc=["don_du_thau", "dang_ky_kinh_doanh"])]))
        return r
    return fake


def _seed(client) -> int:
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-EV", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [{
        "nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "Có đơn dự thầu hợp lệ",
        "hsdt_can_kiem_tra": ["don_du_thau"],
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
            nhom=NHOM_PHAT_HIEN, ten="Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)", ket_qua="không đạt", yeu_cau_goc="",
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

    tt = next(c for c in v["criteria"] if c["nhom"] == NHOM_PHAT_HIEN)
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
        "nhom": "hop_le", "ten": "X", "yeu_cau_goc": "", "hsdt_can_kiem_tra": ["don_du_thau"], "noi_dung_can_kiem_tra": []}]})
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
        "nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "", "hsdt_can_kiem_tra": ["don_du_thau"], "noi_dung_can_kiem_tra": [{
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
    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    s = res["vendors"][0]["summary"]
    assert s["n_khong_ap_dung"] == 1 and s["n_can_lam_ro"] == 0


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
    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    crit = res["vendors"][0]["criteria"][0]
    assert crit["ket_qua"] == "đạt"
    vid = crit["verdicts"][0]["id"]

    ov = client.put(f"/api/v1/evaluation/verdict/{vid}/override", json={"ket_qua": "không đạt"})
    assert ov.status_code == 200
    assert ov.json()["data"]["criterion"]["ket_qua"] == "không đạt"

    res2 = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    crit2 = res2["vendors"][0]["criteria"][0]
    assert crit2["ket_qua"] == "không đạt"
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
        "nhom": "hop_le", "ten": "X", "yeu_cau_goc": "", "hsdt_can_kiem_tra": ["don_du_thau"], "noi_dung_can_kiem_tra": []}]})

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


def _fake_eval_thieu():
    """evaluate_vendor giả: tiêu chí đầu có 1 verdict 'thiếu hồ sơ' + 1 'đạt', tiêu chí sau 'đạt'.

    Roll-up cuộn 'thiếu hồ sơ' thành 'cần làm rõ' -> chính là ca mà ô đếm mới phải bóc tách ra.
    """
    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1)])
        for i, c in enumerate(criteria):
            kqs = ["thiếu hồ sơ", "đạt"] if i == 0 else ["đạt"]
            verds = [Verdict(
                noi_dung_kiem_tra=f"nd{j}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                thong_tin_bo_sung="", ket_qua=kq, bang_chung="", trang=[], do_tin=0.0,
                ghi_chu="", nguon_doc=[]) for j, kq in enumerate(kqs)]
            r.criteria.append(CriterionEval(
                nhom=c["nhom"], ten=c["ten"],
                ket_qua="cần làm rõ" if i == 0 else "đạt", verdicts=verds, yeu_cau_goc=""))
        return r
    return fake


def test_summary_dem_rieng_thieu_ho_so(client, monkeypatch):
    """'thiếu hồ sơ' (nhà thầu không nộp) khác hẳn 'cần làm rõ' (AI chưa đủ căn cứ) — phải bóc tách."""
    import routers.evaluation as re_

    pid = _seed(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_thieu())
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200

    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    s = v["summary"]
    assert s["n_thieu_ho_so"] == 1
    # LÁT CẮT ĐỘC LẬP trên cùng tập tiêu chí, KHÔNG phải khoản mục con của n_can_lam_ro (nó có thể
    # lớn hơn n_can_lam_ro — xem test_thieu_ho_so_trong_tieu_chi_da_khong_dat_van_dem). Cận trên
    # duy nhất đúng là tổng số tiêu chí.
    assert s["n_thieu_ho_so"] <= s["n_tieu_chi"]
    # Đẳng thức tổng KHÔNG được vỡ khi thêm ô đếm mới (n_thieu_ho_so đứng NGOÀI đẳng thức này).
    assert s["n_tieu_chi"] == (s["n_dat"] + s["n_khong_dat"]
                               + s["n_can_lam_ro"] + s["n_khong_ap_dung"])


def test_mot_tieu_chi_hai_verdict_thieu_van_dem_mot(client, monkeypatch):
    """Đếm TIÊU CHÍ, không đếm verdict — hai nội dung cùng thiếu vẫn là một tiêu chí."""
    import routers.evaluation as re_

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"))
        c = criteria[0]
        verds = [Verdict(noi_dung_kiem_tra=f"nd{j}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                         thong_tin_bo_sung="", ket_qua="thiếu hồ sơ", bang_chung="", trang=[],
                         do_tin=0.0, ghi_chu="", nguon_doc=[]) for j in range(2)]
        r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="cần làm rõ",
                                        verdicts=verds, yeu_cau_goc=""))
        return r

    pid = _seed(client)
    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    s = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]["summary"]
    assert s["n_thieu_ho_so"] == 1


def test_thieu_ho_so_trong_tieu_chi_da_khong_dat_van_dem(client, monkeypatch):
    """'thiếu hồ sơ' là LÁT CẮT ĐỘC LẬP, không phải con của 'cần làm rõ'.

    _rollup ưu tiên KET_QUA_KHONG trước {SOI, THIEU, LOI} (routers/evaluation.py:83-86): một tiêu
    chí có cả verdict 'không đạt' lẫn 'thiếu hồ sơ' roll-up thành 'không đạt', rơi vào
    n_khong_dat chứ KHÔNG vào n_can_lam_ro. Nếu _summary lọc n_thieu_ho_so theo
    e.ket_qua == KET_QUA_SOI thì ca này bị giấu mất — mà đây đúng là chỗ chuyên gia cần biết
    nhất (tiêu chí đã hỏng vì lý do khác, LẠI CÒN thiếu tài liệu). Nên ở đây n_thieu_ho_so (1) >
    n_can_lam_ro (0) là ĐÚNG, không phải bug.
    """
    import routers.evaluation as re_

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"))
        c = criteria[0]
        verds = [
            Verdict(noi_dung_kiem_tra="nd0", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                    thong_tin_bo_sung="", ket_qua="không đạt", bang_chung="", trang=[],
                    do_tin=0.0, ghi_chu="", nguon_doc=[]),
            Verdict(noi_dung_kiem_tra="nd1", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                    thong_tin_bo_sung="", ket_qua="thiếu hồ sơ", bang_chung="", trang=[],
                    do_tin=0.0, ghi_chu="", nguon_doc=[]),
        ]
        r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="không đạt",
                                        verdicts=verds, yeu_cau_goc=""))
        return r

    pid = _seed(client)
    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    s = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]["summary"]

    assert s["n_khong_dat"] == 1
    assert s["n_can_lam_ro"] == 0
    assert s["n_thieu_ho_so"] == 1        # > n_can_lam_ro -> ĐÚNG, không phải bug (xem docstring)
    assert s["n_tieu_chi"] == (s["n_dat"] + s["n_khong_dat"]
                               + s["n_can_lam_ro"] + s["n_khong_ap_dung"])


def _seed_hai_loai(client) -> int:
    """Gói có 3 tiêu chí: đơn dự thầu; bảng giá ↔ webform (dùng chung); thỏa thuận liên danh."""
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-CN", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "Có đơn",
         "hsdt_can_kiem_tra": ["don_du_thau"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có đơn", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},
        {"nhom": "hop_le", "ten": "Giá khớp webform", "yeu_cau_goc": "Giá khớp",
         "hsdt_can_kiem_tra": ["bang_gia", "webform"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Giá khớp", "hsdt_kiem_tra": "bang_gia", "yeu_cau": "khớp",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},
        {"nhom": "hop_le", "ten": "Thỏa thuận liên danh", "yeu_cau_goc": "Có thỏa thuận",
         "hsdt_can_kiem_tra": ["thoa_thuan_lien_danh"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có thỏa thuận", "hsdt_kiem_tra": "thoa_thuan_lien_danh",
             "yeu_cau": "có", "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "",
             "nguon": "", "can_review": False, "ap_dung": "lien_danh"}]},
    ]})
    return pid


def _fake_eval_nhan_don(hinh_thuc: str = "độc lập"):
    """evaluate_vendor giả: nhà thầu CHỈ nộp đơn dự thầu, hình thức theo tham số."""
    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc=hinh_thuc, nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1)])
        for c in criteria:
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="đạt",
                                            verdicts=[], yeu_cau_goc=""))
        return r
    return fake


def test_ho_so_chua_nop_loai_webform_va_lien_danh_cho_nha_thau_doc_lap(client, monkeypatch):
    """webform là tài liệu bên mời thầu; thỏa thuận liên danh không áp dụng nhà thầu độc lập."""
    import routers.evaluation as re_

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200

    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    loais = [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]
    assert "bang_gia" in loais                    # thật sự thiếu
    assert "don_du_thau" not in loais             # đã nộp
    assert "webform" not in loais                 # tài liệu DÙNG CHUNG, không phải nhà thầu nộp
    assert "thoa_thuan_lien_danh" not in loais    # chỉ áp dụng liên danh
    # Mỗi mục nêu tiêu chí bị ảnh hưởng để chuyên gia thấy ngay hệ quả.
    bg = next(x for x in v["ho_so_chua_nop"] if x["loai_ho_so"] == "bang_gia")
    assert bg["tieu_chi"] == ["Giá khớp webform"]


def test_ho_so_chua_nop_bao_thoa_thuan_lien_danh_cho_nha_thau_lien_danh(client, monkeypatch):
    import routers.evaluation as re_

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("liên danh"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_hinh_thuc_khong_ro_thi_khong_tru_gi(client, monkeypatch):
    """Fail-safe: không dò được hình thức -> thà báo thừa còn hơn giấu mất hồ sơ thật sự thiếu."""
    import routers.evaluation as re_

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don(""))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_rong_khi_nop_du(client, monkeypatch):
    import routers.evaluation as re_

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1),
                                        HoSoNhanDuoc("bang_gia", ["bg.pdf"], 2)])
        for c in criteria:
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="đạt",
                                            verdicts=[], yeu_cau_goc=""))
        return r

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert v["ho_so_chua_nop"] == []


def _seed_chi_lien_danh_khong_gan_co(client) -> int:
    """1 tiêu chí thỏa thuận liên danh mà decompose QUÊN gán `ap_dung` — mô phỏng thiếu sót thật
    của LLM lúc bóc tiêu chí (`ap_dung` không phải trường bắt buộc, khác `_HO_SO_CHI_LIEN_DANH`
    là hằng CODE kiểm soát)."""
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-LD0", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Thỏa thuận liên danh", "yeu_cau_goc": "Có thỏa thuận",
         "hsdt_can_kiem_tra": ["thoa_thuan_lien_danh"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có thỏa thuận", "hsdt_kiem_tra": "thoa_thuan_lien_danh",
             "yeu_cau": "có", "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "",
             "nguon": "", "can_review": False}]},   # KHÔNG có "ap_dung" -> mặc định ""
    ]})
    return pid


def test_ho_so_chua_nop_khong_bao_lien_danh_du_ap_dung_rong_khi_nha_thau_doc_lap(client, monkeypatch):
    """Ca chính của fix: decompose quên gán ap_dung='lien_danh', nhưng thoa_thuan_lien_danh nằm
    trong _HO_SO_CHI_LIEN_DANH (evaluate.py) nên lõi eval vẫn phát verdict 'không áp dụng' cho nhà
    thầu độc lập. Banner phải im lặng theo, không được mâu thuẫn với verdict đó."""
    import routers.evaluation as re_

    pid = _seed_chi_lien_danh_khong_gan_co(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" not in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_van_bao_lien_danh_ap_dung_rong_khi_nha_thau_lien_danh(client, monkeypatch):
    """Đối chứng: tín hiệu _HO_SO_CHI_LIEN_DANH không được nới lỏng tới mức nuốt mất phát hiện
    thật — nhà thầu liên danh chưa nộp thì vẫn phải báo, kể cả khi ap_dung bị bỏ trống."""
    import routers.evaluation as re_

    pid = _seed_chi_lien_danh_khong_gan_co(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("liên danh"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_van_bao_lien_danh_ap_dung_rong_khi_hinh_thuc_khong_ro(client, monkeypatch):
    """Fail-safe hình thức rỗng vẫn đứng vững dù có thêm tín hiệu _HO_SO_CHI_LIEN_DANH: chưa biết
    nhà thầu là gì thì không được suy diễn — không trừ gì."""
    import routers.evaluation as re_

    pid = _seed_chi_lien_danh_khong_gan_co(client)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don(""))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "thoa_thuan_lien_danh" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_giu_loai_khong_co_noi_dung_tro_toi(client, monkeypatch):
    """hsdt_can_kiem_tra khai một loại mà KHÔNG nội dung nào của tiêu chí trỏ tới (`nds` rỗng) ->
    không đủ thông tin để xét ap_dung, nên fail-safe: vẫn coi là đang áp dụng, giữ trong ds thiếu."""
    import routers.evaluation as re_

    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-ND0", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Giấy ủy quyền", "yeu_cau_goc": "Có giấy",
         "hsdt_can_kiem_tra": ["giay_uy_quyen"],   # khai nhưng KHÔNG noi_dung nào trỏ tới
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có đơn", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},
    ]})
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "giay_uy_quyen" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_giu_loai_khi_mot_trong_hai_tieu_chi_ap_dung_moi_hinh_thuc(client, monkeypatch):
    """Một loại hồ sơ (không thuộc _HO_SO_CHI_LIEN_DANH) được 2 tiêu chí tham chiếu: tiêu chí A
    chỉ áp dụng liên danh, tiêu chí B áp dụng mọi hình thức -> với nhà thầu độc lập, KHÔNG phải
    MỌI nội dung đều lệch (còn tiêu chí B) nên loại này vẫn coi là áp dụng, chưa nộp vẫn phải báo."""
    import routers.evaluation as re_

    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-2TC", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Ủy quyền ký thỏa thuận liên danh", "yeu_cau_goc": "Có A",
         "hsdt_can_kiem_tra": ["giay_uy_quyen"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có A", "hsdt_kiem_tra": "giay_uy_quyen", "yeu_cau": "có",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False, "ap_dung": "lien_danh"}]},
        {"nhom": "hop_le", "ten": "Ủy quyền ký hồ sơ (mọi hình thức)", "yeu_cau_goc": "Có B",
         "hsdt_can_kiem_tra": ["giay_uy_quyen"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có B", "hsdt_kiem_tra": "giay_uy_quyen", "yeu_cau": "có",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},   # KHÔNG gán ap_dung -> áp dụng mọi hình thức
    ]})
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "giay_uy_quyen" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_im_lang_khi_nha_thau_chua_cham(client):
    """Chưa chấm lần nào -> KHÔNG có căn cứ gì về hồ sơ đã nhận, banner phải IM LẶNG.

    Có endpoint chấm riêng từng nhà thầu nên ca "nhà thầu chưa tới lượt chấm" là bình thường.
    Khi đó `ho_so_nhan_duoc` chưa tồn tại, không phải vì nhà thầu không nộp mà vì chưa ai chấm —
    liệt kê MỌI loại hồ sơ yêu cầu thành "chưa nộp" là khẳng định SAI SỰ THẬT về nhà thầu, ngay
    trên màn hình ra quyết định.
    """
    pid = _seed_hai_loai(client)
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert v["criteria"] == []            # đúng là chưa chấm
    assert v["ho_so_chua_nop"] == []      # nên không được nói gì về hồ sơ chưa nộp


def test_ho_so_chua_nop_van_bao_khi_da_cham_ma_khong_nhan_duoc_gi(client, monkeypatch):
    """Đối chứng cho ca trên: ĐÃ chấm mà `ho_so_nhan_duoc` rỗng -> nhà thầu thật sự không nộp gì.

    Hai ca này khác nhau về CĂN CỨ, không chỉ về dữ liệu rỗng: ở đây đã có kết quả chấm nên việc
    báo thiếu là một phát hiện thật, phải giữ.
    """
    import routers.evaluation as re_

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[])
        for c in criteria:
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="đạt",
                                            verdicts=[], yeu_cau_goc=""))
        return r

    pid = _seed_hai_loai(client)
    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    loais = [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]
    assert "don_du_thau" in loais and "bang_gia" in loais


def _seed_uy_quyen_lien_danh(client, ma_so: str, them_noi_dung_chung: bool) -> int:
    """Tiêu chí "Ủy quyền ký thỏa thuận liên danh": `giay_uy_quyen` chỉ vào `hsdt_can_kiem_tra`
    với vai trò TÀI LIỆU ĐỐI CHIẾU (không nội dung nào trỏ tới nó).

    `them_noi_dung_chung=True` thêm một nội dung `ap_dung=""` -> tiêu chí trộn nội dung chung với
    nội dung điều kiện liên danh, không còn "toàn lệch hình thức".
    """
    pid = client.post("/api/v1/packages",
                      json={"ma_so": ma_so, "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    nds = [{"noi_dung_kiem_tra": "Người ký thỏa thuận có ủy quyền",
            "hsdt_kiem_tra": "thoa_thuan_lien_danh", "yeu_cau": "có", "can_lam_ro": "",
            "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "", "can_review": False,
            "ap_dung": "lien_danh"}]
    if them_noi_dung_chung:
        nds.append({"noi_dung_kiem_tra": "Đơn có chữ ký hợp lệ", "hsdt_kiem_tra": "don_du_thau",
                    "yeu_cau": "có", "can_lam_ro": "", "can_tra_cuu": False,
                    "thong_tin_bo_sung": "", "nguon": "", "can_review": False, "ap_dung": ""})
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Ủy quyền ký thỏa thuận liên danh", "yeu_cau_goc": "Có ủy quyền",
         "hsdt_can_kiem_tra": ["thoa_thuan_lien_danh", "giay_uy_quyen"],
         "noi_dung_can_kiem_tra": nds},
    ]})
    return pid


def test_ho_so_chua_nop_bo_tai_lieu_doi_chieu_cua_tieu_chi_toan_lech_hinh_thuc(client, monkeypatch):
    """Tiêu chí ra verdict "không áp dụng" thì tài liệu ĐỐI CHIẾU của nó cũng không được vào banner.

    `giay_uy_quyen` không có nội dung nào trỏ tới -> `nds` rỗng -> rơi vào fail-safe "không đủ
    thông tin, cứ giữ". Nhưng MỌI nội dung của tiêu chí đều chỉ áp dụng liên danh, mà nhà thầu này
    độc lập: tiêu chí không đóng góp gì cho nhà thầu này, nên nó cũng không được kéo tài liệu đối
    chiếu vào danh sách thiếu — nếu không, banner nói "chưa nộp Giấy ủy quyền" ngay cạnh verdict
    "không áp dụng" của chính tiêu chí đó.
    """
    import routers.evaluation as re_

    pid = _seed_uy_quyen_lien_danh(client, "G-UQ1", them_noi_dung_chung=False)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    loais = [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]
    assert "giay_uy_quyen" not in loais
    assert "thoa_thuan_lien_danh" not in loais


def test_ho_so_chua_nop_giu_tai_lieu_doi_chieu_khi_tron_noi_dung_chung(client, monkeypatch):
    """Đối chứng: tiêu chí trộn một nội dung `ap_dung=""` -> vẫn áp dụng cho nhà thầu độc lập, nên
    tài liệu đối chiếu của nó KHÔNG được giấu đi (fail-safe hình thức không được nới thành lỗ hổng).
    """
    import routers.evaluation as re_

    pid = _seed_uy_quyen_lien_danh(client, "G-UQ2", them_noi_dung_chung=True)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert "giay_uy_quyen" in [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]


def test_ho_so_chua_nop_alias_tai_lieu_dung_chung_van_bi_loai(client, monkeypatch):
    """`ket_qua_mo_thau` là alias của `webform` — tài liệu do BÊN MỜI THẦU công bố.

    `hsdt_can_kiem_tra` do LLM sinh nên viết alias là chuyện thường. Không ép về mã catalog thì
    `la_dung_chung` trượt và hệ thống quy kết nhà thầu "chưa nộp kết quả mở thầu" — đúng thứ phép
    trừ tài liệu dùng chung sinh ra để chặn.
    """
    import routers.evaluation as re_

    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-ALS1", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Giá khớp kết quả mở thầu", "yeu_cau_goc": "Giá khớp",
         "hsdt_can_kiem_tra": ["ket_qua_mo_thau"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Giá khớp", "hsdt_kiem_tra": "ket_qua_mo_thau", "yeu_cau": "khớp",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]},
    ]})
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_nhan_don("độc lập"))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    loais = [x["loai_ho_so"] for x in v["ho_so_chua_nop"]]
    assert "ket_qua_mo_thau" not in loais and "webform" not in loais


def test_ho_so_chua_nop_alias_khop_voi_ho_so_da_nop(client, monkeypatch):
    """Tiêu chí khai `bao_lanh_du_thau`, nhà thầu đã nộp `bao_dam_du_thau` — cùng một loại hồ sơ.

    `ho_so_nhan_duoc.loai_ho_so` luôn là mã chuẩn (chọn từ dropdown catalog), còn vế yêu cầu là mã
    LLM sinh. Không ép cả hai về catalog trước khi so tập thì sinh ra "chưa nộp" giả, và mã thô còn
    lọt ra UI vì không tra được nhãn.
    """
    import routers.evaluation as re_

    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-ALS2", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": "Bảo lãnh dự thầu", "yeu_cau_goc": "Có bảo lãnh",
         "hsdt_can_kiem_tra": ["bao_lanh_du_thau"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": "Có bảo lãnh", "hsdt_kiem_tra": "bao_lanh_du_thau",
             "yeu_cau": "có", "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "",
             "nguon": "", "can_review": False}]},
    ]})

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("bao_dam_du_thau", ["bl.pdf"], 2)])
        for c in criteria:
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], ket_qua="đạt",
                                            verdicts=[], yeu_cau_goc=""))
        return r

    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    v = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]
    assert v["ho_so_chua_nop"] == []


def _da_cham(client, pid: int) -> set[int]:
    """Nhà thầu đã có kết quả chấm (dùng để khẳng định 'bỏ qua bước đã xong')."""
    vendors = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"]
    return {v["vendor_id"] for v in vendors if v["criteria"]}


def test_evaluate_bo_qua_da_cham_khong_cham_lai(client, monkeypatch):
    """Cờ bo_qua_da_cham: thêm nhà thầu mới rồi bấm lại thì chỉ chấm người mới, không chấm lại cả lô."""
    import routers.evaluation as re_

    pid = _seed(client)
    goi: list[str] = []

    def dem(base):
        async def fake(criteria, hsdt_files, **kw):
            goi.append(kw.get("vendor_ctx").ten if kw.get("vendor_ctx") else "?")
            return await base(criteria, hsdt_files, **kw)
        return fake

    monkeypatch.setattr(re_, "evaluate_vendor", dem(_fake_eval("đạt")))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200
    assert len(goi) == 1                                    # gói seed có 1 nhà thầu

    client.post(f"/api/v1/packages/{pid}/vendors", json={"ten": "B"})
    goi.clear()
    r = client.post(f"/api/v1/packages/{pid}/evaluate?bo_qua_da_cham=true")
    assert r.status_code == 200
    assert goi == ["B"]                                     # CHỈ chấm nhà thầu mới
    assert len(_da_cham(client, pid)) == 2                  # kết quả cũ vẫn còn nguyên


def test_chay_tu_dong_boc_tieu_chi_roi_cham_het(client, monkeypatch):
    """Gói chưa có tiêu chí -> bước bóc chạy thật, rồi chấm mọi nhà thầu."""
    import routers.evaluation as re_
    import routers.rubric as ru

    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-AUTO", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    import fitz
    d = fitz.open(); d.new_page().insert_text((72, 72), "Tiêu chuẩn đánh giá")
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("hsmt.pdf", d.tobytes(), "application/pdf")},
                data={"loai": "HSMT"})

    async def fake_decomp(pdf_path, workdir, scan_sources=None):
        return {"groups": [{"criteria": [{
            "nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "Có đơn",
            "hsdt_can_kiem_tra": ["don_du_thau"],
            "noi_dung_can_kiem_tra": [{
                "noi_dung_kiem_tra": "Có đơn", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
                "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
                "can_review": False}]}]}]}

    monkeypatch.setattr(ru, "build_decomposition", fake_decomp)
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval("đạt"))
    r = client.post(f"/api/v1/packages/{pid}/chay-tu-dong")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [b["trang_thai"] for b in data["buoc"]] == ["xong", "xong"]
    assert len(data["vendors"]) == 1 and data["loi"] == []
    assert len(_da_cham(client, pid)) == 1


def test_chay_tu_dong_bo_qua_buoc_da_xong(client, monkeypatch):
    """Đã có tiêu chí + nhà thầu đã chấm -> bước bóc 'bo_qua', nhà thầu cũ không bị chấm lại."""
    import routers.evaluation as re_
    import routers.rubric as ru

    pid = _seed(client)
    goi: list[str] = []

    def dem(base):
        async def fake(criteria, hsdt_files, **kw):
            goi.append(kw.get("vendor_ctx").ten if kw.get("vendor_ctx") else "?")
            return await base(criteria, hsdt_files, **kw)
        return fake

    monkeypatch.setattr(re_, "evaluate_vendor", dem(_fake_eval("đạt")))
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200

    async def no_decomp(*a, **kw):
        raise AssertionError("KHÔNG được bóc lại tiêu chí khi gói đã có")

    monkeypatch.setattr(ru, "build_decomposition", no_decomp)
    goi.clear()
    r = client.post(f"/api/v1/packages/{pid}/chay-tu-dong")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["buoc"][0]["trang_thai"] == "bo_qua"
    assert goi == []                                        # không nhà thầu nào bị chấm lại
    assert data["vendors"] == []


def test_chay_tu_dong_boc_tieu_chi_loi_thi_dung_va_bao(client, monkeypatch):
    """Bóc tiêu chí hỏng -> không chấm mù, báo rõ bước nào hỏng."""
    import routers.rubric as ru

    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-ERR", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    import fitz
    d = fitz.open(); d.new_page().insert_text((72, 72), "Tiêu chuẩn đánh giá")
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("hsmt.pdf", d.tobytes(), "application/pdf")},
                data={"loai": "HSMT"})

    async def hong(*a, **kw):
        raise RuntimeError("proxy tắt")

    monkeypatch.setattr(ru, "build_decomposition", hong)
    r = client.post(f"/api/v1/packages/{pid}/chay-tu-dong")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["buoc"][0]["trang_thai"] == "loi"
    assert "proxy tắt" in data["buoc"][0]["chi_tiet"]
    assert len(data["buoc"]) == 1                           # dừng, không chấm mù
    assert data["vendors"] == []


def test_chay_tu_dong_mot_nha_thau_loi_van_cham_tiep(client, monkeypatch):
    """Một nhà thầu hỏng KHÔNG được cuốn theo kết quả của người khác."""
    import routers.evaluation as re_

    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/vendors", json={"ten": "B"})
    base = _fake_eval("đạt")

    async def fake(criteria, hsdt_files, **kw):
        if kw.get("vendor_ctx") and kw["vendor_ctx"].ten == "A":
            raise RuntimeError("vision timeout")
        return await base(criteria, hsdt_files, **kw)

    monkeypatch.setattr(re_, "evaluate_vendor", fake)
    r = client.post(f"/api/v1/packages/{pid}/chay-tu-dong")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [v["ten"] for v in data["vendors"]] == ["B"]
    assert [l["ten"] for l in data["loi"]] == ["A"]
    assert "vision timeout" in data["loi"][0]["error"]
    assert data["buoc"][-1]["trang_thai"] == "xong"
