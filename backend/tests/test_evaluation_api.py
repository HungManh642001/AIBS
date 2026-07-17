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
                   registry=None):
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
        if phat_hien:
            r.phat_hien_bo_sung = [Verdict(
                noi_dung_kiem_tra="Người ký khớp ĐKKD", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                thong_tin_bo_sung="", ket_qua="đạt", bang_chung="khớp", trang=[1], do_tin=0.9,
                ghi_chu="", nguon_doc=["don_du_thau", "tu_cach_phap_ly"])]
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


def test_evaluate_persists_audit_and_profile(client, monkeypatch):
    """Wiring: điều khoản nguồn + yêu cầu gốc + hình thức nhà thầu + phát hiện bổ sung được lưu & trả."""
    monkeypatch.setattr("routers.evaluation.evaluate_vendor", _fake_eval("đạt", phat_hien=True))
    pid = _seed(client)
    client.post(f"/api/v1/packages/{pid}/evaluate")
    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    v = res["vendors"][0]

    crit = v["criteria"][0]
    assert crit["yeu_cau_goc"] == "Có đơn dự thầu hợp lệ"
    assert crit["verdicts"][0]["nguon_hsmt"] == "E-CDNT 1.1"
    assert v["vendor_profile"]["hinh_thuc"] == "độc lập"
    # phát hiện bổ sung TÁCH riêng, KHÔNG lẫn vào tiêu chí thường
    assert [p["noi_dung_kiem_tra"] for p in v["phat_hien_bo_sung"]] == ["Người ký khớp ĐKKD"]
    assert all(c["nhom"] != "phat_hien_bo_sung" for c in v["criteria"])
    assert v["summary"]["n_tieu_chi"] == 1                    # phát hiện KHÔNG vào summary


def test_evaluate_builds_vendor_context_with_abbreviation(client, monkeypatch):
    """Tên viết tắt của nhà thầu -> alias trong VendorContext (khớp webform tên đầy đủ HOẶC tắt)."""
    seen = {}

    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None):
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
