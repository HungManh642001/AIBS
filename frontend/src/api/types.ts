export interface Vendor {
  id: number; ten: string; ten_viet_tat?: string;   // tên đầy đủ + tên viết tắt (khớp webform)
  hinh_thuc?: string;   // khai báo: doc_lap | lien_danh | "" (để trống -> tự dò khi chấm)
}
export interface Package {
  id: number; ma_so: string; ten: string; loai: string;
  gia_tri_uoc_tinh: number; trang_thai: string; nguoi_phu_trach: string;
  vendors: Vendor[]; so_tai_lieu: number; so_tieu_chi: number;
}

export interface TenderDoc {
  id: number; loai: string; vendor_id: number | null;
  file_path: string; file_name?: string; file_kind: string; trang_thai_ocr: string;
  artifact_type?: string; artifact_validation?: { match?: boolean; note?: string } | null;
}

// ---- Tiêu chí đánh giá (decompose) ----
// Điều kiện áp dụng theo GIÁ TRỊ gói thầu, decompose đã đối chiếu tất định (0 call AI).
// ket_luan='' = chưa quyết được -> nội dung VẪN được chấm; can_cu nói rõ vì sao.
export interface DieuKienApDung {
  dai_luong?: string; phep_so_sanh?: string; nguong?: string;
  ket_luan?: "" | "ap_dung" | "khong_ap_dung"; can_cu?: string;
}
export interface NoiDungKiemTra {
  id?: number; noi_dung_kiem_tra: string; hsdt_kiem_tra: string; yeu_cau: string;
  can_lam_ro: string; can_tra_cuu: boolean; thong_tin_bo_sung: string; nguon: string;
  can_review: boolean;
  ap_dung?: string;   // '' = mọi nhà thầu | 'lien_danh' | 'doc_lap' (áp dụng cấp nội dung)
  dieu_kien_ap_dung?: DieuKienApDung;
}
export interface RubricCriteria {
  id?: number; nhom: string; ten: string; yeu_cau_goc: string;
  hsdt_can_kiem_tra: string[]; noi_dung_can_kiem_tra: NoiDungKiemTra[];
  loi_ai?: string;   // ghi chú AI không chắc — GET trả về để PUT không ghi đè mất
}

// ---- Đánh giá HSDT (verdict pipeline vision) ----
export interface Verdict {
  id: number; noi_dung_kiem_tra: string; hsdt_kiem_tra: string; yeu_cau: string;
  thong_tin_bo_sung: string; ket_qua: string; bang_chung: string; trang: number[];
  do_tin: number; ghi_chu: string; overridden: boolean;
  nguon_hsmt?: string;      // điều khoản nguồn HSMT của chuẩn (E-BDL/E-CDNT) — audit chiều HSMT
  nguon_doc?: string[];     // các hồ sơ luật đã đối chiếu (vd [bang_gia, webform])
}
export interface CriterionEval {
  eval_id: number; ten: string; nhom: string;
  ket_qua: string; verdicts: Verdict[];
  yeu_cau_goc?: string;     // nguyên văn HSMT (cấp tiêu chí)
}
export interface EvalSummary {
  n_tieu_chi: number; n_dat: number; n_khong_dat: number; n_can_lam_ro: number;
  n_khong_ap_dung?: number;
  /** Khoản mục CON của n_can_lam_ro: số tiêu chí có ít nhất một nội dung thiếu hồ sơ. */
  n_thieu_ho_so?: number;
}
export interface VendorProfile {
  hinh_thuc: string; nguon: string; bang_chung: string; trang: number[];
  do_tin: number; mau_thuan: boolean; ghi_chu: string;
}
export interface HoSoNhanDuoc { loai_ho_so: string; files: string[]; n_trang: number; }
export interface VendorEval {
  vendor_id: number; ten: string; summary: EvalSummary; criteria: CriterionEval[];
  ten_viet_tat?: string; hinh_thuc?: string;
  vendor_profile?: VendorProfile | null;
  ho_so_nhan_duoc?: HoSoNhanDuoc[];
}
export interface EvalResultsPayload { vendors: VendorEval[]; }
// Danh mục loại hồ sơ giờ lấy động từ backend — dùng hook useArtifactTypes() (api/artifacts.ts).
