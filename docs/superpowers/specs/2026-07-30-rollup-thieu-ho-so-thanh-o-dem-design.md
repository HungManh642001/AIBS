# Thiết kế: "thiếu hồ sơ" thành kết luận cấp tiêu chí, tổng bằng số tiêu chí

> Spec thiết kế. Ngày: 2026-07-30. Nhánh: `feat/ai-accuracy-remediation`.
>
> **Spec này ĐẢO một quyết định trước đó.** `2026-07-30-upload-cho-va-thong-ke-thieu-ho-so-design.md`
> (mục B2) chốt `n_thieu_ho_so` là **lát cắt độc lập** nằm ngoài đẳng thức bốn ô. Sau khi dùng thử,
> chủ dự án thấy cách trình bày đó gây khó đọc và yêu cầu ngược lại: tổng phải bằng số tiêu chí.
> Spec này thay thế mục B2 đó.

## Context

Trên trang Kết quả đánh giá gói thầu 54, chủ dự án thấy: **10 tiêu chí**, nhưng bảng hiện
"4 đạt, 5 không đạt, 1 cần làm rõ, 1 thiếu hồ sơ" — cộng lại **11**. Không đọc được.

Nguyên nhân: hôm nay `"thiếu hồ sơ"` không phải kết luận cấp tiêu chí. Cả hai bản roll-up
(`experiment/evaluate/evaluate.py::evaluate_criterion` và `routers/evaluation.py::_rollup`) đều cuộn
`KET_QUA_THIEU` vào `KET_QUA_SOI`, nên tiêu chí chỉ có thể mang một trong bốn kết quả
(đạt / không đạt / cần làm rõ / không áp dụng). Ô `n_thieu_ho_so` được thêm sau đó đếm theo một
chiều KHÁC — số tiêu chí *có chứa* ít nhất một verdict `"thiếu hồ sơ"` — nên nó chồng lấn với
`n_can_lam_ro` và `n_khong_dat`, và cộng vào là ra thừa.

Yêu cầu mới: **`"thiếu hồ sơ"` trở thành một kết luận cấp tiêu chí thật**, năm ô loại trừ nhau và
cộng đúng bằng `n_tieu_chi`.

## Thay đổi 1 — Roll-up theo thứ tự ưu tiên

Trên tập verdict đã bỏ `"không áp dụng"` (N/A vẫn trung tính như cũ), xét theo thứ tự **cao → thấp**:

```
không đạt   →  có bất kỳ verdict "không đạt"            -> tiêu chí "không đạt"
cần làm rõ  →  có "cần làm rõ" HOẶC "lỗi"               -> tiêu chí "cần làm rõ"
thiếu hồ sơ →  có "thiếu hồ sơ"                          -> tiêu chí "thiếu hồ sơ"
đạt         →  còn lại (tất cả đều "đạt")               -> tiêu chí "đạt"
```

Ba hệ quả cần nêu rõ vì chúng là chỗ dễ hiểu nhầm:

- Tiêu chí **chỉ toàn** `"thiếu hồ sơ"` → kết luận **"thiếu hồ sơ"** (trước đây ra "cần làm rõ").
- Tiêu chí có **cả** `"cần làm rõ"` **và** `"thiếu hồ sơ"` → **"cần làm rõ"** (ưu tiên cao hơn).
- Tiêu chí có `{"đạt", "thiếu hồ sơ"}` → **"thiếu hồ sơ"**. Một nội dung đạt không xoá được việc
  một nội dung khác không có hồ sơ để chấm.

Giữ nguyên hai nhánh biên hiện có: mọi verdict đều N/A → `"không áp dụng"`; danh sách verdict rỗng
→ `"cần làm rõ"`.

**Phải sửa ở CẢ HAI bản roll-up.** `evaluate.py::evaluate_criterion` (lõi, dùng cho CLI và cho lượt
chấm) và `routers/evaluation.py::_rollup` (dùng khi chuyên gia ghi đè verdict rồi tính lại) là hai
cài đặt trùng nhau của cùng một luật. Sửa một bên là hai đường phân kỳ — chấm ra một kiểu, ghi đè
xong ra kiểu khác.

### Quyết định: `"lỗi"` gộp vào `"cần làm rõ"`

`KET_QUA_LOI` (proxy/AI hỏng) **không** thành ô đếm thứ sáu. Lý do: chủ dự án yêu cầu "chỉ tổng hợp
ở mức tiêu chí, không cần thêm thông tin", và về nghĩa thì "lỗi" cũng là *chưa kết luận được* —
cùng nhóm hành động với "cần làm rõ". Đây cũng là hành vi hiện tại, nên không có thay đổi ngầm nào.

## Thay đổi 2 — `n_thieu_ho_so` đổi bản chất

Từ **lát cắt** (đếm tiêu chí *có chứa* verdict thiếu hồ sơ) thành **ô đếm thật**:
`ket_qua == KET_QUA_THIEU`. Năm ô nay loại trừ nhau và:

```
n_tieu_chi = n_dat + n_khong_dat + n_can_lam_ro + n_thieu_ho_so + n_khong_ap_dung
```

Ví dụ của chủ dự án: 4 + 5 + 1 + 1 + 0 = 10 ✓

**Ba bản đếm phải sửa cùng lúc**, nếu không chúng nói ba con số khác nhau:

| Bản đếm | Dùng cho |
|---|---|
| `routers/evaluation.py::_summary` | API `results` → giao diện |
| `experiment/evaluate/schema.py::EvalResult.summary` | đường experiment (CLI, chạy tay) |
| `frontend/src/api/types.ts::EvalSummary` | hợp đồng kiểu phía frontend |

Bản thứ ba chỉ là kiểu + comment, nhưng comment hiện đang mô tả nghĩa "lát cắt" nên phải viết lại —
để nguyên là tài liệu nói dối.

## Thay đổi 3 — Giao diện

- **Khôi phục nhánh `pillClass` cho `"thiếu hồ sơ"`.** Nhánh này từng bị xoá như code chết, với lý
  do đúng ở thời điểm đó: `ResultPill` chỉ dùng ở cấp tiêu chí, mà tiêu chí không bao giờ mang kết
  quả này. Nay thì có, nên nhánh phải quay lại — kèm class CSS riêng để phân biệt với `"cần làm rõ"`.
- **Bỏ Tag/cột "lát cắt" riêng**, đưa "Thiếu hồ sơ" thành một ô ngang hàng với bốn ô còn lại ở
  `SummaryChips` và `SummaryTable`.
- **Cột "Trạng thái" trong bảng so sánh nhà thầu phải thêm một bậc.** Hiện nó xét
  `n_khong_dat > 0` → `n_can_lam_ro > 0` → `"Đạt toàn bộ"`. Không sửa thì một nhà thầu mà mọi tiêu
  chí đều `"thiếu hồ sơ"` sẽ hiện **"Đạt toàn bộ"** — sai nghiêm trọng trên màn hình ra quyết định.
  Chèn bậc "Thiếu hồ sơ" đúng theo thứ tự ưu tiên của Thay đổi 1.

## Không cần sửa — nhưng phải khoá bằng test

`routers/reports.py` tính `passed_legality` bằng `all(e.ket_qua in {KET_QUA_DAT,
KET_QUA_KHONG_AP_DUNG})`. Tiêu chí `"thiếu hồ sơ"` vốn đã không nằm trong tập hợp lệ, nên báo cáo
Word/Excel tự động đúng sau thay đổi này. Thêm test khoá lại thay vì đổi code — nếu ai đó sau này
nới tập hợp lệ, test phải đỏ.

## Kiểm thử

**Roll-up** (viết cho cả hai bản, vì chúng là hai cài đặt của cùng một luật):
- chỉ `{thiếu hồ sơ}` → `"thiếu hồ sơ"`
- `{cần làm rõ, thiếu hồ sơ}` → `"cần làm rõ"`
- `{không đạt, thiếu hồ sơ}` → `"không đạt"`
- `{đạt, thiếu hồ sơ}` → `"thiếu hồ sơ"`
- `{lỗi, thiếu hồ sơ}` → `"cần làm rõ"` (khoá quyết định gộp "lỗi")
- `{đạt}` → `"đạt"`; toàn N/A → `"không áp dụng"`; rỗng → `"cần làm rõ"` (hai nhánh biên không đổi)

**Tổng hợp:** dựng một nhà thầu có đủ năm loại tiêu chí, assert
`n_tieu_chi == n_dat + n_khong_dat + n_can_lam_ro + n_thieu_ho_so + n_khong_ap_dung`. Đây là bất
biến chính của cả đợt — phải có test riêng, không chỉ kiểm từng ô.

**Báo cáo:** nhà thầu có một tiêu chí `"thiếu hồ sơ"`, còn lại `"đạt"` → `passed_legality` là
`false`.

**Hồi quy:** test hiện có nào bám vào việc "thiếu hồ sơ cuộn thành cần làm rõ" sẽ đỏ — đó là thay
đổi hành vi CÓ CHỦ Ý, sửa kỳ vọng của chúng cho khớp luật mới và ghi lý do vào docstring test.
Đây là ngoại lệ duy nhất được phép sửa test cũ trong đợt này.

## Files chạm

Backend: `backend/experiment/evaluate/evaluate.py` (roll-up lõi),
`backend/experiment/evaluate/schema.py` (`EvalResult.summary`),
`backend/routers/evaluation.py` (`_rollup` + `_summary`).

Frontend: `frontend/src/api/types.ts` (`EvalSummary`),
`frontend/src/pages/Evaluation.tsx` (`pillClass`, `SummaryChips`, `SummaryTable`),
`frontend/src/index.css` (class pill cho "thiếu hồ sơ").

Test: `backend/experiment/evaluate/tests/`, `backend/tests/test_evaluation_api.py`,
`backend/tests/test_reports_api.py`.
