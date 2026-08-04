# Thiết kế: tối ưu thời gian chạy pipeline — async hoá + song song hoá

> Spec thiết kế. Ngày: 2026-07-30. Nhánh: `feat/ai-accuracy-remediation`.
> Phạm vi đã chốt với chủ dự án: **Tầng 1 + Tầng 2**. Tầng 3 (giảm DPI/max_tokens) và Tầng 4
> (cấu hình vLLM) để đợt sau — chủ dự án **không can thiệp được vào server vLLM**.

## Context — đo được, không ước lượng

Số liệu lấy từ log chạy thật (`backend/experiment/logs/`, gói 62 và 54, ngày 2026-07-29):

| Giai đoạn | Thời gian | Chi tiết |
|---|---|---|
| Trích tiêu chí (decompose) | **474s** | 6 tiêu chí |
| Chấm 1 nhà thầu | **1507s** | ingest 731s (49%) + chấm 776s (51%) |
| Cả gói 3 nhà thầu | **~83 phút** | 474 + 3×1500 |

Trong 1507s: **32 call vision, trung vị 48s/call**, max 99s. Ingest 13 trang qua vision
(56s/trang); 11 trang còn lại đã đi đường đọc text nhúng nên không tốn call. Phần chấm 19 call
(~41s/call).

**48s/call là con số ĐÚNG cho decode một luồng của model 27B** — decode một luồng bị chặn bởi băng
thông bộ nhớ, không phải compute. Nút thắt không nằm ở model mà ở chỗ **toàn hệ thống chỉ chạy một
request tại một thời điểm**, trong khi vLLM trên H100 sinh ra để chạy hàng chục sequence đồng thời.

## Nguyên nhân gốc

### 1. Call LLM đồng bộ nằm trong `async def` — chẹn event loop

`services/ai_client.py::_litellm_completion` và `experiment/evaluate/vision.py::default_vision_fn`
đều gọi `litellm.completion(...)` — API **đồng bộ** — bên trong coroutine. Nó chẹn event loop, nên
`asyncio.gather` ở `experiment/decompose/workflow.py:494` và `asyncio.Semaphore(max_song_song)` ở
`:118` **không tạo ra song song nào**.

Bằng chứng đo được (không phải suy luận), `decompose.log` run 10:37:00:

```
+271s   [search] Bao_dam_du_thau -> 7 nội dung cần tra cứu (song song)
+361s        [hits] Không vi phạm trường hợp loại trừ
+381s        [hits] Chủ thể phát hành bảo lãnh
+386s        [hits] Giá trị bảo lãnh
+392s        [hits] Thời hạn hiệu lực
+398s        [hits] Đơn vị thụ hưởng
+403s        [hits] Thời điểm ký bảo lãnh
+406s        [hits] Điều kiện kèm theo
```

Bảy need khai "song song" nhưng kết quả rải đều cách nhau 5–20s. Song song thật thì chúng phải về
gần như cùng lúc.

**Đây là điểm chi phối: chừng nào chưa async hoá, mọi tối ưu song song khác đều vô hiệu.**

### 2. Mọi vòng lặp trong đường chấm đều tuần tự

Kể cả sau khi async hoá, các chỗ sau vẫn `await` từng cái một:

| Vị trí | Lặp theo |
|---|---|
| `experiment/evaluate/ingest.py:137` | từng TRANG của một file |
| `experiment/evaluate/evaluate.py:273` | từng NỘI DUNG của một tiêu chí |
| `experiment/evaluate/pipeline.py:79` | từng TIÊU CHÍ của một nhà thầu |
| `experiment/evaluate/rules/registry.py:113` | từng LUẬT thường trực |
| `experiment/evaluate/rules/lien_danh_phan_cong.py:313` | từng CHUNK bảng giá |
| `backend/routers/evaluation.py:336` | từng NHÀ THẦU |

---

## Tầng 1 — async hoá (bắt buộc, mở khoá mọi thứ)

### 1a. Bọc call đồng bộ bằng `asyncio.to_thread`

Sửa hai chỗ: `services/ai_client.py::_litellm_completion` và
`experiment/evaluate/vision.py::default_vision_fn`.

Chọn `asyncio.to_thread` thay vì đổi sang `litellm.acompletion`: diff nhỏ hơn hẳn, không đổi đường
retry/parse/validate đã được test kỹ, và không phụ thuộc hành vi async client của litellm. Ghi chú
trong code rằng `acompletion` là hướng sạch hơn khi nào cần loại bỏ thread pool.

**Ràng buộc bắt buộc kèm theo: KHÔNG được chạm DB từ thread.** `asyncio.to_thread` chỉ được bọc
đúng lời gọi HTTP tới LLM. Mọi thao tác cache (`CachedVision.get/put`, `PageCache.get/put`) phải
tiếp tục chạy trên thread của event loop — chúng dùng chung `Session` của router, mà SQLAlchemy
`Session` không an toàn đa luồng. Hiện tại code đã đúng thế (cache nằm ngoài lời gọi `await`); chỉ
cần không phá vỡ khi sửa.

`asyncio.to_thread` dùng executor mặc định với `max_workers = min(32, cpu+4)`. Trần semaphore
(1b) phải **≤ 32**, nếu không thread pool trở thành nút thắt ẩn.

### 1b. Một semaphore TOÀN CỤC cho mọi call LLM

Module mới `backend/services/llm_gate.py`. Cả `ai_client` lẫn `vision` đều đi qua nó.

Một cái chung, **không phải mỗi tầng một cái**: Tầng 2 lồng gather trong gather (tiêu chí × nội
dung), nếu mỗi tầng tự giới hạn thì tích các trần sẽ dội quá tải xuống proxy.

Trần đọc từ `Settings.ai_song_song` (env `ABES_AI_SONG_SONG`, prefix `ABES_` theo
`config.py:10`), **mặc định 4** — cố ý thấp vì không biết sức chứa của vLLM/LiteLLM phía sau và
không can thiệp được vào server. Cách dò xem mục "Vận hành".

**Semaphore phải tạo theo event loop đang chạy, không phải ở mức module.** Python 3.11:
`asyncio.Semaphore` gắn vào loop ở lần dùng đầu tiên, nên một biến module dùng lại qua nhiều loop
(pytest tạo loop mới mỗi test) sẽ nổ "bound to a different event loop". Dùng `WeakKeyDictionary`
khoá theo `asyncio.get_running_loop()`.

**Giữ semaphore ở phạm vi MỘT LƯỢT gọi, không bao cả vòng retry.** Cả `ai_call` lẫn
`default_vision_fn` đều có `for attempt in range(2)` với `timeout=300` mỗi lượt. Ôm semaphore qua
cả hai lượt nghĩa là một call hỏng có thể giữ chỗ tới 600s và bỏ đói các call khác. Nhả giữa hai
lượt cũng cho call đang chờ chen vào trước khi ta thử lại.

Decompose **không cần sửa gì**: nó đã đi qua `ai_call`, nên `gather` và `Semaphore` sẵn có ở
`workflow.py` tự có tác dụng ngay khi Tầng 1 xong.

---

## Tầng 2 — song song hoá trong phạm vi MỘT nhà thầu

Năm chỗ, dùng `asyncio.gather` (giữ **nguyên thứ tự** kết quả nên danh sách verdict và roll-up
không đổi):

**a. Trang trong ingest** (`ingest.py::_doc_file`) — độ lợi lớn nhất (731s/1507s).
Cần tách làm **hai pha** vì đối tượng PyMuPDF **không an toàn đa luồng**:
1. Pha đồng bộ trên loop: duyệt từng trang, quyết định đọc-text hay vision, và **render sẵn PNG**
   cho các trang cần vision (`page_to_png`).
2. Pha bất đồng bộ: `gather` các lời gọi `_doc_trang_vision` trên các PNG đã render.

Tuyệt đối không gọi `fitz` bên trong coroutine chạy song song hay trong thread.

**b. Nội dung trong tiêu chí** (`evaluate.py::evaluate_criterion`). Gate `_gate_khong_ap_dung` và
`_phan_luat_cho_nd` vẫn chạy đồng bộ trước; chỉ gather phần `await` (chạy luật hoặc `eval_noi_dung`).

**c. Tiêu chí trong nhà thầu** (`pipeline.py::evaluate_hsdt`). `by_type` chỉ đọc nên chia sẻ được.

**d. Luật thường trực** (`registry.py::dispatch_standing`).

**e. Chunk bảng giá** (`lien_danh_phan_cong.py`). Lưu ý đánh đổi: code hiện tại **dừng ở chunk lỗi
đầu tiên**; gather thì mọi chunk đều được gọi rồi mới xét lỗi. Verdict không đổi (vẫn báo lỗi kèm
chỉ số chunk lỗi ĐẦU TIÊN theo thứ tự), nhưng đường lỗi tốn thêm call. Chấp nhận: đường lỗi hiếm,
đổi lại đường thường nhanh hơn nhiều.

## Ngoài phạm vi — kèm lý do

- **Song song cấp NHÀ THẦU** (`routers/evaluation.py:336`). `_eval_and_save_vendor` xoá + ghi +
  `commit()` trên **Session dùng chung của router**, và `DbCallCache.put` cũng `commit()` chính
  Session đó (`services/ai_cache.py`). Chạy song song cần Session riêng mỗi nhà thầu — là một
  thiết kế khác, không phải một dòng `gather`. Để đợt sau.
- **Tầng 3** (hạ DPI 200→130–150, hạ `max_tokens`, mở rộng đường đọc text nhúng): cần đo lại độ
  chính xác trên hồ sơ thật trước khi chốt, vì hạ DPI có rủi ro đọc sót chữ nhỏ.
- **Tầng 4** (`--enable-prefix-caching`, `--max-num-seqs`, chunked prefill, FP8): không can thiệp
  được vào server. Ghi lại để khi nào có quyền thì làm — `--enable-prefix-caching` là món rẻ nhất
  và lợi nhất vì prompt hệ thống lặp y hệt ở mọi call (`SYS_INGEST + ingest_prompt()` giống hệt
  từng trang).

## Tái lập kết quả — nói thẳng một đánh đổi

Chủ dự án yêu cầu kết quả phải tái lập được. Cần phân biệt hai thứ:

- **Chấm lại cùng hồ sơ + tiêu chí vẫn ra y hệt** — vẫn đúng, do lớp cache kết quả chấm
  (`cached_vision.py` + `services/ai_cache.py`) khoá theo hash toàn bộ đầu vào. Không đổi.
- **Lần chạy ĐẦU sau khi sửa có thể ra khác hôm nay.** `cached_vision.py:4-6` đã ghi rõ: vLLM gộp
  batch động nên model **vốn không tái lập tuyệt đối** kể cả `temperature=0` + seed cố định. Tăng
  số request đồng thời làm thành phần batch khác đi.

Đây là hệ quả không tránh được của việc tăng song song, không phải lỗi triển khai. Nếu cần chốt
cứng kết quả hiện tại, phải chấm một lượt trước khi đổi để nạp đầy cache, rồi mới triển khai.

## Kiểm thử

Ba loại, tất cả chạy offline (không cần proxy):

1. **Bất biến kết quả:** cùng một fixture, chạy qua đường song song và đường tuần tự phải cho
   verdict **trùng khít cả nội dung lẫn THỨ TỰ**. Đây là test quan trọng nhất — `gather` giữ thứ
   tự, và roll-up phụ thuộc thứ tự verdict.
2. **Có song song thật:** `vision_fn` giả đếm số call **đang bay** (tăng khi vào, giảm khi ra, ghi
   lại đỉnh) + `await asyncio.sleep(0)` để nhường loop. Đỉnh phải > 1 ở từng chỗ đã song song hoá.
   Không có test này thì `gather` có thể vẫn tuần tự mà không ai biết — đúng cái bệnh đang chữa.
3. **Semaphore chặn đúng trần:** đặt `ai_song_song = 2`, dựng 10 call, khẳng định đỉnh đồng thời
   **không vượt 2**.

Thêm: test khẳng định `_doc_file` **không** gọi `fitz` sau khi vào pha bất đồng bộ (render PNG
xong hết trước khi gather) — chống hồi quy cho ràng buộc an toàn đa luồng của PyMuPDF.

Hồi quy bắt buộc, số đo tại thời điểm viết spec:
`cd backend && python -m pytest -q` → **185 passed, 0 failed** (chỉ chạy `backend/tests` theo
`testpaths` trong `pytest.ini`). Bộ `experiment/evaluate/tests` phải gọi tên tường minh và có
**5 test đỏ có sẵn** không liên quan — số đó không được tăng.

## Vận hành — cách dò trần song song khi không có quyền vào server

Không đọc được `/metrics` của vLLM, nên dò từ phía ứng dụng:

1. Chạy chấm một nhà thầu với `ABES_AI_SONG_SONG=1`, ghi lại wall-clock (đối chứng với 1507s hiện
   tại — phải xấp xỉ bằng, vì đó chính là hành vi hôm nay).
2. Tăng dần 2 → 4 → 8 → 16, mỗi mức chạy lại **sau khi xoá cache chấm** (`DELETE .../cache`), ghi
   wall-clock.
3. Dừng tăng khi: thời gian không giảm thêm, **hoặc** log bắt đầu có lỗi timeout/429 từ proxy.
   `ai_client` retry 1 lần rồi trả `status='error'` → verdict "lỗi", nên quá tải sẽ hiện ra thành
   verdict lỗi chứ không âm thầm.
4. Trần an toàn cuối cùng ghi vào `.env`; giữ **≤ 32** vì thread pool mặc định của
   `asyncio.to_thread`.

### Cạm bẫy khi đo trên máy này — đọc trước khi so bất kỳ con số nào

Repo nằm ở `/mnt/d`, tức **drvfs** (ổ Windows nhìn qua WSL). drvfs chậm hơn ext4 nhiều lần ở thao
tác mở/stat file — thứ chi phối việc import Python, mà `backend/tests/conftest.py` lại **nạp lại
`main`/`database`/`models`/`routers*` cho MỖI test**. Hệ quả:

- Đặt hai nhánh trên hai filesystem khác nhau (vd worktree so sánh ở `/tmp`, bản chính ở `/mnt/d`)
  cho ra chênh lệch **~40% hoàn toàn giả**. Đây là bẫy đã thật sự sập một lần trong đợt này: phép
  đo ban đầu báo "chậm 38%", điều tra ra là do filesystem chứ không phải code.
- Ngay trên cùng một commit, cùng filesystem, ba lần chạy liên tiếp lệch nhau tới **14%** tuỳ tải máy.

**Quy tắc:** mọi phép so hiệu năng phải (a) đặt cả hai nhánh trên **CÙNG** filesystem, và (b) chạy
**xen kẽ** BASE/HEAD nhiều vòng để khử trôi theo thời gian. Đo một lần mỗi bên rồi kết luận là sai.
Phép đo đúng cách trong đợt này (cả hai trên ext4, xen kẽ 2 vòng) cho BASE 51.8/57.1s vs HEAD
50.2/37.0s — tức **không có hồi quy**.

## Files chạm

`backend/services/llm_gate.py` (mới), `backend/services/ai_client.py`, `backend/config.py`,
`backend/experiment/evaluate/vision.py`, `backend/experiment/evaluate/ingest.py`,
`backend/experiment/evaluate/evaluate.py`, `backend/experiment/evaluate/pipeline.py`,
`backend/experiment/evaluate/rules/registry.py`,
`backend/experiment/evaluate/rules/lien_danh_phan_cong.py`, cùng test tương ứng.

## Ước lượng độ lợi

Đạt ~16 request đồng thời: 1507s/nhà thầu → khoảng **150–250s**; cả gói 83 phút → **10–15 phút**.
Decompose 474s cũng tự nhanh lên vì `gather` sẵn có bắt đầu có tác dụng.

Đây là **ước lượng, chưa đo**. Độ lợi thật bị chặn bởi `--max-num-seqs` và KV cache của vLLM — hai
thứ không nhìn thấy được từ phía ứng dụng. Bước dò ở mục "Vận hành" chính là cách biết trần thật.
