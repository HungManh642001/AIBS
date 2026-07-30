# Thiết kế: 3 sửa chữa phần đánh giá HSDT

> Spec thiết kế. Ngày: 2026-07-29. Nhánh: `feat/ai-accuracy-remediation`.
> Ba phần độc lập nhau — có thể triển khai / merge riêng, không phần nào chặn phần nào.

## Context

Ba vấn đề nghiệp vụ phát hiện khi chấm gói thầu 54-2026 (`backend/experiment/samples/54`,
`backend/storage/3`):

1. **Luật `bang_gia_khop_webform` bắn nhầm.** Tiêu chí có 2 nội dung kiểm tra ("phải nộp Bảng chào
   giá đúng Mẫu 05C.1" và "giá trong bảng giá phải phù hợp webform") thì **cả hai** đều bị luật
   thay thế kết luận. Kỳ vọng: chỉ nội dung thứ hai dùng luật; nội dung thứ nhất chỉ đối chiếu
   bảng giá có đúng mẫu biểu hay không.
2. **Chữ ký nhà thầu liên danh neo sai văn bản.** Luật `chu_ky_khop_dkkd` đối chiếu người ký đơn
   dự thầu với đại diện pháp luật trong ĐKKD cho **mọi** nhà thầu. Với liên danh, văn bản quyết
   định ai được ký là **thỏa thuận liên danh (TTLD)**, không phải ĐKKD.
3. **Ingest chạy lại vô ích khi có cảnh báo.** Trang scan bị `kiem_tra_bang` nghi bóc thiếu sẽ
   được gọi vision lần hai, và cả file bị loại khỏi cache. Đo trên `logs/evaluate.log`: 21 lần
   thử lại, 20 lần vẫn nghi ngờ → tỷ lệ cứu được ~5%.

---

## Phần 1 — Luật cấp tiêu chí khớp đúng nội dung

### Nguyên nhân gốc

`backend/experiment/evaluate/evaluate.py:116-130` (`_skill_cho_nd`) khớp luật với nội dung theo
**thành viên** của `ho_so_can`:

```python
key = _norm(nd.get("hsdt_kiem_tra", ""))
for s in skills:
    if key and key in {_norm(h) for h in s.ho_so_can}:
        return s
```

Luật khớp qua 2 tầng: `registry.matching(crit)` ở cấp tiêu chí (đúng — tiêu chí khai đủ
`{bang_gia, webform}`), rồi `_skill_cho_nd` ở cấp nội dung. Dữ liệu thật gói 54
(`backend/storage/3/rubric_work/decomposition.json`, tiêu chí `Bang_gia_va_phu_hop_webform`):

| # | `noi_dung_kiem_tra` | `hsdt_kiem_tra` | Khớp luật? |
|---|---|---|---|
| 1 | Bảng chào giá chi tiết theo Mẫu số 05C.1 | `bang_gia` | ✗ (đang khớp nhầm) |
| 2 | Giá dự thầu phù hợp giữa Webform và Bảng giá | `bang_gia` | ✓ |

Cả hai nội dung đều có `hsdt_kiem_tra = "bang_gia"` ∈ `{bang_gia, webform}` → cả hai bị luật
thay thế. Nội dung 1 đã có `thong_tin_bo_sung` rất tốt (14 cột của Mẫu 05C.1, resolve từ Chương V)
nhưng bị vứt bỏ vì luật không đọc field đó — nó chỉ so hai con số giá.

Giả định ngầm ghi ở `evaluate.py:123-124` — *"tiêu chí khai đủ bộ hồ sơ của luật chính là tiêu chí
về phép đối chiếu đó"* — **đúng ở cấp tiêu chí, sai ở cấp nội dung**.

Gói 62 không dính vì decompose tách thành 2 tiêu chí riêng, tiêu chí "Co bang chao gia 05C.1"
không khai `webform` nên trượt ngay ở `registry.matching`. Gói 54 gộp 1 tiêu chí / 2 nội dung —
**đây là hành vi ĐÚNG của decompose** (`yeu_cau_goc` là một câu liền mạch), nên không chữa bằng
cách ép decompose tách tiêu chí.

### Thay đổi

**a) Schema decompose.** Thêm field vào `NoiDungKiemTra` (`backend/experiment/decompose/schema.py`):

```python
hsdt_doi_chieu: list[str] = []   # tài liệu ĐỐI CHIẾU riêng cho nội dung này
```

`SYS_STRUCT` (`backend/experiment/decompose/prompts.py`) dạy thêm: *`hsdt_doi_chieu` = tài liệu
(chọn trong `hsdt_can_kiem_tra` của tiêu chí) phải xem THÊM để kết luận riêng nội dung này. Nội
dung chỉ cần hồ sơ chính → để rỗng.* Kỳ vọng trên gói 54: nội dung 1 → `[]`, nội dung 2 →
`["webform"]`.

**b) Khớp luật — chỉ can thiệp khi NHẬP NHẰNG.** Giữ nguyên phép khớp theo thành viên hiện tại
(`_skill_cho_nd`) làm bước lọc ứng viên, rồi thêm bước **phân xử** ở cấp tiêu chí: với mỗi luật,
nếu chỉ **một** nội dung là ứng viên → giữ nguyên hành vi hôm nay, không đụng gì. Nếu **từ hai**
nội dung trở lên cùng là ứng viên (đúng ca gói 54) mới chạy phân xử ba tầng:

```
tầng 1 — metadata:  giữ nội dung nào khai ĐỦ bộ hồ sơ của luật
                    (set(ho_so_can) ⊆ {nd.hsdt_kiem_tra} ∪ set(nd.hsdt_doi_chieu))
tầng 2 — từ khóa:   không nội dung nào khai (dữ liệu decompose cũ) → giữ nội dung có NHẮC tài liệu
                    đối chiếu của luật trong `noi_dung_kiem_tra` + `yeu_cau`, tra alias qua
                    services/artifact_catalog.py (webform: "webform", "kết quả mở thầu",
                    "biên bản mở thầu", "danh sách nhà thầu tham dự"...)
tầng 3 — fail-safe: cả hai tầng đều không chọn được ai → GIỮ NGUYÊN toàn bộ ứng viên (hành vi
                    hôm nay) + log.warning, thà thừa còn hơn âm thầm mất luật
```

Chọn cách này thay vì đổi thẳng phép khớp sang "bao trùm" vì bán kính rủi ro nhỏ hơn hẳn: nội dung
duy nhất của một tiêu chí không bao giờ đổi hành vi, kể cả khi STRUCT chọn `hsdt_kiem_tra` là tài
liệu đối chiếu (ca đã có test `test_skill_serves_need_routed_to_reference_doc` khoá lại — nếu rơi
xuống eval chung thì prompt nuốt trọn webform của mọi nhà thầu).

Kết quả trên gói 54: cả 2 nội dung đều là ứng viên → tầng 1 chưa có dữ liệu → tầng 2 giữ nội dung 2
("Giá dự thầu phù hợp giữa Webform và Bảng giá"), loại nội dung 1 ("Bảng chào giá chi tiết theo Mẫu
số 05C.1"). **Đúng ngay cả trước khi re-run decompose.** Sau khi re-run, tầng 1 quyết luôn.

### Hệ quả

Nội dung 1 rơi xuống `eval_noi_dung` bình thường, đối chiếu `thong_tin_bo_sung` (14 cột Mẫu 05C.1)
— đúng nghiệp vụ "chỉ đối chiếu bảng giá có đúng mẫu hay không". Không cần viết luật mới.

### Ngoài phạm vi (cố ý)

`extra_types` truyền vào `eval_noi_dung` (`evaluate.py:223`) vẫn lấy `hsdt_can_kiem_tra` **cấp tiêu
chí** như hiện tại, **không** đổi sang `hsdt_doi_chieu`. Hệ quả: nội dung 1 vẫn được kèm text
webform (đã lọc theo nhà thầu qua `loc_dung_chung`) làm nhiễu nhẹ trong prompt. Chấp nhận: nếu
STRUCT khai thiếu `hsdt_doi_chieu` thì eval chung sẽ **mất hẳn** tài liệu đối chiếu — bán kính rủi
ro lớn hơn nhiều so với chút nhiễu.

### Files chạm

`experiment/decompose/schema.py`, `experiment/decompose/prompts.py`,
`experiment/evaluate/evaluate.py`, có thể thêm helper tra alias trong `services/artifact_catalog.py`.

---

## Phần 2 — Nhánh liên danh cho luật chữ ký đơn dự thầu

### Hiện trạng

`backend/experiment/evaluate/rules/chu_ky_khop_dkkd.py` là standing check (`pham_vi="goi"`), chạy
1 lần/nhà thầu, **không biết hình thức dự thầu** — `thoa_thuan_lien_danh` không xuất hiện ở đâu
trong luật. `dispatch_standing` (`pipeline.py:71`) cũng không truyền `profile`.

Ca thật gói 54 (`logs/evaluate.log` 2026-07-29 11:08:38) — HSDT không có ĐKKD nên đi nhánh GUQ:

- Đơn dự thầu: *"ĐẠI DIỆN HỢP PHÁP CỦA NHÀ THẦU LIÊN DANH — CÔNG TY CỔ PHẦN TẬP ĐOÀN OSB"*, người
  ký Trần Vũ Thường.
- Giấy ủy quyền: Nguyễn Hồng Sơn (TGĐ **Công ty TNHH Công nghệ cao OSB**) ủy quyền Trần Vũ Thường.
- TTLD: OSB Tập đoàn = thành viên đứng đầu; Trần Vũ Thường = Phó GĐ, đại diện OSB Công nghệ cao.
- Verdict hiện tại: **không đạt** — *"bên ủy quyền không phải pháp nhân đứng tên ký đơn"*.

Luật so giấy ủy quyền với pháp nhân ghi trên đơn, hoàn toàn bỏ qua TTLD — trong khi TTLD mới là
văn bản quyết định ai được ký thay mặt liên danh.

### Hai hình thức ký hợp lệ của nhà thầu liên danh

Đơn dự thầu của liên danh hợp lệ theo **một trong hai** cách:

- **(A) Thành viên đứng đầu ký thay mặt liên danh** — một khối chữ ký, đứng tên thành viên đứng đầu.
- **(B) TẤT CẢ thành viên cùng ký** — mỗi thành viên một khối chữ ký.

Ký thiếu (nhiều hơn 1 khối nhưng không đủ thành viên), hoặc một khối duy nhất đứng tên thành viên
**không phải** đứng đầu → không hợp lệ.

### Thay đổi

Rẽ nhánh **tất định** ở đầu `handler`, ngay sau khi kiểm `don_du_thau`, dựa trên
`by_type["thoa_thuan_lien_danh"]` — cùng tín hiệu `vendor_profile.py:38` dùng để kết luận liên
danh, nên không lệch với hình thức in trên báo cáo. Ca "khai độc lập nhưng HSDT có TTLD" vẫn đi
nhánh liên danh: hồ sơ nói vậy.

```
KHÔNG có TTLD → giữ NGUYÊN luồng ĐKKD hiện tại (không sửa gì)

CÓ TTLD → bước 1 (1 call LLM): đọc TTLD + đơn dự thầu, chỉ BÓC dữ liệu
          TTLD → thanh_vien[] {ten_phap_nhan, nguoi_dai_dien, la_dung_dau}
          Đơn  → chu_ky[]     {phap_nhan, nguoi_ky}
        ↓ code quyết định hình thức ký (không để LLM tự kết luận)
        ├ tập pháp nhân ký ⊇ tập thành viên TTLD  → hình thức (B) "tất cả cùng ký"
        │   xét TỪNG chữ ký: người ký = nguoi_dai_dien của CHÍNH thành viên đó theo TTLD?
        ├ đúng 1 pháp nhân ký và là thành viên đứng đầu → hình thức (A) "đứng đầu ký thay"
        │   xét chữ ký đó: người ký = nguoi_dai_dien của thành viên đứng đầu?
        ├ đúng 1 pháp nhân ký nhưng KHÔNG phải đứng đầu → 'không đạt' (dừng, 1 call)
        ├ ký một phần (>1 khối, thiếu thành viên)       → 'không đạt' (dừng, 1 call),
        │                                                 nêu tên thành viên còn thiếu chữ ký
        ├ có khối chữ ký đứng tên pháp nhân KHÔNG có trong TTLD → 'không đạt' (dừng, 1 call),
        │                                                 nêu tên pháp nhân lạ
        └ không bóc được thành viên TTLD nào, hoặc không bóc được chữ ký nào trên đơn
                                                       → 'cần làm rõ' (no-fab, dừng, 1 call)
        ↓ mọi chữ ký khớp → 'đạt' (KHÔNG đụng ĐKKD)
        ↓ có chữ ký lệch người
        ├ HSDT không có giay_uy_quyen → 'không đạt' (không gọi LLM lần 2)
        └ bước 2 (1 call LLM, gộp MỌI chữ ký lệch): thẩm định giấy ủy quyền, mỗi chữ ký lệch
          phải thỏa cả ba:
            (1) bên ủy quyền = CHÍNH thành viên liên danh mà chữ ký đó đứng tên
                (hình thức A: thành viên đứng đầu);
            (2) người được ủy quyền = người đã ký đơn;
            (3) phạm vi ủy quyền bao gồm việc ký đơn dự thầu.
          Vi phạm bất kỳ điều nào ở bất kỳ chữ ký nào → 'không đạt'.
```

Tối đa **2 call LLM** cho cả nhánh, bằng nhánh ĐKKD hiện tại.

**Dùng lại nguyên vẹn:** `khop_phap_nhan()` (guard một chiều chống báo động giả do hoa/thường/dấu)
cho mọi phép so pháp nhân — chỉ đổi vế so sánh từ ĐKKD/đơn sang TTLD/đơn. `_QUY_TAC_PHAP_NHAN`
giữ nguyên, nhúng vào cả hai system prompt mới.

**Nhãn & audit:** nhánh liên danh dùng `_TEN` riêng — *"Người ký đơn dự thầu đúng đại diện liên
danh (thỏa thuận liên danh)"* — và `nguon_doc = [don_du_thau, thoa_thuan_lien_danh]` (+
`giay_uy_quyen` khi có xét bước 2). Không trộn nhãn ĐKKD vào verdict liên danh: báo cáo không được
nói là đã đối chiếu ĐKKD trong khi không hề đọc ĐKKD.

**`SKILL.ho_so_can`** giữ `[don_du_thau, dang_ky_kinh_doanh]`. Là standing check nên `ho_so_can`
chỉ dùng làm nhãn/`nguon_doc` mặc định, không tham gia khớp tiêu chí — `thoa_thuan_lien_danh` và
`giay_uy_quyen` là hồ sơ tùy chọn đọc từ `by_type`, đúng khuôn `_GUQ` hiện tại.

### Kết quả kỳ vọng trên ca OSB gói 54

Đơn có 1 khối chữ ký, đứng tên OSB Tập đoàn = thành viên đứng đầu → hình thức (A). Người ký Trần
Vũ Thường ≠ đại diện của OSB Tập đoàn theo TTLD (Nguyễn Hồng Sơn) → xét GUQ → bên ủy quyền là OSB
Công nghệ cao ≠ OSB Tập đoàn → **không đạt**, `ghi_chu` nêu rõ *"giấy ủy quyền do thành viên KHÁC
của liên danh cấp, không phải thành viên đứng đầu đứng tên ký đơn"*.

Verdict vẫn là "không đạt" như hiện nay, nhưng **lý do đúng** — hiện tại luật nói sai rằng bên ủy
quyền "không phải pháp nhân ký đơn", một kết luận suy ra từ văn bản không liên quan (ĐKKD).

### Files chạm

`experiment/evaluate/rules/chu_ky_khop_dkkd.py` (thêm nhánh + 2 system prompt + 2 schema `_Base`),
tests tương ứng trong `experiment/evaluate/tests/test_rules_chu_ky.py`.

---

## Phần 3 — Ingest: cảnh báo chỉ log, không chạy lại

### Hiện trạng

`backend/experiment/evaluate/ingest.py:74-106` (`_doc_trang_vision`) thử lại **đúng một lần** khi
`finish_reason == "length"` (chạm trần token) **hoặc** `kiem_tra_bang()` báo nghi ngờ, rồi giữ bản
ít vấn đề hơn. Ngoài ra `ingest.py:132` đặt `du_de_cache = False` khi vẫn còn cảnh báo.

Đo trên toàn bộ `backend/experiment/logs/evaluate.log`:

| Sự kiện | Số lần |
|---|---|
| Nghi bóc thiếu → thử lại | 21 |
| Sau khi thử lại **vẫn** nghi bóc thiếu | 20 |

Tỷ lệ cứu được ≈ **1/21 (~5%)**, đổi lại 21 call vision + độ trễ.

Khóa cache là **theo FILE** (`ingest_cache_key(data, dpi)`), nên một trang có cảnh báo làm cả file
không được cache → mỗi lần chấm lại là OCR lại toàn bộ file đó. Log 13:32:03 minh hoạ chính xác:
`Webform_62.2026.pdf tr1 vẫn nghi bóc thiếu` → file webform OCR lại, trong khi 4 file khác đều
"dùng cache (0 call vision)".

### Thay đổi

1. **`_doc_trang_vision` — chỉ thử lại khi chạm trần token.** `finish_reason == "length"` vẫn thử
   lại với `max_tokens` gấp đôi (đây là call thực sự khác, có khả năng lấy lại dòng bị cắt).
   `kiem_tra_bang` báo nghi ngờ mà không chạm trần → `log.warning` rồi trả về ngay, không call lần
   hai. Nhánh giữ-bản-tốt-hơn sau retry chạm trần giữ nguyên.
2. **`_doc_file` — bỏ `du_de_cache = False` ở nhánh `van_de`.** Chỉ **lỗi vision**
   (`out.status != "ok"`) mới chặn cache. Bất biến #1 của cache (trang lỗi vision không bao giờ
   được cache) giữ nguyên.
3. **Bắt buộc kèm theo: thêm `canh_bao` vào payload `cache.put`** (`ingest.py:183`). Payload hiện
   chỉ có `trang/text/co_chu_ky/co_dau/nguon_trich`. Trước đây trang có cảnh báo không bao giờ vào
   cache nên thiếu sót này không lộ; giờ cho phép cache mà không lưu `canh_bao` thì **cảnh báo biến
   mất im lặng ở lần chấm thứ hai**: `pages_text` hết in `[CẢNH BÁO đọc trang này: ...]`, luật hết
   hạ kết luận xuống "cần làm rõ", `EvalResult.canh_bao_doc` rỗng. Đọc lại dùng
   `d.get("canh_bao", "")` nên entry cache cũ vẫn tương thích (chúng vốn chỉ chứa trang sạch).

Cảnh báo vẫn đi trọn đường như cũ: `PageRecord.canh_bao` → `pages_text` → prompt luật/eval →
`EvalResult.canh_bao_doc` (`pipeline.py:74`) → báo cáo. Thay đổi này chỉ thôi **hành động sửa
chữa**, không mất tín hiệu nào.

4. Cập nhật docstring `ingest.py` (mô tả retry ở `_doc_trang_vision` và bất biến cache ở đầu
   module) cho khớp hành vi mới.

### Files chạm

`experiment/evaluate/ingest.py`, tests trong `experiment/evaluate/tests/test_ingest.py` và
`test_ingest_cache.py`.

---

## Kiểm thử

**Phần 1**
- Tầng 1: 2 nội dung ứng viên, một khai `hsdt_doi_chieu=["webform"]` → chỉ nội dung đó khớp luật.
- Tầng 2: 2 nội dung ứng viên, không nội dung nào khai → nội dung có chữ "webform" khớp, nội dung
  nói về "Mẫu số 05C.1" không khớp (ca hồi quy gói 54).
- Tầng 3: 2 nội dung ứng viên, không nội dung nào khai và không nội dung nào nhắc tài liệu đối
  chiếu → cả hai vẫn dùng luật (fail-safe), có WARNING trong log.
- Hồi quy: tiêu chí 1 nội dung duy nhất vẫn khớp luật y như trước, kể cả khi `hsdt_kiem_tra` là
  tài liệu đối chiếu (`webform`) — toàn bộ test luật hiện có phải xanh không sửa.
- E2E `evaluate_criterion` trên đúng dữ liệu tiêu chí `Bang_gia_va_phu_hop_webform` của gói 54: 2
  verdict, chỉ 1 đi qua luật.

**Phần 2**
- Không có TTLD → đi nhánh ĐKKD cũ, mọi test hiện có phải xanh không sửa.
- Có TTLD, hình thức (A), người ký khớp đại diện đứng đầu → 'đạt', **0 call ĐKKD**, `nguon_doc`
  không chứa `dang_ky_kinh_doanh`.
- Có TTLD, hình thức (B), mọi thành viên ký đúng đại diện của mình → 'đạt'.
- Có TTLD, hình thức (B) nhưng thiếu chữ ký 1 thành viên → 'không đạt', bằng chứng nêu tên thành
  viên thiếu, 1 call.
- Một pháp nhân ký nhưng không phải đứng đầu → 'không đạt', 1 call.
- Không bóc được thành viên TTLD nào (hoặc không bóc được chữ ký nào) → 'cần làm rõ', 1 call,
  KHÔNG suy đoán.
- Người ký lệch + không có GUQ → 'không đạt', 1 call.
- Ca OSB gói 54 (fixture từ log): người ký lệch + GUQ từ thành viên KHÔNG đứng đầu → 'không đạt'
  với `ghi_chu` nêu đúng lý do.
- Tên viết tắt (TTLD ghi "Công ty cổ phần Tập đoàn OSB", đơn ghi "Cty CP Tập đoàn OSB"): đường xử
  lý đúng là **LLM gán `thanh_vien_ttld`** — `_tra_thanh_vien` thử khoá đó TRƯỚC khi so tên thô,
  nên khớp được. Test khoá đường này bằng cách đặt `thanh_vien_ttld` và `phap_nhan` trỏ về hai
  thành viên KHÁC nhau, khẳng định `thanh_vien_ttld` thắng.

  **Đánh đổi đã chốt (2026-07-30, chủ dự án quyết sau review cuối nhánh):** khi LLM bỏ trống
  `thanh_vien_ttld`, tên viết tắt và pháp nhân LẠ tới hàm phán quyết dưới dạng dữ liệu **giống hệt
  nhau** — không có trường nào phân biệt. Hệ thống chọn giữ **'không đạt'** (ưu tiên không bỏ sót
  phát hiện thật: pháp nhân ngoài liên danh ký đơn), chấp nhận rủi ro đánh trượt oan tên viết tắt
  trong ca LLM bóc thiếu. Phương án thay thế đã cân nhắc và loại: thêm cờ `thuoc_ttld` để LLM
  khẳng định tường minh (giữ được cả hai, nhưng tốn thêm một vòng prompt + schema + test).
  Ca "không đọc được tên pháp nhân" thì vẫn là 'cần làm rõ' — khác hẳn, đừng gộp.

**Phần 3**
- Trang có `van_de` từ `kiem_tra_bang`, không chạm trần → **đúng 1** call vision, `canh_bao` được
  điền, log có WARNING.
- Trang chạm trần token → vẫn 2 call, giữ bản tốt hơn (test hiện có).
- Cache: trang có `canh_bao` được ghi cache; đọc lại từ cache thì `PageRecord.canh_bao` khôi phục
  đúng chuỗi.
- Cache: trang **lỗi vision** vẫn không được ghi cache (bất biến #1).
- Entry cache cũ (không có key `canh_bao`) đọc ra `canh_bao=""`, không nổ.

## Thứ tự triển khai đề xuất

Phần 3 → Phần 1 → Phần 2. Phần 3 rẻ nhất, độc lập hoàn toàn, và làm mọi lần chạy thử sau đó nhanh
hơn (bớt OCR lại). Phần 1 đụng decompose nên cần re-run decompose để nghiệm thu đầy đủ. Phần 2
nặng nhất về prompt và test fixture.

## Nợ kỹ thuật còn lại (đã triển khai xong, cố ý hoãn — ghi lại để lần sau khỏi phát hiện lại)

Review cuối nhánh (2026-07-30) nêu và chủ dự án đồng ý hoãn:

1. **`khop_phap_nhan` không gộp khoảng trắng GIỮA** (`rules/chu_ky_khop_dkkd.py`). Docstring nói
   guard chống lệch "khoảng trắng" nhưng `_norm(...).strip()` chỉ cắt hai đầu. Cùng lớp lỗi với
   phép so tên người đã sửa, nhưng bán kính là **mọi** phép so pháp nhân ở cả nhánh ĐKKD lẫn liên
   danh — quá rộng cho một đợt fix đang khép lại. Ưu tiên cao nhất trong danh sách này.
2. **Phân xử luật chạy TRƯỚC gate "không áp dụng"** (`evaluate/evaluate.py`). Nội dung đã bị
   `_gate_khong_ap_dung` loại vẫn tính là ứng viên và có thể THẮNG phân xử, khiến nội dung còn
   sống mất luật và rơi xuống eval chung. Xác suất thấp; lọc `nds` đã-gated ra khỏi
   `_phan_luat_cho_nd` là rẻ.
3. **`_bo_ho_so_nd` dùng `_norm` chứ không `artifact_catalog.resolve_code`**. LLM khai
   `hsdt_doi_chieu=["Kết quả mở thầu"]` (alias hợp lệ) sẽ trượt tầng 1 — tầng 2 cứu được nên không
   gấp. Lưu ý khi sửa: `resolve_code` có khớp substring hai chiều, dễ over-match.
4. **Verdict fallback ở `rules/registry.py` mang nhãn ĐKKD cho nhà thầu liên danh.** Khi handler
   ném exception, verdict dùng `skill.ten` và `nguon_doc=[don_du_thau, dang_ky_kinh_doanh]` kể cả
   khi nhánh liên danh chưa hề đọc ĐKKD. Cùng loại vi phạm audit với lỗi đã sửa, nhưng chỉ xảy ra
   ở đường lỗi.
5. **`rules/chu_ky_khop_dkkd.py` nay ~700 dòng**, 4 system prompt + 2 luồng nghiệp vụ độc lập
   (ĐKKD và liên danh). Tách file khi đụng lại lần sau; tách ngay lúc này chỉ làm nhiễu diff.
6. Chưa có test: ca "nhiều luật cùng nhắm một nội dung" trong `_phan_luat_cho_nd` (thứ tự registry
   quyết, giống semantics cũ nên không phải hồi quy); `_xet_uy_quyen_lien_danh` ở mức async với
   ≥2 khối chữ ký lệch cùng lúc (mức hàm thuần đã phủ).
