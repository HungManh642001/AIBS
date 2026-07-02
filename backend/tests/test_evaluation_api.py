"""Tests evaluation router — pipeline verdict (offline, monkeypatch evaluate_vendor).

Không gọi /rubric thật (decompose cần proxy) hay vision thật; seed tiêu chí qua PUT /rubric.
"""
from experiment.evaluate.schema import CriterionEval, EvalResult, Verdict


def _fake_eval(ket_qua: str = "đạt"):
    """evaluate_vendor giả: verdict theo `ket_qua` cho mọi nội dung, roll-up + loại như thật."""
    async def fake(criteria, hsdt_files, doc="HSDT", vision_fn=None):
        r = EvalResult(doc=doc)
        for c in criteria:
            verds = [Verdict(
                noi_dung_kiem_tra=nd["noi_dung_kiem_tra"], hsdt_kiem_tra=nd["hsdt_kiem_tra"],
                yeu_cau=nd["yeu_cau"], thong_tin_bo_sung=nd["thong_tin_bo_sung"],
                ket_qua=ket_qua, bang_chung="bằng chứng", trang=[1], do_tin=0.9, ghi_chu="")
                for nd in c["noi_dung_can_kiem_tra"]]
            loai = ket_qua == "không đạt" and c["tien_quyet"]
            r.criteria.append(CriterionEval(nhom=c["nhom"], ten=c["ten"], tien_quyet=c["tien_quyet"],
                                            ket_qua=ket_qua, loai=loai, verdicts=verds))
        return r
    return fake


def _seed(client, tien_quyet: bool = True) -> int:
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-EV", "ten": "g", "vendors": ["A"]}).json()["data"]["id"]
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [{
        "nhom": "hop_le", "ten": "Đơn dự thầu", "yeu_cau_goc": "",
        "hsdt_can_kiem_tra": ["don_du_thau"], "tien_quyet": tien_quyet,
        "noi_dung_can_kiem_tra": [{
            "noi_dung_kiem_tra": "Chữ ký & con dấu", "hsdt_kiem_tra": "don_du_thau",
            "yeu_cau": "có chữ ký", "can_lam_ro": "", "can_tra_cuu": False,
            "thong_tin_bo_sung": "", "nguon": "", "can_review": False}]}]})
    return pid


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
