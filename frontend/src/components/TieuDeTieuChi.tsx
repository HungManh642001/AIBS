/**
 * Tiêu đề một tiêu chí — NEO VÀO NGUYÊN VĂN HSMT.
 *
 * Trước đây tiêu đề là `ten` do LLM tự đặt: mất dấu ("Tu cac hop le"), sai chính tả (rụng chữ
 * 'h'), và ĐỔI mỗi lần chạy lại (cùng một điều khoản ra "Don du thau hinh thuc va chu ky" /
 * "Don_du_thau_hop_le" / "Don_du_thau_hinh_thuc"). Chuyên gia đấu thầu neo vào nguyên văn điều
 * khoản — đó là thứ họ dò trong bản HSMT giấy — nên đặt một bản diễn giải do máy chế vào giữa
 * chuyên gia và văn bản gốc là sai hướng.
 *
 * `yeu_cau_goc` là nguyên văn HSMT: có dấu, chính xác, và ỔN ĐỊNH giữa các lần chạy.
 */

/** Bỏ phần đuôi nằm trong dấu ngoặc CHƯA ĐÓNG — cắt giữa ngoặc làm tiêu đề đọc như bị gãy. */
function ngoaiNgoacDangMo(s: string): string {
  let mo = 0;
  let viMoCuoi = -1;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(") { if (mo === 0) viMoCuoi = i; mo++; }
    else if (s[i] === ")" && mo > 0) mo--;
  }
  return mo > 0 && viMoCuoi > 0 ? s.slice(0, viMoCuoi).trimEnd() : s;
}

/** Cắt gọn giữ nguyên nghĩa: ưu tiên dừng ở ranh giới mệnh đề (`;` `.`), không cắt giữa từ. */
export function rutGon(text: string, max = 150): string {
  const s = (text || "").trim().replace(/\s+/g, " ");
  if (s.length <= max) return s;

  // Điều khoản HSMT hay ghép nhiều mệnh đề bằng ';' — cắt ở đó là ranh giới nghĩa tự nhiên nhất.
  const cua = s.slice(0, max);
  const nganh = Math.max(cua.lastIndexOf("; "), cua.lastIndexOf(". "));
  const tho = nganh > max * 0.5 ? s.slice(0, nganh)
    : (cua.lastIndexOf(" ") > 0 ? cua.slice(0, cua.lastIndexOf(" ")) : cua);

  const sach = ngoaiNgoacDangMo(tho);
  // Lùi quá tay (ngoặc mở gần đầu câu) thì thà giữ bản cắt thô còn hơn mất gần hết nội dung.
  return (sach.length > max * 0.4 ? sach : tho).replace(/[,;:\s]+$/, "") + "…";
}

export function biCat(text: string, max = 150): boolean {
  return (text || "").trim().replace(/\s+/g, " ").length > max;
}

/**
 * Dòng tiêu đề: nguyên văn điều khoản (rút gọn). Rỗng thì lui về `ten` — bản ghi cũ có thể chưa
 * có yeu_cau_goc, thà hiện nhãn xấu còn hơn hiện tiêu đề trống.
 */
export default function TieuDeTieuChi({
  yeuCauGoc, ten, max = 150,
}: { yeuCauGoc?: string; ten?: string; max?: number }) {
  const goc = (yeuCauGoc || "").trim();
  if (!goc) return <span style={{ fontWeight: 600 }}>{ten || "(chưa có nội dung)"}</span>;
  return (
    <span style={{ fontWeight: 600, whiteSpace: "normal", lineHeight: 1.45 }}>
      {rutGon(goc, max)}
    </span>
  );
}
