# "Thiếu hồ sơ" thành ô đếm cấp tiêu chí Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho `"thiếu hồ sơ"` trở thành một kết luận cấp tiêu chí thật, để bảng tổng hợp có năm ô loại trừ nhau và cộng đúng bằng số tiêu chí.

**Architecture:** Hai task. Task 1 làm trọn phần backend như MỘT đơn vị — đổi thứ tự ưu tiên roll-up ở cả hai bản cài đặt trùng nhau, đổi `n_thieu_ho_so` từ "lát cắt" thành ô đếm thật ở cả hai bản đếm, và cập nhật những test mã hoá ngữ nghĩa cũ. Tách roll-up khỏi ô đếm sẽ để lại cây test đỏ giữa hai commit, nên chúng đi cùng nhau. Task 2 làm giao diện.

**Tech Stack:** Backend Python 3.11 + FastAPI + SQLAlchemy, test bằng pytest (`asyncio_mode = auto`). Frontend React + TypeScript + Ant Design.

**Spec:** `docs/superpowers/specs/2026-07-30-rollup-thieu-ho-so-thanh-o-dem-design.md`

## Global Constraints

- Thư mục làm việc backend: `backend/`. Chạy test: `cd backend && python -m pytest <path> -q`.
- **Baseline (đo tại commit gốc của plan):** `cd backend && python -m pytest -q` → **191 passed, 0 failed**. `cd backend && python -m pytest experiment/evaluate/tests experiment/decompose/tests -q` → **391 passed, 28 failed, 3 errors** (28 failed + 3 errors có sẵn từ trước, KHÔNG liên quan, không sửa, không được tăng).
- **`cd frontend && npx tsc --noEmit`** đang sạch (exit 0). **TUYỆT ĐỐI KHÔNG `npm install` / `npm run dev` trong `frontend/`** — `node_modules` là bản cài từ Windows, cài lại hỏng môi trường dev của người dùng.
- Quy ước code (CLAUDE.md): Python snake_case, **type hints bắt buộc**, PEP 8. **Tiếng Việt trong UI/comment/docstring**, tiếng Anh trong tên code.
- **Máy KHÔNG kết luận loại/không loại nhà thầu** — chỉ trình số liệu để chuyên gia tự quyết.
- Frontend dùng CSS custom properties có sẵn, không hardcode màu mới.
- **Ngoại lệ DUY NHẤT được sửa test cũ:** bốn test được gọi tên ở Task 1 Step 6, vì chúng mã hoá đúng ngữ nghĩa vừa bị đảo. Test nào **khác** chuyển đỏ nghĩa là bản sửa sai — **dừng và báo BLOCKED**, đừng sửa test.
- Commit tiếng Việt, dạng `feat(<scope>): <mô tả>`.

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/experiment/evaluate/evaluate.py` | roll-up lõi trong `evaluate_criterion` | 1 |
| `backend/routers/evaluation.py` | `_rollup` + `_summary` | 1 |
| `backend/experiment/evaluate/schema.py` | `EvalResult.summary` | 1 |
| `backend/experiment/evaluate/tests/test_evaluate.py` | test roll-up lõi | 1 |
| `backend/tests/test_evaluation_api.py` | test `_rollup`/`_summary`, sửa 4 test cũ | 1 |
| `backend/tests/test_reports_api.py` | khoá `passed_legality` | 1 |
| `frontend/src/api/types.ts` | `EvalSummary` | 2 |
| `frontend/src/pages/Evaluation.tsx` | `pillClass`, `SummaryChips`, `SummaryTable` | 2 |
| `frontend/src/index.css` | class pill "thiếu hồ sơ" | 2 |

---

### Task 1: Backend — roll-up ưu tiên + năm ô đếm loại trừ nhau

**Files:**
- Modify: `backend/experiment/evaluate/evaluate.py` (khối roll-up cuối `evaluate_criterion`), `backend/routers/evaluation.py` (`_rollup`, `_summary`), `backend/experiment/evaluate/schema.py` (`EvalResult.summary`)
- Test: `backend/experiment/evaluate/tests/test_evaluate.py`, `backend/tests/test_evaluation_api.py`, `backend/tests/test_reports_api.py`

**Interfaces:**
- Produces: tiêu chí nay có thể mang `ket_qua == KET_QUA_THIEU`; `n_thieu_ho_so` là **ô đếm thật** (`ket_qua == KET_QUA_THIEU`), một trong năm ô loại trừ nhau. Task 2 hiển thị cả hai.

**Bối cảnh (đọc trước khi sửa):**

Chủ dự án thấy trang Kết quả gói 54 hiện "4 đạt, 5 không đạt, 1 cần làm rõ, 1 thiếu hồ sơ" trên **10 tiêu chí** — cộng ra 11. Nguyên nhân: `"thiếu hồ sơ"` không phải kết luận cấp tiêu chí (bị cuộn vào `"cần làm rõ"`), còn `n_thieu_ho_so` đếm theo một chiều KHÁC (số tiêu chí *có chứa* verdict thiếu hồ sơ) nên chồng lấn với các ô kia.

Có **hai** bản roll-up là hai cài đặt của **cùng một luật**: `evaluate_criterion` chạy lúc chấm, `_rollup` chạy khi chuyên gia ghi đè verdict rồi tính lại. Sửa một bên là hai đường phân kỳ — chấm ra một kiểu, ghi đè xong ra kiểu khác. Tương tự có **hai** bản đếm backend (`_summary` cho API, `EvalResult.summary` cho đường experiment/CLI).

Thứ tự ưu tiên mới, trên tập verdict đã bỏ `"không áp dụng"`:

```
không đạt            -> "không đạt"
cần làm rõ HOẶC lỗi  -> "cần làm rõ"     ('lỗi' gộp vào đây, KHÔNG thành ô thứ sáu)
thiếu hồ sơ          -> "thiếu hồ sơ"    (MỚI — trước đây bị cuộn vào "cần làm rõ")
còn lại (toàn "đạt") -> "đạt"
```

Hai nhánh biên giữ nguyên: mọi verdict đều N/A → `"không áp dụng"`; danh sách verdict rỗng → `"cần làm rõ"`.

- [ ] **Step 1: Bổ sung import còn thiếu cho test lõi**

`backend/experiment/evaluate/tests/test_evaluate.py` hiện import
`PageRecord, KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_THIEU` — **thiếu `KET_QUA_SOI`** mà
test ở Step 2 cần. Thêm nó vào đúng khối import đó.

- [ ] **Step 2: Viết test thất bại cho roll-up lõi**

Thêm vào cuối `backend/experiment/evaluate/tests/test_evaluate.py`:

```python
async def _rollup_loi(kqs: list[str]) -> str:
    """Chạy evaluate_criterion với verdict DỰNG SẴN -> lấy ket_qua tiêu chí.

    Dùng một luật giả trả đúng verdict mong muốn cho từng nội dung, để test đúng phép roll-up
    chứ không phải đường chấm.
    """
    from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill
    from experiment.evaluate.schema import Verdict

    async def handler(by_type, ctx, crit, vision_fn, *, nd=None, pkg=None):
        i = int((nd or {})["noi_dung_kiem_tra"][2:])       # "nd3" -> 3
        return Verdict(noi_dung_kiem_tra=f"nd{i}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                       thong_tin_bo_sung="", ket_qua=kqs[i], bang_chung="", trang=[],
                       do_tin=0.0, ghi_chu="", nguon_doc=[])

    reg = RuleRegistry()
    reg.register(RuleSkill(id="gia", ten="gia", ho_so_can=["don_du_thau"], can_vendor=False,
                           handler=handler))
    crit = {"nhom": "hop_le", "ten": "TC", "hsdt_can_kiem_tra": ["don_du_thau"],
            "noi_dung_can_kiem_tra": [
                {"noi_dung_kiem_tra": f"nd{i}", "hsdt_kiem_tra": "don_du_thau",
                 "yeu_cau": "có", "thong_tin_bo_sung": ""} for i in range(len(kqs))]}
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "x")], ScriptedVision({}),
                                  registry=reg)
    return ce.ket_qua


async def test_rollup_uu_tien_thieu_ho_so():
    """Ưu tiên: không đạt > cần làm rõ > thiếu hồ sơ > đạt.

    'thiếu hồ sơ' nay là KẾT LUẬN cấp tiêu chí, không còn bị cuộn vào 'cần làm rõ' — nhờ vậy năm
    ô tổng hợp loại trừ nhau và cộng đúng bằng số tiêu chí.
    """
    assert await _rollup_loi(["thiếu hồ sơ"]) == KET_QUA_THIEU
    assert await _rollup_loi(["thiếu hồ sơ", "đạt"]) == KET_QUA_THIEU
    assert await _rollup_loi(["cần làm rõ", "thiếu hồ sơ"]) == KET_QUA_SOI
    assert await _rollup_loi(["không đạt", "thiếu hồ sơ"]) == KET_QUA_KHONG
    assert await _rollup_loi(["lỗi", "thiếu hồ sơ"]) == KET_QUA_SOI   # 'lỗi' gộp vào 'cần làm rõ'
    assert await _rollup_loi(["đạt", "đạt"]) == KET_QUA_DAT
```

- [ ] **Step 3: Viết test thất bại cho `_rollup` của router**

Thêm vào cuối `backend/tests/test_evaluation_api.py`:

```python
def test_rollup_router_uu_tien_thieu_ho_so():
    """`_rollup` (chạy khi chuyên gia ghi đè verdict) phải khớp TỪNG LY với roll-up lõi —
    lệch nhau là chấm ra một kiểu, ghi đè xong ra kiểu khác."""
    from routers.evaluation import _rollup

    assert _rollup({"thiếu hồ sơ"}) == "thiếu hồ sơ"
    assert _rollup({"thiếu hồ sơ", "đạt"}) == "thiếu hồ sơ"
    assert _rollup({"cần làm rõ", "thiếu hồ sơ"}) == "cần làm rõ"
    assert _rollup({"không đạt", "thiếu hồ sơ"}) == "không đạt"
    assert _rollup({"lỗi", "thiếu hồ sơ"}) == "cần làm rõ"
    assert _rollup({"đạt"}) == "đạt"
    # Ba nhánh biên KHÔNG đổi.
    assert _rollup({"không áp dụng"}) == "không áp dụng"
    assert _rollup(set()) == "cần làm rõ"
    assert _rollup({"thiếu hồ sơ", "không áp dụng"}) == "thiếu hồ sơ"   # N/A vẫn trung tính
```

- [ ] **Step 4: Viết test thất bại cho đẳng thức năm ô**

Thêm tiếp vào cuối `backend/tests/test_evaluation_api.py`:

```python
def _fake_eval_du_nam_loai():
    """evaluate_vendor giả: 5 tiêu chí, mỗi tiêu chí một loại kết quả."""
    async def fake(criteria, hsdt_files, *, doc="HSDT", vision_fn=None, vendor_ctx=None,
                   registry=None, pkg_ctx=None, cache=None, call_cache=None):
        r = EvalResult(doc=doc, vendor=vendor_ctx,
                       vendor_profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo"),
                       ho_so_nhan_duoc=[HoSoNhanDuoc("don_du_thau", ["don.pdf"], 1)])
        for i, kq in enumerate(["đạt", "không đạt", "cần làm rõ", "thiếu hồ sơ", "không áp dụng"]):
            v = Verdict(noi_dung_kiem_tra=f"nd{i}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                        thong_tin_bo_sung="", ket_qua=kq, bang_chung="", trang=[], do_tin=0.0,
                        ghi_chu="", nguon_doc=[])
            r.criteria.append(CriterionEval(nhom="hop_le", ten=f"TC{i}", ket_qua=kq,
                                            verdicts=[v], yeu_cau_goc=""))
        return r
    return fake


def test_tong_nam_o_bang_dung_so_tieu_chi(client, monkeypatch):
    """Bất biến CHÍNH của cả đợt: năm ô loại trừ nhau, cộng đúng bằng n_tieu_chi.

    Trước đây bảng hiện '4 đạt, 5 không đạt, 1 cần làm rõ, 1 thiếu hồ sơ' trên 10 tiêu chí —
    cộng ra 11 vì 'thiếu hồ sơ' là lát cắt chồng lấn chứ không phải ô đếm.
    """
    import routers.evaluation as re_

    pid = _seed(client)
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": [
        {"nhom": "hop_le", "ten": f"TC{i}", "yeu_cau_goc": "x",
         "hsdt_can_kiem_tra": ["don_du_thau"],
         "noi_dung_can_kiem_tra": [{
             "noi_dung_kiem_tra": f"nd{i}", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
             "can_lam_ro": "", "can_tra_cuu": False, "thong_tin_bo_sung": "", "nguon": "",
             "can_review": False}]} for i in range(5)]})
    monkeypatch.setattr(re_, "evaluate_vendor", _fake_eval_du_nam_loai())
    assert client.post(f"/api/v1/packages/{pid}/evaluate").status_code == 200

    s = client.get(f"/api/v1/packages/{pid}/results").json()["data"]["vendors"][0]["summary"]
    assert (s["n_dat"], s["n_khong_dat"], s["n_can_lam_ro"],
            s["n_thieu_ho_so"], s["n_khong_ap_dung"]) == (1, 1, 1, 1, 1)
    assert s["n_tieu_chi"] == (s["n_dat"] + s["n_khong_dat"] + s["n_can_lam_ro"]
                               + s["n_thieu_ho_so"] + s["n_khong_ap_dung"])
```

- [ ] **Step 5: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_evaluate.py::test_rollup_uu_tien_thieu_ho_so tests/test_evaluation_api.py::test_rollup_router_uu_tien_thieu_ho_so tests/test_evaluation_api.py::test_tong_nam_o_bang_dung_so_tieu_chi -q`
Expected: FAIL cả ba — hai test roll-up trả `"cần làm rõ"` thay vì `"thiếu hồ sơ"`; test đẳng thức báo `n_thieu_ho_so` ra 0 và tổng năm ô ≠ `n_tieu_chi`.

- [ ] **Step 6: Sửa roll-up lõi**

Trong `backend/experiment/evaluate/evaluate.py`, thay khối roll-up ở cuối `evaluate_criterion`:

```python
    xet = [v for v in verdicts if v.ket_qua != KET_QUA_KHONG_AP_DUNG]   # N/A trung tính
    kq = {v.ket_qua for v in xet}
    # Ưu tiên CAO -> THẤP: không đạt > cần làm rõ > thiếu hồ sơ > đạt. Năm kết quả cấp tiêu chí
    # loại trừ nhau, nhờ vậy bảng tổng hợp cộng đúng bằng số tiêu chí — trước đây 'thiếu hồ sơ'
    # bị cuộn vào 'cần làm rõ' rồi phải đếm bằng một lát cắt chồng lấn, làm tổng ra thừa.
    # 'lỗi' (proxy/AI hỏng) gộp vào 'cần làm rõ': cùng nghĩa "chưa kết luận được".
    if KET_QUA_KHONG in kq:
        ket_qua = KET_QUA_KHONG
    elif kq & {KET_QUA_SOI, KET_QUA_LOI}:
        ket_qua = KET_QUA_SOI
    elif KET_QUA_THIEU in kq:
        ket_qua = KET_QUA_THIEU
    elif kq == {KET_QUA_DAT}:
        ket_qua = KET_QUA_DAT
    elif verdicts and not xet:          # có verdict nhưng TẤT CẢ đều N/A
        ket_qua = KET_QUA_KHONG_AP_DUNG
    else:                               # verdicts rỗng -> giữ hành vi cũ
        ket_qua = KET_QUA_SOI
```

- [ ] **Step 7: Sửa `_rollup` của router**

Trong `backend/routers/evaluation.py`, thay `_rollup`:

```python
def _rollup(kqs: set[str]) -> str:
    """Roll-up ket_qua tiêu chí — PHẢI khớp từng ly `experiment.evaluate.evaluate_criterion`.

    Ưu tiên CAO -> THẤP: không đạt > cần làm rõ > thiếu hồ sơ > đạt; N/A trung tính; 'lỗi' gộp
    vào 'cần làm rõ'. Đây là hai cài đặt của CÙNG một luật (bản kia chạy lúc chấm, bản này chạy
    khi chuyên gia ghi đè verdict) — sửa lệch nhau là chấm ra một kiểu, ghi đè xong ra kiểu khác.
    """
    xet = kqs - {KET_QUA_KHONG_AP_DUNG}
    if KET_QUA_KHONG in xet:
        return KET_QUA_KHONG
    if xet & {KET_QUA_SOI, KET_QUA_LOI}:
        return KET_QUA_SOI
    if KET_QUA_THIEU in xet:
        return KET_QUA_THIEU
    if xet == {KET_QUA_DAT}:
        return KET_QUA_DAT
    if kqs and not xet:                 # có verdict nhưng TẤT CẢ N/A
        return KET_QUA_KHONG_AP_DUNG
    return KET_QUA_SOI
```

- [ ] **Step 8: Sửa `_summary` của router**

Trong `backend/routers/evaluation.py`, thay thân `_summary` (giữ nguyên chữ ký):

```python
def _summary(evals: list[models.HsdtCriterionEval]) -> dict[str, int]:
    """Đếm MỌI tiêu chí — kiểm tra thường trực của hệ thống có trọng số ngang tiêu chí HSMT.

    NĂM ô loại trừ nhau và cộng đúng bằng `n_tieu_chi`:
        n_tieu_chi = n_dat + n_khong_dat + n_can_lam_ro + n_thieu_ho_so + n_khong_ap_dung
    Được vậy vì `_rollup` nay cho `"thiếu hồ sơ"` là một KẾT LUẬN cấp tiêu chí (ưu tiên dưới
    'cần làm rõ'), thay vì cuộn nó vào 'cần làm rõ' rồi đếm bằng một lát cắt chồng lấn — cách cũ
    làm bảng tổng hợp cộng ra thừa so với số tiêu chí và không đọc được.
    """
    tc = list(evals)

    def cnt(k: str) -> int:
        return sum(1 for e in tc if e.ket_qua == k)
    return {
        "n_tieu_chi": len(tc), "n_dat": cnt(KET_QUA_DAT), "n_khong_dat": cnt(KET_QUA_KHONG),
        "n_can_lam_ro": cnt(KET_QUA_SOI), "n_thieu_ho_so": cnt(KET_QUA_THIEU),
        "n_khong_ap_dung": cnt(KET_QUA_KHONG_AP_DUNG),
    }
```

- [ ] **Step 9: Sửa `EvalResult.summary`**

Trong `backend/experiment/evaluate/schema.py`, thêm ô đếm và viết lại comment cho khớp (`KET_QUA_THIEU` được ĐỊNH NGHĨA ngay trong file này nên dùng thẳng, không cần import):

```python
    def summary(self) -> dict[str, int]:
        # Bản đếm của ĐƯỜNG EXPERIMENT (chạy tay/CLI). Bản đếm mà API trả cho UI nằm ở
        # `routers/evaluation.py::_summary` (đếm từ DB) — hai bên phải cho CÙNG bộ khoá, sửa một
        # bên thì xem lại bên kia. Năm ô loại trừ nhau, cộng đúng bằng n_tieu_chi.
        def cnt(k: str) -> int:
            return sum(1 for c in self.criteria if c.ket_qua == k)
        return {
            "n_tieu_chi": len(self.criteria),
            "n_dat": cnt(KET_QUA_DAT),
            "n_khong_dat": cnt(KET_QUA_KHONG),
            "n_can_lam_ro": cnt(KET_QUA_SOI),
            "n_thieu_ho_so": cnt(KET_QUA_THIEU),
            "n_khong_ap_dung": cnt(KET_QUA_KHONG_AP_DUNG),
        }
```

- [ ] **Step 10: Sửa bốn test cũ mã hoá ngữ nghĩa đã bị đảo**

Đây là **ngoại lệ duy nhất** được sửa test cũ. Trong `backend/tests/test_evaluation_api.py`:

1. **`_fake_eval_thieu`** — tiêu chí đầu có verdicts `["thiếu hồ sơ", "đạt"]` nhưng fake đặt
   `ket_qua="cần làm rõ"`. Theo luật mới roll-up ra `"thiếu hồ sơ"` → đổi cho nhất quán. Viết lại
   docstring: fake phải khớp luật roll-up mới.
2. **`test_summary_dem_rieng_thieu_ho_so`** — bỏ assert `n_thieu_ho_so <= n_tieu_chi` và đẳng thức
   **bốn** ô; thay bằng đẳng thức **năm** ô. Docstring nêu: `"thiếu hồ sơ"` nay là ô đếm thật.
3. **`test_mot_tieu_chi_hai_verdict_thieu_van_dem_mot`** — fake đặt `ket_qua="cần làm rõ"` cho tiêu
   chí có hai verdict `"thiếu hồ sơ"` → đổi thành `"thiếu hồ sơ"`. Ý nghĩa test giữ nguyên: đếm
   theo TIÊU CHÍ, hai verdict thiếu vẫn là một.
4. **`test_thieu_ho_so_trong_tieu_chi_da_khong_dat_van_dem`** — ca `{"không đạt", "thiếu hồ sơ"}`
   nay roll-up ra `"không đạt"` nên **không** được đếm vào `n_thieu_ho_so`. Đổi kỳ vọng thành
   `n_thieu_ho_so == 0` và `n_khong_dat == 1`; **đổi tên test** cho khớp ý mới (vd
   `test_tieu_chi_khong_dat_khong_tinh_la_thieu_ho_so`). Docstring ghi rõ đây là thay đổi hành vi
   CÓ CHỦ Ý: ưu tiên "không đạt" cao hơn "thiếu hồ sơ".

- [ ] **Step 11: Thêm test khoá báo cáo**

Thêm vào cuối `backend/tests/test_reports_api.py`:

```python
def test_tieu_chi_thieu_ho_so_khong_duoc_tinh_la_hop_le():
    """'thiếu hồ sơ' nay là kết luận cấp tiêu chí — báo cáo KHÔNG được coi nó là hợp lệ.

    `_KET_QUA_HOP_LE` chỉ gồm {đạt, không áp dụng} nên hành vi vốn đã đúng; test này khoá lại để
    ai nới tập hợp lệ sau này phải thấy đỏ.
    """
    from routers.reports import _KET_QUA_HOP_LE

    assert "thiếu hồ sơ" not in _KET_QUA_HOP_LE
    assert "cần làm rõ" not in _KET_QUA_HOP_LE
    assert "lỗi" not in _KET_QUA_HOP_LE
```

- [ ] **Step 12: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest tests/ -q` rồi `cd backend && python -m pytest experiment/evaluate/tests experiment/decompose/tests -q`
Expected: suite `tests/` **0 failed**; bộ experiment đúng **28 failed, 3 errors** baseline, không tăng. Test nào ngoài bốn test ở Step 10 mà đỏ → **dừng, báo BLOCKED**.

- [ ] **Step 13: Commit**

```bash
git add backend/experiment/evaluate/evaluate.py backend/experiment/evaluate/schema.py \
        backend/routers/evaluation.py backend/experiment/evaluate/tests/test_evaluate.py \
        backend/tests/test_evaluation_api.py backend/tests/test_reports_api.py
git commit -m "feat(eval): 'thiếu hồ sơ' thành kết luận cấp tiêu chí, năm ô tổng bằng số tiêu chí"
```

---

### Task 2: Giao diện — ô ngang hàng, pill và bậc trạng thái

**Files:**
- Modify: `frontend/src/api/types.ts` (`EvalSummary`), `frontend/src/pages/Evaluation.tsx` (`pillClass`, `SummaryChips`, `SummaryTable`), `frontend/src/index.css`

**Interfaces:**
- Consumes (từ Task 1): `n_thieu_ho_so` là ô đếm thật, một trong năm ô loại trừ nhau; tiêu chí có thể mang `ket_qua === "thiếu hồ sơ"`.

**Bối cảnh (đọc trước khi sửa):** ba chỗ trong `Evaluation.tsx` đang mã hoá ngữ nghĩa "lát cắt" vừa bị đảo, và một chỗ sẽ **sai nghiêm trọng** nếu không sửa: cột "Trạng thái" xét `n_khong_dat > 0` → `n_can_lam_ro > 0` → `"Đạt toàn bộ"`, nên một nhà thầu mà mọi tiêu chí đều `"thiếu hồ sơ"` sẽ hiện **"Đạt toàn bộ"** trên đúng màn hình ra quyết định.

`pillClass` cũng cần khôi phục nhánh `"thiếu hồ sơ"` — nhánh đó từng bị xoá như code chết với lý do đúng ở thời điểm ấy (tiêu chí không bao giờ mang kết quả này), nay thì có. Comment phía trên nó hiện cũng nói ngược, phải sửa.

- [ ] **Step 1: Sửa kiểu `EvalSummary`**

Trong `frontend/src/api/types.ts`, thay field `n_thieu_ho_so` cùng comment của nó bằng:

```ts
  /** Số tiêu chí kết luận "thiếu hồ sơ". Một trong NĂM ô loại trừ nhau:
   *  n_tieu_chi = n_dat + n_khong_dat + n_can_lam_ro + n_thieu_ho_so + n_khong_ap_dung. */
  n_thieu_ho_so?: number;
```

Giữ dấu `?` — payload từ backend cũ không có khoá này.

- [ ] **Step 2: Khôi phục nhánh pill + class CSS**

Trong `frontend/src/pages/Evaluation.tsx`, sửa `pillClass` **và comment ngay phía trên nó** (comment hiện nói "không có nhánh thiếu hồ sơ"):

```tsx
// Pill cấp TIÊU CHÍ. Tiêu chí nay CÓ thể kết luận "thiếu hồ sơ" (xem _rollup ở backend), nên
// nhánh đó phải có màu riêng — dùng chung màu cam với "cần làm rõ" thì chuyên gia không phân
// biệt được "nhà thầu không nộp" với "AI chưa đủ căn cứ", hai việc cần hai hành động khác nhau.
function pillClass(kq: string): string {
  if (kq === "đạt") return "dat";
  if (kq === "không đạt") return "khong-dat";
  if (kq === "lỗi") return "loi";
  if (kq === "không áp dụng") return "khong-ap-dung";   // trung tính (xám), khác cam "cần làm rõ"
  if (kq === "thiếu hồ sơ") return "thieu-ho-so";
  return "can-lam-ro";
}
```

Trong `frontend/src/index.css`, thêm lại class ngay sau `.verdict-result-pill.loi`. Nếu chỗ đó đang có comment nói class này đã bị xoá thì thay luôn comment:

```css
.verdict-result-pill.thieu-ho-so  { background: var(--teal-tint);  color: var(--teal); }
```

- [ ] **Step 3: Sửa `SummaryChips` — ô ngang hàng thay vì lát cắt**

Thay khối Tag `"thiếu hồ sơ"` hiện tại (Tag `color="blue"` với chữ "tiêu chí vướng thiếu hồ sơ", kèm comment giải thích "lát cắt độc lập") bằng một Tag ngang hàng, đặt **sau** "cần làm rõ" và **trước** "không áp dụng", theo đúng thứ tự ưu tiên:

```tsx
      {(s.n_thieu_ho_so ?? 0) > 0 &&
        <Tag color="blue">{s.n_thieu_ho_so} thiếu hồ sơ</Tag>}
```

Xoá hẳn comment cũ về "lát cắt" — nó nay sai.

- [ ] **Step 4: Sửa `SummaryTable` — comment cột + bậc trạng thái mới**

Cột "Thiếu hồ sơ": giữ nguyên phần render (số, tô `var(--teal)` khi > 0), thay comment "Lát cắt ĐỘC LẬP…" bằng:

```tsx
        /* Một trong năm ô loại trừ nhau — tiêu chí kết luận "thiếu hồ sơ" (ưu tiên dưới
           "cần làm rõ", xem _rollup ở backend). */
```

Cột "Trạng thái": thêm bậc "Thiếu hồ sơ" đúng theo thứ tự ưu tiên:

```tsx
        { title: "Trạng thái", width: 150, render: (_, v) =>
          v.criteria.length === 0
            ? <Tag>Chưa chấm</Tag>
            : v.summary.n_khong_dat > 0
              ? <Tag color="volcano">Có tiêu chí không đạt</Tag>
              : v.summary.n_can_lam_ro > 0
                ? <Tag color="orange">Cần làm rõ</Tag>
                : (v.summary.n_thieu_ho_so ?? 0) > 0
                  ? <Tag color="blue">Thiếu hồ sơ</Tag>
                  : <Tag color="green">Đạt toàn bộ</Tag> },
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, không lỗi.

- [ ] **Step 6: Quét tàn dư mô hình cũ**

Run: `cd frontend && grep -rn "lát cắt\|LÁT CẮT\|vướng thiếu hồ sơ\|không phải con của" src/`
Expected: rỗng. Còn kết quả nào là comment nói ngược code — sửa nốt.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/Evaluation.tsx frontend/src/index.css
git commit -m "feat(frontend): 'thiếu hồ sơ' thành ô tổng hợp ngang hàng, thêm bậc trạng thái"
```

---

## Nghiệm thu cuối (sau khi xong cả 2 task)

- [ ] `cd backend && python -m pytest -q` — **0 failed**.
- [ ] `cd backend && python -m pytest experiment/evaluate/tests experiment/decompose/tests -q` — đúng **28 failed, 3 errors** baseline, không tăng.
- [ ] `cd frontend && npx tsc --noEmit` — sạch.
- [ ] `cd frontend && grep -rn "lát cắt\|vướng thiếu hồ sơ" src/` — rỗng.
- [ ] `git log --oneline` có đủ 2 commit, mỗi commit một task.
- [ ] Kiểm bằng tay trên app thật (cần backend + frontend chạy): mở trang Kết quả của một gói đã chấm, cộng năm ô lại phải **bằng đúng** số tiêu chí; tiêu chí kết luận "thiếu hồ sơ" hiện pill màu riêng, khác màu "cần làm rõ".
