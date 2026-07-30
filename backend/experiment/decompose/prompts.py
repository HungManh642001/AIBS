"""System prompt + builder cho các bước phân rã. Dùng cot_block của services.

Mỗi prompt nhúng 1 TAG máy đọc được ([TAG:LIST]/[TAG:CRITIQUE]/[TAG:STRUCT:<ten>]/
[TAG:QUERY:<ten>]/[TAG:RESOLVE:<ten>]) để ScriptedLlm khớp kịch bản theo bước (bền với fan-out).

Output phẳng: mỗi tiêu chí có noi_dung_can_kiem_tra (ô HẠNG NHẤT) — buộc model liệt kê rõ
"cần kiểm tra nội dung gì", thay vì chôn trong thong_so.
"""
from __future__ import annotations

from typing import Any

from services import artifact_catalog
from services.prompts import cot_block

SYS_LIST = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc nội dung TIÊU CHUẨN ĐÁNH GIÁ của "
    "MỘT nhóm và LIỆT KÊ ĐẦY ĐỦ các tiêu chí cụ thể (đừng bỏ sót). "
    "QUY TẮC NGUYÊN TỬ — bắt buộc: mỗi tiêu chí chỉ hướng tới MỘT nội dung kiểm tra trên MỘT hồ sơ "
    "CHÍNH của nhà thầu. Nếu một loại hồ sơ có NHIỀU nội dung kiểm tra độc lập → TÁCH thành nhiều tiêu "
    "chí; KHÔNG gộp nhiều vấn đề vào một tiêu chí; KHÔNG để hai tiêu chí trùng/đè nội dung nhau. "
    "Mỗi tiêu chí: nhom (hop_le/nang_luc/ky_thuat/tai_chinh), ten, yeu_cau_goc (trích "
    "NGUYÊN VĂN câu yêu cầu gốc trong HSMT, KHÔNG TÓM TẮT, KHÔNG VIẾT GỌN, PHẢI TRÍCH ĐẦY ĐỦ), hsdt_can_kiem_tra.\n"
    "ten = nhãn NGẮN (3-8 từ) bằng TIẾNG VIỆT CÓ DẤU ĐẦY ĐỦ, viết như tiêu đề cho người đọc: hoa "
    "chữ đầu, các chữ sau viết thường, ngăn bằng DẤU CÁCH. TUYỆT ĐỐI KHÔNG viết kiểu định danh máy "
    "— không bỏ dấu, không gạch dưới, không viết hoa mỗi từ, không viết tắt tự chế. "
    'ĐÚNG: "Tư cách hợp lệ" · "Bảo đảm dự thầu" · "Thỏa thuận liên danh" · "Hiệu lực hồ sơ dự thầu". '
    'SAI: "Tu_cach_hop_le" · "Tu cach hop le" · "Bao dam du thau (Thong thuong)" · "Hieu_luc_HSDT". '
    "Đặt tên theo ĐÚNG cách HSMT gọi sự việc đó trong yeu_cau_goc, đừng tự nghĩ ra cách gọi mới — "
    "nhãn này hiện trên giao diện cho chuyên gia đấu thầu đọc.\n"
    "hsdt_can_kiem_tra = MỌI tài liệu hồ sơ dự thầu cần xem để kết luận tiêu chí này, HỒ SƠ CHÍNH đứng ĐẦU danh "
    "sách. Quy tắc nguyên tử ràng buộc NỘI DUNG và HỒ SƠ CHÍNH — nó KHÔNG cấm liệt kê thêm tài "
    "liệu ĐỐI CHIẾU: nếu yêu cầu đòi so hồ sơ chính với một tài liệu KHÁC thì PHẢI liệt kê thêm "
    "tài liệu đó. Ví dụ 'giá trong bảng giá phải phù hợp với webform (kết quả mở thầu)' → "
    "hsdt_can_kiem_tra=[bang_gia, webform] (bang_gia là hồ sơ chính bị chấm).\n"
    "CÁCH CHỌN HỒ SƠ — bắt buộc: đối chiếu yêu cầu với cột NỘI DUNG TÀI LIỆU CHỨA trong DANH MỤC "
    "trên, chọn tài liệu THỰC SỰ CHỨA thứ cần kiểm. TUYỆT ĐỐI KHÔNG suy theo CHỦ ĐỀ của tiêu chí "
    "(chủ đề 'tư cách hợp lệ' KHÔNG có nghĩa hồ sơ là giấy đăng ký kinh doanh). Nếu yêu cầu chỉ "
    "trỏ tới một điều khoản HSMT (vd 'theo quy định tại Mục 5 A-CDNT') mà KHÔNG gọi tên tài liệu "
    "nhà thầu phải nộp, thì đó là điều nhà thầu TỰ KHAI → hồ sơ chính = don_du_thau."
)
SYS_CRITIQUE = (
    "Bạn là chuyên gia rà soát. So sánh DANH SÁCH tiêu chí đã liệt kê với NGUỒN gốc và chỉ ra các "
    "tiêu chí BỊ SÓT (chỉ trả tiêu chí còn THIẾU, không lặp lại tiêu chí đã có). Giữ QUY TẮC NGUYÊN "
    "TỬ: mỗi tiêu chí = 1 nội dung trên 1 hồ sơ CHÍNH; hsdt_can_kiem_tra vẫn liệt kê THÊM tài liệu "
    "đối chiếu nếu yêu cầu đòi so với tài liệu khác (hồ sơ chính đứng đầu). Mục tiêu: không sót.\n"
    "ten theo ĐÚNG quy ước như bước liệt kê: nhãn ngắn TIẾNG VIỆT CÓ DẤU, hoa chữ đầu, ngăn bằng "
    'dấu cách (vd "Thỏa thuận liên danh") — KHÔNG bỏ dấu, KHÔNG gạch dưới.'
)
SYS_STRUCT = (
    "Bạn là chuyên gia đấu thầu. Cho MỘT tiêu chí (đã có yeu_cau_goc trích từ Hồ sơ mời thầu (HSMT) và "
    "hsdt_can_kiem_tra), hãy lập CHECKLIST noi_dung_can_kiem_tra — những nội dung cần kiểm tra trên "
    "Hồ sơ dự thầu (HSDT) để kết luận tiêu chí. Liệt kê ĐẦY ĐỦ, đừng bỏ sót. Mỗi nội dung gồm:\n"
    "- noi_dung_kiem_tra: điều cần kiểm trên HSDT (vd 'Giá trị bảo lãnh', 'Bảo đảm tư cách hợp lệ').\n"
    "  MỆNH ĐỀ 'HOẶC' — KHÔNG ĐƯỢC TÁCH: hai vế nối bằng 'hoặc' là HAI CÁCH THOẢ CÙNG MỘT yêu cầu, "
    "chỉ cần đạt MỘT vế là đạt. Giữ nguyên thành MỘT nội dung, `yeu_cau` chép ĐỦ CẢ HAI vế kèm chữ "
    "'hoặc'. Tách ra thành hai nội dung riêng là biến quan hệ HOẶC thành VÀ -> bước chấm sẽ đánh "
    "trượt vế mà nhà thầu không dùng, dù họ hoàn toàn hợp lệ. (Ngược lại, các vế nối bằng 'và' / "
    "dấu chấm phẩy là những yêu cầu ĐỘC LẬP -> vẫn tách như bình thường.)\n"
    "- hsdt_kiem_tra: CHỌN 1 loại hồ sơ (trong hsdt_can_kiem_tra của tiêu chí) để kiểm nội dung này "
    "— phải là hồ sơ CỦA NHÀ THẦU đang BỊ CHẤM (hồ sơ chính, thường đứng đầu hsdt_can_kiem_tra), "
    "KHÔNG PHẢI TÀI LIỆU ĐỐI CHIẾU. Vd 'giá bảng giá phải khớp webform' -> hsdt_kiem_tra='bang_gia' "
    "(chấm bảng giá của nhà thầu), KHÔNG phải 'webform'.\n"
    "- hsdt_doi_chieu: các loại hồ sơ KHÁC (chọn trong hsdt_can_kiem_tra của tiêu chí) mà RIÊNG "
    "nội dung này phải đem ra so sánh mới kết luận được. Nội dung chỉ cần đọc hồ sơ chính -> để "
    "MẢNG RỖNG. Ví dụ MỘT yêu cầu gốc sinh hai nội dung cùng nằm trên bang_gia: 'phải nộp Bảng "
    "chào giá theo đúng Mẫu số 05C.1' -> hsdt_doi_chieu=[] (chỉ soi mẫu biểu); 'giá trong Bảng "
    "chào giá phải phù hợp giá trên webform' -> hsdt_doi_chieu=['webform'] (phải so hai tài "
    "liệu). Khai đúng field này quyết định nội dung nào được chấm bằng phép đối chiếu chuyên "
    "dụng — khai thừa sẽ làm nội dung soi mẫu biểu bị chấm nhầm bằng phép so giá.\n"
    "- yeu_cau: YÊU CẦU nội dung này phải đáp ứng, diễn giải từ yeu_cau_goc (vd 'Phải bảo đảm tư cách hợp "
    "lệ theo Mục 5 A-CDNT', 'Thỏa mãn giá trị bảo lãnh theo HSMT'). LUÔN điền.\n"
    "Diển giải để RÕ NGHĨA, không siết chặt hơn, yeu_cau_goc không nêu thì đừng tự nêu.\n"
    "- can_lam_ro: nếu yeu_cau còn CHƯA RÕ (trỏ tới điều khoản/biểu mẫu mà chưa nêu con số/nội dung cụ thể) "
    "-> ghi NGẮN thứ cần làm rõ (vd 'Giá trị bảo lãnh', 'Nội dung tư cách hợp lệ tại Mục 5 A-CDNT', 'Mẫu số 05C chương V Bảng giá chi tiết'). "
    "Nếu đã rõ (không cần tra) -> để trống.\n"
    "  QUAN TRỌNG: can_lam_ro CHỈ dành cho thông tin PHÍA MỜI THẦU (chuẩn nêu trong A-BDL/A-CDNT/"
    "biểu mẫu/thông báo mời thầu). Nếu điều chưa rõ là NỘI DUNG NẰM TRONG hồ sơ nhà thầu nộp "
    "(vd phân công trách nhiệm trong thỏa thuận liên danh CỦA nhà thầu, nội dung đơn CỦA nhà thầu) "
    "-> KHÔNG tra được trong HSMT: để trống can_lam_ro, can_tra_cuu=false (bước chấm sẽ đối chiếu "
    "trực tiếp trên HSDT).\n"
    "- can_tra_cuu: true nếu can_lam_ro khác rỗng; false nếu không.\n"
    "- ap_dung: nội dung này áp dụng cho AI? '' = MỌI nhà thầu (mặc định). Đặt 'lien_danh' nếu "
    "yeu_cau_goc NÊU RÕ nội dung CHỈ áp dụng khi nhà thầu là liên danh (mệnh đề 'Đối với nhà thầu "
    "liên danh...', 'trường hợp liên danh...', 'thỏa thuận liên danh...'); đặt 'doc_lap' nếu chỉ áp dụng nhà thầu độc lập. "
    "MỘT yêu cầu gốc có thể CHỨA cả mệnh đề CHUNG (ap_dung='') lẫn mệnh đề điều kiện liên danh "
    "(ap_dung='lien_danh') -> TÁCH thành nội dung riêng, gắn ap_dung đúng cho từng cái. KHI KHÔNG "
    "CHẮC -> để '' (chấm cho mọi nhà thầu, không bỏ sót).\n"
    "- dieu_kien_ap_dung: CHỈ điền khi yeu_cau_goc nêu điều kiện kích hoạt theo MỘT GIÁ TRỊ CỦA GÓI "
    "THẦU (không phải theo hình thức nhà thầu), dạng 'Đối với gói thầu có <đại lượng> <so sánh> "
    "<ngưỡng> thì...'. Tách thành {dai_luong, phep_so_sanh, nguong}: dai_luong PHẢI CHỌN NGUYÊN VĂN "
    "MỘT MỤC trong DANH MỤC ĐẠI LƯỢNG GÓI THẦU nêu ở cuối prompt (chép đúng từng chữ, KHÔNG diễn "
    "đạt lại — hệ thống đối chiếu theo đúng tên đó); phep_so_sanh là một trong < <= > >= = !=; "
    "nguong giữ NGUYÊN VĂN kèm đơn vị (vd '50 triệu đồng'). Ví dụ: 'Đối với gói thầu có giá trị bảo "
    "đảm dự thầu nhỏ hơn 50 triệu đồng, nhà thầu có cam kết trong đơn dự thầu' -> "
    '{"dai_luong":"giá trị bảo đảm dự thầu","phep_so_sanh":"<","nguong":"50 triệu đồng"}. '
    "Điều kiện dựa trên đại lượng KHÔNG có trong danh mục -> bỏ trống cả ba (hệ thống sẽ chấm bình "
    "thường, KHÔNG bỏ sót). KHÔNG có điều kiện dạng này -> cũng bỏ trống cả ba. KHÔNG tự đối chiếu "
    "điều kiện, KHÔNG tự bỏ nội dung: cứ liệt kê nội dung như bình thường, hệ thống đối chiếu sau.\n"
    "TUYỆT ĐỐI KHÔNG bịa số/nội dung."
)
SYS_QUERY = (
    "Bạn tạo MỘT câu truy vấn tìm kiếm tiếng Việt NGẮN, giàu từ khoá để tra GIÁ TRỊ mà HỒ SƠ MỜI THẦU (HSMT) quy định "
    "cho MỘT nội dung (thường nằm trong Bảng dữ liệu đầu thấu A-BDL / Chỉ dẫn đấu thầu A-CDNT). \n"
    # "QUAN TRỌNG -MỞ RỘNG THEO NGHIỆP VỤ: thông tin có thể được HSMT ghi dưới MỘT KHÁI NIỆM KHÁC; "
    # "hãy THÊM từ đồng nghĩa / nơi thông tin thường nằm. Ví dụ: 'đơn vị thụ hưởng (của) bảo đảm dự "
    # "thầu' THƯỜNG CHÍNH LÀ 'Chủ đầu tư / Bên mời thầu'; 'thời gian hiệu lực bảo đảm' nằm cùng mục bảo "
    # "đảm dự thầu. Query nên gồm CẢ câu theo từ gốc KẾT HỢP câu theo từ đồng nghĩa/khái niệm tương đương.\n"
    "Trả JSON phẳng đúng cấu trúc nêu ở cuối prompt."
)
SYS_RESOLVE = (
    "Bạn là chuyên gia đấu thầu. Cho THÔNG TIN CẦN LÀM RÕ của một nội dung và PHẦN BẰNG CHỨNG truy "
    "hồi từ HSMT, hãy trả 'thong_tin_bo_sung' — chuẩn cụ thể để bước chấm thầu đối chiếu:\n"
    "- TỰ ĐỦ: nếu bằng chứng trỏ tới nội dung điều khoản (vd tư cách hợp lệ Mục 5), TRÍCH NỘI DUNG "
    "THỰC (các điều kiện a, b, c...), KHÔNG trả lại con trỏ 'nội dung Mục 5'.\n"
    "- CÓ QUAN HỆ SO SÁNH: vd 'Giá trị bảo lãnh: 6.100.000 VNĐ', 'Thời gian hiệu lực: ≥ 120 ngày', "
    "'Đơn vị thụ hưởng: Liên doanh Việt - Nga Vietsovpetro', 'Đáp ứng đủ điều kiện: (a)...(b)...'.\n"
    "- 'nguon': mã điều khoản chứa thông tin (vd 'A-BDL 18.2', 'A-CDNT 1.1') trích từ bằng chứng.\n"
    "- MỐC CHUNG: nếu chuẩn tham chiếu mốc chung của gói thầu (thời điểm đóng/mở thầu, hiệu lực "
    "A-HSDT...) và phần [BẢNG NEO] có giá trị -> chèn giá trị cụ thể trong ngoặc ngay sau tham "
    "chiếu, vd 'Thời gian hiệu lực: ≥ 120 ngày kể từ thời điểm đóng thầu (09h00 ngày 20/6/2025 "
    "[TBMT])'. BẢNG NEO không có mốc đó -> GIỮ NGUYÊN tham chiếu, KHÔNG bịa.\n"
    'Trả {"thong_tin_bo_sung":"...","nguon":"...","can_review":false}. Nếu bằng chứng KHÔNG chứa/không '
    'chắc -> {"thong_tin_bo_sung":"","nguon":"","can_review":true} — TUYỆT ĐỐI KHÔNG bịa.'
)


SYS_ANCHORS = (
    "Bạn là chuyên gia đấu thầu. Đọc TƯ LIỆU GÓI THẦU (Bảng dữ liệu A-BDL + thông báo mời thầu/"
    "nguồn kèm theo) và trích BẢNG NEO — các MỐC CHUNG mà nhiều chuẩn khác tham chiếu tới. "
    "CHỈ trả các neo TÌM THẤY nguyên văn trong tư liệu; neo không thấy thì BỎ QUA — TUYỆT ĐỐI "
    "KHÔNG bịa. 'nguon': nơi chứa mốc (vd 'TBMT', 'A-BDL 19.1')."
)

_ANCHOR_CATALOG = (
    "- thời điểm đóng thầu\n- thời điểm mở thầu\n- thời gian hiệu lực A-HSDT\n"
    "- tên gói thầu\n- bên mời thầu\n- chủ đầu tư\n- giá gói thầu\n"
    "- giá trị bảo đảm dự thầu"
)


def anchor_names() -> str:
    """Danh mục neo dạng danh sách phẳng — DÙNG CHUNG cho ANCHORS và STRUCT.

    Đây là TỪ VỰNG CÓ KIỂM SOÁT nối hai bước: ANCHORS trích giá trị và đặt tên theo danh mục này,
    STRUCT phải gọi `dai_luong` bằng ĐÚNG tên đó. Nhờ vậy bước đối chiếu điều kiện khớp tất định,
    KHÔNG phụ thuộc việc LLM xếp mệnh đề điều kiện vào tiêu chí nào (trước đây chỉ tra trong nội
    dung anh em cùng tiêu chí -> tách sang tiêu chí riêng là mất dấu; và 'giá trị bảo lãnh' vs
    'giá trị bảo đảm dự thầu' là hai cách gọi cùng một thứ nên khớp chuỗi cũng trượt).
    """
    return _ANCHOR_CATALOG


def anchors_prompt(body: str) -> str:
    """1 call/run đầu decompose — trích mốc chung từ A-BDL + nguyên văn nguồn scan."""
    return (
        "[TAG:ANCHORS]\n"
        f"DANH MỤC NEO CẦN TÌM:\n{_ANCHOR_CATALOG}\n\n"
        f"TƯ LIỆU GÓI THẦU:\n{body}\n\n"
        + cot_block('{"neo":[{"ten":"<tên neo trong danh mục>","gia_tri":"...","nguon":"..."}]}')
    )


# Schema step structure/resolve — noi_dung_can_kiem_tra là ô hạng nhất.
_CRIT_SCHEMA = (
    '{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...],'
    '"noi_dung_can_kiem_tra":[{"noi_dung_kiem_tra","hsdt_kiem_tra","hsdt_doi_chieu":[...],'
    '"yeu_cau","can_lam_ro",'
    '"can_tra_cuu":false,"ap_dung":"",'
    '"dieu_kien_ap_dung":{"dai_luong":"","phep_so_sanh":"","nguong":""}}]}'
)


def catalog_codes() -> str:
    """Danh mục hồ sơ cho prompt — MỖI MÃ MỘT DÒNG.

    Trước đây nối bằng ", ": `mo_ta` cũng chứa dấu phẩy nên ranh giới giữa các mã nhập nhằng, và
    13 mô tả dồn thành một dòng dài thì mô tả bị đọc lướt. Xuống dòng để mô tả nội dung đủ nổi —
    đó là căn cứ CHÍNH để chọn hồ sơ (xem quy tắc trong SYS_LIST).
    """
    return "\n".join(
        f"- {c}: {artifact_catalog.get_artifact(c)['mo_ta']}" for c in artifact_catalog.all_codes()
    )


def list_prompt(source_text: str) -> str:
    return (
        "[TAG:LIST]\n"
        f"DANH MỤC LOẠI HỒ SƠ HSDT (mã: nội dung tài liệu chứa):\n{catalog_codes()}\n\n"
        f"NỘI DUNG TIÊU CHUẨN ĐÁNH GIÁ (nhóm):\n{source_text}\n\n"
        + cot_block('{"criteria":[{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...]}]}')
    )


def critique_prompt(source_text: str, listed: list[dict[str, Any]]) -> str:
    names = "; ".join(c.get("ten", "") for c in listed)
    return (
        "[TAG:CRITIQUE]\n"
        f"NGUỒN:\n{source_text}\n\n"
        f"ĐÃ LIỆT KÊ: {names}\n\n"
        + cot_block('{"criteria":[{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...]}]}  // CHỈ tiêu chí còn thiếu')
    )


def struct_prompt(crit: dict[str, Any]) -> str:
    """Step analyze — chỉ từ tiêu chí (KHÔNG đưa source toàn nhóm để tránh nhiễu)."""
    return (
        f"[TAG:STRUCT:{crit.get('ten', '')}]\n"
        f"DANH MỤC LOẠI HỒ SƠ HSDT (mã: nội dung tài liệu chứa):\n{catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n"
        f"YÊU CẦU GỐC (HSMT): {crit.get('yeu_cau_goc', '')}\n"
        f"HSDT cần kiểm tra: {crit.get('hsdt_can_kiem_tra', [])}\n\n"
        "VÍ DỤ 1 — 'Nhà thầu bảo đảm tư cách hợp lệ theo Mục 5 A-CDNT' (hsdt=[don_du_thau]):\n"
        '  [{"noi_dung_kiem_tra":"Bảo đảm tư cách hợp lệ","hsdt_kiem_tra":"don_du_thau",'
        '"yeu_cau":"Phải bảo đảm tư cách hợp lệ theo Mục 5 A-CDNT",'
        '"can_lam_ro":"Nội dung tư cách hợp lệ tại Mục 5 A-CDNT","can_tra_cuu":true}]\n'
        "VÍ DỤ 2 — 'Thư bảo lãnh đúng giá trị/hiệu lực/đơn vị thụ hưởng theo HSMT' (hsdt=[bao_dam_du_thau]):\n"
        '  [{"noi_dung_kiem_tra":"Giá trị bảo lãnh","hsdt_kiem_tra":"bao_dam_du_thau",'
        '"yeu_cau":"Thỏa mãn giá trị bảo lãnh theo HSMT","can_lam_ro":"Giá trị bảo lãnh","can_tra_cuu":true},\n'
        '   {"noi_dung_kiem_tra":"Thời gian hiệu lực","hsdt_kiem_tra":"bao_dam_du_thau",'
        '"yeu_cau":"Thỏa mãn thời gian hiệu lực theo HSMT","can_lam_ro":"Thời gian hiệu lực bảo lãnh","can_tra_cuu":true}]\n\n'
        "VÍ DỤ 3 (TRỘN chung + liên danh) — 'Đơn dự thầu phải được đại diện hợp pháp của nhà thầu ký "
        "tên, đóng dấu. Đối với nhà thầu liên danh, đơn phải do đại diện từng thành viên ký hoặc "
        "thành viên đứng đầu ký thay mặt theo phân công trong thỏa thuận liên danh' "
        "(hsdt=[don_du_thau, thoa_thuan_lien_danh]) — mệnh đề 1 áp dụng MỌI nhà thầu, mệnh đề 2 CHỈ "
        "liên danh; hồ sơ BỊ CHẤM là đơn dự thầu, thỏa thuận liên danh là tài liệu ĐỐI CHIẾU. "
        "CHÚ Ý mệnh đề 2 có chữ 'hoặc' -> hai vế là hai cách ký ĐỀU HỢP LỆ, gộp làm MỘT nội dung và "
        "chép đủ cả hai; tách đôi sẽ đánh trượt nhà thầu chỉ dùng một cách:\n"
        '  [{"noi_dung_kiem_tra":"Đơn ký bởi đại diện hợp pháp","hsdt_kiem_tra":"don_du_thau",'
        '"yeu_cau":"Đơn được đại diện hợp pháp của nhà thầu ký tên, đóng dấu",'
        '"can_lam_ro":"","can_tra_cuu":false,"ap_dung":""},\n'
        '   {"noi_dung_kiem_tra":"Liên danh: cách ký đơn hợp lệ","hsdt_kiem_tra":"don_du_thau",'
        '"yeu_cau":"Đơn do đại diện hợp pháp của TỪNG thành viên liên danh ký tên, đóng dấu (nếu '
        'có) HOẶC thành viên đứng đầu liên danh thay mặt liên danh ký theo phân công trách nhiệm '
        'trong thỏa thuận liên danh — thoả MỘT trong hai là đạt",'
        '"can_lam_ro":"","can_tra_cuu":false,"ap_dung":"lien_danh"}]\n\n'
        f"DANH MỤC ĐẠI LƯỢNG GÓI THẦU (chỉ dùng cho dieu_kien_ap_dung.dai_luong — chép NGUYÊN VĂN "
        f"tên mục, không có mục nào khớp thì bỏ trống dieu_kien_ap_dung):\n{anchor_names()}\n\n"
        + cot_block(_CRIT_SCHEMA)
    )


def query_prompt(crit: dict[str, Any], need: dict[str, Any], sources: dict[str, str] | None = None) -> str:
    """Step search — sinh 1 truy vấn cho THÔNG TIN CẦN LÀM RÕ của một nội dung (kèm ngữ cảnh)."""
    routing = ""
    schema = '{"query":"..."}'
    if sources:
        cat = "\n".join(f"-{code}: {mo_ta}" for code, mo_ta in sources.items())
        routing = (
            "\nCÁC NGUỒN TÀI LIỆU CÓ THỂ TRA (mã: tóm tắt nội dung):\n"
            f"{cat}\n"
            "nguon_goi_y: chọn các MÃ nguồn NHIỀU KHẢ NĂNG chứa thông tin nhất.\n"
        )
        schema = '{"query":"...","nguon_goi_y":["<mã nguồn>"]}'
    return (
        f"[TAG:QUERY:{need.get('noi_dung_kiem_tra', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"YÊU CẦU GỐC (HSMT): {crit.get('yeu_cau_goc', '')}\n"
        f"THÔNG TIN CẦN LÀM RÕ: {need.get('can_lam_ro', '')}\n"
        f"{routing}\n"
        + cot_block(schema)
    )


def retry_query_prompt(crit: dict[str, Any], need: dict[str, Any], prev_query: str) -> str:
    """Step search bậc retry — sinh query GÓC KHÁC sau khi lần 1 không ra kết quả."""
    return (
        f"[TAG:QUERY2:{need.get('noi_dung_kiem_tra', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"YÊU CẦU GỐC (HSMT): {crit.get('yeu_cau_goc', '')}\n"
        f"THÔNG TIN CẦN LÀM RÕ: {need.get('can_lam_ro', '')}\n"
        f"QUERY ĐÃ THỬ (KHÔNG ra kết quả): {prev_query}\n\n"
        "Đặt 1 query KHÁC góc nhìn: từ đồng nghĩa nghiệp vụ khác, hoặc tên NƠI thông tin có thể nằm "
        "(bảng dữ liệu, chỉ dẫn nhà thầu, biểu mẫu, thông báo mời thầu). KHÔNG lặp từ khóa chính cũ.\n"
        + cot_block('{"query":"..."}')
    )


def resolve_prompt(crit: dict[str, Any], need: dict[str, Any], evidence_text: str,
                   attempt: int = 1) -> str:
    """Step search — trả thong_tin_bo_sung (tự đủ + quan hệ so sánh) + nguon; không thấy -> can_review."""
    return (
        f"[TAG:RESOLVE{'' if attempt == 1 else '2'}:{need.get('noi_dung_kiem_tra', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"YÊU CẦU: {need.get('yeu_cau', '')}\n"
        f"THÔNG TIN CẦN LÀM RÕ: {need.get('can_lam_ro', '')}\n\n"
        f"BẰNG CHỨNG (truy hồi từ HSMT/A-BDL/A-CDNT):\n{evidence_text or '(không có)'}\n\n"
        + cot_block('{"thong_tin_bo_sung":"<chuẩn cụ thể, tự đủ, có quan hệ so sánh>","nguon":"<mã điều khoản>","can_review":false}')
    )
