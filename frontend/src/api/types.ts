export interface Vendor { id: number; ten: string; ma_so_thue?: string; }
export interface Package {
  id: number; ma_so: string; ten: string; loai: string;
  gia_tri_uoc_tinh: number; trang_thai: string; nguoi_phu_trach: string;
  vendors: Vendor[]; so_tai_lieu: number; so_tieu_chi: number;
}

// ---- Tiêu chí đánh giá (decompose) ----
export interface NoiDungKiemTra {
  id?: number; noi_dung_kiem_tra: string; hsdt_kiem_tra: string; yeu_cau: string;
  can_lam_ro: string; can_tra_cuu: boolean; thong_tin_bo_sung: string; nguon: string;
  can_review: boolean;
}
export interface RubricCriteria {
  id?: number; nhom: string; ten: string; yeu_cau_goc: string;
  hsdt_can_kiem_tra: string[]; tien_quyet: boolean; noi_dung_can_kiem_tra: NoiDungKiemTra[];
}

// ---- Đánh giá HSDT (verdict pipeline vision) ----
export interface Verdict {
  id: number; noi_dung_kiem_tra: string; hsdt_kiem_tra: string; yeu_cau: string;
  thong_tin_bo_sung: string; ket_qua: string; bang_chung: string; trang: number[];
  do_tin: number; ghi_chu: string; overridden: boolean;
}
export interface CriterionEval {
  eval_id: number; ten: string; nhom: string; tien_quyet: boolean;
  ket_qua: string; loai: boolean; verdicts: Verdict[];
}
export interface EvalSummary {
  n_tieu_chi: number; n_dat: number; n_khong_dat: number; n_can_lam_ro: number; n_loai: number;
}
export interface VendorEval {
  vendor_id: number; ten: string; summary: EvalSummary; criteria: CriterionEval[];
}
export interface EvalResultsPayload { vendors: VendorEval[]; }
// Danh mục loại hồ sơ giờ lấy động từ backend — dùng hook useArtifactTypes() (api/artifacts.ts).
